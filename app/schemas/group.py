from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
from uuid import UUID

from app.models.group import GroupMemberRole


# Group schemas
class GroupCreate(BaseModel):
    """Schema for creating a group"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    member_ids: List[UUID] = Field(..., min_items=1)
    is_public: bool = False
    allow_member_invites: bool = True
    require_admin_approval: bool = False


class GroupUpdate(BaseModel):
    """Schema for updating a group"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    is_public: Optional[bool] = None
    allow_member_invites: Optional[bool] = None
    require_admin_approval: Optional[bool] = None


class GroupMemberAdd(BaseModel):
    """Schema for adding members to a group"""
    user_ids: List[UUID] = Field(..., min_items=1)


class GroupMemberRemove(BaseModel):
    """Schema for removing a member from a group"""
    user_id: UUID


class GroupMemberRoleUpdate(BaseModel):
    """Schema for updating member role"""
    role: GroupMemberRole
    permissions: Optional[Dict[str, bool]] = None


class GroupMemberResponse(BaseModel):
    """Schema for group member response"""
    user_id: UUID
    display_name: str
    avatar_url: Optional[str] = None
    role: GroupMemberRole
    permissions: Optional[Dict[str, bool]] = None
    joined_at: datetime

    class Config:
        from_attributes = True


class GroupResponse(BaseModel):
    """Schema for group response"""
    id: UUID
    conversation_id: UUID
    name: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    created_by: UUID
    is_public: bool
    allow_member_invites: bool
    require_admin_approval: bool
    members: List[GroupMemberResponse]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GroupListResponse(BaseModel):
    """Schema for group list response"""
    groups: List[GroupResponse]
    total: int
