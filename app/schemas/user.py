from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict
from datetime import datetime
from uuid import UUID

from app.models.user import UserRole


# User schemas
class UserBase(BaseModel):
    """Base user schema"""
    phone_number: str = Field(..., min_length=10, max_length=20)
    email: Optional[EmailStr] = None
    display_name: str = Field(..., min_length=1, max_length=100)
    bio: Optional[str] = None
    social_links: Optional[Dict[str, str]] = None


class UserCreate(BaseModel):
    """Schema for user registration"""
    phone_number: str = Field(..., min_length=10, max_length=20)
    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=8, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=100)
    verification_code: Optional[str] = None


class UserLogin(BaseModel):
    """Schema for user login"""
    phone_number: str = Field(..., min_length=10, max_length=20)
    password: str = Field(..., min_length=8, max_length=100)


class UserUpdate(BaseModel):
    """Schema for user profile update"""
    email: Optional[EmailStr] = None
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    social_links: Optional[Dict[str, str]] = None


class UserResponse(BaseModel):
    """Schema for user response"""
    id: UUID
    phone_number: str
    email: Optional[str] = None
    display_name: str
    avatar_url: Optional[str] = None
    role: UserRole
    bio: Optional[str] = None
    social_links: Optional[Dict[str, str]] = None
    is_verified: bool
    is_online: bool
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserSearchResponse(BaseModel):
    """Schema for user search response"""
    users: list[UserResponse]
    total: int
    limit: int
    offset: int


class UserStatusResponse(BaseModel):
    """Schema for user status response"""
    user_id: UUID
    is_online: bool
    last_seen: Optional[datetime] = None

    class Config:
        from_attributes = True
