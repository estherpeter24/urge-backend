from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.database import get_db
from app.schemas.auth import SuccessResponse
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.privacy import BlockedUser

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.post("/privacy/block/{user_id}", response_model=SuccessResponse)
async def block_user(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Block a user"""
    # Check if user exists
    user_to_block = db.query(User).filter(User.id == user_id).first()

    if not user_to_block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Check if already blocked
    existing_block = db.query(BlockedUser).filter(
        BlockedUser.blocker_id == current_user.id,
        BlockedUser.blocked_id == user_id
    ).first()

    if existing_block:
        return SuccessResponse(
            success=True,
            message="User already blocked"
        )

    # Create block
    block = BlockedUser(
        blocker_id=current_user.id,
        blocked_id=user_id
    )
    db.add(block)
    db.commit()

    return SuccessResponse(
        success=True,
        message="User blocked successfully"
    )


@router.delete("/privacy/unblock/{user_id}", response_model=SuccessResponse)
async def unblock_user(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Unblock a user"""
    # Find block
    block = db.query(BlockedUser).filter(
        BlockedUser.blocker_id == current_user.id,
        BlockedUser.blocked_id == user_id
    ).first()

    if not block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not blocked"
        )

    # Remove block
    db.delete(block)
    db.commit()

    return SuccessResponse(
        success=True,
        message="User unblocked successfully"
    )


@router.get("/privacy/blocked", response_model=list[UUID])
async def get_blocked_users(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get list of blocked user IDs"""
    blocks = db.query(BlockedUser).filter(
        BlockedUser.blocker_id == current_user.id
    ).all()

    return [block.blocked_id for block in blocks]
