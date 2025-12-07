from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from uuid import UUID
import os
import uuid
from pathlib import Path

from app.db.database import get_db
from app.schemas.media import MediaUploadResponse
from app.schemas.auth import SuccessResponse
from app.core.security import get_current_active_user
from app.core.config import settings
from app.models.user import User
from app.models.media import MediaFile, FileType

router = APIRouter(prefix="/media", tags=["Media"])

# Create uploads directory if it doesn't exist
UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def get_file_type(content_type: str) -> FileType:
    """Determine file type from content type"""
    if content_type.startswith("image/"):
        return FileType.IMAGE
    elif content_type.startswith("video/"):
        return FileType.VIDEO
    elif content_type.startswith("audio/"):
        return FileType.AUDIO
    else:
        return FileType.DOCUMENT


@router.post("/upload", response_model=MediaUploadResponse)
async def upload_media(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Upload a media file"""
    # Validate file size based on type
    content = await file.read()
    file_size = len(content)

    file_type = get_file_type(file.content_type)

    if file_type == FileType.IMAGE and file_size > settings.MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image size exceeds maximum allowed size of {settings.MAX_IMAGE_SIZE} bytes"
        )
    elif file_type == FileType.VIDEO and file_size > settings.MAX_VIDEO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Video size exceeds maximum allowed size of {settings.MAX_VIDEO_SIZE} bytes"
        )
    elif file_type == FileType.DOCUMENT and file_size > settings.MAX_DOCUMENT_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Document size exceeds maximum allowed size of {settings.MAX_DOCUMENT_SIZE} bytes"
        )

    # Generate unique filename
    file_extension = Path(file.filename).suffix
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = UPLOAD_DIR / unique_filename

    # Save file
    with open(file_path, "wb") as f:
        f.write(content)

    # Create media record (without message_id for now - will be added when message is created)
    # For now, we'll return the file info and the frontend will use it when creating a message
    file_url = f"/api/media/{unique_filename}"

    return MediaUploadResponse(
        id=uuid.uuid4(),  # Temporary ID
        file_url=file_url,
        thumbnail_url=None,  # TODO: Generate thumbnails for images/videos
        file_type=file_type,
        file_size=file_size,
        file_name=file.filename,
        mime_type=file.content_type,
        duration=None,  # TODO: Extract duration for audio/video
        created_at=__import__('datetime').datetime.utcnow()
    )


@router.get("/{filename}")
async def download_media(
    filename: str,
    current_user: User = Depends(get_current_active_user)
):
    """Download a media file"""
    file_path = UPLOAD_DIR / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    return FileResponse(
        path=file_path,
        filename=filename
    )


@router.delete("/{media_id}", response_model=SuccessResponse)
async def delete_media(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a media file"""
    media = db.query(MediaFile).filter(MediaFile.id == media_id).first()

    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found"
        )

    # Check if user is the uploader
    if media.uploader_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own media files"
        )

    # Extract filename from URL
    filename = media.file_url.split("/")[-1]
    file_path = UPLOAD_DIR / filename

    # Delete file from disk
    if file_path.exists():
        os.remove(file_path)

    # Delete thumbnail if exists
    if media.thumbnail_url:
        thumbnail_filename = media.thumbnail_url.split("/")[-1]
        thumbnail_path = UPLOAD_DIR / thumbnail_filename
        if thumbnail_path.exists():
            os.remove(thumbnail_path)

    # Delete from database
    db.delete(media)
    db.commit()

    return SuccessResponse(success=True, message="Media file deleted successfully")


@router.get("/{media_id}/thumbnail")
async def get_media_thumbnail(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get thumbnail for a media file"""
    media = db.query(MediaFile).filter(MediaFile.id == media_id).first()

    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found"
        )

    if not media.thumbnail_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail not available"
        )

    # Extract filename from URL
    filename = media.thumbnail_url.split("/")[-1]
    file_path = UPLOAD_DIR / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail file not found"
        )

    return FileResponse(
        path=file_path,
        filename=filename
    )
