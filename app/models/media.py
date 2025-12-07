from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
import enum

from app.db.database import Base


class FileType(str, enum.Enum):
    """File type enumeration"""
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"


class MediaFile(Base):
    """Media file model"""
    __tablename__ = "media_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    uploader_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    file_type = Column(Enum(FileType), nullable=False)
    file_size = Column(BigInteger, nullable=False)  # Size in bytes
    file_name = Column(String(255), nullable=False)
    file_url = Column(String(500), nullable=False)
    thumbnail_url = Column(String(500), nullable=True)
    mime_type = Column(String(100), nullable=False)
    duration = Column(BigInteger, nullable=True)  # Duration in seconds for audio/video
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    message = relationship("Message", back_populates="media_file")

    def __repr__(self):
        return f"<MediaFile {self.file_name} ({self.file_type})>"
