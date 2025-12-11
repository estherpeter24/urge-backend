from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from datetime import datetime

from ..core.database import get_db
from ..core.security import get_current_user
from ..core.config import settings
from ..models.user import User
from ..models.verification import UserVerificationRequest
from ..services.paystack_service import paystack_service, SUBSCRIPTION_PLANS
import uuid

router = APIRouter(prefix="/account", tags=["Account"])


# ============= Subscription Models =============

class SubscriptionPlan(BaseModel):
    id: str
    name: str
    description: str
    price: float
    period: str  # month, year, forever
    features: List[str]
    is_active: bool = True


class SubscriptionResponse(BaseModel):
    current_plan: str
    expires_at: Optional[str]
    plans: List[SubscriptionPlan]


class SubscribeRequest(BaseModel):
    plan_id: str
    success_url: str = "urge://subscription/success"
    cancel_url: str = "urge://subscription/cancel"


# ============= Verification Models =============

class VerificationRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    reason: str = Field(..., min_length=10, max_length=1000)
    social_proof: Optional[str] = None


class VerificationStatusResponse(BaseModel):
    is_verified: bool
    verification_status: str  # none, pending, approved, rejected
    requested_at: Optional[str]


# ============= Social Media Models =============

class SocialLinksUpdate(BaseModel):
    instagram: Optional[str] = None
    twitter: Optional[str] = None
    linkedin: Optional[str] = None
    tiktok: Optional[str] = None
    youtube: Optional[str] = None
    facebook: Optional[str] = None


class SocialLinksResponse(BaseModel):
    social_links: Dict[str, str]


# ============= Subscription Endpoints =============

@router.get("/subscriptions", response_model=SubscriptionResponse)
async def get_subscriptions(
    current_user: User = Depends(get_current_user),
):
    """Get user's subscription status and available plans"""
    plans = [
        SubscriptionPlan(
            id="free",
            name="Free",
            description="Basic features for personal use",
            price=0.0,
            period="forever",
            features=[
                "Basic messaging",
                "Group chats up to 10 members",
                "Standard support",
            ]
        ),
        SubscriptionPlan(
            id="premium",
            name="Premium",
            description="Enhanced features for power users",
            price=5000.0,  # 5,000 NGN
            period="month",
            features=[
                "Unlimited messaging",
                "Group chats up to 100 members",
                "Priority support",
                "Custom themes",
                "Read receipts control",
                "No ads",
            ]
        ),
        SubscriptionPlan(
            id="business",
            name="Business",
            description="Professional features for teams",
            price=10000.0,  # 10,000 NGN
            period="month",
            features=[
                "Everything in Premium",
                "Unlimited group members",
                "Admin dashboard",
                "Team management",
                "Analytics",
                "API access",
                "Dedicated support",
            ]
        ),
    ]

    return SubscriptionResponse(
        current_plan=current_user.subscription_plan or "free",
        expires_at=current_user.subscription_expires_at.isoformat() if current_user.subscription_expires_at else None,
        plans=plans,
    )


@router.post("/subscriptions/subscribe")
async def subscribe_to_plan(
    request: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Subscribe to a plan using Paystack"""
    valid_plans = ["free", "premium", "business"]
    if request.plan_id not in valid_plans:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan ID"
        )

    if request.plan_id == current_user.subscription_plan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already subscribed to this plan"
        )

    # For free plan, just update directly
    if request.plan_id == "free":
        current_user.subscription_plan = "free"
        current_user.subscription_expires_at = None
        await db.commit()
        await db.refresh(current_user)
        return {
            "success": True,
            "message": "Successfully switched to free plan",
            "current_plan": "free",
            "expires_at": None,
        }

    # Check if Paystack is configured
    if not settings.PAYSTACK_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment system is not configured. Please contact support."
        )

    # Get plan details
    plan = SUBSCRIPTION_PLANS.get(request.plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan"
        )

    try:
        # Get user email (required for Paystack)
        email = current_user.email
        if not email:
            # Generate a placeholder email using phone number
            email = f"{current_user.phone_number.replace('+', '')}@urge.app"

        # Generate unique reference
        reference = f"urge_{current_user.id}_{request.plan_id}_{uuid.uuid4().hex[:8]}"

        # Initialize Paystack transaction
        transaction = await paystack_service.initialize_transaction(
            email=email,
            amount=plan["amount"],  # Amount in cents
            currency=plan["currency"],
            reference=reference,
            callback_url=request.success_url,
            metadata={
                "user_id": current_user.id,
                "plan_id": request.plan_id,
                "custom_fields": [
                    {"display_name": "Plan", "variable_name": "plan", "value": plan["name"]},
                    {"display_name": "User ID", "variable_name": "user_id", "value": current_user.id},
                ]
            }
        )

        return {
            "success": True,
            "message": "Payment initialized",
            "authorization_url": transaction["authorization_url"],
            "access_code": transaction["access_code"],
            "reference": transaction["reference"],
            "paystack_public_key": settings.PAYSTACK_PUBLIC_KEY,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment processing error: {str(e)}"
        )


@router.post("/subscriptions/cancel")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel current subscription and revert to free plan"""
    if current_user.subscription_plan == "free":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already on the free plan"
        )

    # Cancel Paystack subscription if exists
    if current_user.paystack_subscription_code and current_user.paystack_email_token:
        try:
            await paystack_service.cancel_subscription(
                current_user.paystack_subscription_code,
                current_user.paystack_email_token
            )
        except Exception as e:
            # Log error but continue with local cancellation
            import logging
            logging.error(f"Failed to cancel Paystack subscription: {e}")

    current_user.subscription_plan = "free"
    current_user.subscription_expires_at = None
    current_user.paystack_subscription_code = None
    current_user.paystack_email_token = None
    await db.commit()

    return {
        "success": True,
        "message": "Subscription cancelled. You are now on the free plan.",
    }


@router.post("/subscriptions/verify-payment")
async def verify_payment(
    reference: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify Paystack payment and activate subscription"""
    from datetime import timedelta

    if not settings.PAYSTACK_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment system is not configured"
        )

    try:
        # Verify the transaction
        transaction = await paystack_service.verify_transaction(reference)

        if transaction["status"] != "success":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment not successful. Status: {transaction['status']}"
            )

        # Get plan_id from metadata
        metadata = transaction.get("metadata", {})
        plan_id = metadata.get("plan_id")
        user_id = metadata.get("user_id")

        # Verify this payment belongs to this user
        if user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Payment does not belong to this user"
            )

        if not plan_id or plan_id not in SUBSCRIPTION_PLANS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid plan in payment"
            )

        # Store authorization for future charges
        authorization = transaction.get("authorization", {})
        if authorization.get("reusable"):
            current_user.paystack_authorization_code = authorization.get("authorization_code")
            current_user.paystack_customer_code = transaction.get("customer", {}).get("customer_code")

        # Activate subscription
        current_user.subscription_plan = plan_id
        current_user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
        await db.commit()
        await db.refresh(current_user)

        return {
            "success": True,
            "message": f"Successfully subscribed to {plan_id} plan",
            "current_plan": current_user.subscription_plan,
            "expires_at": current_user.subscription_expires_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment verification failed: {str(e)}"
        )


@router.post("/subscriptions/create-payment-intent")
async def create_payment_intent(
    request: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a PaymentIntent for mobile in-app payment"""
    valid_plans = ["premium", "business"]
    if request.plan_id not in valid_plans:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan ID for payment"
        )

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment system is not configured"
        )

    try:
        # Get or create Stripe customer
        customer_id = await stripe_service.get_or_create_customer(
            user_id=current_user.id,
            stripe_customer_id=current_user.stripe_customer_id,
            email=current_user.email,
            phone=current_user.phone_number,
            name=current_user.display_name,
        )

        # Save customer ID if new
        if current_user.stripe_customer_id != customer_id:
            current_user.stripe_customer_id = customer_id
            await db.commit()

        # Create PaymentIntent
        payment_data = await stripe_service.create_payment_intent(
            customer_id=customer_id,
            plan_id=request.plan_id,
            user_id=current_user.id,
        )

        return {
            "success": True,
            "client_secret": payment_data["client_secret"],
            "payment_intent_id": payment_data["payment_intent_id"],
            "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment processing error: {str(e)}"
        )


@router.post("/subscriptions/confirm-payment")
async def confirm_payment(
    payment_intent_id: str,
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm payment and activate subscription (called after successful payment)"""
    from datetime import timedelta
    import stripe

    try:
        # Verify payment intent
        payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)

        if payment_intent.status != "succeeded":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment not completed. Status: {payment_intent.status}"
            )

        # Verify this payment belongs to this user
        if payment_intent.metadata.get("user_id") != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Payment does not belong to this user"
            )

        # Activate subscription
        current_user.subscription_plan = plan_id
        current_user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
        await db.commit()
        await db.refresh(current_user)

        return {
            "success": True,
            "message": f"Successfully subscribed to {plan_id} plan",
            "current_plan": current_user.subscription_plan,
            "expires_at": current_user.subscription_expires_at.isoformat(),
        }
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment verification failed: {str(e)}"
        )


@router.get("/subscriptions/billing-portal")
async def get_billing_portal(
    return_url: str = "urge://settings",
    current_user: User = Depends(get_current_user),
):
    """Get Stripe billing portal URL for managing subscription"""
    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No payment account found. Please subscribe to a plan first."
        )

    try:
        portal_url = await stripe_service.create_portal_session(
            customer_id=current_user.stripe_customer_id,
            return_url=return_url,
        )
        return {
            "success": True,
            "portal_url": portal_url,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create billing portal: {str(e)}"
        )


# ============= Verification Endpoints =============

@router.get("/verification/status", response_model=VerificationStatusResponse)
async def get_verification_status(
    current_user: User = Depends(get_current_user),
):
    """Get user's verification status"""
    return VerificationStatusResponse(
        is_verified=current_user.is_verified,
        verification_status=current_user.verification_status or "none",
        requested_at=current_user.verification_requested_at.isoformat() if current_user.verification_requested_at else None,
    )


@router.post("/verification/request")
async def request_verification(
    request: VerificationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a verification request"""
    if current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your account is already verified"
        )

    if current_user.verification_status == "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have a pending verification request"
        )

    # Check account age (7 days minimum)
    if current_user.created_at:
        account_age = (datetime.utcnow() - current_user.created_at).days
        if account_age < 7:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your account must be at least 7 days old. Current age: {account_age} days"
            )

    # Create verification request record with all details
    verification_request = UserVerificationRequest(
        user_id=current_user.id,
        full_name=request.full_name,
        reason=request.reason,
        social_proof=request.social_proof,
        status="pending",
    )
    db.add(verification_request)

    # Update user status
    current_user.verification_status = "pending"
    current_user.verification_requested_at = datetime.utcnow()

    await db.commit()
    await db.refresh(current_user)
    await db.refresh(verification_request)

    return {
        "success": True,
        "message": "Verification request submitted successfully. Our team will review it within 24-48 hours.",
        "verification_status": current_user.verification_status,
        "requested_at": current_user.verification_requested_at.isoformat(),
        "request_id": verification_request.id,
    }


# Admin endpoint to list pending verification requests
@router.get("/verification/pending")
async def list_pending_verifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin endpoint to list all pending verification requests with details"""
    # Check if current user is admin
    if current_user.role not in ["FOUNDER", "CO_FOUNDER", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view verification requests"
        )

    # Get all pending verification requests with user info
    result = await db.execute(
        select(UserVerificationRequest)
        .where(UserVerificationRequest.status == "pending")
        .order_by(UserVerificationRequest.created_at.desc())
    )
    requests = result.scalars().all()

    # Get user info for each request
    pending_requests = []
    for req in requests:
        user_result = await db.execute(select(User).where(User.id == req.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            pending_requests.append({
                "request_id": req.id,
                "user_id": req.user_id,
                "full_name": req.full_name,
                "reason": req.reason,
                "social_proof": req.social_proof,
                "status": req.status,
                "created_at": req.created_at.isoformat() if req.created_at else None,
                "user": {
                    "display_name": user.display_name,
                    "phone_number": user.phone_number,
                    "avatar_url": user.avatar_url,
                    "bio": user.bio,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                }
            })

    return {
        "success": True,
        "requests": pending_requests,
        "total": len(pending_requests),
    }


# Pydantic model for review request
class VerificationReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    rejection_reason: Optional[str] = None


# Admin endpoint to approve/reject verification (should be protected by admin role)
@router.post("/verification/review/{user_id}")
async def review_verification(
    user_id: str,
    review: VerificationReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin endpoint to approve or reject verification request"""
    # Check if current user is admin (FOUNDER or CO_FOUNDER)
    if current_user.role not in ["FOUNDER", "CO_FOUNDER", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can review verification requests"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if target_user.verification_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not have a pending verification request"
        )

    # Update the verification request record
    request_result = await db.execute(
        select(UserVerificationRequest)
        .where(UserVerificationRequest.user_id == user_id)
        .where(UserVerificationRequest.status == "pending")
    )
    verification_request = request_result.scalar_one_or_none()

    if review.action == "approve":
        target_user.is_verified = True
        target_user.verification_status = "approved"
        if verification_request:
            verification_request.status = "approved"
            verification_request.reviewed_by = current_user.id
            verification_request.reviewed_at = datetime.utcnow()
    else:
        target_user.verification_status = "rejected"
        if verification_request:
            verification_request.status = "rejected"
            verification_request.reviewed_by = current_user.id
            verification_request.reviewed_at = datetime.utcnow()
            verification_request.rejection_reason = review.rejection_reason

    await db.commit()

    return {
        "success": True,
        "message": f"Verification request {review.action}d",
        "user_id": user_id,
        "verification_status": target_user.verification_status,
        "is_verified": target_user.is_verified,
        "rejection_reason": review.rejection_reason if review.action == "reject" else None,
    }


# ============= Social Media Endpoints =============

@router.get("/social-links", response_model=SocialLinksResponse)
async def get_social_links(
    current_user: User = Depends(get_current_user),
):
    """Get user's connected social media accounts"""
    return SocialLinksResponse(
        social_links=current_user.social_links or {}
    )


@router.put("/social-links")
async def update_social_links(
    links: SocialLinksUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user's social media links"""
    # Build the new social links dict, removing empty values
    new_links = {}
    links_dict = links.model_dump()

    for platform, username in links_dict.items():
        if username:
            # Clean up the username (remove @ if present)
            clean_username = username.strip().lstrip("@")
            if clean_username:
                new_links[platform] = clean_username

    current_user.social_links = new_links
    flag_modified(current_user, "social_links")
    await db.commit()
    await db.refresh(current_user)

    return {
        "success": True,
        "message": "Social media links updated successfully",
        "social_links": current_user.social_links,
    }


@router.delete("/social-links/{platform}")
async def disconnect_social_account(
    platform: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect a specific social media account"""
    valid_platforms = ["instagram", "twitter", "linkedin", "tiktok", "youtube", "facebook"]
    if platform not in valid_platforms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid platform. Valid options: {', '.join(valid_platforms)}"
        )

    social_links = dict(current_user.social_links or {})
    if platform not in social_links:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{platform} is not connected"
        )

    del social_links[platform]
    current_user.social_links = social_links
    flag_modified(current_user, "social_links")
    await db.commit()
    await db.refresh(current_user)

    return {
        "success": True,
        "message": f"{platform} disconnected successfully",
        "social_links": current_user.social_links,
    }


# ============= Profile Settings Endpoints =============

@router.get("/profile")
async def get_account_profile(
    current_user: User = Depends(get_current_user),
):
    """Get full account profile with all settings"""
    return {
        "success": True,
        "data": current_user.to_dict(),
    }


@router.put("/profile")
async def update_account_profile(
    display_name: Optional[str] = None,
    email: Optional[str] = None,
    bio: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update account profile details"""
    if display_name is not None:
        if len(display_name.strip()) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Display name must be at least 2 characters"
            )
        current_user.display_name = display_name.strip()

    if email is not None:
        # Basic email validation
        if email and "@" not in email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format"
            )
        current_user.email = email if email else None

    if bio is not None:
        current_user.bio = bio.strip() if bio else None

    await db.commit()
    await db.refresh(current_user)

    return {
        "success": True,
        "message": "Profile updated successfully",
        "data": current_user.to_dict(),
    }
