import socketio
from typing import Dict, Set
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.core.security import decode_token
from app.models.user import User
from app.models.message import Message, MessageStatus
from app.models.conversation import ConversationParticipant

# Create Socket.IO server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True
)

# Store active connections
active_users: Dict[str, Set[str]] = {}  # user_id -> set of session_ids
user_sessions: Dict[str, str] = {}  # session_id -> user_id
typing_status: Dict[str, Set[str]] = {}  # conversation_id -> set of user_ids typing


def get_db():
    """Get database session"""
    return SessionLocal()


@sio.event
async def connect(sid, environ, auth):
    """Handle client connection"""
    print(f"Client {sid} connecting...")

    # Authenticate using JWT token
    token = auth.get('token') if auth else None

    if not token:
        print(f"Client {sid} connection rejected: No token provided")
        return False

    try:
        # Decode token
        payload = decode_token(token)
        user_id = payload.get('sub')

        print(f"Decoded payload: {payload}")
        print(f"User ID from token: {user_id}, type: {type(user_id)}")

        if not user_id:
            print(f"Client {sid} connection rejected: Invalid token")
            return False

        # Convert string UUID to UUID object
        from uuid import UUID
        try:
            user_uuid = UUID(user_id)
            print(f"Converted to UUID: {user_uuid}")
        except (ValueError, AttributeError, TypeError) as e:
            print(f"Client {sid} connection rejected: Invalid UUID format - {user_id}, error: {e}")
            return False

        # Store session (keep as string for dictionary key)
        user_sessions[sid] = user_id

        # Add to active users (keep as string for dictionary key)
        if user_id not in active_users:
            active_users[user_id] = set()
        active_users[user_id].add(sid)

        # Update user online status
        db = get_db()
        try:
            user = db.query(User).filter(User.id == user_uuid).first()
            if user:
                user.is_online = True
                user.last_seen = datetime.utcnow()
                db.commit()
            db.close()
        except Exception as e:
            print(f"Database error: {str(e)}")
            db.close()
            raise

        # Notify other users that this user came online
        await sio.emit('user:online', {'userId': user_id})

        print(f"Client {sid} authenticated as user {user_id}")
        await sio.emit('authenticated', {'userId': user_id}, room=sid)

        return True

    except Exception as e:
        print(f"Client {sid} connection error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


@sio.event
async def disconnect(sid):
    """Handle client disconnection"""
    print(f"Client {sid} disconnected")

    user_id = user_sessions.get(sid)

    if user_id:
        # Remove from active users
        if user_id in active_users:
            active_users[user_id].discard(sid)

            # If no more active sessions, mark user as offline
            if not active_users[user_id]:
                del active_users[user_id]

                # Update user online status
                db = get_db()
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    user.is_online = False
                    user.last_seen = datetime.utcnow()
                    db.commit()

                # Notify other users that this user went offline
                await sio.emit('user:offline', {
                    'userId': user_id,
                    'lastSeen': user.last_seen.isoformat() if user.last_seen else None
                })

        # Remove session
        del user_sessions[sid]


@sio.event
async def join_conversation(sid, data):
    """Join a conversation room"""
    conversation_id = data.get('conversationId')
    user_id = user_sessions.get(sid)

    if not conversation_id or not user_id:
        return

    # Verify user is participant in conversation
    db = get_db()
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == user_id
    ).first()

    if participant:
        await sio.enter_room(sid, f"conversation:{conversation_id}")
        print(f"User {user_id} joined conversation {conversation_id}")


@sio.event
async def leave_conversation(sid, data):
    """Leave a conversation room"""
    conversation_id = data.get('conversationId')
    user_id = user_sessions.get(sid)

    if not conversation_id or not user_id:
        return

    await sio.leave_room(sid, f"conversation:{conversation_id}")
    print(f"User {user_id} left conversation {conversation_id}")


@sio.event
async def message_sent(sid, data):
    """Handle new message sent"""
    user_id = user_sessions.get(sid)

    if not user_id:
        return

    conversation_id = data.get('conversationId')
    message_id = data.get('id')

    # Broadcast message to all participants in the conversation
    await sio.emit(
        'message:received',
        data,
        room=f"conversation:{conversation_id}",
        skip_sid=sid  # Don't send to sender
    )

    print(f"Message {message_id} sent to conversation {conversation_id}")


@sio.event
async def message_delivered(sid, data):
    """Handle message delivered confirmation"""
    message_id = data.get('messageId')
    user_id = user_sessions.get(sid)

    if not message_id or not user_id:
        return

    # Update message status in database
    db = get_db()
    message = db.query(Message).filter(Message.id == message_id).first()

    if message and message.status == MessageStatus.SENT:
        message.status = MessageStatus.DELIVERED
        db.commit()

    # Notify sender
    sender_id = str(message.sender_id) if message else None
    if sender_id and sender_id in active_users:
        for session_id in active_users[sender_id]:
            await sio.emit('message:delivered', {
                'messageId': message_id,
                'userId': user_id
            }, room=session_id)


@sio.event
async def message_read(sid, data):
    """Handle message read confirmation"""
    message_id = data.get('messageId')
    conversation_id = data.get('conversationId')
    user_id = user_sessions.get(sid)

    if not message_id or not user_id:
        return

    # Update message status in database
    db = get_db()
    message = db.query(Message).filter(Message.id == message_id).first()

    if message:
        message.status = MessageStatus.READ
        db.commit()

        # Notify sender
        sender_id = str(message.sender_id)
        if sender_id and sender_id in active_users:
            for session_id in active_users[sender_id]:
                await sio.emit('message:read', {
                    'messageId': message_id,
                    'conversationId': conversation_id,
                    'userId': user_id
                }, room=session_id)


@sio.event
async def typing_start(sid, data):
    """Handle typing start"""
    conversation_id = data.get('conversationId')
    user_id = user_sessions.get(sid)

    if not conversation_id or not user_id:
        return

    # Add to typing status
    if conversation_id not in typing_status:
        typing_status[conversation_id] = set()
    typing_status[conversation_id].add(user_id)

    # Get user info
    db = get_db()
    user = db.query(User).filter(User.id == user_id).first()

    # Broadcast to conversation participants
    await sio.emit(
        'typing:start',
        {
            'conversationId': conversation_id,
            'userId': user_id,
            'userName': user.display_name if user else 'Unknown'
        },
        room=f"conversation:{conversation_id}",
        skip_sid=sid
    )


@sio.event
async def typing_stop(sid, data):
    """Handle typing stop"""
    conversation_id = data.get('conversationId')
    user_id = user_sessions.get(sid)

    if not conversation_id or not user_id:
        return

    # Remove from typing status
    if conversation_id in typing_status:
        typing_status[conversation_id].discard(user_id)
        if not typing_status[conversation_id]:
            del typing_status[conversation_id]

    # Broadcast to conversation participants
    await sio.emit(
        'typing:stop',
        {
            'conversationId': conversation_id,
            'userId': user_id
        },
        room=f"conversation:{conversation_id}",
        skip_sid=sid
    )


@sio.event
async def get_online_status(sid, data):
    """Get online status of users"""
    user_ids = data.get('userIds', [])
    online_users = []

    for user_id in user_ids:
        if user_id in active_users:
            online_users.append(user_id)

    await sio.emit('online:status', {
        'onlineUsers': online_users
    }, room=sid)


# Create ASGI application
socket_app = socketio.ASGIApp(
    sio,
    socketio_path='socket.io'
)
