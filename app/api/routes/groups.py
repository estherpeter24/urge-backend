from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.database import get_db
from app.schemas.group import (
    GroupCreate,
    GroupUpdate,
    GroupMemberAdd,
    GroupMemberRoleUpdate,
    GroupResponse,
    GroupMemberResponse
)
from app.schemas.auth import SuccessResponse
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.group import Group, GroupMember, GroupMemberRole
from app.models.conversation import Conversation, ConversationParticipant, ConversationType

router = APIRouter(prefix="/groups", tags=["Groups"])


@router.post("", response_model=GroupResponse)
async def create_group(
    group_data: GroupCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new group"""
    # Create conversation first
    conversation = Conversation(
        type=ConversationType.GROUP,
        name=group_data.name,
        avatar_url=group_data.avatar_url
    )
    db.add(conversation)
    db.flush()

    # Create group
    new_group = Group(
        conversation_id=conversation.id,
        description=group_data.description,
        created_by=current_user.id,
        is_public=group_data.is_public,
        allow_member_invites=group_data.allow_member_invites,
        require_admin_approval=group_data.require_admin_approval
    )
    db.add(new_group)
    db.flush()

    # Add creator as admin
    creator_member = GroupMember(
        group_id=new_group.id,
        user_id=current_user.id,
        role=GroupMemberRole.ADMIN
    )
    db.add(creator_member)

    # Add creator to conversation participants
    creator_participant = ConversationParticipant(
        conversation_id=conversation.id,
        user_id=current_user.id
    )
    db.add(creator_participant)

    # Add other members
    for member_id in group_data.member_ids:
        if member_id != current_user.id:
            member = GroupMember(
                group_id=new_group.id,
                user_id=member_id,
                role=GroupMemberRole.MEMBER
            )
            db.add(member)

            participant = ConversationParticipant(
                conversation_id=conversation.id,
                user_id=member_id
            )
            db.add(participant)

    db.commit()
    db.refresh(new_group)

    # Build response
    members = db.query(GroupMember).filter(GroupMember.group_id == new_group.id).all()
    member_responses = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        member_responses.append(GroupMemberResponse(
            user_id=m.user_id,
            display_name=user.display_name if user else "Unknown",
            avatar_url=user.avatar_url if user else None,
            role=m.role,
            permissions=m.permissions,
            joined_at=m.joined_at
        ))

    return GroupResponse(
        id=new_group.id,
        conversation_id=new_group.conversation_id,
        name=group_data.name,
        description=new_group.description,
        avatar_url=group_data.avatar_url,
        created_by=new_group.created_by,
        is_public=new_group.is_public,
        allow_member_invites=new_group.allow_member_invites,
        require_admin_approval=new_group.require_admin_approval,
        members=member_responses,
        created_at=new_group.created_at,
        updated_at=new_group.updated_at
    )


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get group details"""
    group = db.query(Group).filter(Group.id == group_id).first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    # Check if user is member
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )

    # Get conversation
    conversation = db.query(Conversation).filter(Conversation.id == group.conversation_id).first()

    # Get all members
    members = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
    member_responses = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        member_responses.append(GroupMemberResponse(
            user_id=m.user_id,
            display_name=user.display_name if user else "Unknown",
            avatar_url=user.avatar_url if user else None,
            role=m.role,
            permissions=m.permissions,
            joined_at=m.joined_at
        ))

    return GroupResponse(
        id=group.id,
        conversation_id=group.conversation_id,
        name=conversation.name if conversation else None,
        description=group.description,
        avatar_url=conversation.avatar_url if conversation else None,
        created_by=group.created_by,
        is_public=group.is_public,
        allow_member_invites=group.allow_member_invites,
        require_admin_approval=group.require_admin_approval,
        members=member_responses,
        created_at=group.created_at,
        updated_at=group.updated_at
    )


@router.put("/{group_id}", response_model=SuccessResponse)
async def update_group(
    group_id: UUID,
    group_data: GroupUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update group information"""
    group = db.query(Group).filter(Group.id == group_id).first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    # Check if user is admin
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).first()

    if not member or member.role != GroupMemberRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update group information"
        )

    # Update group
    if group_data.description is not None:
        group.description = group_data.description
    if group_data.is_public is not None:
        group.is_public = group_data.is_public
    if group_data.allow_member_invites is not None:
        group.allow_member_invites = group_data.allow_member_invites
    if group_data.require_admin_approval is not None:
        group.require_admin_approval = group_data.require_admin_approval

    # Update conversation
    conversation = db.query(Conversation).filter(Conversation.id == group.conversation_id).first()
    if conversation:
        if group_data.name is not None:
            conversation.name = group_data.name
        if group_data.avatar_url is not None:
            conversation.avatar_url = group_data.avatar_url

    db.commit()

    return SuccessResponse(success=True, message="Group updated successfully")


@router.delete("/{group_id}", response_model=SuccessResponse)
async def delete_group(
    group_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a group"""
    group = db.query(Group).filter(Group.id == group_id).first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    # Check if user is creator or admin
    if group.created_by != current_user.id:
        member = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id == current_user.id
        ).first()

        if not member or member.role != GroupMemberRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the creator or admins can delete the group"
            )

    # Delete conversation (cascade will handle group and members)
    conversation = db.query(Conversation).filter(Conversation.id == group.conversation_id).first()
    if conversation:
        db.delete(conversation)

    db.commit()

    return SuccessResponse(success=True, message="Group deleted successfully")


@router.post("/{group_id}/members", response_model=SuccessResponse)
async def add_members(
    group_id: UUID,
    member_data: GroupMemberAdd,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Add members to a group"""
    group = db.query(Group).filter(Group.id == group_id).first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    # Check permissions
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )

    if member.role != GroupMemberRole.ADMIN and not group.allow_member_invites:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can add members to this group"
        )

    # Add members
    for user_id in member_data.user_ids:
        # Check if already a member
        existing = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id
        ).first()

        if not existing:
            new_member = GroupMember(
                group_id=group_id,
                user_id=user_id,
                role=GroupMemberRole.MEMBER
            )
            db.add(new_member)

            # Add to conversation participants
            participant = ConversationParticipant(
                conversation_id=group.conversation_id,
                user_id=user_id
            )
            db.add(participant)

    db.commit()

    return SuccessResponse(success=True, message="Members added successfully")


@router.delete("/{group_id}/members/{user_id}", response_model=SuccessResponse)
async def remove_member(
    group_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Remove a member from a group"""
    group = db.query(Group).filter(Group.id == group_id).first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    # Check if current user is admin
    current_member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).first()

    if not current_member or current_member.role != GroupMemberRole.ADMIN:
        # Allow users to remove themselves
        if user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can remove members"
            )

    # Remove member
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id
    ).first()

    if member:
        db.delete(member)

        # Remove from conversation participants
        participant = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == group.conversation_id,
            ConversationParticipant.user_id == user_id
        ).first()

        if participant:
            db.delete(participant)

    db.commit()

    return SuccessResponse(success=True, message="Member removed successfully")


@router.put("/{group_id}/members/{user_id}/role", response_model=SuccessResponse)
async def update_member_role(
    group_id: UUID,
    user_id: UUID,
    role_data: GroupMemberRoleUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update member role in a group"""
    group = db.query(Group).filter(Group.id == group_id).first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    # Check if current user is admin
    current_member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).first()

    if not current_member or current_member.role != GroupMemberRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update member roles"
        )

    # Update member role
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )

    member.role = role_data.role
    if role_data.permissions:
        member.permissions = role_data.permissions

    db.commit()

    return SuccessResponse(success=True, message="Member role updated successfully")


@router.post("/{group_id}/leave", response_model=SuccessResponse)
async def leave_group(
    group_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Leave a group"""
    group = db.query(Group).filter(Group.id == group_id).first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    # Check if user is the creator
    if group.created_by == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group creator cannot leave. Transfer ownership or delete the group."
        )

    # Remove member
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).first()

    if member:
        db.delete(member)

        # Update conversation participant
        participant = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == group.conversation_id,
            ConversationParticipant.user_id == current_user.id
        ).first()

        if participant:
            from datetime import datetime
            participant.left_at = datetime.utcnow()

    db.commit()

    return SuccessResponse(success=True, message="You have left the group")


@router.get("/{group_id}/members", response_model=list[GroupMemberResponse])
async def get_group_members(
    group_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all members of a group"""
    group = db.query(Group).filter(Group.id == group_id).first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    # Check if user is member
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )

    # Get all members
    members = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
    member_responses = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        member_responses.append(GroupMemberResponse(
            user_id=m.user_id,
            display_name=user.display_name if user else "Unknown",
            avatar_url=user.avatar_url if user else None,
            role=m.role,
            permissions=m.permissions,
            joined_at=m.joined_at
        ))

    return member_responses
