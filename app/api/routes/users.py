from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List
from uuid import UUID

from app.db.database import get_db
from app.schemas.user import UserResponse, UserSearchResponse, UserStatusResponse
from app.core.security import get_current_active_user
from app.models.user import User

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=UserSearchResponse)
async def get_all_users(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all users (excluding current user)"""
    query = db.query(User).filter(User.id != current_user.id)

    total = query.count()
    users = query.offset(offset).limit(limit).all()

    return UserSearchResponse(
        users=[UserResponse.model_validate(user) for user in users],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/search", response_model=UserSearchResponse)
async def search_users(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Search for users by name or phone number"""
    query = db.query(User).filter(
        or_(
            User.display_name.ilike(f"%{q}%"),
            User.phone_number.ilike(f"%{q}%")
        ),
        User.id != current_user.id  # Exclude current user from search
    )

    total = query.count()
    users = query.offset(offset).limit(limit).all()

    return UserSearchResponse(
        users=[UserResponse.model_validate(user) for user in users],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get user profile by ID"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserResponse.model_validate(user)


@router.get("/{user_id}/status", response_model=UserStatusResponse)
async def get_user_status(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get user online status"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserStatusResponse(
        user_id=user.id,
        is_online=user.is_online,
        last_seen=user.last_seen
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user profile"""
    return UserResponse.model_validate(current_user)
