import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum

from ..core.database import Base


class FileType(str, enum.Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"


class Media(Base):
    __tablename__ = "media"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # File information
    file_key = Column(String(500), nullable=False)  # S3 key
    file_url = Column(String(1000), nullable=False)  # Full URL (CDN or S3)
    file_name = Column(String(255), nullable=False)
    file_type = Column(Enum(FileType), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size = Column(Integer, default=0)  # Size in bytes

    # Optional metadata
    thumbnail_url = Column(String(1000), nullable=True)
    duration = Column(Integer, nullable=True)  # For audio/video in seconds
    width = Column(Integer, nullable=True)  # For images/videos
    height = Column(Integer, nullable=True)  # For images/videos

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="media")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "file_key": self.file_key,
            "file_url": self.file_url,
            "file_name": self.file_name,
            "file_type": self.file_type.value if self.file_type else None,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "thumbnail_url": self.thumbnail_url,
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
