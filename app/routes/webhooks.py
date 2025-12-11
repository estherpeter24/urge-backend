from fastapi import APIRouter, Request, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
import logging

from ..core.database import get_db
from ..core.config import settings
from ..models.user import User
from ..services.paystack_service import paystack_service, SUBSCRIPTION_PLANS

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = logging.getLogger(__name__)


@router.post("/paystack")
async def paystack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Paystack webhook events"""
    payload = await request.body()
    sig_header = request.headers.get("x-paystack-signature")

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Paystack signature header"
        )

    # Verify webhook signature
    if not paystack_service.verify_webhook_signature(payload, sig_header):
        logger.error("Invalid Paystack webhook signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature"
        )

    try:
        import json
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    event_type = event.get("event")
    data = event.get("data", {})

    logger.info(f"Received Paystack webhook: {event_type}")

    # Handle different event types
    if event_type == "charge.success":
        await handle_charge_success(data, db)

    elif event_type == "subscription.create":
        await handle_subscription_created(data, db)

    elif event_type == "subscription.disable":
        await handle_subscription_disabled(data, db)

    elif event_type == "subscription.not_renew":
        await handle_subscription_not_renew(data, db)

    elif event_type == "invoice.create":
        await handle_invoice_created(data, db)

    elif event_type == "invoice.payment_failed":
        await handle_invoice_payment_failed(data, db)

    elif event_type == "invoice.update":
        await handle_invoice_updated(data, db)

    return {"status": "success", "event_type": event_type}


async def handle_charge_success(data: dict, db: AsyncSession):
    """Handle successful charge (one-time payment)"""
    metadata = data.get("metadata", {})
    user_id = metadata.get("user_id")
    plan_id = metadata.get("plan_id")
    reference = data.get("reference")

    if not user_id:
        logger.error(f"No user_id in charge metadata: {reference}")
        return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        logger.error(f"User not found: {user_id}")
        return

    # Store authorization for future charges
    authorization = data.get("authorization", {})
    if authorization.get("reusable"):
        user.paystack_authorization_code = authorization.get("authorization_code")

    customer = data.get("customer", {})
    if customer.get("customer_code"):
        user.paystack_customer_code = customer.get("customer_code")

    # Activate subscription if plan_id is provided
    if plan_id and plan_id in SUBSCRIPTION_PLANS:
        user.subscription_plan = plan_id
        user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
        logger.info(f"User {user_id} subscribed to {plan_id} via charge")

    await db.commit()
    logger.info(f"Charge success processed for user {user_id}")


async def handle_subscription_created(data: dict, db: AsyncSession):
    """Handle new subscription created"""
    customer = data.get("customer", {})
    customer_code = customer.get("customer_code")
    subscription_code = data.get("subscription_code")
    email_token = data.get("email_token")
    plan = data.get("plan", {})

    if not customer_code:
        logger.warning("No customer_code in subscription data")
        return

    result = await db.execute(
        select(User).where(User.paystack_customer_code == customer_code)
    )
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(f"No user found for customer: {customer_code}")
        return

    user.paystack_subscription_code = subscription_code
    user.paystack_email_token = email_token

    # Determine plan from Paystack plan
    plan_code = plan.get("plan_code")
    if plan_code == settings.PAYSTACK_PREMIUM_PLAN_CODE:
        user.subscription_plan = "premium"
    elif plan_code == settings.PAYSTACK_BUSINESS_PLAN_CODE:
        user.subscription_plan = "business"

    # Set expiration based on next_payment_date
    next_payment = data.get("next_payment_date")
    if next_payment:
        try:
            user.subscription_expires_at = datetime.fromisoformat(next_payment.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
    else:
        user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)

    await db.commit()
    logger.info(f"Subscription created for user {user.id}")


async def handle_subscription_disabled(data: dict, db: AsyncSession):
    """Handle subscription cancellation"""
    subscription_code = data.get("subscription_code")

    if not subscription_code:
        return

    result = await db.execute(
        select(User).where(User.paystack_subscription_code == subscription_code)
    )
    user = result.scalar_one_or_none()

    if not user:
        return

    user.subscription_plan = "free"
    user.subscription_expires_at = None
    user.paystack_subscription_code = None
    user.paystack_email_token = None

    await db.commit()
    logger.info(f"Subscription disabled for user {user.id}")


async def handle_subscription_not_renew(data: dict, db: AsyncSession):
    """Handle subscription that won't renew"""
    subscription_code = data.get("subscription_code")

    if not subscription_code:
        return

    result = await db.execute(
        select(User).where(User.paystack_subscription_code == subscription_code)
    )
    user = result.scalar_one_or_none()

    if not user:
        return

    # Don't immediately cancel - wait until expiration
    logger.warning(f"Subscription will not renew for user {user.id}")


async def handle_invoice_created(data: dict, db: AsyncSession):
    """Handle invoice creation (subscription renewal)"""
    subscription = data.get("subscription", {})
    subscription_code = subscription.get("subscription_code")

    if not subscription_code:
        return

    logger.info(f"Invoice created for subscription {subscription_code}")


async def handle_invoice_payment_failed(data: dict, db: AsyncSession):
    """Handle failed invoice payment"""
    subscription = data.get("subscription", {})
    subscription_code = subscription.get("subscription_code")

    if not subscription_code:
        return

    result = await db.execute(
        select(User).where(User.paystack_subscription_code == subscription_code)
    )
    user = result.scalar_one_or_none()

    if not user:
        return

    # Don't immediately cancel - Paystack will retry
    logger.warning(f"Invoice payment failed for user {user.id}")


async def handle_invoice_updated(data: dict, db: AsyncSession):
    """Handle invoice update (successful payment)"""
    subscription = data.get("subscription", {})
    subscription_code = subscription.get("subscription_code")
    paid = data.get("paid")

    if not subscription_code or not paid:
        return

    result = await db.execute(
        select(User).where(User.paystack_subscription_code == subscription_code)
    )
    user = result.scalar_one_or_none()

    if not user:
        return

    # Extend subscription by 30 days
    user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
    await db.commit()
    logger.info(f"Invoice paid, subscription renewed for user {user.id}")


# Keep Stripe webhook for backwards compatibility
@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhook events (legacy)"""
    return {"status": "deprecated", "message": "Please use Paystack webhooks"}
