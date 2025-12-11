from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.notification import DeviceTokenRegister, NotificationSettings, NotificationSettingsResponse
from app.schemas.auth import SuccessResponse
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.notification import DeviceToken, NotificationSettings as NotificationSettingsModel
from datetime import datetime

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.post("/register", response_model=SuccessResponse)
async def register_device_token(
    token_data: DeviceTokenRegister,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Register device token for push notifications"""
    # Check if token already exists
    existing_token = db.query(DeviceToken).filter(
        DeviceToken.device_token == token_data.device_token
    ).first()

    if existing_token:
        # Update existing token
        existing_token.user_id = current_user.id
        existing_token.platform = token_data.platform
        existing_token.is_active = True
        existing_token.last_used_at = datetime.utcnow()
    else:
        # Create new token
        new_token = DeviceToken(
            user_id=current_user.id,
            device_token=token_data.device_token,
            platform=token_data.platform,
            is_active=True
        )
        db.add(new_token)

    db.commit()

    return SuccessResponse(
        success=True,
        message="Device token registered successfully"
    )


@router.put("/settings", response_model=SuccessResponse)
async def update_notification_settings(
    settings_data: NotificationSettings,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update notification settings"""
    # Check if settings exist for user
    existing_settings = db.query(NotificationSettingsModel).filter(
        NotificationSettingsModel.user_id == current_user.id
    ).first()

    if existing_settings:
        # Update existing settings
        existing_settings.enabled = settings_data.enabled
        existing_settings.show_preview = settings_data.show_preview
        existing_settings.sound = settings_data.sound
        existing_settings.vibration = settings_data.vibration
        existing_settings.message_notifications = settings_data.message_notifications
        existing_settings.group_notifications = settings_data.group_notifications
    else:
        # Create new settings
        new_settings = NotificationSettingsModel(
            user_id=current_user.id,
            enabled=settings_data.enabled,
            show_preview=settings_data.show_preview,
            sound=settings_data.sound,
            vibration=settings_data.vibration,
            message_notifications=settings_data.message_notifications,
            group_notifications=settings_data.group_notifications
        )
        db.add(new_settings)

    db.commit()

    return SuccessResponse(
        success=True,
        message="Notification settings updated successfully"
    )


@router.get("/settings", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get notification settings"""
    # Retrieve notification settings from database
    user_settings = db.query(NotificationSettingsModel).filter(
        NotificationSettingsModel.user_id == current_user.id
    ).first()

    if user_settings:
        settings = NotificationSettings(
            enabled=user_settings.enabled,
            show_preview=user_settings.show_preview,
            sound=user_settings.sound,
            vibration=user_settings.vibration,
            message_notifications=user_settings.message_notifications,
            group_notifications=user_settings.group_notifications
        )
    else:
        # Return default settings if none exist
        settings = NotificationSettings(
            enabled=True,
            show_preview=True,
            sound=True,
            vibration=True,
            message_notifications=True,
            group_notifications=True
        )

    return NotificationSettingsResponse(
        user_id=current_user.id,
        settings=settings
    )
