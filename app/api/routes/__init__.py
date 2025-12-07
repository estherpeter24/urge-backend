from fastapi import APIRouter

from app.api.routes import (
    auth,
    users,
    conversations,
    messages,
    groups,
    media,
    notifications,
    settings
)

# Create main API router
api_router = APIRouter()

# Include all route modules
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(conversations.router)
api_router.include_router(messages.router)
api_router.include_router(groups.router)
api_router.include_router(media.router)
api_router.include_router(notifications.router)
api_router.include_router(settings.router)
