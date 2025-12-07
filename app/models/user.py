from sqlalchemy import Column, String, Boolean, DateTime, Enum, Text
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
import enum

from app.db.database import Base


class UserRole(str, enum.Enum):
    """User role enumeration"""
    FOUNDER = "FOUNDER"
    CO_FOUNDER = "CO_FOUNDER"
    VERIFIED = "VERIFIED"
    REGULAR = "REGULAR"


class User(Base):
    """User model"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    display_name = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    avatar_url = Column(String(500), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.REGULAR, nullable=False)
    bio = Column(Text, nullable=True)
    social_links = Column(JSON, nullable=True)  # {instagram: "", twitter: "", linkedin: ""}
    is_verified = Column(Boolean, default=False, nullable=False)
    is_online = Column(Boolean, default=False, nullable=False)
    last_seen = Column(DateTime, nullable=True)
    public_key = Column(Text, nullable=True)  # For E2E encryption
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    sent_messages = relationship("Message", back_populates="sender", foreign_keys="Message.sender_id")
    conversation_participants = relationship("ConversationParticipant", back_populates="user")
    group_members = relationship("GroupMember", back_populates="user")
    device_tokens = relationship("DeviceToken", back_populates="user")
    notification_settings = relationship("NotificationSettings", back_populates="user", uselist=False)
    blocked_users = relationship("BlockedUser", foreign_keys="BlockedUser.blocker_id", back_populates="blocker")
    blocked_by_users = relationship("BlockedUser", foreign_keys="BlockedUser.blocked_id", back_populates="blocked")

    def __repr__(self):
        return f"<User {self.display_name} ({self.phone_number})>"
