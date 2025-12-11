from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import pyotp
import secrets
import hashlib

from ..core.database import get_db
from ..core.security import get_current_user
from ..models.user import User

router = APIRouter(prefix="/settings", tags=["Settings"])


# ============= Notification Models =============

class NotificationSettingsResponse(BaseModel):
    enabled: bool
    showPreview: bool
    sound: bool
    vibration: bool
    messageNotifications: bool
    groupNotifications: bool


class NotificationSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    showPreview: Optional[bool] = None
    sound: Optional[bool] = None
    vibration: Optional[bool] = None
    messageNotifications: Optional[bool] = None
    groupNotifications: Optional[bool] = None


class DeviceTokenRequest(BaseModel):
    token: str
    platform: str  # "ios" or "android"


# ============= Privacy Settings - Blocked Users =============

@router.get("/privacy/blocked")
async def get_blocked_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get list of blocked users with their details"""
    blocked_ids = current_user.blocked_users or []

    if not blocked_ids:
        return {"blocked_users": []}

    # Get user details for blocked users
    result = await db.execute(
        select(User).where(User.id.in_(blocked_ids))
    )
    blocked_users = result.scalars().all()

    return {
        "blocked_users": [
            {
                "id": user.id,
                "display_name": user.display_name,
                "phone_number": user.phone_number,
                "avatar_url": user.avatar_url,
            }
            for user in blocked_users
        ]
    }


@router.get("/privacy/blocked/check/{user_id}")
async def check_if_blocked(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if a user is blocked (bidirectional check)"""
    # Check if current user blocked target
    i_blocked_them = user_id in (current_user.blocked_users or [])

    # Check if target user blocked current user
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()

    they_blocked_me = False
    if target_user:
        they_blocked_me = current_user.id in (target_user.blocked_users or [])

    return {
        "i_blocked_them": i_blocked_them,
        "they_blocked_me": they_blocked_me,
        "is_blocked": i_blocked_them or they_blocked_me,
    }


@router.post("/privacy/block/{user_id}")
async def block_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Block a user"""
    # Can't block yourself
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot block yourself"
        )

    # Check if user exists
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Get current blocked list
    blocked_users = list(current_user.blocked_users or [])

    # Check if already blocked
    if user_id in blocked_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already blocked"
        )

    # Add to blocked list
    blocked_users.append(user_id)
    current_user.blocked_users = blocked_users
    flag_modified(current_user, "blocked_users")
    await db.commit()
    await db.refresh(current_user)

    return {
        "success": True,
        "message": f"User {target_user.display_name or user_id} has been blocked",
        "blocked_users": current_user.blocked_users,
    }


@router.delete("/privacy/unblock/{user_id}")
async def unblock_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unblock a user"""
    # Get current blocked list
    blocked_users = list(current_user.blocked_users or [])

    # Check if user is blocked
    if user_id not in blocked_users:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not blocked"
        )

    # Remove from blocked list
    blocked_users.remove(user_id)
    current_user.blocked_users = blocked_users
    flag_modified(current_user, "blocked_users")
    await db.commit()
    await db.refresh(current_user)

    return {
        "success": True,
        "message": "User has been unblocked",
        "blocked_users": current_user.blocked_users,
    }


# ============= Privacy Settings =============

@router.get("/privacy")
async def get_privacy_settings(
    current_user: User = Depends(get_current_user),
):
    """Get privacy settings"""
    return {
        "show_online_status": current_user.show_online_status,
        "show_last_seen": current_user.show_last_seen,
        "show_profile_photo": current_user.show_profile_photo,
        "show_read_receipts": current_user.show_read_receipts,
        "blocked_users_count": len(current_user.blocked_users or []),
    }


@router.put("/privacy")
async def update_privacy_settings(
    show_online_status: bool = None,
    show_last_seen: bool = None,
    show_profile_photo: bool = None,
    show_read_receipts: bool = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update privacy settings"""
    if show_online_status is not None:
        current_user.show_online_status = show_online_status
    if show_last_seen is not None:
        current_user.show_last_seen = show_last_seen
    if show_profile_photo is not None:
        current_user.show_profile_photo = show_profile_photo
    if show_read_receipts is not None:
        current_user.show_read_receipts = show_read_receipts

    await db.commit()
    await db.refresh(current_user)

    return {
        "success": True,
        "message": "Privacy settings updated",
        "settings": {
            "show_online_status": current_user.show_online_status,
            "show_last_seen": current_user.show_last_seen,
            "show_profile_photo": current_user.show_profile_photo,
            "show_read_receipts": current_user.show_read_receipts,
        }
    }


# ============= Notification Settings =============

@router.get("/notifications", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    current_user: User = Depends(get_current_user),
):
    """Get notification settings"""
    return NotificationSettingsResponse(
        enabled=current_user.notifications_enabled if current_user.notifications_enabled is not None else True,
        showPreview=current_user.notification_preview if current_user.notification_preview is not None else True,
        sound=current_user.notification_sound if current_user.notification_sound is not None else True,
        vibration=current_user.notification_vibration if current_user.notification_vibration is not None else True,
        messageNotifications=current_user.message_notifications if current_user.message_notifications is not None else True,
        groupNotifications=current_user.group_notifications if current_user.group_notifications is not None else True,
    )


@router.put("/notifications")
async def update_notification_settings(
    settings: NotificationSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update notification settings"""
    if settings.enabled is not None:
        current_user.notifications_enabled = settings.enabled
    if settings.showPreview is not None:
        current_user.notification_preview = settings.showPreview
    if settings.sound is not None:
        current_user.notification_sound = settings.sound
    if settings.vibration is not None:
        current_user.notification_vibration = settings.vibration
    if settings.messageNotifications is not None:
        current_user.message_notifications = settings.messageNotifications
    if settings.groupNotifications is not None:
        current_user.group_notifications = settings.groupNotifications

    await db.commit()
    await db.refresh(current_user)

    return {
        "success": True,
        "message": "Notification settings updated",
        "settings": {
            "enabled": current_user.notifications_enabled,
            "showPreview": current_user.notification_preview,
            "sound": current_user.notification_sound,
            "vibration": current_user.notification_vibration,
            "messageNotifications": current_user.message_notifications,
            "groupNotifications": current_user.group_notifications,
        }
    }


# ============= Device Token Registration =============

@router.post("/notifications/register")
async def register_device_token(
    request: DeviceTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a device token for push notifications"""
    if request.platform not in ["ios", "android"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Platform must be 'ios' or 'android'"
        )

    # Get current tokens
    device_tokens = list(current_user.device_tokens or [])

    # Check if token already exists
    existing_token = next(
        (t for t in device_tokens if t.get("token") == request.token),
        None
    )

    if existing_token:
        # Update existing token
        existing_token["platform"] = request.platform
        existing_token["updated_at"] = datetime.utcnow().isoformat()
    else:
        # Add new token
        device_tokens.append({
            "token": request.token,
            "platform": request.platform,
            "created_at": datetime.utcnow().isoformat(),
        })

    current_user.device_tokens = device_tokens
    flag_modified(current_user, "device_tokens")
    await db.commit()

    return {
        "success": True,
        "message": "Device token registered successfully",
    }


@router.delete("/notifications/unregister")
async def unregister_device_token(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unregister a device token"""
    device_tokens = list(current_user.device_tokens or [])

    # Remove the token
    device_tokens = [t for t in device_tokens if t.get("token") != token]

    current_user.device_tokens = device_tokens
    flag_modified(current_user, "device_tokens")
    await db.commit()

    return {
        "success": True,
        "message": "Device token unregistered successfully",
    }


# ============= Two-Factor Authentication =============

class TwoFactorVerifyRequest(BaseModel):
    code: str


def generate_backup_codes(count: int = 8) -> List[str]:
    """Generate backup codes for 2FA recovery"""
    return [secrets.token_hex(4).upper() for _ in range(count)]


def hash_backup_code(code: str) -> str:
    """Hash a backup code for secure storage"""
    return hashlib.sha256(code.encode()).hexdigest()


@router.get("/security/2fa/status")
async def get_2fa_status(
    current_user: User = Depends(get_current_user),
):
    """Get current 2FA status"""
    return {
        "enabled": current_user.two_factor_enabled or False,
        "has_backup_codes": bool(current_user.two_factor_backup_codes),
    }


@router.post("/security/2fa/setup")
async def setup_2fa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initialize 2FA setup - generates secret and QR code data"""
    if current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is already enabled"
        )

    # Generate a new secret
    secret = pyotp.random_base32()

    # Store the secret temporarily (not enabled yet)
    current_user.two_factor_secret = secret
    await db.commit()

    # Generate provisioning URI for QR code
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=current_user.phone_number,
        issuer_name="URGE"
    )

    return {
        "success": True,
        "secret": secret,
        "provisioning_uri": provisioning_uri,
        "message": "Scan the QR code with your authenticator app, then verify with a code"
    }


@router.post("/security/2fa/verify")
async def verify_and_enable_2fa(
    request: TwoFactorVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify TOTP code and enable 2FA"""
    if current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is already enabled"
        )

    if not current_user.two_factor_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please initiate 2FA setup first"
        )

    # Verify the code
    totp = pyotp.TOTP(current_user.two_factor_secret)
    if not totp.verify(request.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code"
        )

    # Generate backup codes
    backup_codes = generate_backup_codes()
    hashed_codes = [hash_backup_code(code) for code in backup_codes]

    # Enable 2FA
    current_user.two_factor_enabled = True
    current_user.two_factor_backup_codes = hashed_codes
    flag_modified(current_user, "two_factor_backup_codes")
    await db.commit()

    return {
        "success": True,
        "message": "Two-factor authentication has been enabled",
        "backup_codes": backup_codes,  # Show only once
    }


@router.post("/security/2fa/disable")
async def disable_2fa(
    request: TwoFactorVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable 2FA (requires current TOTP code)"""
    if not current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not enabled"
        )

    # Verify the code
    totp = pyotp.TOTP(current_user.two_factor_secret)
    if not totp.verify(request.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code"
        )

    # Disable 2FA
    current_user.two_factor_enabled = False
    current_user.two_factor_secret = None
    current_user.two_factor_backup_codes = []
    flag_modified(current_user, "two_factor_backup_codes")
    await db.commit()

    return {
        "success": True,
        "message": "Two-factor authentication has been disabled"
    }


@router.post("/security/2fa/regenerate-backup-codes")
async def regenerate_backup_codes(
    request: TwoFactorVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate backup codes (requires current TOTP code)"""
    if not current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not enabled"
        )

    # Verify the code
    totp = pyotp.TOTP(current_user.two_factor_secret)
    if not totp.verify(request.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code"
        )

    # Generate new backup codes
    backup_codes = generate_backup_codes()
    hashed_codes = [hash_backup_code(code) for code in backup_codes]

    current_user.two_factor_backup_codes = hashed_codes
    flag_modified(current_user, "two_factor_backup_codes")
    await db.commit()

    return {
        "success": True,
        "message": "Backup codes have been regenerated",
        "backup_codes": backup_codes,
    }
