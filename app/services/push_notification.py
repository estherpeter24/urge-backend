"""
Firebase Cloud Messaging (FCM) Push Notification Service

This service handles sending push notifications to iOS and Android devices
using Firebase Cloud Messaging.
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

import firebase_admin
from firebase_admin import credentials, messaging

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class NotificationPayload:
    """Data class for notification payload"""
    title: str
    body: str
    data: Optional[Dict[str, str]] = None
    image_url: Optional[str] = None
    sound: str = "default"
    badge: Optional[int] = None


class PushNotificationService:
    """Service for sending push notifications via Firebase Cloud Messaging"""

    _initialized = False
    _app = None

    @classmethod
    def initialize(cls):
        """Initialize Firebase Admin SDK"""
        if cls._initialized:
            return True

        try:
            # Check if credentials are configured
            if settings.FIREBASE_CREDENTIALS_PATH:
                # Use JSON credentials file
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                cls._app = firebase_admin.initialize_app(cred)
                cls._initialized = True
                logger.info("Firebase initialized with credentials file")
                return True
            elif settings.FIREBASE_PROJECT_ID and settings.FIREBASE_PRIVATE_KEY and settings.FIREBASE_CLIENT_EMAIL:
                # Use individual credentials
                cred_dict = {
                    "type": "service_account",
                    "project_id": settings.FIREBASE_PROJECT_ID,
                    "private_key": settings.FIREBASE_PRIVATE_KEY.replace("\\n", "\n"),
                    "client_email": settings.FIREBASE_CLIENT_EMAIL,
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
                cred = credentials.Certificate(cred_dict)
                cls._app = firebase_admin.initialize_app(cred)
                cls._initialized = True
                logger.info("Firebase initialized with individual credentials")
                return True
            else:
                logger.warning("Firebase credentials not configured. Push notifications disabled.")
                return False
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            return False

    @classmethod
    def is_available(cls) -> bool:
        """Check if push notification service is available"""
        if not cls._initialized:
            cls.initialize()
        return cls._initialized

    @classmethod
    async def send_to_token(
        cls,
        token: str,
        payload: NotificationPayload,
        platform: str = "ios"
    ) -> bool:
        """
        Send push notification to a single device token

        Args:
            token: FCM device token
            payload: Notification payload
            platform: Target platform ("ios" or "android")

        Returns:
            True if sent successfully, False otherwise
        """
        if not cls.is_available():
            logger.warning("Push notification service not available")
            return False

        try:
            # Build notification
            notification = messaging.Notification(
                title=payload.title,
                body=payload.body,
                image=payload.image_url,
            )

            # Platform-specific configuration
            if platform == "ios":
                apns = messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound=payload.sound,
                            badge=payload.badge,
                            mutable_content=True,
                        )
                    )
                )
                android = None
            else:
                android = messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        sound=payload.sound,
                        channel_id="urge_messages",
                    )
                )
                apns = None

            # Build message
            message = messaging.Message(
                notification=notification,
                data=payload.data or {},
                token=token,
                apns=apns,
                android=android,
            )

            # Send message
            response = messaging.send(message)
            logger.info(f"Push notification sent successfully: {response}")
            return True

        except messaging.UnregisteredError:
            logger.warning(f"Device token is unregistered: {token[:20]}...")
            return False
        except messaging.SenderIdMismatchError:
            logger.error("Sender ID mismatch - check Firebase configuration")
            return False
        except Exception as e:
            logger.error(f"Failed to send push notification: {e}")
            return False

    @classmethod
    async def send_to_tokens(
        cls,
        tokens: List[Dict[str, str]],
        payload: NotificationPayload,
    ) -> Dict[str, Any]:
        """
        Send push notification to multiple device tokens

        Args:
            tokens: List of dicts with "token" and "platform" keys
            payload: Notification payload

        Returns:
            Dict with success/failure counts and failed tokens
        """
        if not cls.is_available():
            logger.warning("Push notification service not available")
            return {"success": 0, "failure": len(tokens), "failed_tokens": []}

        if not tokens:
            return {"success": 0, "failure": 0, "failed_tokens": []}

        success_count = 0
        failure_count = 0
        failed_tokens = []

        for token_info in tokens:
            token = token_info.get("token")
            platform = token_info.get("platform", "ios")

            if not token:
                continue

            result = await cls.send_to_token(token, payload, platform)
            if result:
                success_count += 1
            else:
                failure_count += 1
                failed_tokens.append(token)

        return {
            "success": success_count,
            "failure": failure_count,
            "failed_tokens": failed_tokens,
        }

    @classmethod
    async def send_message_notification(
        cls,
        tokens: List[Dict[str, str]],
        sender_name: str,
        message_text: str,
        conversation_id: str,
        message_id: str,
        sender_avatar: Optional[str] = None,
        is_group: bool = False,
        group_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a new message notification

        Args:
            tokens: List of device tokens with platform info
            sender_name: Name of the message sender
            message_text: Message content (truncated for notification)
            conversation_id: ID of the conversation
            message_id: ID of the message
            sender_avatar: URL of sender's avatar
            is_group: Whether this is a group message
            group_name: Name of the group (if group message)
        """
        # Truncate message for notification
        display_text = message_text[:100] + "..." if len(message_text) > 100 else message_text

        # Build title
        if is_group and group_name:
            title = f"{sender_name} in {group_name}"
        else:
            title = sender_name

        payload = NotificationPayload(
            title=title,
            body=display_text,
            image_url=sender_avatar,
            data={
                "type": "new_message",
                "conversation_id": conversation_id,
                "message_id": message_id,
                "sender_name": sender_name,
                "is_group": str(is_group).lower(),
            }
        )

        return await cls.send_to_tokens(tokens, payload)

    @classmethod
    async def send_call_notification(
        cls,
        tokens: List[Dict[str, str]],
        caller_name: str,
        caller_id: str,
        call_type: str = "audio",
        caller_avatar: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send an incoming call notification

        Args:
            tokens: List of device tokens with platform info
            caller_name: Name of the caller
            caller_id: ID of the caller
            call_type: Type of call ("audio" or "video")
            caller_avatar: URL of caller's avatar
        """
        call_type_display = "Video" if call_type == "video" else "Audio"

        payload = NotificationPayload(
            title=f"Incoming {call_type_display} Call",
            body=f"{caller_name} is calling you",
            image_url=caller_avatar,
            sound="ringtone",
            data={
                "type": "incoming_call",
                "caller_id": caller_id,
                "caller_name": caller_name,
                "call_type": call_type,
            }
        )

        return await cls.send_to_tokens(tokens, payload)

    @classmethod
    async def send_group_invite_notification(
        cls,
        tokens: List[Dict[str, str]],
        inviter_name: str,
        group_name: str,
        group_id: str,
    ) -> Dict[str, Any]:
        """
        Send a group invite notification
        """
        payload = NotificationPayload(
            title="Group Invitation",
            body=f"{inviter_name} invited you to join {group_name}",
            data={
                "type": "group_invite",
                "group_id": group_id,
                "group_name": group_name,
                "inviter_name": inviter_name,
            }
        )

        return await cls.send_to_tokens(tokens, payload)


# Singleton instance
push_service = PushNotificationService()
