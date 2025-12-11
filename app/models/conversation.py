import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum, Text, Integer
from sqlalchemy.orm import relationship
import enum

from ..core.database import Base


class ConversationType(str, enum.Enum):
    DIRECT = "DIRECT"
    GROUP = "GROUP"


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(Enum(ConversationType), nullable=False, default=ConversationType.DIRECT)

    # Group specific fields
    name = Column(String(100), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Settings
    is_muted = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    is_favorite = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_message_at = Column(DateTime, nullable=True)

    # Relationships
    participants = relationship("ConversationParticipant", back_populates="conversation", lazy="selectin")
    messages = relationship("Message", back_populates="conversation", lazy="dynamic")

    def to_dict(self, user_id: str = None):
        return {
            "id": self.id,
            "type": self.type.value if self.type else None,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "description": self.description,
            "created_by": self.created_by,
            "is_muted": self.is_muted,
            "is_archived": self.is_archived,
            "is_favorite": self.is_favorite,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
        }


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    role = Column(String(20), default="member")  # admin, member
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_read_at = Column(DateTime, nullable=True)
    unread_count = Column(Integer, default=0)

    # Relationships
    conversation = relationship("Conversation", back_populates="participants")
    user = relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "role": self.role,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "last_read_at": self.last_read_at.isoformat() if self.last_read_at else None,
            "unread_count": self.unread_count,
        }
