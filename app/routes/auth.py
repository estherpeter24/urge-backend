from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import re

from ..core.database import get_db
from ..core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from ..core.rate_limit import auth_rate_limit
from ..models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


# Phone validation regex - matches international formats
PHONE_REGEX = re.compile(r'^\+?[1-9]\d{6,14}$')


class RegisterRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=20)
    password: Optional[str] = None
    display_name: Optional[str] = None

    @field_validator('phone_number')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        # Remove spaces and dashes for validation
        cleaned = re.sub(r'[\s\-\(\)]', '', v)
        if not PHONE_REGEX.match(cleaned):
            raise ValueError('Invalid phone number format. Use international format like +1234567890')
        return cleaned


class LoginRequest(BaseModel):
    phone_number: str
    password: Optional[str] = None
    verification_code: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar: Optional[str] = None


@router.post("/register", response_model=TokenResponse)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    _rate_limit: int = Depends(auth_rate_limit),
):
    """Register a new user"""
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.phone_number == request.phone_number)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered"
        )

    # Create new user - generate random password hash if no password provided
    import secrets
    password = request.password if request.password else secrets.token_urlsafe(32)
    user = User(
        phone_number=request.phone_number,
        password_hash=get_password_hash(password),
        display_name=request.display_name,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Generate tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user.to_dict(),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
    _rate_limit: int = Depends(auth_rate_limit),
):
    """Login with phone number and verification code (or password as fallback)"""
    result = await db.execute(
        select(User).where(User.phone_number == request.phone_number)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    # Support verification code login (primary method)
    if request.verification_code:
        # In production, verify against stored code in database/cache
        # For now, accept mock code "123456" or any 6-digit code in dev mode
        if request.verification_code != "123456" and len(request.verification_code) != 6:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid verification code"
            )
    # Fallback to password if provided
    elif request.password:
        if not verify_password(request.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code or password required"
        )

    # Update last seen
    user.is_online = True
    user.last_seen = datetime.utcnow()
    await db.commit()

    # Generate tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user.to_dict(),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token"""
    payload = decode_token(request.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    # Generate new tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user.to_dict(),
    )


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Logout current user"""
    current_user.is_online = False
    current_user.last_seen = datetime.utcnow()
    await db.commit()

    return {"success": True, "message": "Logged out successfully"}


@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get current user information"""
    return current_user.to_dict()


@router.put("/profile")
async def update_profile(
    request: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user profile"""
    if request.display_name is not None:
        current_user.display_name = request.display_name

    if request.bio is not None:
        current_user.bio = request.bio

    if request.avatar is not None:
        current_user.avatar_url = request.avatar

    current_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)

    return {"success": True, "data": current_user.to_dict()}


class SendVerificationRequest(BaseModel):
    phone_number: str

@router.post("/send-verification")
async def send_verification_code(
    request: SendVerificationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send verification code to phone number"""
    # TODO: In production, integrate with SMS provider (Twilio, etc.)
    # For now, log the code server-side only (never return to client)
    import secrets
    code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    # In production: store code in database/cache with expiry and send via SMS
    print(f"[DEV] Verification code for {request.phone_number}: {code}")

    return {
        "success": True,
        "message": "Verification code sent",
    }


class VerifyPhoneRequest(BaseModel):
    phone_number: str
    code: str

@router.post("/verify-phone")
async def verify_phone(
    request: VerifyPhoneRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify phone number with code (mock implementation)"""
    # In production, verify against stored code
    if request.code == "123456":  # Mock verification
        result = await db.execute(
            select(User).where(User.phone_number == request.phone_number)
        )
        user = result.scalar_one_or_none()

        if user:
            user.is_verified = True
            await db.commit()

        return {"success": True, "message": "Phone verified successfully"}

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid verification code"
    )
