import random
import string
import httpx
from typing import Optional
from app.core.config import settings


class SMSService:
    """Service for sending SMS messages via Termii or Twilio"""

    def __init__(self):
        # Check which SMS provider is configured
        if hasattr(settings, 'TERMII_API_KEY') and settings.TERMII_API_KEY:
            self.provider = 'termii'
            self.api_key = settings.TERMII_API_KEY
            self.sender_id = getattr(settings, 'TERMII_SENDER_ID', 'URGE')
        elif settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            self.provider = 'twilio'
            from twilio.rest import Client
            self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            self.from_number = settings.TWILIO_PHONE_NUMBER
        else:
            self.provider = 'console'

    def generate_otp(self, length: int = 6) -> str:
        """Generate a random OTP code"""
        return ''.join(random.choices(string.digits, k=length))

    async def send_sms(self, to_number: str, message: str) -> bool:
        """Send SMS message to a phone number"""
        if self.provider == 'console':
            # In development mode, just log the OTP
            print(f"\n{'='*60}")
            print(f"[SMS - DEVELOPMENT MODE]")
            print(f"To: {to_number}")
            print(f"Message: {message}")
            print(f"{'='*60}\n")
            return True

        elif self.provider == 'termii':
            return await self._send_via_termii(to_number, message)

        elif self.provider == 'twilio':
            return await self._send_via_twilio(to_number, message)

        return False

    async def _send_via_termii(self, to_number: str, message: str) -> bool:
        """Send SMS via Termii API"""
        try:
            # Termii API endpoint
            url = "https://api.ng.termii.com/api/sms/send"

            # Format phone number (ensure it has country code)
            if not to_number.startswith('+'):
                # Assume Nigerian number if no country code
                to_number = f"+234{to_number.lstrip('0')}"

            payload = {
                "to": to_number,
                "from": self.sender_id,
                "sms": message,
                "type": "plain",
                "channel": "generic",
                "api_key": self.api_key,
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)

                if response.status_code == 200:
                    result = response.json()
                    print(f"[Termii] SMS sent successfully: {result}")
                    return True
                else:
                    print(f"[Termii] Error: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Termii] Error sending SMS: {str(e)}")
            return False

    async def _send_via_twilio(self, to_number: str, message: str) -> bool:
        """Send SMS via Twilio"""
        try:
            message = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number
            )
            return message.sid is not None
        except Exception as e:
            print(f"[Twilio] Error sending SMS: {str(e)}")
            return False

    async def send_verification_code(self, phone_number: str, code: str) -> bool:
        """Send verification code via SMS"""
        message = f"Your URGE verification code is: {code}. Valid for {settings.OTP_EXPIRY_MINUTES} minutes."
        return await self.send_sms(phone_number, message)

    async def send_password_reset_code(self, phone_number: str, code: str) -> bool:
        """Send password reset code via SMS"""
        message = f"Your URGE password reset code is: {code}. Valid for {settings.OTP_EXPIRY_MINUTES} minutes."
        return await self.send_sms(phone_number, message)


# Singleton instance
sms_service = SMSService()
