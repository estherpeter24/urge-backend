from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

from app.models.conversation import ConversationType
from app.schemas.message import MessageResponse


# Participant info schema
class ParticipantInfo(BaseModel):
    """Schema for participant information"""
    id: UUID
    display_name: str
    avatar_url: Optional[str] = None
    is_online: bool = False

    class Config:
        from_attributes = True
        populate_by_name = True


# Conversation schemas
class ConversationCreate(BaseModel):
    """Schema for creating a conversation"""
    type: ConversationType
    participant_ids: List[UUID] = Field(..., min_items=1)
    name: Optional[str] = None
    avatar_url: Optional[str] = None


class ConversationUpdate(BaseModel):
    """Schema for updating a conversation"""
    name: Optional[str] = None
    avatar_url: Optional[str] = None


class ConversationResponse(BaseModel):
    """Schema for conversation response"""
    id: UUID
    type: ConversationType
    name: Optional[str] = None
    avatar: Optional[str] = None
    participants: List[ParticipantInfo]
    last_message: Optional[MessageResponse] = Field(None, alias="lastMessage")
    unread_count: int = Field(0, alias="unreadCount")
    is_typing: bool = Field(False, alias="isTyping")
    typing_users: List[str] = Field([], alias="typingUsers")
    is_favorite: bool = Field(False, alias="isFavourite")
    is_muted: bool = Field(False, alias="isMuted")
    is_archived: bool = Field(False, alias="isArchived")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class ConversationListResponse(BaseModel):
    """Schema for conversation list response"""
    conversations: List[ConversationResponse]
    total: int
    limit: int
    offset: int


class TypingIndicator(BaseModel):
    """Schema for typing indicator"""
    conversation_id: UUID
    user_id: UUID
    is_typing: bool
