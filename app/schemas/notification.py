from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID

from app.models.notification import DevicePlatform


# Notification schemas
class DeviceTokenRegister(BaseModel):
    """Schema for registering device token"""
    device_token: str = Field(..., min_length=1)
    platform: DevicePlatform


class NotificationSettings(BaseModel):
    """Schema for notification settings"""
    enabled: bool = True
    show_preview: bool = True
    sound: bool = True
    vibration: bool = True
    message_notifications: bool = True
    group_notifications: bool = True


class NotificationSettingsResponse(BaseModel):
    """Schema for notification settings response"""
    user_id: UUID
    settings: NotificationSettings

    class Config:
        from_attributes = True
