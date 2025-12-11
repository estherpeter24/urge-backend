from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class PresignedUrlRequest(BaseModel):
    """Request for generating a presigned upload URL"""
    file_name: str = Field(..., min_length=1, max_length=255)
    file_type: str = Field(..., min_length=1, description="MIME type of the file")
    folder: Literal["avatars", "media", "documents", "voice"] = "media"

    class Config:
        json_schema_extra = {
            "example": {
                "file_name": "profile_photo.jpg",
                "file_type": "image/jpeg",
                "folder": "avatars"
            }
        }


class PresignedUrlResponse(BaseModel):
    """Response containing presigned URL for upload"""
    upload_url: str
    file_key: str
    file_url: str
    expires_in: int

    class Config:
        json_schema_extra = {
            "example": {
                "upload_url": "https://bucket.s3.amazonaws.com/avatars/...",
                "file_key": "avatars/user123/2025/01/abc123_profile.jpg",
                "file_url": "https://media.urge.app/avatars/user123/2025/01/abc123_profile.jpg",
                "expires_in": 3600
            }
        }


class CompleteUploadRequest(BaseModel):
    """Request to complete an upload and create database record"""
    file_key: str = Field(..., min_length=1)
    file_url: str = Field(..., min_length=1)
    file_type: Literal["IMAGE", "VIDEO", "AUDIO", "DOCUMENT"]
    file_size: int = Field(ge=0, default=0)
    file_name: str = Field(..., min_length=1, max_length=255)
    mime_type: str = Field(..., min_length=1)
    duration: Optional[int] = Field(None, ge=0, description="Duration in seconds for audio/video")
    width: Optional[int] = Field(None, ge=0, description="Width for images/videos")
    height: Optional[int] = Field(None, ge=0, description="Height for images/videos")

    class Config:
        json_schema_extra = {
            "example": {
                "file_key": "avatars/user123/2025/01/abc123_profile.jpg",
                "file_url": "https://media.urge.app/avatars/user123/2025/01/abc123_profile.jpg",
                "file_type": "IMAGE",
                "file_size": 1024000,
                "file_name": "profile_photo.jpg",
                "mime_type": "image/jpeg"
            }
        }


class MediaResponse(BaseModel):
    """Response containing media information"""
    id: str
    file_url: str
    thumbnail_url: Optional[str] = None
    file_type: str
    file_size: int
    file_name: str
    mime_type: str
    duration: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "file_url": "https://media.urge.app/avatars/user123/2025/01/abc123_profile.jpg",
                "thumbnail_url": None,
                "file_type": "IMAGE",
                "file_size": 1024000,
                "file_name": "profile_photo.jpg",
                "mime_type": "image/jpeg",
                "duration": None,
                "created_at": "2025-01-08T12:00:00Z"
            }
        }


class MediaListResponse(BaseModel):
    """Response containing list of media"""
    media: list[MediaResponse]
    total: int
    limit: int
    offset: int
