from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from pydantic import BaseModel
from typing import List, Optional

from ..core.database import get_db
from ..core.security import get_current_user
from ..models.user import User

router = APIRouter(prefix="/users", tags=["Users"])


class UserResponse(BaseModel):
    id: str
    phone_number: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    bio: Optional[str]
    is_online: bool
    last_seen: Optional[str]

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    limit: int
    offset: int


class BatchUsersRequest(BaseModel):
    user_ids: List[str]


class BatchUsersResponse(BaseModel):
    users: List[UserResponse]


@router.get("", response_model=UserListResponse)
async def get_users(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get list of all users"""
    # Get total count
    count_result = await db.execute(select(User))
    all_users = count_result.scalars().all()
    total = len(all_users)

    # Get paginated users (excluding current user)
    result = await db.execute(
        select(User)
        .where(User.id != current_user.id)
        .offset(offset)
        .limit(limit)
    )
    users = result.scalars().all()

    return UserListResponse(
        users=[
            UserResponse(
                id=u.id,
                phone_number=u.phone_number,
                display_name=u.display_name,
                avatar_url=u.avatar_url,
                bio=u.bio,
                is_online=u.is_online,
                last_seen=u.last_seen.isoformat() if u.last_seen else None,
            )
            for u in users
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=UserListResponse)
async def search_users(
    q: str,
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search users by name or phone number"""
    search_term = f"%{q}%"

    result = await db.execute(
        select(User)
        .where(
            User.id != current_user.id,
            or_(
                User.display_name.ilike(search_term),
                User.phone_number.ilike(search_term),
            )
        )
        .offset(offset)
        .limit(limit)
    )
    users = result.scalars().all()

    return UserListResponse(
        users=[
            UserResponse(
                id=u.id,
                phone_number=u.phone_number,
                display_name=u.display_name,
                avatar_url=u.avatar_url,
                bio=u.bio,
                is_online=u.is_online,
                last_seen=u.last_seen.isoformat() if u.last_seen else None,
            )
            for u in users
        ],
        total=len(users),
        limit=limit,
        offset=offset,
    )


@router.post("/batch", response_model=BatchUsersResponse)
async def get_users_by_ids(
    request: BatchUsersRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get multiple users by their IDs (batch endpoint)"""
    if not request.user_ids:
        return BatchUsersResponse(users=[])

    result = await db.execute(
        select(User).where(User.id.in_(request.user_ids))
    )
    users = result.scalars().all()

    return BatchUsersResponse(
        users=[
            UserResponse(
                id=u.id,
                phone_number=u.phone_number,
                display_name=u.display_name,
                avatar_url=u.avatar_url,
                bio=u.bio,
                is_online=u.is_online,
                last_seen=u.last_seen.isoformat() if u.last_seen else None,
            )
            for u in users
        ]
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    """Get current user's profile"""
    return UserResponse(
        id=current_user.id,
        phone_number=current_user.phone_number,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        bio=current_user.bio,
        is_online=current_user.is_online,
        last_seen=current_user.last_seen.isoformat() if current_user.last_seen else None,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user by ID"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserResponse(
        id=user.id,
        phone_number=user.phone_number,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        bio=user.bio,
        is_online=user.is_online,
        last_seen=user.last_seen.isoformat() if user.last_seen else None,
    )


@router.get("/{user_id}/status")
async def get_user_status(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's online status"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return {
        "user_id": user.id,
        "is_online": user.is_online,
        "last_seen": user.last_seen.isoformat() if user.last_seen else None,
    }
