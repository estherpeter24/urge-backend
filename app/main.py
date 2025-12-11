from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import socketio

from .core.config import settings
from .core.database import init_db
from .routes import media_router, auth_router, users_router, messages_router, conversations_router, groups_router, account_router, settings_router, webhooks_router
from .services.socket_manager import sio


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    """Application lifespan events"""
    # Startup
    print(f"Starting {settings.APP_NAME} API...")
    await init_db()
    print("Database initialized")
    print("Socket.IO server ready")
    yield
    # Shutdown
    print("Shutting down...")


fastapi_app = FastAPI(
    title=f"{settings.APP_NAME} API",
    description="Backend API for URGE messaging application",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - must be added before wrapping with Socket.IO
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create Socket.IO ASGI app that wraps FastAPI
# This is the main app that uvicorn should run
# socketio_path specifies the URL path for Socket.IO connections
app = socketio.ASGIApp(
    sio,
    fastapi_app,
    socketio_path='socket.io',
)


# Health check
@fastapi_app.get("/health")
async def health_check():
    return {"status": "healthy", "app": settings.APP_NAME}


@fastapi_app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.APP_NAME} API",
        "docs": "/docs",
        "version": "1.0.0",
    }


# Include routers
fastapi_app.include_router(auth_router, prefix="/api")
fastapi_app.include_router(users_router, prefix="/api")
fastapi_app.include_router(media_router, prefix="/api")
fastapi_app.include_router(messages_router, prefix="/api")
fastapi_app.include_router(conversations_router, prefix="/api")
fastapi_app.include_router(groups_router, prefix="/api")
fastapi_app.include_router(account_router, prefix="/api")
fastapi_app.include_router(settings_router, prefix="/api")
fastapi_app.include_router(webhooks_router, prefix="/api")


# Error handlers
@fastapi_app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors with user-friendly messages"""
    errors = exc.errors()
    # Build a more helpful error message
    error_messages = []
    for error in errors:
        field = '.'.join(str(loc) for loc in error.get('loc', []) if loc != 'body')
        msg = error.get('msg', 'Invalid value')
        if field:
            error_messages.append(f"{field}: {msg}")
        else:
            error_messages.append(msg)

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": error_messages[0] if error_messages else "Validation error",
            "detail": errors,
        }
    )


@fastapi_app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import logging
    logging.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal server error",
            "detail": str(exc) if settings.DEBUG else None,
        }
    )
