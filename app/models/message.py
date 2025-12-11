import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum, Text, Integer
from sqlalchemy.orm import relationship
import enum

from ..core.database import Base


class MessageType(str, enum.Enum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    VOICE = "VOICE"
    LOCATION = "LOCATION"
    CONTACT = "CONTACT"
    SYSTEM = "SYSTEM"  # System messages (member left, joined, etc.)


class MessageStatus(str, enum.Enum):
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    sender_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # Content
    content = Column(Text, nullable=True)
    message_type = Column(Enum(MessageType), nullable=False, default=MessageType.TEXT)
    status = Column(Enum(MessageStatus), nullable=False, default=MessageStatus.SENT)

    # Media (for IMAGE, VIDEO, AUDIO, DOCUMENT types)
    media_url = Column(String(1000), nullable=True)
    thumbnail_url = Column(String(1000), nullable=True)
    audio_duration = Column(Integer, nullable=True)  # For voice messages

    # Reply
    reply_to_id = Column(String(36), ForeignKey("messages.id"), nullable=True)

    # Flags
    is_edited = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    is_encrypted = Column(Boolean, default=False)
    is_starred = Column(Boolean, default=False)
    is_forwarded = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    read_at = Column(DateTime, nullable=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", back_populates="messages")
    reply_to = relationship("Message", remote_side=[id], foreign_keys=[reply_to_id])

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender_id": self.sender_id,
            "content": self.content,
            "message_type": self.message_type.value if self.message_type else None,
            "status": self.status.value if self.status else None,
            "media_url": self.media_url,
            "thumbnail_url": self.thumbnail_url,
            "audio_duration": self.audio_duration,
            "reply_to_id": self.reply_to_id,
            "is_edited": self.is_edited,
            "is_deleted": self.is_deleted,
            "is_encrypted": self.is_encrypted,
            "is_starred": self.is_starred,
            "is_forwarded": self.is_forwarded,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }
