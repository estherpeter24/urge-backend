from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime
from uuid import UUID
from typing import Optional

from app.db.database import get_db
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationListResponse,
    ParticipantInfo
)
from app.schemas.message import MessageResponse, MessageListResponse
from app.schemas.auth import SuccessResponse
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.conversation import Conversation, ConversationParticipant, ConversationType
from app.models.message import Message, StarredMessage

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get("", response_model=ConversationListResponse, response_model_by_alias=True)
async def get_conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all user conversations (excluding archived)"""
    # Get conversations where user is participant and not archived
    query = db.query(Conversation).join(ConversationParticipant).filter(
        ConversationParticipant.user_id == current_user.id,
        ConversationParticipant.left_at.is_(None),
        ConversationParticipant.is_archived == False
    ).order_by(Conversation.last_message_at.desc())

    total = query.count()
    conversations = query.offset(offset).limit(limit).all()

    conversation_responses = []
    for conv in conversations:
        # Get participant
        participant = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conv.id,
            ConversationParticipant.user_id == current_user.id
        ).first()

        # Get last message
        last_message = None
        if conv.last_message_id:
            msg = db.query(Message).filter(Message.id == conv.last_message_id).first()
            if msg:
                sender = db.query(User).filter(User.id == msg.sender_id).first()
                last_message = MessageResponse(
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
                )

        # Get participant details
        participant_records = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conv.id
        ).all()

        participant_infos = []
        for p in participant_records:
            user = db.query(User).filter(User.id == p.user_id).first()
            if user:
                participant_infos.append(ParticipantInfo(
                    id=user.id,
                    display_name=user.display_name,
                    avatar_url=user.avatar_url,
                    is_online=user.is_online
                ))

        conversation_responses.append(ConversationResponse(
            id=conv.id,
            type=conv.type,
            name=conv.name,
            avatar=conv.avatar_url,
            participants=participant_infos,
            last_message=last_message,
            unread_count=participant.unread_count if participant else 0,
            is_typing=False,
            typing_users=[],
            is_favorite=participant.is_favorite if participant else False,
            is_muted=participant.is_muted if participant else False,
            is_archived=participant.is_archived if participant else False,
            created_at=conv.created_at,
            updated_at=conv.updated_at
        ))

    return ConversationListResponse(
        conversations=conversation_responses,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/archived", response_model=ConversationListResponse, response_model_by_alias=True)
async def get_archived_conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all archived conversations"""
    # Get archived conversations where user is participant
    query = db.query(Conversation).join(ConversationParticipant).filter(
        ConversationParticipant.user_id == current_user.id,
        ConversationParticipant.left_at.is_(None),
        ConversationParticipant.is_archived == True
    ).order_by(Conversation.last_message_at.desc())

    total = query.count()
    conversations = query.offset(offset).limit(limit).all()

    conversation_responses = []
    for conv in conversations:
        # Get participant
        participant = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conv.id,
            ConversationParticipant.user_id == current_user.id
        ).first()

        # Get last message
        last_message = None
        if conv.last_message_id:
            msg = db.query(Message).filter(Message.id == conv.last_message_id).first()
            if msg:
                sender = db.query(User).filter(User.id == msg.sender_id).first()
                last_message = MessageResponse(
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
                )

        # Get participant details
        participant_records = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conv.id
        ).all()

        participant_infos = []
        for p in participant_records:
            user = db.query(User).filter(User.id == p.user_id).first()
            if user:
                participant_infos.append(ParticipantInfo(
                    id=user.id,
                    display_name=user.display_name,
                    avatar_url=user.avatar_url,
                    is_online=user.is_online
                ))

        conversation_responses.append(ConversationResponse(
            id=conv.id,
            type=conv.type,
            name=conv.name,
            avatar=conv.avatar_url,
            participants=participant_infos,
            last_message=last_message,
            unread_count=participant.unread_count if participant else 0,
            is_typing=False,
            typing_users=[],
            is_favorite=participant.is_favorite if participant else False,
            is_muted=participant.is_muted if participant else False,
            is_archived=participant.is_archived if participant else True,
            created_at=conv.created_at,
            updated_at=conv.updated_at
        ))

    return ConversationListResponse(
        conversations=conversation_responses,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get conversation details"""
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    # Check if user is participant
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    # Get last message (similar to get_conversations)
    last_message = None
    if conversation.last_message_id:
        msg = db.query(Message).filter(Message.id == conversation.last_message_id).first()
        if msg:
            sender = db.query(User).filter(User.id == msg.sender_id).first()
            last_message = MessageResponse(
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
            )

    # Get participant details
    participant_records = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id
    ).all()

    participant_infos = []
    for p in participant_records:
        user = db.query(User).filter(User.id == p.user_id).first()
        if user:
            participant_infos.append(ParticipantInfo(
                id=user.id,
                display_name=user.display_name,
                avatar_url=user.avatar_url,
                is_online=user.is_online
            ))

    return ConversationResponse(
        id=conversation.id,
        type=conversation.type,
        name=conversation.name,
        avatar=conversation.avatar_url,
        participants=participant_infos,
        last_message=last_message,
        unread_count=participant.unread_count,
        is_typing=False,
        typing_users=[],
        is_favorite=participant.is_favorite,
        is_muted=participant.is_muted,
        is_archived=participant.is_archived,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at
    )


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    conversation_data: ConversationCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new conversation"""
    # Create conversation
    new_conversation = Conversation(
        type=conversation_data.type,
        name=conversation_data.name,
        avatar_url=conversation_data.avatar_url
    )

    db.add(new_conversation)
    db.flush()

    # Add current user as participant
    if current_user.id not in conversation_data.participant_ids:
        conversation_data.participant_ids.append(current_user.id)

    # Add all participants
    for participant_id in conversation_data.participant_ids:
        participant = ConversationParticipant(
            conversation_id=new_conversation.id,
            user_id=participant_id
        )
        db.add(participant)

    db.commit()
    db.refresh(new_conversation)

    # Get participant details
    participant_infos = []
    for participant_id in conversation_data.participant_ids:
        user = db.query(User).filter(User.id == participant_id).first()
        if user:
            participant_infos.append(ParticipantInfo(
                id=user.id,
                display_name=user.display_name,
                avatar_url=user.avatar_url,
                is_online=user.is_online
            ))

    return ConversationResponse(
        id=new_conversation.id,
        type=new_conversation.type,
        name=new_conversation.name,
        avatar=new_conversation.avatar_url,
        participants=participant_infos,
        last_message=None,
        unread_count=0,
        is_typing=False,
        typing_users=[],
        is_favorite=False,
        is_muted=False,
        is_archived=False,
        created_at=new_conversation.created_at,
        updated_at=new_conversation.updated_at
    )


@router.delete("/{conversation_id}", response_model=SuccessResponse)
async def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a conversation"""
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    # Check if user is participant
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    # Clear last_message_id to avoid circular reference issues
    conversation.last_message_id = None
    db.flush()

    # Delete starred messages for messages in this conversation
    db.query(StarredMessage).filter(
        StarredMessage.message_id.in_(
            db.query(Message.id).filter(Message.conversation_id == conversation_id)
        )
    ).delete(synchronize_session=False)

    # Delete messages in this conversation
    db.query(Message).filter(Message.conversation_id == conversation_id).delete(synchronize_session=False)

    # Delete participants
    db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id
    ).delete(synchronize_session=False)

    # Delete the conversation
    db.delete(conversation)
    db.commit()

    return SuccessResponse(success=True, message="Conversation deleted successfully")


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
    conversation_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    before: Optional[datetime] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get messages for a conversation with pagination"""
    # Check if user is participant
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    # Query messages
    query = db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.deleted_at.is_(None)
    )

    if before:
        query = query.filter(Message.created_at < before)

    query = query.order_by(Message.created_at.desc())

    total = query.count()
    messages = query.limit(limit).all()

    message_responses = []
    for msg in messages:
        sender = db.query(User).filter(User.id == msg.sender_id).first()
        message_responses.append(MessageResponse(
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

    return MessageListResponse(
        messages=message_responses,
        total=total,
        limit=limit,
        has_more=len(messages) == limit
    )


@router.put("/{conversation_id}/read", response_model=SuccessResponse)
async def mark_conversation_as_read(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Mark all messages in conversation as read"""
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    # Reset unread count
    participant.unread_count = 0
    db.commit()

    return SuccessResponse(success=True, message="Conversation marked as read")


@router.put("/{conversation_id}/archive", response_model=SuccessResponse)
async def archive_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Archive a conversation"""
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    participant.is_archived = True
    db.commit()

    return SuccessResponse(success=True, message="Conversation archived successfully")


@router.put("/{conversation_id}/unarchive", response_model=SuccessResponse)
async def unarchive_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Unarchive a conversation"""
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    participant.is_archived = False
    db.commit()

    return SuccessResponse(success=True, message="Conversation unarchived successfully")


@router.put("/{conversation_id}/mute", response_model=SuccessResponse)
async def mute_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Mute a conversation"""
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    participant.is_muted = True
    db.commit()

    return SuccessResponse(success=True, message="Conversation muted successfully")


@router.put("/{conversation_id}/unmute", response_model=SuccessResponse)
async def unmute_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Unmute a conversation"""
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    participant.is_muted = False
    db.commit()

    return SuccessResponse(success=True, message="Conversation unmuted successfully")


@router.put("/{conversation_id}/favorite", response_model=SuccessResponse)
async def toggle_favorite_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Toggle favorite status of a conversation"""
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    participant.is_favorite = not participant.is_favorite
    db.commit()

    message = "added to" if participant.is_favorite else "removed from"
    return SuccessResponse(success=True, message=f"Conversation {message} favorites")


@router.delete("/{conversation_id}/clear", response_model=SuccessResponse)
async def clear_conversation_history(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Clear conversation history (soft delete all messages)"""
    # Check if user is participant
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    # Soft delete all messages
    db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).update({"deleted_at": datetime.utcnow()})

    db.commit()

    return SuccessResponse(success=True, message="Conversation history cleared successfully")
