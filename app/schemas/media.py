from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID

from app.models.media import FileType


# Media schemas
class MediaUploadResponse(BaseModel):
    """Schema for media upload response"""
    id: UUID
    file_url: str
    thumbnail_url: Optional[str] = None
    file_type: FileType
    file_size: int
    file_name: str
    mime_type: str
    duration: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MediaResponse(BaseModel):
    """Schema for media response"""
    id: UUID
    message_id: UUID
    uploader_id: UUID
    file_type: FileType
    file_size: int
    file_name: str
    file_url: str
    thumbnail_url: Optional[str] = None
    mime_type: str
    duration: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
