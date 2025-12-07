from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.auth import (
    SendCodeRequest,
    VerifyPhoneRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    AuthResponse,
    RefreshTokenRequest,
    TokenResponse,
    SuccessResponse
)
from app.schemas.user import UserCreate, UserLogin, UserUpdate, UserResponse
from app.services.auth_service import auth_service
from app.models.verification import VerificationType
from app.core.security import get_current_active_user, decode_token, create_access_token
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/send-code", response_model=SuccessResponse)
async def send_verification_code(
    request: SendCodeRequest,
    db: Session = Depends(get_db)
):
    """Send verification code to phone number - auto-detects login vs registration"""
    # Check if user exists to determine verification type
    user = db.query(User).filter(User.phone_number == request.phone_number).first()
    verification_type = VerificationType.LOGIN if user else VerificationType.REGISTRATION

    success = await auth_service.send_verification_code(
        request,
        verification_type,
        db
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification code"
        )

    return SuccessResponse(
        success=True,
        message=f"Verification code sent to {request.phone_number}"
    )


@router.post("/verify-phone", response_model=AuthResponse)
async def verify_phone(
    request: VerifyPhoneRequest,
    db: Session = Depends(get_db)
):
    """Verify phone number with OTP - works for both login and registration"""
    # Verify the code (supports both REGISTRATION and LOGIN types)
    verification_type = VerificationType.REGISTRATION

    # Try to verify with REGISTRATION first, fallback to LOGIN
    try:
        auth_service.verify_code(request, VerificationType.REGISTRATION, db)
    except:
        try:
            auth_service.verify_code(request, VerificationType.LOGIN, db)
            verification_type = VerificationType.LOGIN
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification code"
            )

    # Check if user exists
    user = db.query(User).filter(User.phone_number == request.phone_number).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please complete registration."
        )

    # Update user as verified
    user.is_verified = True
    db.commit()
    db.refresh(user)

    # Create tokens
    from app.core.security import create_access_token, create_refresh_token
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return AuthResponse(
        user=UserResponse.model_validate(user),
        token=access_token,
        refresh_token=refresh_token
    )


@router.post("/register", response_model=AuthResponse)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """Register a new user"""
    user, access_token, refresh_token = auth_service.register_user(user_data, db)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        token=access_token,
        refresh_token=refresh_token
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    login_data: UserLogin,
    db: Session = Depends(get_db)
):
    """Login user"""
    user, access_token, refresh_token = auth_service.login_user(login_data, db)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        token=access_token,
        refresh_token=refresh_token
    )


@router.post("/forgot-password", response_model=SuccessResponse)
async def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """Send password reset code"""
    # Check if user exists
    user = db.query(User).filter(User.phone_number == request.phone_number).first()

    if not user:
        # Don't reveal if user exists or not for security
        return SuccessResponse(
            success=True,
            message="If this phone number is registered, you will receive a reset code."
        )

    # Send reset code
    success = await auth_service.send_verification_code(
        SendCodeRequest(phone_number=request.phone_number),
        VerificationType.PASSWORD_RESET,
        db
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send reset code"
        )

    return SuccessResponse(
        success=True,
        message="Password reset code sent"
    )


@router.post("/reset-password", response_model=SuccessResponse)
async def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """Reset user password"""
    success = auth_service.reset_password(request, db)

    return SuccessResponse(
        success=True,
        message="Password reset successfully"
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """Refresh access token"""
    try:
        payload = decode_token(request.refresh_token)

        # Check token type
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

        # Create new access token
        access_token = create_access_token(data={"sub": user_id})

        from app.core.security import create_refresh_token
        new_refresh_token = create_refresh_token(data={"sub": user_id})

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )


@router.put("/profile", response_model=SuccessResponse)
async def update_profile(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update user profile"""
    # Update fields
    if user_data.email is not None:
        current_user.email = user_data.email
    if user_data.display_name is not None:
        current_user.display_name = user_data.display_name
    if user_data.bio is not None:
        current_user.bio = user_data.bio
    if user_data.avatar_url is not None:
        current_user.avatar_url = user_data.avatar_url
    if user_data.social_links is not None:
        current_user.social_links = user_data.social_links

    db.commit()
    db.refresh(current_user)

    return SuccessResponse(
        success=True,
        message="Profile updated successfully"
    )


@router.post("/logout", response_model=SuccessResponse)
async def logout(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Logout user"""
    auth_service.logout_user(current_user, db)

    return SuccessResponse(
        success=True,
        message="Logged out successfully"
    )
