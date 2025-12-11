import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum

from ..core.database import Base


class GroupRole(str, enum.Enum):
    """
    Group member roles:
    - FOUNDER: Original creator, has all permissions
    - ACCOUNTANT: Co-founder responsible for finances
    - MODERATOR: Co-founder responsible for ethics/moderation
    - RECRUITER: Co-founder responsible for vetting new members
    - SUPPORT: Co-founder for helping members with challenges
    - CHEERLEADER: Co-founder for keeping community active
    - MEMBER: Regular member
    """
    FOUNDER = "FOUNDER"
    ACCOUNTANT = "ACCOUNTANT"
    MODERATOR = "MODERATOR"
    RECRUITER = "RECRUITER"
    SUPPORT = "SUPPORT"
    CHEERLEADER = "CHEERLEADER"
    MEMBER = "MEMBER"


class GroupSettings(Base):
    """Extended group settings"""
    __tablename__ = "group_settings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.id"), unique=True, nullable=False)

    # Visibility
    is_public = Column(Boolean, default=False)
    allow_member_invites = Column(Boolean, default=True)
    require_admin_approval = Column(Boolean, default=False)

    # Permissions
    only_admins_can_post = Column(Boolean, default=False)
    only_admins_can_edit_info = Column(Boolean, default=True)

    # Invite link
    invite_link = Column(String(100), unique=True, nullable=True)
    invite_link_enabled = Column(Boolean, default=True)

    # Minimum network requirement for founders
    min_network_size = Column(Integer, default=5)

    # Notification settings
    mute_notifications = Column(Boolean, default=False)

    # Theme
    theme_color = Column(String(20), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "is_public": self.is_public,
            "allow_member_invites": self.allow_member_invites,
            "require_admin_approval": self.require_admin_approval,
            "only_admins_can_post": self.only_admins_can_post,
            "only_admins_can_edit_info": self.only_admins_can_edit_info,
            "invite_link": self.invite_link,
            "invite_link_enabled": self.invite_link_enabled,
            "min_network_size": self.min_network_size,
            "mute_notifications": self.mute_notifications,
            "theme_color": self.theme_color,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class GroupEvent(Base):
    """Group events (can be created by Founder/Co-founders)"""
    __tablename__ = "group_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String(500), nullable=True)

    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)

    is_online = Column(Boolean, default=False)
    meeting_link = Column(String(500), nullable=True)

    max_attendees = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    attendees = relationship("GroupEventAttendee", back_populates="event", lazy="selectin")

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "created_by": self.created_by,
            "title": self.title,
            "description": self.description,
            "location": self.location,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "is_online": self.is_online,
            "meeting_link": self.meeting_link,
            "max_attendees": self.max_attendees,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "attendees_count": len(self.attendees) if self.attendees else 0,
        }


class GroupEventAttendee(Base):
    """Event attendees"""
    __tablename__ = "group_event_attendees"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String(36), ForeignKey("group_events.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    status = Column(String(20), default="going")  # going, maybe, not_going

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    event = relationship("GroupEvent", back_populates="attendees")

    def to_dict(self):
        return {
            "id": self.id,
            "event_id": self.event_id,
            "user_id": self.user_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class VerificationRequest(Base):
    """URGE verification requests for group members"""
    __tablename__ = "verification_requests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    group_id = Column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)

    status = Column(String(20), default="pending")  # pending, approved, rejected

    # Verification fee and founder profit share
    fee_amount = Column(Integer, default=0)  # in cents
    founder_share_percent = Column(Integer, default=10)  # percentage for founder

    reviewed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "group_id": self.group_id,
            "status": self.status,
            "fee_amount": self.fee_amount,
            "founder_share_percent": self.founder_share_percent,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Helper function to check if user has co-founder role
def is_cofounder(role: str) -> bool:
    """Check if the role is a co-founder role"""
    cofounder_roles = [
        GroupRole.ACCOUNTANT.value,
        GroupRole.MODERATOR.value,
        GroupRole.RECRUITER.value,
        GroupRole.SUPPORT.value,
        GroupRole.CHEERLEADER.value,
    ]
    return role in cofounder_roles


def is_admin_role(role: str) -> bool:
    """Check if the role has admin privileges (Founder or any Co-founder)"""
    return role == GroupRole.FOUNDER.value or is_cofounder(role)


def can_manage_events(role: str) -> bool:
    """Check if the role can create/manage events"""
    return role == GroupRole.FOUNDER.value or is_cofounder(role)


def can_manage_members(role: str) -> bool:
    """Check if the role can add/remove members"""
    return role in [
        GroupRole.FOUNDER.value,
        GroupRole.RECRUITER.value,
        GroupRole.MODERATOR.value,
    ]


def can_manage_finances(role: str) -> bool:
    """Check if the role can manage finances/verification"""
    return role in [
        GroupRole.FOUNDER.value,
        GroupRole.ACCOUNTANT.value,
    ]
