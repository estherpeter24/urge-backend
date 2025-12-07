from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID

from app.models.message import MessageType, MessageStatus


# Message schemas
class MessageCreate(BaseModel):
    """Schema for creating a message"""
    conversation_id: UUID
    content: str = Field(..., min_length=1)
    message_type: MessageType = MessageType.TEXT
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    audio_duration: Optional[int] = None
    reply_to_id: Optional[UUID] = None
    is_encrypted: bool = False


class MessageUpdate(BaseModel):
    """Schema for updating a message"""
    content: str = Field(..., min_length=1)


class MessageForward(BaseModel):
    """Schema for forwarding messages"""
    message_ids: list[UUID] = Field(..., min_items=1)
    conversation_id: UUID


class ReplyToMessage(BaseModel):
    """Schema for reply to message info"""
    id: UUID
    sender_name: str
    content: str

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Schema for message response"""
    id: UUID
    conversation_id: UUID = Field(alias="conversationId")
    sender_id: UUID = Field(alias="senderId")
    sender_name: str = Field(alias="senderName")
    sender_avatar: Optional[str] = Field(None, alias="senderAvatar")
    content: str
    message_type: MessageType = Field(alias="messageType")
    status: MessageStatus
    media_url: Optional[str] = Field(None, alias="mediaUrl")
    thumbnail_url: Optional[str] = Field(None, alias="thumbnailUrl")
    audio_duration: Optional[int] = Field(None, alias="audioDuration")
    reply_to: Optional[ReplyToMessage] = Field(None, alias="replyTo")
    is_encrypted: bool = Field(alias="isEncrypted")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    deleted_at: Optional[datetime] = Field(None, alias="deletedAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class MessageListResponse(BaseModel):
    """Schema for message list response"""
    messages: list[MessageResponse]
    total: int
    limit: int
    has_more: bool


class MessageSearchResponse(BaseModel):
    """Schema for message search response"""
    messages: list[MessageResponse]
    total: int

    class Config:
        from_attributes = True
