from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.user import User, UserRole
from app.models.verification import VerificationCode, VerificationType
from app.schemas.user import UserCreate, UserLogin
from app.schemas.auth import SendCodeRequest, VerifyPhoneRequest, ResetPasswordRequest
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token
from app.core.config import settings
from app.utils.sms import sms_service


class AuthService:
    """Authentication service"""

    @staticmethod
    async def send_verification_code(
        request: SendCodeRequest,
        verification_type: VerificationType,
        db: Session
    ) -> bool:
        """Send verification code to phone number"""
        # Generate OTP
        code = sms_service.generate_otp()

        # Calculate expiry
        expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)

        # Delete old verification codes for this phone number
        db.query(VerificationCode).filter(
            VerificationCode.phone_number == request.phone_number,
            VerificationCode.type == verification_type
        ).delete()

        # Create new verification code
        verification = VerificationCode(
            phone_number=request.phone_number,
            code=code,
            type=verification_type,
            expires_at=expires_at
        )
        db.add(verification)
        db.commit()

        # Send SMS
        if verification_type == VerificationType.REGISTRATION:
            success = await sms_service.send_verification_code(request.phone_number, code)
        else:
            success = await sms_service.send_password_reset_code(request.phone_number, code)

        return success

    @staticmethod
    def verify_code(
        request: VerifyPhoneRequest,
        verification_type: VerificationType,
        db: Session
    ) -> bool:
        """Verify the OTP code"""
        # Find the verification code
        verification = db.query(VerificationCode).filter(
            VerificationCode.phone_number == request.phone_number,
            VerificationCode.code == request.code,
            VerificationCode.type == verification_type,
            VerificationCode.is_used == False
        ).first()

        if not verification:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code"
            )

        # Check if expired
        if verification.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code has expired"
            )

        # Check attempts
        if verification.attempts >= settings.OTP_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many attempts. Please request a new code."
            )

        # Increment attempts
        verification.attempts += 1

        # Mark as used
        verification.is_used = True
        db.commit()

        return True

    @staticmethod
    def register_user(user_data: UserCreate, db: Session) -> Tuple[User, str, str]:
        """Register a new user"""
        # Check if user already exists
        existing_user = db.query(User).filter(User.phone_number == user_data.phone_number).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number already registered"
            )

        # Check if email is already used
        if user_data.email:
            existing_email = db.query(User).filter(User.email == user_data.email).first()
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )

        # Hash password
        hashed_password = get_password_hash(user_data.password)

        # Create user
        new_user = User(
            phone_number=user_data.phone_number,
            email=user_data.email,
            display_name=user_data.display_name,
            password_hash=hashed_password,
            role=UserRole.REGULAR,
            is_verified=False
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # Create tokens
        access_token = create_access_token(data={"sub": str(new_user.id)})
        refresh_token = create_refresh_token(data={"sub": str(new_user.id)})

        return new_user, access_token, refresh_token

    @staticmethod
    def login_user(login_data: UserLogin, db: Session) -> Tuple[User, str, str]:
        """Login user"""
        # Find user
        user = db.query(User).filter(User.phone_number == login_data.phone_number).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect phone number or password"
            )

        # Verify password
        if not verify_password(login_data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect phone number or password"
            )

        # Update user online status
        user.is_online = True
        user.last_seen = datetime.utcnow()
        db.commit()
        db.refresh(user)

        # Create tokens
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        return user, access_token, refresh_token

    @staticmethod
    def reset_password(request: ResetPasswordRequest, db: Session) -> bool:
        """Reset user password"""
        # Verify the code first
        verify_request = VerifyPhoneRequest(
            phone_number=request.phone_number,
            code=request.code
        )

        AuthService.verify_code(verify_request, VerificationType.PASSWORD_RESET, db)

        # Find user
        user = db.query(User).filter(User.phone_number == request.phone_number).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Update password
        user.password_hash = get_password_hash(request.new_password)
        db.commit()

        return True

    @staticmethod
    def logout_user(user: User, db: Session) -> bool:
        """Logout user"""
        user.is_online = False
        user.last_seen = datetime.utcnow()
        db.commit()
        return True


# Create singleton instance
auth_service = AuthService()
