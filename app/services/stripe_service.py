import stripe
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from ..core.config import settings


# Initialize Stripe with API key
stripe.api_key = settings.STRIPE_SECRET_KEY

# Plan configuration
SUBSCRIPTION_PLANS = {
    "premium": {
        "name": "Premium",
        "price_id": settings.STRIPE_PREMIUM_PRICE_ID,
        "price": 4.99,
        "period": "month",
    },
    "business": {
        "name": "Business",
        "price_id": settings.STRIPE_BUSINESS_PRICE_ID,
        "price": 9.99,
        "period": "month",
    },
}


class StripeService:
    """Service for handling Stripe payment operations"""

    @staticmethod
    async def create_customer(user_id: str, email: Optional[str], phone: str, name: Optional[str]) -> str:
        """Create a Stripe customer for the user"""
        try:
            customer = stripe.Customer.create(
                metadata={"user_id": user_id},
                email=email,
                phone=phone,
                name=name or phone,
            )
            return customer.id
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to create Stripe customer: {str(e)}")

    @staticmethod
    async def get_or_create_customer(
        user_id: str,
        stripe_customer_id: Optional[str],
        email: Optional[str],
        phone: str,
        name: Optional[str]
    ) -> str:
        """Get existing customer or create a new one"""
        if stripe_customer_id:
            try:
                customer = stripe.Customer.retrieve(stripe_customer_id)
                if not customer.deleted:
                    return stripe_customer_id
            except stripe.error.StripeError:
                pass

        return await StripeService.create_customer(user_id, email, phone, name)

    @staticmethod
    async def create_checkout_session(
        customer_id: str,
        plan_id: str,
        success_url: str,
        cancel_url: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """Create a Stripe Checkout session for subscription"""
        plan = SUBSCRIPTION_PLANS.get(plan_id)
        if not plan:
            raise ValueError(f"Invalid plan: {plan_id}")

        if not plan["price_id"]:
            raise ValueError(f"No Stripe price ID configured for plan: {plan_id}")

        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                mode="subscription",
                line_items=[
                    {
                        "price": plan["price_id"],
                        "quantity": 1,
                    }
                ],
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "user_id": user_id,
                    "plan_id": plan_id,
                },
            )
            return {
                "session_id": session.id,
                "url": session.url,
            }
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to create checkout session: {str(e)}")

    @staticmethod
    async def create_payment_intent(
        customer_id: str,
        plan_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """Create a PaymentIntent for one-time payment (alternative to checkout)"""
        plan = SUBSCRIPTION_PLANS.get(plan_id)
        if not plan:
            raise ValueError(f"Invalid plan: {plan_id}")

        amount = int(plan["price"] * 100)  # Convert to cents

        try:
            intent = stripe.PaymentIntent.create(
                amount=amount,
                currency="usd",
                customer=customer_id,
                metadata={
                    "user_id": user_id,
                    "plan_id": plan_id,
                },
                automatic_payment_methods={"enabled": True},
            )
            return {
                "client_secret": intent.client_secret,
                "payment_intent_id": intent.id,
            }
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to create payment intent: {str(e)}")

    @staticmethod
    async def cancel_subscription(subscription_id: str) -> bool:
        """Cancel a Stripe subscription"""
        try:
            stripe.Subscription.cancel(subscription_id)
            return True
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to cancel subscription: {str(e)}")

    @staticmethod
    async def get_subscription(subscription_id: str) -> Optional[Dict[str, Any]]:
        """Get subscription details"""
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return {
                "id": subscription.id,
                "status": subscription.status,
                "current_period_end": datetime.fromtimestamp(subscription.current_period_end),
                "cancel_at_period_end": subscription.cancel_at_period_end,
            }
        except stripe.error.StripeError:
            return None

    @staticmethod
    def verify_webhook_signature(payload: bytes, sig_header: str) -> Dict[str, Any]:
        """Verify and parse webhook payload"""
        try:
            event = stripe.Webhook.construct_event(
                payload,
                sig_header,
                settings.STRIPE_WEBHOOK_SECRET
            )
            return event
        except ValueError as e:
            raise ValueError(f"Invalid payload: {str(e)}")
        except stripe.error.SignatureVerificationError as e:
            raise ValueError(f"Invalid signature: {str(e)}")

    @staticmethod
    async def create_portal_session(customer_id: str, return_url: str) -> str:
        """Create a billing portal session for subscription management"""
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return session.url
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to create portal session: {str(e)}")


stripe_service = StripeService()
