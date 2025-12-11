import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    bio = Column(Text, nullable=True)
    role = Column(String(20), default="user")

    is_verified = Column(Boolean, default=False)
    verification_status = Column(String(20), default="none")  # none, pending, approved, rejected
    verification_requested_at = Column(DateTime, nullable=True)

    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime, nullable=True)

    # Social links stored as JSON
    social_links = Column(JSON, default=dict)  # {"instagram": "", "twitter": "", "linkedin": "", etc.}

    # Subscription info
    subscription_plan = Column(String(20), default="free")  # free, premium, business
    subscription_expires_at = Column(DateTime, nullable=True)
    stripe_customer_id = Column(String(100), nullable=True)  # Stripe customer ID (legacy)
    stripe_subscription_id = Column(String(100), nullable=True)  # Stripe subscription ID (legacy)

    # Paystack payment info
    paystack_customer_code = Column(String(100), nullable=True)  # Paystack customer code
    paystack_authorization_code = Column(String(100), nullable=True)  # For recurring charges
    paystack_subscription_code = Column(String(100), nullable=True)  # Paystack subscription code
    paystack_email_token = Column(String(100), nullable=True)  # Email token for subscription management

    # Blocked users stored as JSON array
    blocked_users = Column(JSON, default=list)  # ["user_id_1", "user_id_2", ...]

    # Privacy settings
    show_online_status = Column(Boolean, default=True)
    show_last_seen = Column(Boolean, default=True)
    show_profile_photo = Column(Boolean, default=True)
    show_read_receipts = Column(Boolean, default=True)

    # Notification settings
    notifications_enabled = Column(Boolean, default=True)
    notification_sound = Column(Boolean, default=True)
    notification_vibration = Column(Boolean, default=True)
    notification_preview = Column(Boolean, default=True)
    message_notifications = Column(Boolean, default=True)
    group_notifications = Column(Boolean, default=True)

    # Push notification device tokens
    device_tokens = Column(JSON, default=list)  # [{"token": "...", "platform": "ios/android", "created_at": "..."}]

    # Two-Factor Authentication
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String(255), nullable=True)  # Encrypted TOTP secret
    two_factor_backup_codes = Column(JSON, default=list)  # Encrypted backup codes

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    media = relationship("Media", back_populates="user", lazy="dynamic")
    messages = relationship("Message", back_populates="sender", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "phone_number": self.phone_number,
            "email": self.email,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "bio": self.bio,
            "role": self.role,
            "is_verified": self.is_verified,
            "verification_status": self.verification_status,
            "is_online": self.is_online,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "social_links": self.social_links or {},
            "subscription_plan": self.subscription_plan,
            "subscription_expires_at": self.subscription_expires_at.isoformat() if self.subscription_expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
