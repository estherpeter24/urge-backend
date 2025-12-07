from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
import enum

from app.db.database import Base


class ConversationType(str, enum.Enum):
    """Conversation type enumeration"""
    DIRECT = "DIRECT"
    GROUP = "GROUP"


class Conversation(Base):
    """Conversation model"""
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    type = Column(Enum(ConversationType), nullable=False)
    name = Column(String(100), nullable=True)  # For group conversations
    avatar_url = Column(String(500), nullable=True)
    last_message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    last_message_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    participants = relationship("ConversationParticipant", back_populates="conversation", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="conversation", foreign_keys="Message.conversation_id")
    group = relationship("Group", back_populates="conversation", uselist=False)

    def __repr__(self):
        return f"<Conversation {self.id} ({self.type})>"


class ConversationParticipant(Base):
    """Conversation participant model"""
    __tablename__ = "conversation_participants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    unread_count = Column(Integer, default=0, nullable=False)
    is_muted = Column(Boolean, default=False, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False)
    is_favorite = Column(Boolean, default=False, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    left_at = Column(DateTime, nullable=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="participants")
    user = relationship("User", back_populates="conversation_participants")

    def __repr__(self):
        return f"<ConversationParticipant {self.user_id} in {self.conversation_id}>"
