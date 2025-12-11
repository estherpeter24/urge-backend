import httpx
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import hashlib
import hmac
import json

from ..core.config import settings


# Plan configuration with prices in Kobo (NGN) - 100 kobo = 1 NGN
# Prices are set in NGN which is Paystack's default supported currency
SUBSCRIPTION_PLANS = {
    "premium": {
        "name": "Premium",
        "amount": 500000,  # 5,000 NGN in kobo (approx $3.25 USD)
        "currency": "NGN",
        "interval": "monthly",
        "description": "Enhanced features for power users",
    },
    "business": {
        "name": "Business",
        "amount": 1000000,  # 10,000 NGN in kobo (approx $6.50 USD)
        "currency": "NGN",
        "interval": "monthly",
        "description": "Professional features for teams",
    },
}


class PaystackService:
    """Service for handling Paystack payment operations"""

    BASE_URL = "https://api.paystack.co"

    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.public_key = settings.PAYSTACK_PUBLIC_KEY

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    async def initialize_transaction(
        self,
        email: str,
        amount: int,
        currency: str = "USD",
        reference: str = None,
        callback_url: str = None,
        metadata: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Initialize a Paystack transaction

        Args:
            email: Customer email
            amount: Amount in smallest currency unit (cents for USD, kobo for NGN)
            currency: Currency code (USD, NGN, GHS, ZAR, KES)
            reference: Unique transaction reference
            callback_url: URL to redirect after payment
            metadata: Additional data to attach to transaction
        """
        url = f"{self.BASE_URL}/transaction/initialize"

        payload = {
            "email": email,
            "amount": amount,  # Amount in cents/kobo
            "currency": currency,
        }

        if reference:
            payload["reference"] = reference
        if callback_url:
            payload["callback_url"] = callback_url
        if metadata:
            payload["metadata"] = metadata

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=self._get_headers())
            data = response.json()

            if not data.get("status"):
                raise Exception(f"Paystack error: {data.get('message', 'Unknown error')}")

            return {
                "authorization_url": data["data"]["authorization_url"],
                "access_code": data["data"]["access_code"],
                "reference": data["data"]["reference"],
            }

    async def verify_transaction(self, reference: str) -> Dict[str, Any]:
        """Verify a transaction by reference"""
        url = f"{self.BASE_URL}/transaction/verify/{reference}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self._get_headers())
            data = response.json()

            if not data.get("status"):
                raise Exception(f"Paystack error: {data.get('message', 'Unknown error')}")

            return data["data"]

    async def create_subscription_plan(
        self,
        name: str,
        amount: int,
        interval: str = "monthly",
        currency: str = "USD",
        description: str = None,
    ) -> Dict[str, Any]:
        """Create a subscription plan on Paystack"""
        url = f"{self.BASE_URL}/plan"

        payload = {
            "name": name,
            "amount": amount,
            "interval": interval,
            "currency": currency,
        }

        if description:
            payload["description"] = description

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=self._get_headers())
            data = response.json()

            if not data.get("status"):
                raise Exception(f"Paystack error: {data.get('message', 'Unknown error')}")

            return data["data"]

    async def create_subscription(
        self,
        customer_email: str,
        plan_code: str,
        authorization_code: str = None,
    ) -> Dict[str, Any]:
        """Subscribe a customer to a plan"""
        url = f"{self.BASE_URL}/subscription"

        payload = {
            "customer": customer_email,
            "plan": plan_code,
        }

        if authorization_code:
            payload["authorization"] = authorization_code

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=self._get_headers())
            data = response.json()

            if not data.get("status"):
                raise Exception(f"Paystack error: {data.get('message', 'Unknown error')}")

            return data["data"]

    async def cancel_subscription(self, subscription_code: str, token: str) -> bool:
        """Cancel a subscription"""
        url = f"{self.BASE_URL}/subscription/disable"

        payload = {
            "code": subscription_code,
            "token": token,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=self._get_headers())
            data = response.json()

            return data.get("status", False)

    async def get_subscription(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        """Get subscription details"""
        url = f"{self.BASE_URL}/subscription/{subscription_id}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self._get_headers())
            data = response.json()

            if not data.get("status"):
                return None

            return data["data"]

    async def create_customer(
        self,
        email: str,
        first_name: str = None,
        last_name: str = None,
        phone: str = None,
        metadata: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Create a customer on Paystack"""
        url = f"{self.BASE_URL}/customer"

        payload = {"email": email}

        if first_name:
            payload["first_name"] = first_name
        if last_name:
            payload["last_name"] = last_name
        if phone:
            payload["phone"] = phone
        if metadata:
            payload["metadata"] = metadata

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=self._get_headers())
            data = response.json()

            if not data.get("status"):
                raise Exception(f"Paystack error: {data.get('message', 'Unknown error')}")

            return data["data"]

    async def get_customer(self, email_or_code: str) -> Optional[Dict[str, Any]]:
        """Get customer by email or customer code"""
        url = f"{self.BASE_URL}/customer/{email_or_code}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self._get_headers())
            data = response.json()

            if not data.get("status"):
                return None

            return data["data"]

    async def charge_authorization(
        self,
        email: str,
        amount: int,
        authorization_code: str,
        reference: str = None,
        currency: str = "USD",
        metadata: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Charge a previously authorized card"""
        url = f"{self.BASE_URL}/transaction/charge_authorization"

        payload = {
            "email": email,
            "amount": amount,
            "authorization_code": authorization_code,
            "currency": currency,
        }

        if reference:
            payload["reference"] = reference
        if metadata:
            payload["metadata"] = metadata

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=self._get_headers())
            data = response.json()

            if not data.get("status"):
                raise Exception(f"Paystack error: {data.get('message', 'Unknown error')}")

            return data["data"]

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Paystack webhook signature"""
        computed_signature = hmac.new(
            self.secret_key.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()

        return hmac.compare_digest(computed_signature, signature)

    async def list_banks(self, country: str = "nigeria") -> list:
        """List banks for transfers"""
        url = f"{self.BASE_URL}/bank"

        params = {"country": country}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=self._get_headers())
            data = response.json()

            if not data.get("status"):
                return []

            return data["data"]


paystack_service = PaystackService()
