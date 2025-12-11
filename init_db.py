#!/usr/bin/env python3
"""
Database initialization script for URGE backend

This script creates all database tables and optionally seeds initial data.
"""

from app.db.database import engine, Base
from app.models import (
    User,
    Conversation,
    ConversationParticipant,
    Message,
    StarredMessage,
    Group,
    GroupMember,
    MediaFile,
    VerificationCode,
    DeviceToken,
    BlockedUser,
    NotificationSettings
)


def init_database():
    """Initialize database by creating all tables"""
    print("Creating database tables...")

    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("✓ Database tables created successfully!")

    except Exception as e:
        print(f"✗ Error creating database tables: {str(e)}")
        raise


def drop_all_tables():
    """Drop all database tables (use with caution!)"""
    print("WARNING: This will drop all tables!")
    response = input("Are you sure you want to continue? (yes/no): ")

    if response.lower() == "yes":
        print("Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        print("✓ All tables dropped successfully!")
    else:
        print("Operation cancelled.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--drop":
        drop_all_tables()
    else:
        init_database()

    print("\nDatabase initialization complete!")
    print("You can now start the server with: python -m uvicorn app.main:app --reload")
