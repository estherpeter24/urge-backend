from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

from ..core.database import get_db
from ..core.security import get_current_user
from ..models.message import Message, MessageStatus
from ..models.conversation import Conversation, ConversationParticipant, ConversationType
from ..models.user import User
from ..services.socket_manager import emit_to_conversation

router = APIRouter(prefix="/conversations", tags=["Conversations"])


# Request/Response Models
class ConversationCreateRequest(BaseModel):
    type: str = "DIRECT"
    participant_ids: List[str]
    name: Optional[str] = None
    avatar_url: Optional[str] = None


class ConversationResponse(BaseModel):
    id: str
    type: str
    name: Optional[str] = None
    avatarUrl: Optional[str] = None
    description: Optional[str] = None
    isMuted: bool = False
    isArchived: bool = False
    isFavourite: bool = False
    createdAt: str = ""
    updatedAt: str = ""
    lastMessageAt: Optional[str] = None
    unreadCount: int = 0
    participantCount: int = 0
    lastMessage: Optional[dict] = None
    participants: List[dict] = []

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    conversations: List[ConversationResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    sender_name: Optional[str] = None
    content: Optional[str] = None
    message_type: str
    status: str
    media_url: Optional[str] = None
    is_edited: bool
    is_deleted: bool
    is_encrypted: bool
    is_starred: bool
    created_at: str
    updated_at: str
    reply_to: Optional[dict] = None

    class Config:
        from_attributes = True


@router.get("", response_model=ConversationListResponse)
async def get_conversations(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all conversations for current user"""
    # Get conversation IDs where user is participant
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.user_id == current_user.id
        )
    )
    participants = participant_result.scalars().all()
    conversation_ids = [p.conversation_id for p in participants]
    unread_map = {p.conversation_id: p.unread_count for p in participants}

    if not conversation_ids:
        return ConversationListResponse(
            conversations=[],
            total=0,
            limit=limit,
            offset=offset,
        )

    # Count total
    count_result = await db.execute(
        select(func.count(Conversation.id)).where(
            and_(
                Conversation.id.in_(conversation_ids),
                Conversation.is_archived == False,
            )
        )
    )
    total = count_result.scalar()

    # Get conversations ordered by last_message_at
    result = await db.execute(
        select(Conversation).where(
            and_(
                Conversation.id.in_(conversation_ids),
                Conversation.is_archived == False,
            )
        ).order_by(desc(Conversation.last_message_at)).offset(offset).limit(limit)
    )
    conversations = result.scalars().all()

    # Format conversations
    formatted_conversations = []
    for conv in conversations:
        # Get last message
        last_msg_result = await db.execute(
            select(Message).where(
                and_(
                    Message.conversation_id == conv.id,
                    Message.is_deleted == False,
                )
            ).order_by(desc(Message.created_at)).limit(1)
        )
        last_message = last_msg_result.scalar_one_or_none()

        last_message_data = None
        if last_message:
            last_message_data = {
                "content": last_message.content,
                "createdAt": last_message.created_at.isoformat() if last_message.created_at else "",
                "messageType": last_message.message_type.value if last_message.message_type else "TEXT",
            }

        # Get conversation name for DIRECT conversations
        conv_name = conv.name
        conv_avatar = conv.avatar_url

        if conv.type == ConversationType.DIRECT:
            # Get the other participant
            other_participant_result = await db.execute(
                select(ConversationParticipant).where(
                    and_(
                        ConversationParticipant.conversation_id == conv.id,
                        ConversationParticipant.user_id != current_user.id
                    )
                )
            )
            other_participant = other_participant_result.scalar_one_or_none()
            if other_participant:
                other_user_result = await db.execute(
                    select(User).where(User.id == other_participant.user_id)
                )
                other_user = other_user_result.scalar_one_or_none()
                if other_user:
                    conv_name = other_user.display_name or other_user.phone_number
                    conv_avatar = other_user.avatar_url

        # Get participants
        conv_participants_result = await db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conv.id
            )
        )
        conv_participants = conv_participants_result.scalars().all()

        participants_data = []
        for cp in conv_participants:
            user_result = await db.execute(
                select(User).where(User.id == cp.user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                participants_data.append({
                    "id": user.id,
                    "display_name": user.display_name,
                    "phone_number": user.phone_number,
                    "avatar_url": user.avatar_url,
                    "is_online": user.is_online if hasattr(user, 'is_online') else False,
                    "role": cp.role,
                })

        formatted_conversations.append(ConversationResponse(
            id=conv.id,
            type=conv.type.value,
            name=conv_name,
            avatarUrl=conv_avatar,
            description=conv.description,
            isMuted=conv.is_muted,
            isArchived=conv.is_archived,
            isFavourite=conv.is_favorite,
            createdAt=conv.created_at.isoformat() if conv.created_at else "",
            updatedAt=conv.updated_at.isoformat() if conv.updated_at else "",
            lastMessageAt=conv.last_message_at.isoformat() if conv.last_message_at else None,
            unreadCount=unread_map.get(conv.id, 0),
            participantCount=len(participants_data),
            lastMessage=last_message_data,
            participants=participants_data,
        ))

    return ConversationListResponse(
        conversations=formatted_conversations,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/archived", response_model=ConversationListResponse)
async def get_archived_conversations(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get archived conversations for current user"""
    # Get conversation IDs where user is participant
    participant_result = await db.execute(
        select(ConversationParticipant.conversation_id).where(
            ConversationParticipant.user_id == current_user.id
        )
    )
    conversation_ids = [row[0] for row in participant_result.fetchall()]

    if not conversation_ids:
        return ConversationListResponse(
            conversations=[],
            total=0,
            limit=limit,
            offset=offset,
        )

    # Get archived conversations
    result = await db.execute(
        select(Conversation).where(
            and_(
                Conversation.id.in_(conversation_ids),
                Conversation.is_archived == True,
            )
        ).order_by(desc(Conversation.last_message_at)).offset(offset).limit(limit)
    )
    conversations = result.scalars().all()

    formatted_conversations = []
    for conv in conversations:
        formatted_conversations.append(ConversationResponse(
            id=conv.id,
            type=conv.type.value,
            name=conv.name,
            avatarUrl=conv.avatar_url,
            description=conv.description,
            isMuted=conv.is_muted,
            isArchived=conv.is_archived,
            isFavourite=conv.is_favorite,
            createdAt=conv.created_at.isoformat() if conv.created_at else "",
            updatedAt=conv.updated_at.isoformat() if conv.updated_at else "",
            lastMessageAt=conv.last_message_at.isoformat() if conv.last_message_at else None,
            unreadCount=0,
        ))

    return ConversationListResponse(
        conversations=formatted_conversations,
        total=len(formatted_conversations),
        limit=limit,
        offset=offset,
    )


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific conversation"""
    # Verify user is participant
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == current_user.id
            )
        )
    )
    if not participant_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    # Get participants with user details
    conv_participants_result = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id
        )
    )
    conv_participants = conv_participants_result.scalars().all()

    participants_data = []
    for cp in conv_participants:
        user_result = await db.execute(
            select(User).where(User.id == cp.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            participants_data.append({
                "id": user.id,
                "display_name": user.display_name,
                "phone_number": user.phone_number,
                "avatar_url": user.avatar_url,
                "is_online": user.is_online if hasattr(user, 'is_online') else False,
                "role": cp.role,
            })

    conv_data = conversation.to_dict()
    conv_data["participants"] = participants_data
    return conv_data


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    request: ConversationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new conversation"""
    # Ensure current user is included in participants
    all_participant_ids = list(set(request.participant_ids + [current_user.id]))

    # For DIRECT conversations, check if one already exists
    if request.type == "DIRECT" and len(all_participant_ids) == 2:
        # Check for existing direct conversation between these users
        existing_result = await db.execute(
            select(Conversation).where(
                and_(
                    Conversation.type == ConversationType.DIRECT,
                )
            )
        )
        existing_convs = existing_result.scalars().all()

        for conv in existing_convs:
            part_result = await db.execute(
                select(ConversationParticipant.user_id).where(
                    ConversationParticipant.conversation_id == conv.id
                )
            )
            conv_participant_ids = [row[0] for row in part_result.fetchall()]
            if set(conv_participant_ids) == set(all_participant_ids):
                # Return existing conversation
                return ConversationResponse(
                    id=conv.id,
                    type=conv.type.value,
                    name=conv.name,
                    avatarUrl=conv.avatar_url,
                    description=conv.description,
                    isMuted=conv.is_muted,
                    isArchived=conv.is_archived,
                    isFavourite=conv.is_favorite,
                    createdAt=conv.created_at.isoformat() if conv.created_at else "",
                    updatedAt=conv.updated_at.isoformat() if conv.updated_at else "",
                    unreadCount=0,
                )

    # Create new conversation
    conv_type = ConversationType.GROUP if request.type == "GROUP" else ConversationType.DIRECT

    conversation = Conversation(
        id=str(uuid.uuid4()),
        type=conv_type,
        name=request.name,
        avatar_url=request.avatar_url,
        created_by=current_user.id,
    )
    db.add(conversation)

    # Add participants
    for user_id in all_participant_ids:
        participant = ConversationParticipant(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            user_id=user_id,
            role="admin" if user_id == current_user.id else "member",
        )
        db.add(participant)

    await db.commit()
    await db.refresh(conversation)

    return ConversationResponse(
        id=conversation.id,
        type=conversation.type.value,
        name=conversation.name,
        avatarUrl=conversation.avatar_url,
        description=conversation.description,
        isMuted=conversation.is_muted,
        isArchived=conversation.is_archived,
        isFavourite=conversation.is_favorite,
        createdAt=conversation.created_at.isoformat() if conversation.created_at else "",
        updatedAt=conversation.updated_at.isoformat() if conversation.updated_at else "",
        unreadCount=0,
    )


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete/leave a conversation"""
    # Remove user from conversation
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == current_user.id
            )
        )
    )
    participant = participant_result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    await db.delete(participant)
    await db.commit()

    return {"success": True, "message": "Left conversation"}


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    limit: int = 50,
    before: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get messages for a conversation"""
    # Verify user is participant
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == current_user.id
            )
        )
    )
    if not participant_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    # Build query
    query = select(Message).where(
        and_(
            Message.conversation_id == conversation_id,
            Message.is_deleted == False,
        )
    )

    if before:
        # Get messages before a specific message ID (for pagination)
        before_result = await db.execute(
            select(Message.created_at).where(Message.id == before)
        )
        before_time = before_result.scalar_one_or_none()
        if before_time:
            query = query.where(Message.created_at < before_time)

    query = query.order_by(desc(Message.created_at)).limit(limit)

    result = await db.execute(query)
    messages = result.scalars().all()

    # Reverse to get chronological order
    messages = list(reversed(messages))

    # Format messages
    formatted_messages = []
    for msg in messages:
        # Get sender
        sender_result = await db.execute(
            select(User).where(User.id == msg.sender_id)
        )
        sender = sender_result.scalar_one_or_none()

        # Get reply_to if exists
        reply_to_data = None
        if msg.reply_to_id:
            reply_result = await db.execute(
                select(Message).where(Message.id == msg.reply_to_id)
            )
            reply_msg = reply_result.scalar_one_or_none()
            if reply_msg:
                reply_sender_result = await db.execute(
                    select(User).where(User.id == reply_msg.sender_id)
                )
                reply_sender = reply_sender_result.scalar_one_or_none()
                reply_to_data = {
                    "id": reply_msg.id,
                    "sender_name": reply_sender.display_name if reply_sender else "Unknown",
                    "content": reply_msg.content or "Media",
                }

        formatted_messages.append({
            "id": msg.id,
            "conversation_id": msg.conversation_id,
            "sender_id": msg.sender_id,
            "sender_name": sender.display_name if sender else "Unknown",
            "content": msg.content,
            "message_type": msg.message_type.value,
            "status": msg.status.value,
            "media_url": msg.media_url,
            "thumbnail_url": msg.thumbnail_url,
            "audio_duration": msg.audio_duration,
            "reply_to_id": msg.reply_to_id,
            "is_edited": msg.is_edited,
            "is_deleted": msg.is_deleted,
            "is_encrypted": msg.is_encrypted,
            "is_starred": msg.is_starred,
            "is_forwarded": msg.is_forwarded,
            "created_at": msg.created_at.isoformat(),
            "updated_at": msg.updated_at.isoformat(),
            "reply_to": reply_to_data,
        })

    # Check if there are more messages
    has_more = len(messages) == limit

    return {
        "messages": formatted_messages,
        "total": len(formatted_messages),
        "limit": limit,
        "has_more": has_more,
    }


@router.put("/{conversation_id}/read")
async def mark_conversation_as_read(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all messages in a conversation as read"""
    # Update participant's unread count
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == current_user.id
            )
        )
    )
    participant = participant_result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    participant.unread_count = 0
    participant.last_read_at = datetime.utcnow()

    # Mark all messages as read
    await db.execute(
        select(Message).where(
            and_(
                Message.conversation_id == conversation_id,
                Message.sender_id != current_user.id,
                Message.status != MessageStatus.READ,
            )
        )
    )
    # Update messages - simpler approach
    messages_result = await db.execute(
        select(Message).where(
            and_(
                Message.conversation_id == conversation_id,
                Message.sender_id != current_user.id,
            )
        )
    )
    messages = messages_result.scalars().all()
    read_message_ids = []
    for msg in messages:
        if msg.status != MessageStatus.READ:
            msg.status = MessageStatus.READ
            msg.read_at = datetime.utcnow()
            read_message_ids.append(msg.id)

    await db.commit()

    # Broadcast read receipts via WebSocket
    if read_message_ids:
        try:
            for msg_id in read_message_ids:
                await emit_to_conversation(
                    conversation_id,
                    "message:read",
                    {
                        "messageId": msg_id,
                        "message_id": msg_id,
                        "userId": current_user.id,
                        "user_id": current_user.id,
                        "conversationId": conversation_id,
                        "conversation_id": conversation_id,
                    }
                )
            logger.info(f"Read receipts broadcast for {len(read_message_ids)} messages in conversation {conversation_id}")
        except Exception as e:
            logger.error(f"Failed to broadcast read receipts: {e}")

    return {"success": True, "message": "Conversation marked as read"}


@router.put("/{conversation_id}/archive")
async def archive_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Archive a conversation"""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    conversation.is_archived = True
    await db.commit()

    return {"success": True, "message": "Conversation archived"}


@router.put("/{conversation_id}/unarchive")
async def unarchive_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unarchive a conversation"""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    conversation.is_archived = False
    await db.commit()

    return {"success": True, "message": "Conversation unarchived"}


@router.put("/{conversation_id}/mute")
async def mute_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mute a conversation"""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    conversation.is_muted = True
    await db.commit()

    return {"success": True, "message": "Conversation muted"}


@router.put("/{conversation_id}/unmute")
async def unmute_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unmute a conversation"""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    conversation.is_muted = False
    await db.commit()

    return {"success": True, "message": "Conversation unmuted"}


@router.put("/{conversation_id}/favorite")
async def toggle_favorite_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle favorite status of a conversation"""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    conversation.is_favorite = not conversation.is_favorite
    await db.commit()

    return {
        "success": True,
        "message": "Favorite status updated",
        "is_favorite": conversation.is_favorite,
    }


@router.delete("/{conversation_id}/clear")
async def clear_conversation_history(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clear conversation history (soft delete all messages)"""
    # Verify user is participant
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == current_user.id
            )
        )
    )
    if not participant_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    # Soft delete all messages
    messages_result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
    )
    messages = messages_result.scalars().all()

    for msg in messages:
        msg.is_deleted = True
        msg.content = "This message was deleted"

    await db.commit()

    return {"success": True, "message": "Conversation history cleared"}
