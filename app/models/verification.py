from sqlalchemy import Column, String, DateTime, Enum, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
import enum

from app.db.database import Base


class VerificationType(str, enum.Enum):
    """Verification type enumeration"""
    REGISTRATION = "REGISTRATION"
    LOGIN = "LOGIN"
    PASSWORD_RESET = "PASSWORD_RESET"


class VerificationCode(Base):
    """Verification code model for OTP"""
    __tablename__ = "verification_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    code = Column(String(10), nullable=False)
    type = Column(Enum(VerificationType), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    attempts = Column(Integer, default=0, nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<VerificationCode {self.phone_number} ({self.type})>"
