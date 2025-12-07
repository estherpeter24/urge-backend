from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
import enum

from app.db.database import Base


class DevicePlatform(str, enum.Enum):
    """Device platform enumeration"""
    IOS = "IOS"
    ANDROID = "ANDROID"


class DeviceToken(Base):
    """Device token model for push notifications"""
    __tablename__ = "device_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_token = Column(String(255), unique=True, nullable=False)
    platform = Column(Enum(DevicePlatform), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="device_tokens")

    def __repr__(self):
        return f"<DeviceToken {self.device_token[:20]}... ({self.platform})>"


class NotificationSettings(Base):
    """User notification settings model"""
    __tablename__ = "notification_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    enabled = Column(Boolean, default=True, nullable=False)
    show_preview = Column(Boolean, default=True, nullable=False)
    sound = Column(Boolean, default=True, nullable=False)
    vibration = Column(Boolean, default=True, nullable=False)
    message_notifications = Column(Boolean, default=True, nullable=False)
    group_notifications = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="notification_settings")

    def __repr__(self):
        return f"<NotificationSettings user_id={self.user_id} enabled={self.enabled}>"
