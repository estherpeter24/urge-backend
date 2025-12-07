from pydantic import BaseModel, Field
from typing import Optional
from app.schemas.user import UserResponse


# Authentication schemas
class SendCodeRequest(BaseModel):
    """Schema for sending OTP"""
    phone_number: str = Field(..., min_length=10, max_length=20)


class VerifyPhoneRequest(BaseModel):
    """Schema for verifying phone number"""
    phone_number: str = Field(..., min_length=10, max_length=20)
    code: str = Field(..., min_length=4, max_length=10)


class ForgotPasswordRequest(BaseModel):
    """Schema for forgot password"""
    phone_number: str = Field(..., min_length=10, max_length=20)


class ResetPasswordRequest(BaseModel):
    """Schema for reset password"""
    phone_number: str = Field(..., min_length=10, max_length=20)
    code: str = Field(..., min_length=4, max_length=10)
    new_password: str = Field(..., min_length=8, max_length=100)


class TokenResponse(BaseModel):
    """Schema for token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    """Schema for authentication response"""
    user: UserResponse
    token: str
    refresh_token: str


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request"""
    refresh_token: str


class SuccessResponse(BaseModel):
    """Generic success response"""
    success: bool
    message: Optional[str] = None
