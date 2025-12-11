from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, delete
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid
import secrets
import string

from ..core.database import get_db
from ..core.security import get_current_user
from ..models.conversation import Conversation, ConversationParticipant, ConversationType
from ..models.user import User
from ..models.message import Message, MessageType
from ..models.group import (
    GroupRole,
    GroupSettings,
    GroupEvent,
    GroupEventAttendee,
    VerificationRequest,
    is_admin_role,
    can_manage_events,
    can_manage_members,
    can_manage_finances,
)

router = APIRouter(prefix="/groups", tags=["Groups"])


# ============== Request/Response Models ==============

class GroupCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    member_ids: List[str] = []
    is_public: Optional[bool] = False
    allow_member_invites: Optional[bool] = True
    require_admin_approval: Optional[bool] = False


class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None


class GroupSettingsUpdateRequest(BaseModel):
    is_public: Optional[bool] = None
    allow_member_invites: Optional[bool] = None
    require_admin_approval: Optional[bool] = None
    only_admins_can_post: Optional[bool] = None
    only_admins_can_edit_info: Optional[bool] = None
    invite_link_enabled: Optional[bool] = None
    mute_notifications: Optional[bool] = None
    theme_color: Optional[str] = None


class RoleUpdateRequest(BaseModel):
    role: str  # FOUNDER, ACCOUNTANT, MODERATOR, RECRUITER, SUPPORT, CHEERLEADER, MEMBER


class GroupMemberResponse(BaseModel):
    user_id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone_number: Optional[str] = None
    role: str
    role_display: Optional[str] = None
    is_verified: bool = False
    is_online: bool = False
    joined_at: str

    class Config:
        from_attributes = True


class GroupSettingsResponse(BaseModel):
    is_public: bool = False
    allow_member_invites: bool = True
    require_admin_approval: bool = False
    only_admins_can_post: bool = False
    only_admins_can_edit_info: bool = True
    invite_link: Optional[str] = None
    invite_link_enabled: bool = True
    mute_notifications: bool = False
    theme_color: Optional[str] = None

    class Config:
        from_attributes = True


class GroupResponse(BaseModel):
    id: str
    conversation_id: str
    name: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    created_by: Optional[str] = None
    founder_name: Optional[str] = None
    settings: GroupSettingsResponse
    members: List[GroupMemberResponse] = []
    member_count: int = 0
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class EventCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    is_online: bool = False
    meeting_link: Optional[str] = None
    max_attendees: Optional[int] = None


class EventResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    is_online: bool
    meeting_link: Optional[str] = None
    max_attendees: Optional[int] = None
    attendees_count: int = 0
    created_by: str
    creator_name: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


# ============== Helper Functions ==============

def generate_invite_link():
    """Generate a unique invite link code"""
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))


def get_role_display(role: str) -> str:
    """Get human-readable role name"""
    role_displays = {
        GroupRole.FOUNDER.value: "Founder",
        GroupRole.ACCOUNTANT.value: "Accountant (Co-founder)",
        GroupRole.MODERATOR.value: "Moderator (Co-founder)",
        GroupRole.RECRUITER.value: "Recruiter (Co-founder)",
        GroupRole.SUPPORT.value: "Support (Co-founder)",
        GroupRole.CHEERLEADER.value: "Cheer Leader (Co-founder)",
        GroupRole.MEMBER.value: "Member",
    }
    return role_displays.get(role, "Member")


async def _get_group_members(db: AsyncSession, group_id: str) -> List[GroupMemberResponse]:
    """Helper to get group members with full details"""
    participants_result = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == group_id
        )
    )
    participants = participants_result.scalars().all()

    members = []
    for p in participants:
        user_result = await db.execute(
            select(User).where(User.id == p.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            members.append(GroupMemberResponse(
                user_id=user.id,
                display_name=user.display_name,
                avatar_url=user.avatar_url,
                phone_number=user.phone_number,
                role=p.role or GroupRole.MEMBER.value,
                role_display=get_role_display(p.role or GroupRole.MEMBER.value),
                is_verified=user.is_verified or False,
                is_online=user.is_online or False,
                joined_at=p.joined_at.isoformat() if p.joined_at else "",
            ))

    # Sort by role priority
    role_priority = {
        GroupRole.FOUNDER.value: 0,
        GroupRole.ACCOUNTANT.value: 1,
        GroupRole.MODERATOR.value: 2,
        GroupRole.RECRUITER.value: 3,
        GroupRole.SUPPORT.value: 4,
        GroupRole.CHEERLEADER.value: 5,
        GroupRole.MEMBER.value: 6,
    }
    members.sort(key=lambda m: role_priority.get(m.role, 6))

    return members


async def _get_or_create_group_settings(db: AsyncSession, conversation_id: str) -> GroupSettings:
    """Get or create group settings"""
    result = await db.execute(
        select(GroupSettings).where(GroupSettings.conversation_id == conversation_id)
    )
    settings = result.scalar_one_or_none()

    if not settings:
        settings = GroupSettings(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            invite_link=generate_invite_link(),
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    return settings


async def _check_founder_requirements(db: AsyncSession, user: User) -> bool:
    """Check if user meets founder requirements (verified + 5 users in network)"""
    if not user.is_verified:
        return False

    # Count user's conversations (network size)
    result = await db.execute(
        select(func.count(ConversationParticipant.id)).where(
            ConversationParticipant.user_id == user.id
        )
    )
    network_count = result.scalar() or 0

    return network_count >= 5


# ============== Group CRUD Endpoints ==============

@router.post("", response_model=GroupResponse)
async def create_group(
    request: GroupCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new group (user becomes Founder)"""
    # Check founder requirements
    meets_requirements = await _check_founder_requirements(db, current_user)
    # For now, allow group creation even without meeting requirements
    # but mark the founder status appropriately

    # Create conversation for group
    conversation = Conversation(
        id=str(uuid.uuid4()),
        type=ConversationType.GROUP,
        name=request.name,
        description=request.description,
        avatar_url=request.avatar_url,
        created_by=current_user.id,
    )
    db.add(conversation)

    # Add creator as FOUNDER
    creator_participant = ConversationParticipant(
        id=str(uuid.uuid4()),
        conversation_id=conversation.id,
        user_id=current_user.id,
        role=GroupRole.FOUNDER.value,
    )
    db.add(creator_participant)

    # Create group settings
    settings = GroupSettings(
        id=str(uuid.uuid4()),
        conversation_id=conversation.id,
        is_public=request.is_public or False,
        allow_member_invites=request.allow_member_invites if request.allow_member_invites is not None else True,
        require_admin_approval=request.require_admin_approval or False,
        invite_link=generate_invite_link(),
    )
    db.add(settings)

    # Build members list starting with founder
    members = [GroupMemberResponse(
        user_id=current_user.id,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        phone_number=current_user.phone_number,
        role=GroupRole.FOUNDER.value,
        role_display=get_role_display(GroupRole.FOUNDER.value),
        is_verified=current_user.is_verified or False,
        is_online=current_user.is_online or False,
        joined_at=datetime.utcnow().isoformat(),
    )]

    # Add other members
    for member_id in request.member_ids:
        if member_id != current_user.id:
            participant = ConversationParticipant(
                id=str(uuid.uuid4()),
                conversation_id=conversation.id,
                user_id=member_id,
                role=GroupRole.MEMBER.value,
            )
            db.add(participant)

            # Get member info
            member_result = await db.execute(
                select(User).where(User.id == member_id)
            )
            member = member_result.scalar_one_or_none()
            if member:
                members.append(GroupMemberResponse(
                    user_id=member.id,
                    display_name=member.display_name,
                    avatar_url=member.avatar_url,
                    phone_number=member.phone_number,
                    role=GroupRole.MEMBER.value,
                    role_display=get_role_display(GroupRole.MEMBER.value),
                    is_verified=member.is_verified or False,
                    is_online=member.is_online or False,
                    joined_at=datetime.utcnow().isoformat(),
                ))

    await db.commit()
    await db.refresh(conversation)
    await db.refresh(settings)

    return GroupResponse(
        id=conversation.id,
        conversation_id=conversation.id,
        name=conversation.name or "",
        description=conversation.description,
        avatar_url=conversation.avatar_url,
        created_by=conversation.created_by,
        founder_name=current_user.display_name,
        settings=GroupSettingsResponse(
            is_public=settings.is_public,
            allow_member_invites=settings.allow_member_invites,
            require_admin_approval=settings.require_admin_approval,
            only_admins_can_post=settings.only_admins_can_post,
            only_admins_can_edit_info=settings.only_admins_can_edit_info,
            invite_link=settings.invite_link,
            invite_link_enabled=settings.invite_link_enabled,
            mute_notifications=settings.mute_notifications,
            theme_color=settings.theme_color,
        ),
        members=members,
        member_count=len(members),
        created_at=conversation.created_at.isoformat() if conversation.created_at else "",
        updated_at=conversation.updated_at.isoformat() if conversation.updated_at else "",
    )


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get group details"""
    result = await db.execute(
        select(Conversation).where(
            and_(
                Conversation.id == group_id,
                Conversation.type == ConversationType.GROUP,
            )
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    # Get settings
    settings = await _get_or_create_group_settings(db, group_id)

    # Get members
    members = await _get_group_members(db, group_id)

    # Get founder name
    founder_name = None
    if conversation.created_by:
        founder_result = await db.execute(
            select(User).where(User.id == conversation.created_by)
        )
        founder = founder_result.scalar_one_or_none()
        if founder:
            founder_name = founder.display_name

    return GroupResponse(
        id=conversation.id,
        conversation_id=conversation.id,
        name=conversation.name or "",
        description=conversation.description,
        avatar_url=conversation.avatar_url,
        created_by=conversation.created_by,
        founder_name=founder_name,
        settings=GroupSettingsResponse(
            is_public=settings.is_public,
            allow_member_invites=settings.allow_member_invites,
            require_admin_approval=settings.require_admin_approval,
            only_admins_can_post=settings.only_admins_can_post,
            only_admins_can_edit_info=settings.only_admins_can_edit_info,
            invite_link=settings.invite_link,
            invite_link_enabled=settings.invite_link_enabled,
            mute_notifications=settings.mute_notifications,
            theme_color=settings.theme_color,
        ),
        members=members,
        member_count=len(members),
        created_at=conversation.created_at.isoformat() if conversation.created_at else "",
        updated_at=conversation.updated_at.isoformat() if conversation.updated_at else "",
    )


@router.get("/conversation/{conversation_id}", response_model=GroupResponse)
async def get_group_by_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get group details by conversation ID"""
    return await get_group(conversation_id, db, current_user)


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: str,
    request: GroupUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update group details (Founder and Co-founders only)"""
    # Get user's role in group
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == current_user.id,
            )
        )
    )
    participant = participant_result.scalar_one_or_none()

    if not participant or not is_admin_role(participant.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Founder and Co-founders can update group"
        )

    result = await db.execute(
        select(Conversation).where(Conversation.id == group_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    if request.name is not None:
        conversation.name = request.name
    if request.description is not None:
        conversation.description = request.description
    if request.avatar_url is not None:
        conversation.avatar_url = request.avatar_url

    conversation.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(conversation)

    # Get full group response
    return await get_group(group_id, db, current_user)


@router.put("/{group_id}/settings", response_model=GroupSettingsResponse)
async def update_group_settings(
    group_id: str,
    request: GroupSettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update group settings (Founder only)"""
    # Verify user is founder
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == current_user.id,
                ConversationParticipant.role == GroupRole.FOUNDER.value,
            )
        )
    )
    if not participant_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Founder can update group settings"
        )

    settings = await _get_or_create_group_settings(db, group_id)

    if request.is_public is not None:
        settings.is_public = request.is_public
    if request.allow_member_invites is not None:
        settings.allow_member_invites = request.allow_member_invites
    if request.require_admin_approval is not None:
        settings.require_admin_approval = request.require_admin_approval
    if request.only_admins_can_post is not None:
        settings.only_admins_can_post = request.only_admins_can_post
    if request.only_admins_can_edit_info is not None:
        settings.only_admins_can_edit_info = request.only_admins_can_edit_info
    if request.invite_link_enabled is not None:
        settings.invite_link_enabled = request.invite_link_enabled
    if request.mute_notifications is not None:
        settings.mute_notifications = request.mute_notifications
    if request.theme_color is not None:
        settings.theme_color = request.theme_color

    settings.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(settings)

    return GroupSettingsResponse(
        is_public=settings.is_public,
        allow_member_invites=settings.allow_member_invites,
        require_admin_approval=settings.require_admin_approval,
        only_admins_can_post=settings.only_admins_can_post,
        only_admins_can_edit_info=settings.only_admins_can_edit_info,
        invite_link=settings.invite_link,
        invite_link_enabled=settings.invite_link_enabled,
        mute_notifications=settings.mute_notifications,
        theme_color=settings.theme_color,
    )


@router.post("/{group_id}/regenerate-invite-link")
async def regenerate_invite_link(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Regenerate the invite link (Founder only)"""
    # Verify user is founder
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == current_user.id,
                ConversationParticipant.role == GroupRole.FOUNDER.value,
            )
        )
    )
    if not participant_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Founder can regenerate invite link"
        )

    settings = await _get_or_create_group_settings(db, group_id)
    settings.invite_link = generate_invite_link()
    settings.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(settings)

    return {"success": True, "invite_link": settings.invite_link}


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a group (Founder only)"""
    result = await db.execute(
        select(Conversation).where(Conversation.id == group_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    # Verify user is founder
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == current_user.id,
                ConversationParticipant.role == GroupRole.FOUNDER.value,
            )
        )
    )
    if not participant_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Founder can delete group"
        )

    # Delete settings
    await db.execute(
        delete(GroupSettings).where(GroupSettings.conversation_id == group_id)
    )

    # Delete events and attendees
    events_result = await db.execute(
        select(GroupEvent).where(GroupEvent.conversation_id == group_id)
    )
    for event in events_result.scalars().all():
        await db.execute(
            delete(GroupEventAttendee).where(GroupEventAttendee.event_id == event.id)
        )
        await db.delete(event)

    # Delete all messages in the group
    await db.execute(
        delete(Message).where(Message.conversation_id == group_id)
    )

    # Delete participants
    await db.execute(
        delete(ConversationParticipant).where(
            ConversationParticipant.conversation_id == group_id
        )
    )

    # Notify members via Socket.IO before deleting
    try:
        from ..services.socket_manager import emit_to_conversation
        await emit_to_conversation(
            group_id,
            "group:deleted",
            {"group_id": group_id, "message": "This group has been deleted by the founder"}
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to broadcast group deletion: {e}")

    # Delete conversation
    await db.delete(conversation)
    await db.commit()

    return {"success": True, "message": "Group deleted"}


# ============== Member Management Endpoints ==============

@router.get("/{group_id}/members", response_model=List[GroupMemberResponse])
async def get_members(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get group members"""
    return await _get_group_members(db, group_id)


@router.post("/{group_id}/members")
async def add_members(
    group_id: str,
    request: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add members to group (Founder, Recruiter, or if allowed)"""
    user_ids = request.get("user_ids", [])

    # Get current user's role
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == current_user.id,
            )
        )
    )
    participant = participant_result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )

    # Check permissions
    settings = await _get_or_create_group_settings(db, group_id)
    if not can_manage_members(participant.role) and not settings.allow_member_invites:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to add members"
        )

    added = []
    for user_id in user_ids:
        # Check if already a member
        existing_result = await db.execute(
            select(ConversationParticipant).where(
                and_(
                    ConversationParticipant.conversation_id == group_id,
                    ConversationParticipant.user_id == user_id,
                )
            )
        )
        if not existing_result.scalar_one_or_none():
            new_participant = ConversationParticipant(
                id=str(uuid.uuid4()),
                conversation_id=group_id,
                user_id=user_id,
                role=GroupRole.MEMBER.value,
            )
            db.add(new_participant)
            added.append(user_id)

    await db.commit()

    return {"success": True, "added": len(added)}


@router.delete("/{group_id}/members/{user_id}")
async def remove_member(
    group_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a member from group (Founder, Moderator, or self)"""
    # Get current user's role
    current_participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == current_user.id,
            )
        )
    )
    current_participant = current_participant_result.scalar_one_or_none()

    if not current_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )

    # Check permissions (can remove self, or must be Founder/Moderator)
    if user_id != current_user.id and not can_manage_members(current_participant.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Founder and Moderator can remove members"
        )

    # Get member to remove
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == user_id,
            )
        )
    )
    participant = participant_result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )

    # Cannot remove founder
    if participant.role == GroupRole.FOUNDER.value and user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot remove the Founder"
        )

    await db.delete(participant)
    await db.commit()

    return {"success": True, "message": "Member removed"}


@router.put("/{group_id}/members/{user_id}/role")
async def update_member_role(
    group_id: str,
    user_id: str,
    request: RoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update member role (Founder only can assign co-founder roles)"""
    # Verify current user is founder
    founder_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == current_user.id,
                ConversationParticipant.role == GroupRole.FOUNDER.value,
            )
        )
    )
    if not founder_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Founder can assign roles"
        )

    # Cannot change founder role
    if request.role == GroupRole.FOUNDER.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign Founder role. Transfer ownership instead."
        )

    # Get member
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == user_id,
            )
        )
    )
    participant = participant_result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )

    # Cannot demote founder
    if participant.role == GroupRole.FOUNDER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change Founder's role"
        )

    # Validate role
    valid_roles = [r.value for r in GroupRole if r.value != GroupRole.FOUNDER.value]
    if request.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Valid roles: {', '.join(valid_roles)}"
        )

    participant.role = request.role
    await db.commit()

    return {
        "success": True,
        "message": f"Role updated to {get_role_display(request.role)}",
        "role": request.role,
        "role_display": get_role_display(request.role),
    }


@router.post("/{group_id}/leave")
async def leave_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Leave a group"""
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == current_user.id,
            )
        )
    )
    participant = participant_result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not a member of this group"
        )

    # Founder cannot leave without transferring ownership
    if participant.role == GroupRole.FOUNDER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Founder cannot leave. Transfer ownership or delete the group."
        )

    # Get user display name for system message
    user_display_name = current_user.display_name or current_user.phone_number

    await db.delete(participant)

    # Create system message for member leaving
    system_message = Message(
        conversation_id=group_id,
        sender_id=current_user.id,
        content=f"{user_display_name} left the group",
        message_type=MessageType.SYSTEM,
    )
    db.add(system_message)
    await db.commit()
    await db.refresh(system_message)

    # Broadcast system message to group via socket
    try:
        from ..services.socket_manager import emit_to_conversation
        await emit_to_conversation(
            group_id,
            "message:received",
            system_message.to_dict()
        )
    except Exception as e:
        # Log but don't fail if socket broadcast fails
        import logging
        logging.getLogger(__name__).error(f"Failed to broadcast leave message: {e}")

    return {"success": True, "message": "Left group"}


@router.post("/{group_id}/transfer-ownership")
async def transfer_ownership(
    group_id: str,
    request: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transfer founder ownership to another member"""
    new_founder_id = request.get("new_founder_id")

    if not new_founder_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="new_founder_id is required"
        )

    # Verify current user is founder
    current_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == current_user.id,
                ConversationParticipant.role == GroupRole.FOUNDER.value,
            )
        )
    )
    current_participant = current_result.scalar_one_or_none()

    if not current_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Founder can transfer ownership"
        )

    # Get new founder
    new_founder_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == new_founder_id,
            )
        )
    )
    new_founder_participant = new_founder_result.scalar_one_or_none()

    if not new_founder_participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this group"
        )

    # Transfer ownership
    current_participant.role = GroupRole.MEMBER.value
    new_founder_participant.role = GroupRole.FOUNDER.value

    # Update conversation created_by
    result = await db.execute(
        select(Conversation).where(Conversation.id == group_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation:
        conversation.created_by = new_founder_id

    await db.commit()

    return {"success": True, "message": "Ownership transferred"}


# ============== Event Endpoints ==============

@router.get("/{group_id}/events", response_model=List[EventResponse])
async def get_events(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get group events"""
    result = await db.execute(
        select(GroupEvent).where(
            GroupEvent.conversation_id == group_id
        ).order_by(GroupEvent.start_time.asc())
    )
    events = result.scalars().all()

    response = []
    for event in events:
        # Get creator name
        creator_result = await db.execute(
            select(User).where(User.id == event.created_by)
        )
        creator = creator_result.scalar_one_or_none()

        response.append(EventResponse(
            id=event.id,
            title=event.title,
            description=event.description,
            location=event.location,
            start_time=event.start_time.isoformat() if event.start_time else "",
            end_time=event.end_time.isoformat() if event.end_time else None,
            is_online=event.is_online,
            meeting_link=event.meeting_link,
            max_attendees=event.max_attendees,
            attendees_count=len(event.attendees) if event.attendees else 0,
            created_by=event.created_by,
            creator_name=creator.display_name if creator else None,
            created_at=event.created_at.isoformat() if event.created_at else "",
        ))

    return response


@router.post("/{group_id}/events", response_model=EventResponse)
async def create_event(
    group_id: str,
    request: EventCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a group event (Founder and Co-founders only)"""
    # Check permission
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == current_user.id,
            )
        )
    )
    participant = participant_result.scalar_one_or_none()

    if not participant or not can_manage_events(participant.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Founder and Co-founders can create events"
        )

    event = GroupEvent(
        id=str(uuid.uuid4()),
        conversation_id=group_id,
        created_by=current_user.id,
        title=request.title,
        description=request.description,
        location=request.location,
        start_time=datetime.fromisoformat(request.start_time.replace('Z', '+00:00')),
        end_time=datetime.fromisoformat(request.end_time.replace('Z', '+00:00')) if request.end_time else None,
        is_online=request.is_online,
        meeting_link=request.meeting_link,
        max_attendees=request.max_attendees,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    return EventResponse(
        id=event.id,
        title=event.title,
        description=event.description,
        location=event.location,
        start_time=event.start_time.isoformat() if event.start_time else "",
        end_time=event.end_time.isoformat() if event.end_time else None,
        is_online=event.is_online,
        meeting_link=event.meeting_link,
        max_attendees=event.max_attendees,
        attendees_count=0,
        created_by=event.created_by,
        creator_name=current_user.display_name,
        created_at=event.created_at.isoformat() if event.created_at else "",
    )


@router.delete("/{group_id}/events/{event_id}")
async def delete_event(
    group_id: str,
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an event (creator or Founder only)"""
    event_result = await db.execute(
        select(GroupEvent).where(
            and_(
                GroupEvent.id == event_id,
                GroupEvent.conversation_id == group_id,
            )
        )
    )
    event = event_result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    # Check permission
    if event.created_by != current_user.id:
        participant_result = await db.execute(
            select(ConversationParticipant).where(
                and_(
                    ConversationParticipant.conversation_id == group_id,
                    ConversationParticipant.user_id == current_user.id,
                    ConversationParticipant.role == GroupRole.FOUNDER.value,
                )
            )
        )
        if not participant_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only event creator or Founder can delete events"
            )

    # Delete attendees
    await db.execute(
        delete(GroupEventAttendee).where(GroupEventAttendee.event_id == event_id)
    )

    await db.delete(event)
    await db.commit()

    return {"success": True, "message": "Event deleted"}


@router.post("/{group_id}/events/{event_id}/attend")
async def attend_event(
    group_id: str,
    event_id: str,
    request: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """RSVP to an event"""
    rsvp_status = request.get("status", "going")  # going, maybe, not_going

    # Verify user is member
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == group_id,
                ConversationParticipant.user_id == current_user.id,
            )
        )
    )
    if not participant_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )

    # Check if already attending
    existing_result = await db.execute(
        select(GroupEventAttendee).where(
            and_(
                GroupEventAttendee.event_id == event_id,
                GroupEventAttendee.user_id == current_user.id,
            )
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.status = rsvp_status
    else:
        attendee = GroupEventAttendee(
            id=str(uuid.uuid4()),
            event_id=event_id,
            user_id=current_user.id,
            status=rsvp_status,
        )
        db.add(attendee)

    await db.commit()

    return {"success": True, "status": rsvp_status}


# ============== Invite Link Endpoints ==============

@router.get("/join/{invite_code}")
async def get_group_by_invite(
    invite_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get group info by invite code"""
    result = await db.execute(
        select(GroupSettings).where(
            and_(
                GroupSettings.invite_link == invite_code,
                GroupSettings.invite_link_enabled == True,
            )
        )
    )
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or disabled invite link"
        )

    return await get_group(settings.conversation_id, db, current_user)


@router.post("/join/{invite_code}")
async def join_group_by_invite(
    invite_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Join a group using invite link"""
    result = await db.execute(
        select(GroupSettings).where(
            and_(
                GroupSettings.invite_link == invite_code,
                GroupSettings.invite_link_enabled == True,
            )
        )
    )
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or disabled invite link"
        )

    # Check if already a member
    existing_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == settings.conversation_id,
                ConversationParticipant.user_id == current_user.id,
            )
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already a member of this group"
        )

    # Add as member
    participant = ConversationParticipant(
        id=str(uuid.uuid4()),
        conversation_id=settings.conversation_id,
        user_id=current_user.id,
        role=GroupRole.MEMBER.value,
    )
    db.add(participant)
    await db.commit()

    return {"success": True, "group_id": settings.conversation_id, "message": "Joined group"}
