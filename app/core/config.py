from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings and configuration"""

    # Application
    APP_NAME: str = "URGE"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8080

    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/urge_db"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT & Security
    SECRET_KEY: str = "your-super-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Encryption
    ENCRYPTION_KEY: str = "your-32-byte-encryption-key-here"

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8081,http://localhost:19000"

    @property
    def cors_origins(self) -> List[str]:
        """Parse ALLOWED_ORIGINS as a list"""
        if isinstance(self.ALLOWED_ORIGINS, str):
            return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
        return self.ALLOWED_ORIGINS

    # SMS/OTP (Termii - Primary)
    TERMII_API_KEY: str = ""
    TERMII_SENDER_ID: str = "URGE"

    # SMS/OTP (Twilio - Alternative)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # OTP Settings
    OTP_EXPIRY_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 3

    # AWS S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "urge-media-bucket"

    # Firebase
    FIREBASE_CREDENTIALS_PATH: str = "./firebase-credentials.json"

    # File Upload Limits (in bytes)
    MAX_IMAGE_SIZE: int = 10485760  # 10MB
    MAX_VIDEO_SIZE: int = 104857600  # 100MB
    MAX_DOCUMENT_SIZE: int = 20971520  # 20MB

    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@urge.app"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/app.log"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Support
    SUPPORT_EMAIL: str = "support@urge.app"
    PRIVACY_POLICY_URL: str = "https://urge.app/privacy"
    TERMS_URL: str = "https://urge.app/terms"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
