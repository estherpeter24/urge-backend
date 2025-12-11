# URGE Backend API

FastAPI backend for the URGE messaging application with S3 storage integration.

## Features

- **Authentication**: JWT-based auth with phone number login
- **Media Upload**: Direct S3 upload via presigned URLs
- **User Management**: Profile, search, and batch user endpoints
- **RESTful API**: Clean REST endpoints with OpenAPI documentation

## Quick Start

### 1. Install Dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 3. AWS S3 Setup

1. Create an S3 bucket (e.g., `urge-dev-media`)
2. Configure bucket CORS:

```json
[
    {
        "AllowedHeaders": ["*"],
        "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
        "AllowedOrigins": ["*"],
        "ExposeHeaders": ["ETag"],
        "MaxAgeSeconds": 3600
    }
]
```

3. Create an IAM user with S3 access and add credentials to `.env`

### 4. Run the Server

```bash
# Development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 4
```

### 5. Access API Documentation

- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login with phone/password
- `POST /api/auth/refresh` - Refresh access token
- `POST /api/auth/logout` - Logout
- `GET /api/auth/me` - Get current user
- `PUT /api/auth/profile` - Update profile

### Media (S3)
- `POST /api/media/presigned-url` - Get presigned URL for S3 upload
- `POST /api/media/complete-upload` - Complete upload and create record
- `POST /api/media/upload` - Direct upload through server (fallback)
- `GET /api/media/{id}` - Get media info
- `DELETE /api/media/{id}` - Delete media
- `GET /api/media/{id}/download` - Get download URL

### Users
- `GET /api/users` - List users
- `GET /api/users/search?q=query` - Search users
- `POST /api/users/batch` - Get users by IDs
- `GET /api/users/{id}` - Get user by ID
- `GET /api/users/{id}/status` - Get user status

## S3 Upload Flow

1. **Client** requests presigned URL:
   ```
   POST /api/media/presigned-url
   {
     "file_name": "photo.jpg",
     "file_type": "image/jpeg",
     "folder": "avatars"
   }
   ```

2. **Server** returns presigned URL:
   ```json
   {
     "upload_url": "https://bucket.s3.amazonaws.com/...",
     "file_key": "avatars/user123/2025/01/abc_photo.jpg",
     "file_url": "https://media.urge.app/avatars/...",
     "expires_in": 3600
   }
   ```

3. **Client** uploads directly to S3:
   ```
   PUT {upload_url}
   Content-Type: image/jpeg
   Body: <file binary>
   ```

4. **Client** completes upload:
   ```
   POST /api/media/complete-upload
   {
     "file_key": "avatars/user123/2025/01/abc_photo.jpg",
     "file_url": "https://media.urge.app/avatars/...",
     "file_type": "IMAGE",
     "file_size": 1024000,
     "file_name": "photo.jpg",
     "mime_type": "image/jpeg"
   }
   ```

## Project Structure

```
backend/
├── app/
│   ├── core/
│   │   ├── config.py      # Settings & environment
│   │   ├── database.py    # Database connection
│   │   └── security.py    # JWT & password utils
│   ├── models/
│   │   ├── user.py        # User model
│   │   ├── media.py       # Media model
│   │   ├── conversation.py # Conversation models
│   │   └── message.py     # Message model
│   ├── routes/
│   │   ├── auth.py        # Auth endpoints
│   │   ├── users.py       # User endpoints
│   │   └── media.py       # Media/S3 endpoints
│   ├── schemas/
│   │   └── media.py       # Pydantic schemas
│   ├── services/
│   │   └── s3_service.py  # AWS S3 operations
│   └── main.py            # FastAPI app
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection string | `sqlite+aiosqlite:///./urge.db` |
| `AWS_ACCESS_KEY_ID` | AWS access key | - |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | - |
| `AWS_REGION` | AWS region | `us-east-1` |
| `S3_BUCKET_NAME` | S3 bucket name | `urge-dev-media` |
| `CDN_URL` | CloudFront CDN URL (optional) | - |
| `JWT_SECRET_KEY` | JWT signing key | - |
| `CORS_ORIGINS` | Allowed CORS origins | `http://localhost:3000` |

## License

MIT
