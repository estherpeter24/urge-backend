from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

from ..core.database import get_db
from ..core.security import get_current_user
from ..models.message import Message, MessageType, MessageStatus
from ..models.conversation import Conversation, ConversationParticipant
from ..models.user import User
from ..services.push_notification import push_service
from ..services.socket_manager import socket_manager, emit_to_conversation

router = APIRouter(prefix="/messages", tags=["Messages"])


# Request/Response Models
class MessageCreateRequest(BaseModel):
    conversation_id: str
    content: str
    message_type: Optional[str] = "TEXT"
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    audio_duration: Optional[int] = None
    reply_to_id: Optional[str] = None
    is_encrypted: Optional[bool] = False


class MessageUpdateRequest(BaseModel):
    content: str


class MessageForwardRequest(BaseModel):
    message_ids: List[str]
    conversation_id: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    sender_name: Optional[str] = None
    content: Optional[str] = None
    message_type: str
    status: str
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    audio_duration: Optional[int] = None
    reply_to_id: Optional[str] = None
    is_edited: bool
    is_deleted: bool
    is_encrypted: bool
    is_starred: bool
    is_forwarded: bool = False
    created_at: str
    updated_at: str
    reply_to: Optional[dict] = None

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    total: int
    limit: int
    has_more: bool


@router.post("", response_model=MessageResponse)
async def send_message(
    request: MessageCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a new message"""
    # Verify user is participant in conversation
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == request.conversation_id,
                ConversationParticipant.user_id == current_user.id
            )
        )
    )
    participant = participant_result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    # Get conversation (will be reused later for last_message_at update)
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == request.conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()

    # Check for blocks in direct conversations

    if conversation and conversation.type == "DIRECT":
        # Get the other participant(s)
        other_participants_result = await db.execute(
            select(ConversationParticipant).where(
                and_(
                    ConversationParticipant.conversation_id == request.conversation_id,
                    ConversationParticipant.user_id != current_user.id
                )
            )
        )
        other_participants = other_participants_result.scalars().all()

        for other_participant in other_participants:
            # Get the other user to check their blocked list
            other_user_result = await db.execute(
                select(User).where(User.id == other_participant.user_id)
            )
            other_user = other_user_result.scalar_one_or_none()

            if other_user:
                # Check if current user blocked the other user
                if other_user.id in (current_user.blocked_users or []):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You have blocked this user. Unblock them to send messages."
                    )

                # Check if the other user blocked the current user
                if current_user.id in (other_user.blocked_users or []):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You cannot send messages to this user."
                    )

    # Get message type enum
    try:
        msg_type = MessageType(request.message_type.upper())
    except ValueError:
        msg_type = MessageType.TEXT

    # Create message
    message = Message(
        id=str(uuid.uuid4()),
        conversation_id=request.conversation_id,
        sender_id=current_user.id,
        content=request.content,
        message_type=msg_type,
        media_url=request.media_url,
        thumbnail_url=request.thumbnail_url,
        audio_duration=request.audio_duration,
        reply_to_id=request.reply_to_id,
        is_encrypted=request.is_encrypted,
        status=MessageStatus.SENT,
    )

    db.add(message)

    # Update conversation last_message_at
    if conversation:
        conversation.last_message_at = datetime.utcnow()

    # Increment unread_count for all participants except sender
    other_participants_for_unread = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == request.conversation_id,
                ConversationParticipant.user_id != current_user.id
            )
        )
    )
    for p in other_participants_for_unread.scalars().all():
        p.unread_count = (p.unread_count or 0) + 1

    await db.commit()
    await db.refresh(message)

    # Send push notifications to offline recipients
    try:
        # Get all participants except sender
        all_participants_result = await db.execute(
            select(ConversationParticipant).where(
                and_(
                    ConversationParticipant.conversation_id == request.conversation_id,
                    ConversationParticipant.user_id != current_user.id
                )
            )
        )
        all_participants = all_participants_result.scalars().all()

        # Collect device tokens for offline users who have notifications enabled
        tokens_to_notify = []
        is_group = conversation and conversation.type == "GROUP"
        group_name = conversation.name if is_group else None

        for p in all_participants:
            # Check if user is online via socket
            if socket_manager.is_user_online(p.user_id):
                continue  # Skip online users - they'll get realtime via socket

            # Check if conversation is muted for this user
            if p.is_muted:
                continue

            # Get user to check notification settings and device tokens
            user_result = await db.execute(
                select(User).where(User.id == p.user_id)
            )
            recipient = user_result.scalar_one_or_none()

            if not recipient:
                continue

            # Check notification settings
            if not recipient.notifications_enabled:
                continue
            if not recipient.message_notifications:
                continue
            if is_group and not recipient.group_notifications:
                continue

            # Add device tokens
            if recipient.device_tokens:
                for token_info in recipient.device_tokens:
                    tokens_to_notify.append({
                        "token": token_info.get("token"),
                        "platform": token_info.get("platform", "ios"),
                    })

        # Send push notifications
        if tokens_to_notify:
            message_preview = request.content if request.message_type == "TEXT" else f"Sent a {request.message_type.lower()}"
            await push_service.send_message_notification(
                tokens=tokens_to_notify,
                sender_name=current_user.display_name or "User",
                message_text=message_preview,
                conversation_id=request.conversation_id,
                message_id=message.id,
                sender_avatar=current_user.avatar_url,
                is_group=is_group,
                group_name=group_name,
            )
    except Exception as e:
        # Log error but don't fail the message send
        import logging
        logging.error(f"Failed to send push notifications: {e}")

    # Broadcast message via WebSocket to all participants in the conversation
    try:
        message_broadcast_data = {
            "id": message.id,
            "conversationId": message.conversation_id,
            "conversation_id": message.conversation_id,
            "senderId": message.sender_id,
            "sender_id": message.sender_id,
            "senderName": current_user.display_name,
            "sender_name": current_user.display_name,
            "senderAvatar": current_user.avatar_url,
            "content": message.content,
            "messageType": message.message_type.value,
            "message_type": message.message_type.value,
            "status": message.status.value,
            "mediaUrl": message.media_url,
            "media_url": message.media_url,
            "thumbnailUrl": message.thumbnail_url,
            "thumbnail_url": message.thumbnail_url,
            "audioDuration": message.audio_duration,
            "audio_duration": message.audio_duration,
            "replyToId": message.reply_to_id,
            "reply_to_id": message.reply_to_id,
            "isEdited": message.is_edited,
            "is_edited": message.is_edited,
            "isDeleted": message.is_deleted,
            "is_deleted": message.is_deleted,
            "isEncrypted": message.is_encrypted,
            "is_encrypted": message.is_encrypted,
            "isStarred": message.is_starred,
            "is_starred": message.is_starred,
            "isForwarded": message.is_forwarded,
            "is_forwarded": message.is_forwarded,
            "createdAt": message.created_at.isoformat(),
            "created_at": message.created_at.isoformat(),
            "updatedAt": message.updated_at.isoformat(),
            "updated_at": message.updated_at.isoformat(),
        }
        await emit_to_conversation(
            message.conversation_id,
            "message:received",
            message_broadcast_data
        )
        logger.info(f"Message {message.id} broadcast to conversation {message.conversation_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast message via WebSocket: {e}")

    # Get reply_to message if exists
    reply_to_data = None
    if message.reply_to_id:
        reply_result = await db.execute(
            select(Message).where(Message.id == message.reply_to_id)
        )
        reply_msg = reply_result.scalar_one_or_none()
        if reply_msg:
            # Get sender name
            sender_result = await db.execute(
                select(User).where(User.id == reply_msg.sender_id)
            )
            sender = sender_result.scalar_one_or_none()
            reply_to_data = {
                "id": reply_msg.id,
                "sender_name": sender.display_name if sender else "Unknown",
                "content": reply_msg.content or "Media",
            }

    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        sender_name=current_user.display_name,
        content=message.content,
        message_type=message.message_type.value,
        status=message.status.value,
        media_url=message.media_url,
        thumbnail_url=message.thumbnail_url,
        audio_duration=message.audio_duration,
        reply_to_id=message.reply_to_id,
        is_edited=message.is_edited,
        is_deleted=message.is_deleted,
        is_encrypted=message.is_encrypted,
        is_starred=message.is_starred,
        created_at=message.created_at.isoformat(),
        updated_at=message.updated_at.isoformat(),
        reply_to=reply_to_data,
    )


@router.put("/{message_id}", response_model=MessageResponse)
async def edit_message(
    message_id: str,
    request: MessageUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit a message"""
    result = await db.execute(
        select(Message).where(Message.id == message_id)
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    if message.sender_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own messages"
        )

    message.content = request.content
    message.is_edited = True
    message.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(message)

    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        sender_name=current_user.display_name,
        content=message.content,
        message_type=message.message_type.value,
        status=message.status.value,
        media_url=message.media_url,
        thumbnail_url=message.thumbnail_url,
        audio_duration=message.audio_duration,
        reply_to_id=message.reply_to_id,
        is_edited=message.is_edited,
        is_deleted=message.is_deleted,
        is_encrypted=message.is_encrypted,
        is_starred=message.is_starred,
        created_at=message.created_at.isoformat(),
        updated_at=message.updated_at.isoformat(),
    )


@router.delete("/{message_id}")
async def delete_message(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a message"""
    result = await db.execute(
        select(Message).where(Message.id == message_id)
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    # Check if user is sender or participant
    if message.sender_id != current_user.id:
        # Check if user is participant
        participant_result = await db.execute(
            select(ConversationParticipant).where(
                and_(
                    ConversationParticipant.conversation_id == message.conversation_id,
                    ConversationParticipant.user_id == current_user.id
                )
            )
        )
        if not participant_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot delete this message"
            )

    # Soft delete
    message.is_deleted = True
    message.content = "This message was deleted"
    message.updated_at = datetime.utcnow()

    await db.commit()

    return {"success": True, "message": "Message deleted"}


@router.post("/forward")
async def forward_messages(
    request: MessageForwardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forward messages to another conversation"""
    # Verify user is participant in target conversation
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == request.conversation_id,
                ConversationParticipant.user_id == current_user.id
            )
        )
    )
    if not participant_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in the target conversation"
        )

    forwarded_messages = []

    for msg_id in request.message_ids:
        # Get original message
        result = await db.execute(
            select(Message).where(Message.id == msg_id)
        )
        original = result.scalar_one_or_none()

        if original and not original.is_deleted:
            # Create forwarded message with is_forwarded flag
            forwarded = Message(
                id=str(uuid.uuid4()),
                conversation_id=request.conversation_id,
                sender_id=current_user.id,
                content=original.content,
                message_type=original.message_type,
                media_url=original.media_url,
                thumbnail_url=original.thumbnail_url,
                audio_duration=original.audio_duration,
                is_encrypted=original.is_encrypted,
                is_forwarded=True,  # Mark as forwarded
                status=MessageStatus.SENT,
            )
            db.add(forwarded)
            forwarded_messages.append(forwarded)

    # Update conversation last_message_at
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == request.conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()
    if conversation:
        conversation.last_message_at = datetime.utcnow()

    await db.commit()

    return {
        "success": True,
        "message": f"Forwarded {len(forwarded_messages)} message(s)",
        "forwarded_count": len(forwarded_messages),
    }


@router.post("/{message_id}/star")
async def star_message(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Star a message"""
    result = await db.execute(
        select(Message).where(Message.id == message_id)
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    # Verify user is participant
    participant_result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == message.conversation_id,
                ConversationParticipant.user_id == current_user.id
            )
        )
    )
    if not participant_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )

    message.is_starred = True
    message.updated_at = datetime.utcnow()

    await db.commit()

    return {"success": True, "message": "Message starred"}


@router.delete("/{message_id}/star")
async def unstar_message(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unstar a message"""
    result = await db.execute(
        select(Message).where(Message.id == message_id)
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    message.is_starred = False
    message.updated_at = datetime.utcnow()

    await db.commit()

    return {"success": True, "message": "Message unstarred"}


@router.get("/starred", response_model=MessageListResponse)
async def get_starred_messages(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all starred messages for current user"""
    # Get conversations user is part of
    participant_result = await db.execute(
        select(ConversationParticipant.conversation_id).where(
            ConversationParticipant.user_id == current_user.id
        )
    )
    conversation_ids = [row[0] for row in participant_result.fetchall()]

    # Get starred messages from those conversations
    count_result = await db.execute(
        select(func.count(Message.id)).where(
            and_(
                Message.conversation_id.in_(conversation_ids),
                Message.is_starred == True,
                Message.is_deleted == False,
            )
        )
    )
    total = count_result.scalar()

    result = await db.execute(
        select(Message).where(
            and_(
                Message.conversation_id.in_(conversation_ids),
                Message.is_starred == True,
                Message.is_deleted == False,
            )
        ).order_by(Message.created_at.desc()).offset(offset).limit(limit)
    )
    messages = result.scalars().all()

    # Format messages
    formatted_messages = []
    for msg in messages:
        # Get sender name
        sender_result = await db.execute(
            select(User).where(User.id == msg.sender_id)
        )
        sender = sender_result.scalar_one_or_none()

        formatted_messages.append(MessageResponse(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            sender_name=sender.display_name if sender else "Unknown",
            content=msg.content,
            message_type=msg.message_type.value,
            status=msg.status.value,
            media_url=msg.media_url,
            thumbnail_url=msg.thumbnail_url,
            audio_duration=msg.audio_duration,
            reply_to_id=msg.reply_to_id,
            is_edited=msg.is_edited,
            is_deleted=msg.is_deleted,
            is_encrypted=msg.is_encrypted,
            is_starred=msg.is_starred,
            created_at=msg.created_at.isoformat(),
            updated_at=msg.updated_at.isoformat(),
        ))

    return MessageListResponse(
        messages=formatted_messages,
        total=total,
        limit=limit,
        has_more=offset + limit < total,
    )


@router.get("/search")
async def search_messages(
    q: str,
    conversation_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search messages"""
    # Get conversations user is part of
    participant_result = await db.execute(
        select(ConversationParticipant.conversation_id).where(
            ConversationParticipant.user_id == current_user.id
        )
    )
    conversation_ids = [row[0] for row in participant_result.fetchall()]

    # Filter by specific conversation if provided
    if conversation_id:
        if conversation_id not in conversation_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a participant in this conversation"
            )
        conversation_ids = [conversation_id]

    # Search messages
    result = await db.execute(
        select(Message).where(
            and_(
                Message.conversation_id.in_(conversation_ids),
                Message.content.ilike(f"%{q}%"),
                Message.is_deleted == False,
            )
        ).order_by(Message.created_at.desc()).limit(limit)
    )
    messages = result.scalars().all()

    # Format messages
    formatted_messages = []
    for msg in messages:
        sender_result = await db.execute(
            select(User).where(User.id == msg.sender_id)
        )
        sender = sender_result.scalar_one_or_none()

        formatted_messages.append({
            "id": msg.id,
            "conversation_id": msg.conversation_id,
            "sender_id": msg.sender_id,
            "sender_name": sender.display_name if sender else "Unknown",
            "content": msg.content,
            "message_type": msg.message_type.value,
            "created_at": msg.created_at.isoformat(),
        })

    return {
        "messages": formatted_messages,
        "total": len(formatted_messages),
    }


@router.put("/{message_id}/status")
async def update_message_status(
    message_id: str,
    status_update: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update message status (delivered/read)"""
    result = await db.execute(
        select(Message).where(Message.id == message_id)
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    new_status = status_update.get("status", "").upper()
    if new_status in ["DELIVERED", "READ"]:
        try:
            old_status = message.status
            message.status = MessageStatus(new_status)
            if new_status == "READ":
                message.read_at = datetime.utcnow()
            await db.commit()

            # Broadcast status change via WebSocket
            if old_status != MessageStatus(new_status):
                event_name = "message:delivered" if new_status == "DELIVERED" else "message:read"
                try:
                    await emit_to_conversation(
                        message.conversation_id,
                        event_name,
                        {
                            "messageId": message_id,
                            "message_id": message_id,
                            "userId": current_user.id,
                            "user_id": current_user.id,
                            "conversationId": message.conversation_id,
                            "conversation_id": message.conversation_id,
                        }
                    )
                    logger.info(f"Message {message_id} status changed to {new_status}")
                except Exception as e:
                    logger.error(f"Failed to broadcast status change: {e}")
        except ValueError:
            pass

    return {"success": True}


@router.post("/read")
async def mark_messages_as_read(
    request: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch mark messages as read"""
    message_ids = request.get("message_ids", [])
    conversation_id = request.get("conversation_id")

    if not message_ids:
        return {"success": True, "updated": 0}

    result = await db.execute(
        select(Message).where(Message.id.in_(message_ids))
    )
    messages = result.scalars().all()

    updated = 0
    read_message_ids = []
    conv_id = conversation_id
    for message in messages:
        if message.status != MessageStatus.READ:
            message.status = MessageStatus.READ
            message.read_at = datetime.utcnow()
            updated += 1
            read_message_ids.append(message.id)
            if not conv_id:
                conv_id = message.conversation_id

    await db.commit()

    # Broadcast read receipts via WebSocket
    if read_message_ids and conv_id:
        try:
            for msg_id in read_message_ids:
                await emit_to_conversation(
                    conv_id,
                    "message:read",
                    {
                        "messageId": msg_id,
                        "message_id": msg_id,
                        "userId": current_user.id,
                        "user_id": current_user.id,
                        "conversationId": conv_id,
                        "conversation_id": conv_id,
                    }
                )
            logger.info(f"Read receipts broadcast for {len(read_message_ids)} messages in conversation {conv_id}")
        except Exception as e:
            logger.error(f"Failed to broadcast read receipts: {e}")

    return {"success": True, "updated": updated}
