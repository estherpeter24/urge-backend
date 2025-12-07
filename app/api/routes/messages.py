from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime
from uuid import UUID
from typing import Optional

from app.db.database import get_db
from app.schemas.message import (
    MessageCreate,
    MessageUpdate,
    MessageForward,
    MessageResponse,
    MessageListResponse,
    MessageSearchResponse
)
from app.schemas.auth import SuccessResponse
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.message import Message, StarredMessage, MessageStatus
from app.models.conversation import Conversation, ConversationParticipant

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.post("", response_model=MessageResponse)
async def send_message(
    message_data: MessageCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Send a new message"""
    # Check if conversation exists and user is participant
    conversation = db.query(Conversation).filter(
        Conversation.id == message_data.conversation_id
    ).first()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    # Check if user is participant
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == message_data.conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    # Create message
    new_message = Message(
        conversation_id=message_data.conversation_id,
        sender_id=current_user.id,
        content=message_data.content,
        message_type=message_data.message_type,
        status=MessageStatus.SENT,
        media_url=message_data.media_url,
        thumbnail_url=message_data.thumbnail_url,
        audio_duration=message_data.audio_duration,
        reply_to_id=message_data.reply_to_id,
        is_encrypted=message_data.is_encrypted
    )

    db.add(new_message)
    db.flush()  # Flush to generate the ID before updating conversation

    # Update conversation last message
    conversation.last_message_id = new_message.id
    conversation.last_message_at = datetime.utcnow()

    # Increment unread count for all participants except sender
    db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == message_data.conversation_id,
        ConversationParticipant.user_id != current_user.id
    ).update({"unread_count": ConversationParticipant.unread_count + 1})

    db.commit()
    db.refresh(new_message)

    # Build response
    response = MessageResponse(
        id=new_message.id,
        conversation_id=new_message.conversation_id,
        sender_id=new_message.sender_id,
        sender_name=current_user.display_name,
        sender_avatar=current_user.avatar_url,
        content=new_message.content,
        message_type=new_message.message_type,
        status=new_message.status,
        media_url=new_message.media_url,
        thumbnail_url=new_message.thumbnail_url,
        audio_duration=new_message.audio_duration,
        reply_to=None,  # TODO: Implement reply_to lookup
        is_encrypted=new_message.is_encrypted,
        created_at=new_message.created_at,
        updated_at=new_message.updated_at,
        deleted_at=new_message.deleted_at
    )

    return response


@router.put("/{message_id}", response_model=MessageResponse)
async def edit_message(
    message_id: UUID,
    message_data: MessageUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Edit a message"""
    message = db.query(Message).filter(Message.id == message_id).first()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    # Check if user is the sender
    if message.sender_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own messages"
        )

    # Update message
    message.content = message_data.content
    message.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(message)

    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        sender_name=current_user.display_name,
        sender_avatar=current_user.avatar_url,
        content=message.content,
        message_type=message.message_type,
        status=message.status,
        media_url=message.media_url,
        thumbnail_url=message.thumbnail_url,
        audio_duration=message.audio_duration,
        reply_to=None,
        is_encrypted=message.is_encrypted,
        created_at=message.created_at,
        updated_at=message.updated_at,
        deleted_at=message.deleted_at
    )


@router.delete("/{message_id}", response_model=SuccessResponse)
async def delete_message(
    message_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a message"""
    message = db.query(Message).filter(Message.id == message_id).first()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    # Check if user is the sender
    if message.sender_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own messages"
        )

    # Soft delete
    message.deleted_at = datetime.utcnow()
    db.commit()

    return SuccessResponse(success=True, message="Message deleted successfully")


@router.post("/forward", response_model=SuccessResponse)
async def forward_messages(
    forward_data: MessageForward,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Forward messages to another conversation"""
    # Check if destination conversation exists and user is participant
    conversation = db.query(Conversation).filter(
        Conversation.id == forward_data.conversation_id
    ).first()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Destination conversation not found"
        )

    # Check if user is participant
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == forward_data.conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in the destination conversation"
        )

    # Forward each message
    for message_id in forward_data.message_ids:
        original_message = db.query(Message).filter(Message.id == message_id).first()

        if original_message:
            new_message = Message(
                conversation_id=forward_data.conversation_id,
                sender_id=current_user.id,
                content=original_message.content,
                message_type=original_message.message_type,
                status=MessageStatus.SENT,
                media_url=original_message.media_url,
                thumbnail_url=original_message.thumbnail_url,
                audio_duration=original_message.audio_duration,
                is_encrypted=original_message.is_encrypted
            )
            db.add(new_message)

    # Update conversation last message
    conversation.last_message_at = datetime.utcnow()

    db.commit()

    return SuccessResponse(success=True, message="Messages forwarded successfully")


@router.post("/{message_id}/star", response_model=SuccessResponse)
async def star_message(
    message_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Star a message"""
    message = db.query(Message).filter(Message.id == message_id).first()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    # Check if already starred
    existing = db.query(StarredMessage).filter(
        StarredMessage.user_id == current_user.id,
        StarredMessage.message_id == message_id
    ).first()

    if existing:
        return SuccessResponse(success=True, message="Message already starred")

    # Star the message
    starred = StarredMessage(
        user_id=current_user.id,
        message_id=message_id
    )
    db.add(starred)
    db.commit()

    return SuccessResponse(success=True, message="Message starred successfully")


@router.delete("/{message_id}/star", response_model=SuccessResponse)
async def unstar_message(
    message_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Unstar a message"""
    starred = db.query(StarredMessage).filter(
        StarredMessage.user_id == current_user.id,
        StarredMessage.message_id == message_id
    ).first()

    if not starred:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Starred message not found"
        )

    db.delete(starred)
    db.commit()

    return SuccessResponse(success=True, message="Message unstarred successfully")


@router.get("/starred", response_model=MessageSearchResponse)
async def get_starred_messages(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all starred messages"""
    starred_messages = db.query(Message).join(StarredMessage).filter(
        StarredMessage.user_id == current_user.id
    ).all()

    messages = []
    for msg in starred_messages:
        sender = db.query(User).filter(User.id == msg.sender_id).first()
        messages.append(MessageResponse(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            sender_name=sender.display_name if sender else "Unknown",
            sender_avatar=sender.avatar_url if sender else None,
            content=msg.content,
            message_type=msg.message_type,
            status=msg.status,
            media_url=msg.media_url,
            thumbnail_url=msg.thumbnail_url,
            audio_duration=msg.audio_duration,
            reply_to=None,
            is_encrypted=msg.is_encrypted,
            created_at=msg.created_at,
            updated_at=msg.updated_at,
            deleted_at=msg.deleted_at
        ))

    return MessageSearchResponse(
        messages=messages,
        total=len(messages)
    )


@router.get("/search", response_model=MessageSearchResponse)
async def search_messages(
    q: str = Query(..., min_length=1),
    conversation_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Search messages"""
    query = db.query(Message).join(ConversationParticipant).filter(
        ConversationParticipant.user_id == current_user.id,
        Message.content.ilike(f"%{q}%"),
        Message.deleted_at.is_(None)
    )

    if conversation_id:
        query = query.filter(Message.conversation_id == conversation_id)

    messages_result = query.all()

    messages = []
    for msg in messages_result:
        sender = db.query(User).filter(User.id == msg.sender_id).first()
        messages.append(MessageResponse(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            sender_name=sender.display_name if sender else "Unknown",
            sender_avatar=sender.avatar_url if sender else None,
            content=msg.content,
            message_type=msg.message_type,
            status=msg.status,
            media_url=msg.media_url,
            thumbnail_url=msg.thumbnail_url,
            audio_duration=msg.audio_duration,
            reply_to=None,
            is_encrypted=msg.is_encrypted,
            created_at=msg.created_at,
            updated_at=msg.updated_at,
            deleted_at=msg.deleted_at
        ))

    return MessageSearchResponse(
        messages=messages,
        total=len(messages)
    )
