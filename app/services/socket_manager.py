import socketio
from typing import Dict, Set
import logging

logger = logging.getLogger(__name__)

# Create Socket.IO server with CORS allowed
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True,
)


class SocketManager:
    def __init__(self):
        # Track connected users: user_id -> set of session_ids
        self.connected_users: Dict[str, Set[str]] = {}
        # Track user sessions: session_id -> user_id
        self.session_users: Dict[str, str] = {}
        # Track conversation rooms: conversation_id -> set of session_ids
        self.conversation_rooms: Dict[str, Set[str]] = {}

    def add_user(self, user_id: str, session_id: str):
        """Add a user connection"""
        if user_id not in self.connected_users:
            self.connected_users[user_id] = set()
        self.connected_users[user_id].add(session_id)
        self.session_users[session_id] = user_id
        logger.info(f"User {user_id} connected with session {session_id}")

    def remove_user(self, session_id: str):
        """Remove a user connection"""
        user_id = self.session_users.get(session_id)
        if user_id:
            if user_id in self.connected_users:
                self.connected_users[user_id].discard(session_id)
                if not self.connected_users[user_id]:
                    del self.connected_users[user_id]
            del self.session_users[session_id]
            logger.info(f"User {user_id} disconnected from session {session_id}")
        return user_id

    def get_user_sessions(self, user_id: str) -> Set[str]:
        """Get all session IDs for a user"""
        return self.connected_users.get(user_id, set())

    def is_user_online(self, user_id: str) -> bool:
        """Check if a user is online"""
        return user_id in self.connected_users and len(self.connected_users[user_id]) > 0

    def join_conversation(self, session_id: str, conversation_id: str):
        """Add a session to a conversation room"""
        if conversation_id not in self.conversation_rooms:
            self.conversation_rooms[conversation_id] = set()
        self.conversation_rooms[conversation_id].add(session_id)
        logger.info(f"Session {session_id} joined conversation {conversation_id}")

    def leave_conversation(self, session_id: str, conversation_id: str):
        """Remove a session from a conversation room"""
        if conversation_id in self.conversation_rooms:
            self.conversation_rooms[conversation_id].discard(session_id)
            if not self.conversation_rooms[conversation_id]:
                del self.conversation_rooms[conversation_id]
        logger.info(f"Session {session_id} left conversation {conversation_id}")

    def get_conversation_sessions(self, conversation_id: str) -> Set[str]:
        """Get all sessions in a conversation"""
        return self.conversation_rooms.get(conversation_id, set())


# Global socket manager instance
socket_manager = SocketManager()


# Socket.IO event handlers
@sio.event
async def connect(sid, environ, auth):
    """Handle client connection"""
    logger.info(f"Client connecting: {sid}")

    # Extract token from auth
    token = None
    if auth and isinstance(auth, dict):
        token = auth.get('token')

    if not token:
        logger.warning(f"No token provided for connection {sid}")
        # Allow connection but mark as unauthenticated
        return True

    # Verify token and get user_id
    try:
        from ..core.security import decode_token
        payload = decode_token(token)
        user_id = payload.get('sub')

        if user_id:
            socket_manager.add_user(user_id, sid)
            # Store user_id in session
            await sio.save_session(sid, {'user_id': user_id})

            # Auto-join user to all their conversation rooms
            await auto_join_user_conversations(sid, user_id)

            # Notify others that user is online
            await sio.emit('user:online', user_id, skip_sid=sid)
            logger.info(f"User {user_id} authenticated and connected")
            return True
    except Exception as e:
        logger.error(f"Token verification failed: {e}")

    return True


async def auto_join_user_conversations(sid: str, user_id: str):
    """Auto-join user to all their conversation rooms on connect"""
    try:
        from sqlalchemy import select
        from ..core.database import AsyncSessionLocal
        from ..models.conversation import ConversationParticipant

        async with AsyncSessionLocal() as db:
            # Get all conversations this user is part of
            result = await db.execute(
                select(ConversationParticipant).filter(
                    ConversationParticipant.user_id == user_id
                )
            )
            participants = result.scalars().all()

            for participant in participants:
                conversation_id = str(participant.conversation_id)
                socket_manager.join_conversation(sid, conversation_id)
                await sio.enter_room(sid, f"conversation:{conversation_id}")
                logger.info(f"Auto-joined user {user_id} to conversation {conversation_id}")
    except Exception as e:
        logger.error(f"Error auto-joining conversations for user {user_id}: {e}")


@sio.event
async def disconnect(sid):
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {sid}")

    # Get user from session
    session = await sio.get_session(sid)
    user_id = session.get('user_id') if session else None

    if not user_id:
        user_id = socket_manager.remove_user(sid)
    else:
        socket_manager.remove_user(sid)

    # Leave all conversation rooms
    for conv_id in list(socket_manager.conversation_rooms.keys()):
        if sid in socket_manager.conversation_rooms.get(conv_id, set()):
            socket_manager.leave_conversation(sid, conv_id)

    # Notify others that user is offline (if no more sessions)
    if user_id and not socket_manager.is_user_online(user_id):
        await sio.emit('user:offline', user_id)


@sio.event
async def join_conversation(sid, conversation_id):
    """Handle joining a conversation room"""
    socket_manager.join_conversation(sid, conversation_id)
    await sio.enter_room(sid, f"conversation:{conversation_id}")
    logger.info(f"Session {sid} joined room conversation:{conversation_id}")


@sio.event
async def leave_conversation(sid, conversation_id):
    """Handle leaving a conversation room"""
    socket_manager.leave_conversation(sid, conversation_id)
    await sio.leave_room(sid, f"conversation:{conversation_id}")
    logger.info(f"Session {sid} left room conversation:{conversation_id}")


@sio.on('join:conversation')
async def on_join_conversation(sid, conversation_id):
    """Alternative event name for joining conversation"""
    await join_conversation(sid, conversation_id)


@sio.on('leave:conversation')
async def on_leave_conversation(sid, conversation_id):
    """Alternative event name for leaving conversation"""
    await leave_conversation(sid, conversation_id)


@sio.event
async def message_sent(sid, message_data):
    """Handle message sent event - broadcast to conversation"""
    conversation_id = message_data.get('conversationId') or message_data.get('conversation_id')

    if conversation_id:
        # Broadcast to all users in the conversation except sender
        await sio.emit(
            'message:received',
            message_data,
            room=f"conversation:{conversation_id}",
            skip_sid=sid
        )
        logger.info(f"Message broadcast to conversation {conversation_id}")


@sio.on('message:sent')
async def on_message_sent(sid, message_data):
    """Alternative event name for message sent"""
    await message_sent(sid, message_data)


@sio.event
async def message_delivered(sid, message_id):
    """Handle message delivered event"""
    session = await sio.get_session(sid)
    user_id = session.get('user_id') if session else None

    # Broadcast delivery status
    await sio.emit('message:delivered', message_id, skip_sid=sid)
    logger.info(f"Message {message_id} marked as delivered")


@sio.on('message:delivered')
async def on_message_delivered(sid, message_id):
    """Alternative event name for message delivered"""
    await message_delivered(sid, message_id)


@sio.event
async def message_read(sid, data):
    """Handle message read event"""
    message_id = data.get('messageId') or data.get('message_id')
    conversation_id = data.get('conversationId') or data.get('conversation_id')

    session = await sio.get_session(sid)
    user_id = session.get('user_id') if session else None

    if conversation_id:
        # Broadcast read status to conversation
        await sio.emit(
            'message:read',
            {'messageId': message_id, 'userId': user_id},
            room=f"conversation:{conversation_id}",
            skip_sid=sid
        )
        logger.info(f"Message {message_id} marked as read by {user_id}")


@sio.on('message:read')
async def on_message_read(sid, data):
    """Alternative event name for message read"""
    await message_read(sid, data)


@sio.event
async def typing_start(sid, data):
    """Handle typing start event"""
    conversation_id = data.get('conversationId') or data.get('conversation_id')

    session = await sio.get_session(sid)
    user_id = session.get('user_id') if session else None

    if conversation_id and user_id:
        await sio.emit(
            'typing:start',
            {'userId': user_id, 'conversationId': conversation_id},
            room=f"conversation:{conversation_id}",
            skip_sid=sid
        )


@sio.on('typing:start')
async def on_typing_start(sid, data):
    """Alternative event name for typing start"""
    await typing_start(sid, data)


@sio.event
async def typing_stop(sid, data):
    """Handle typing stop event"""
    conversation_id = data.get('conversationId') or data.get('conversation_id')

    session = await sio.get_session(sid)
    user_id = session.get('user_id') if session else None

    if conversation_id and user_id:
        await sio.emit(
            'typing:stop',
            {'userId': user_id, 'conversationId': conversation_id},
            room=f"conversation:{conversation_id}",
            skip_sid=sid
        )


@sio.on('typing:stop')
async def on_typing_stop(sid, data):
    """Alternative event name for typing stop"""
    await typing_stop(sid, data)


# Helper function to emit to specific user
async def emit_to_user(user_id: str, event: str, data: dict):
    """Emit an event to all sessions of a specific user"""
    sessions = socket_manager.get_user_sessions(user_id)
    for session_id in sessions:
        await sio.emit(event, data, to=session_id)


# Helper function to emit to conversation
async def emit_to_conversation(conversation_id: str, event: str, data: dict, skip_sid: str = None):
    """Emit an event to all users in a conversation"""
    await sio.emit(event, data, room=f"conversation:{conversation_id}", skip_sid=skip_sid)
