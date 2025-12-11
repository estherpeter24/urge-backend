from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import aiofiles
import os

from ..core.database import get_db
from ..core.security import get_current_user
from ..core.config import settings
from ..models.user import User
from ..models.media import Media, FileType
from ..services.s3_service import s3_service
from ..schemas.media import (
    PresignedUrlRequest,
    PresignedUrlResponse,
    CompleteUploadRequest,
    MediaResponse,
)

router = APIRouter(prefix="/media", tags=["Media"])

# Allowed MIME types per folder
ALLOWED_TYPES = {
    "avatars": ["image/jpeg", "image/png", "image/gif", "image/webp"],
    "media": ["image/jpeg", "image/png", "image/gif", "image/webp", "video/mp4", "video/quicktime"],
    "documents": ["application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    "voice": ["audio/m4a", "audio/mp4", "audio/mpeg", "audio/wav", "audio/aac"],
}

# Max file sizes per type (in bytes)
MAX_SIZES = {
    "image": settings.max_image_size,
    "video": settings.max_video_size,
    "audio": settings.max_document_size,  # Using document size for audio
    "application": settings.max_document_size,
}


def get_max_size_for_type(mime_type: str) -> int:
    """Get max file size based on MIME type"""
    type_prefix = mime_type.split("/")[0]
    return MAX_SIZES.get(type_prefix, settings.max_document_size)


@router.post("/presigned-url", response_model=PresignedUrlResponse)
async def get_presigned_upload_url(
    request: PresignedUrlRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Generate a presigned URL for direct upload to S3.

    The client should:
    1. Call this endpoint to get a presigned URL
    2. Upload the file directly to S3 using the presigned URL
    3. Call /media/complete-upload to register the file in the database
    """
    # Validate file type
    allowed = ALLOWED_TYPES.get(request.folder, [])
    if request.file_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{request.file_type}' not allowed for folder '{request.folder}'. Allowed: {allowed}"
        )

    try:
        # Generate unique file key
        file_key = s3_service.generate_file_key(
            folder=request.folder,
            filename=request.file_name,
            user_id=current_user.id,
        )

        # Generate presigned URL
        result = s3_service.get_presigned_upload_url(
            file_key=file_key,
            content_type=request.file_type,
        )

        return PresignedUrlResponse(**result)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate upload URL: {str(e)}"
        )


@router.post("/complete-upload", response_model=MediaResponse)
async def complete_upload(
    request: CompleteUploadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Complete the upload process by registering the file in the database.

    This should be called after successfully uploading to S3.
    """
    # Verify the file exists in S3
    if not s3_service.file_exists(request.file_key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File not found in storage. Please upload first."
        )

    # Get file metadata from S3 to verify
    metadata = s3_service.get_file_metadata(request.file_key)
    if metadata:
        # Use actual size from S3 if available
        actual_size = metadata.get("content_length", request.file_size)

        # Validate file size
        max_size = get_max_size_for_type(request.mime_type)
        if actual_size > max_size:
            # Delete the file since it's too large
            s3_service.delete_file(request.file_key)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size ({actual_size} bytes) exceeds maximum allowed ({max_size} bytes)"
            )
    else:
        actual_size = request.file_size

    # Create media record
    media = Media(
        user_id=current_user.id,
        file_key=request.file_key,
        file_url=request.file_url,
        file_name=request.file_name,
        file_type=FileType(request.file_type),
        mime_type=request.mime_type,
        file_size=actual_size,
        duration=request.duration,
        width=request.width,
        height=request.height,
    )

    db.add(media)
    await db.commit()
    await db.refresh(media)

    return MediaResponse(
        id=media.id,
        file_url=media.file_url,
        thumbnail_url=media.thumbnail_url,
        file_type=media.file_type.value,
        file_size=media.file_size,
        file_name=media.file_name,
        mime_type=media.mime_type,
        duration=media.duration,
        created_at=media.created_at,
    )


@router.post("/upload", response_model=MediaResponse)
async def upload_media_direct(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Direct file upload through the server (fallback method).

    This endpoint handles the complete upload process server-side.
    Use presigned URLs for better performance with large files.
    """
    if not file.content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content type is required"
        )

    # Determine folder based on content type
    if file.content_type.startswith("image/"):
        folder = "media"
        file_type = FileType.IMAGE
    elif file.content_type.startswith("video/"):
        folder = "media"
        file_type = FileType.VIDEO
    elif file.content_type.startswith("audio/"):
        folder = "voice"
        file_type = FileType.AUDIO
    else:
        folder = "documents"
        file_type = FileType.DOCUMENT

    # Validate file type
    allowed = ALLOWED_TYPES.get(folder, [])
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{file.content_type}' not allowed"
        )

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Validate file size
    max_size = get_max_size_for_type(file.content_type)
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size ({file_size} bytes) exceeds maximum allowed ({max_size} bytes)"
        )

    try:
        # Generate file key
        file_key = s3_service.generate_file_key(
            folder=folder,
            filename=file.filename or "upload",
            user_id=current_user.id,
        )

        # Upload to S3
        s3_service.client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=file_key,
            Body=content,
            ContentType=file.content_type,
        )

        file_url = f"{settings.s3_base_url}/{file_key}"

        # Create media record
        media = Media(
            user_id=current_user.id,
            file_key=file_key,
            file_url=file_url,
            file_name=file.filename or "upload",
            file_type=file_type,
            mime_type=file.content_type,
            file_size=file_size,
        )

        db.add(media)
        await db.commit()
        await db.refresh(media)

        return MediaResponse(
            id=media.id,
            file_url=media.file_url,
            thumbnail_url=media.thumbnail_url,
            file_type=media.file_type.value,
            file_size=media.file_size,
            file_name=media.file_name,
            mime_type=media.mime_type,
            duration=media.duration,
            created_at=media.created_at,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}"
        )


@router.get("/{media_id}", response_model=MediaResponse)
async def get_media(
    media_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get media information by ID"""
    result = await db.execute(select(Media).where(Media.id == media_id))
    media = result.scalar_one_or_none()

    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )

    return MediaResponse(
        id=media.id,
        file_url=media.file_url,
        thumbnail_url=media.thumbnail_url,
        file_type=media.file_type.value,
        file_size=media.file_size,
        file_name=media.file_name,
        mime_type=media.mime_type,
        duration=media.duration,
        created_at=media.created_at,
    )


@router.delete("/{media_id}")
async def delete_media(
    media_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete media file"""
    result = await db.execute(
        select(Media).where(Media.id == media_id, Media.user_id == current_user.id)
    )
    media = result.scalar_one_or_none()

    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found or access denied"
        )

    try:
        # Delete from S3
        s3_service.delete_file(media.file_key)

        # Delete thumbnail if exists
        if media.thumbnail_url:
            thumbnail_key = media.thumbnail_url.replace(f"{settings.s3_base_url}/", "")
            try:
                s3_service.delete_file(thumbnail_key)
            except:
                pass  # Ignore thumbnail deletion errors

    except Exception as e:
        # Log but don't fail if S3 deletion fails
        print(f"Warning: Failed to delete from S3: {e}")

    # Delete from database
    await db.delete(media)
    await db.commit()

    return {"success": True, "message": "Media deleted successfully"}


@router.get("/{media_id}/download")
async def get_download_url(
    media_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a presigned download URL for a media file"""
    result = await db.execute(select(Media).where(Media.id == media_id))
    media = result.scalar_one_or_none()

    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )

    try:
        download_url = s3_service.get_presigned_download_url(
            file_key=media.file_key,
            filename=media.file_name,
        )

        return {"download_url": download_url, "expires_in": 3600}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate download URL: {str(e)}"
        )
