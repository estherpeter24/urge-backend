# URGE Backend API

Backend server for the URGE mobile messaging application built with FastAPI, PostgreSQL, and Socket.IO.

## Features

- 🔐 **JWT Authentication** - Secure token-based authentication with refresh tokens
- 📱 **Phone Number Registration** - OTP-based phone verification
- 💬 **Real-time Messaging** - WebSocket support via Socket.IO
- 👥 **Group Chat** - Create and manage group conversations
- 📁 **Media Upload** - Support for images, videos, audio, and documents
- 🔒 **End-to-End Encryption Ready** - AES-256-GCM encryption support
- 🔔 **Push Notifications** - Firebase Cloud Messaging integration
- 🚫 **Privacy Controls** - Block users, mute conversations
- ⭐ **Message Features** - Star, forward, reply, edit, delete messages

## Tech Stack

- **Framework**: FastAPI 0.104+
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Real-time**: Socket.IO (python-socketio)
- **Authentication**: JWT (python-jose)
- **Password Hashing**: bcrypt
- **File Storage**: Local storage (easily replaceable with S3)
- **SMS**: Twilio integration for OTP

## Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Redis (optional, for production WebSocket scaling)

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd urge-backend
```

### 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up PostgreSQL

```bash
# Create database
createdb urge_db

# Or using psql
psql -U postgres
CREATE DATABASE urge_db;
\q
```

### 5. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/urge_db

# JWT Secret (generate a secure random string)
SECRET_KEY=your-super-secret-key-change-this

# Twilio (for SMS OTP)
TWILIO_ACCOUNT_SID=your-twilio-sid
TWILIO_AUTH_TOKEN=your-twilio-token
TWILIO_PHONE_NUMBER=+1234567890

# AWS S3 (optional, for media storage)
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
S3_BUCKET_NAME=urge-media-bucket
```

### 6. Initialize database

```bash
python init_db.py
```

### 7. Run the server

```bash
# Development mode
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# Or using Python
python -m app.main
```

The server will start at `http://localhost:8080`

## API Documentation

Once the server is running, visit:

- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc

## API Endpoints

### Authentication

```
POST   /api/auth/register          - Register new user
POST   /api/auth/login             - Login user
POST   /api/auth/send-code         - Send OTP verification code
POST   /api/auth/verify-phone      - Verify phone with OTP
POST   /api/auth/forgot-password   - Request password reset
POST   /api/auth/reset-password    - Reset password with code
POST   /api/auth/refresh           - Refresh access token
PUT    /api/auth/profile           - Update user profile
POST   /api/auth/logout            - Logout user
```

### Users

```
GET    /api/users/search           - Search users
GET    /api/users/{id}             - Get user profile
GET    /api/users/{id}/status      - Get user online status
GET    /api/users/me               - Get current user
```

### Conversations

```
GET    /api/conversations                    - Get all conversations
GET    /api/conversations/{id}               - Get conversation details
POST   /api/conversations                    - Create new conversation
DELETE /api/conversations/{id}               - Delete conversation
GET    /api/conversations/{id}/messages      - Get messages (paginated)
PUT    /api/conversations/{id}/read          - Mark as read
PUT    /api/conversations/{id}/archive       - Archive conversation
PUT    /api/conversations/{id}/unarchive     - Unarchive conversation
PUT    /api/conversations/{id}/mute          - Mute conversation
PUT    /api/conversations/{id}/unmute        - Unmute conversation
PUT    /api/conversations/{id}/favorite      - Toggle favorite
DELETE /api/conversations/{id}/clear         - Clear history
```

### Messages

```
POST   /api/messages                - Send message
PUT    /api/messages/{id}           - Edit message
DELETE /api/messages/{id}           - Delete message
POST   /api/messages/forward        - Forward messages
POST   /api/messages/{id}/star      - Star message
DELETE /api/messages/{id}/star      - Unstar message
GET    /api/messages/starred        - Get starred messages
GET    /api/messages/search         - Search messages
```

### Groups

```
POST   /api/groups                          - Create group
GET    /api/groups/{id}                     - Get group details
PUT    /api/groups/{id}                     - Update group
DELETE /api/groups/{id}                     - Delete group
POST   /api/groups/{id}/members             - Add members
DELETE /api/groups/{id}/members/{userId}    - Remove member
PUT    /api/groups/{id}/members/{userId}/role - Update member role
POST   /api/groups/{id}/leave               - Leave group
GET    /api/groups/{id}/members             - Get group members
```

### Media

```
POST   /api/media/upload            - Upload media file
GET    /api/media/{filename}        - Download media file
DELETE /api/media/{id}              - Delete media file
GET    /api/media/{id}/thumbnail    - Get media thumbnail
```

### Notifications

```
POST   /api/notifications/register  - Register device token
PUT    /api/notifications/settings  - Update notification settings
GET    /api/notifications/settings  - Get notification settings
```

### Settings & Privacy

```
POST   /api/settings/privacy/block/{userId}    - Block user
DELETE /api/settings/privacy/unblock/{userId}  - Unblock user
GET    /api/settings/privacy/blocked           - Get blocked users
```

## WebSocket Events (Socket.IO)

### Client → Server

```javascript
// Connection
socket.connect({ auth: { token: 'JWT_TOKEN' } });

// Join/Leave conversation
socket.emit('join:conversation', { conversationId: 'uuid' });
socket.emit('leave:conversation', { conversationId: 'uuid' });

// Messages
socket.emit('message:sent', messageData);
socket.emit('message:delivered', { messageId: 'uuid' });
socket.emit('message:read', { messageId: 'uuid', conversationId: 'uuid' });

// Typing indicators
socket.emit('typing:start', { conversationId: 'uuid' });
socket.emit('typing:stop', { conversationId: 'uuid' });
```

### Server → Client

```javascript
// Connection
socket.on('authenticated', (data) => { /* { userId } */ });

// Messages
socket.on('message:received', (message) => { /* New message */ });
socket.on('message:delivered', (data) => { /* { messageId, userId } */ });
socket.on('message:read', (data) => { /* { messageId, conversationId, userId } */ });

// Typing indicators
socket.on('typing:start', (data) => { /* { conversationId, userId, userName } */ });
socket.on('typing:stop', (data) => { /* { conversationId, userId } */ });

// User status
socket.on('user:online', (data) => { /* { userId } */ });
socket.on('user:offline', (data) => { /* { userId, lastSeen } */ });
```

## Database Schema

### Tables

- `users` - User accounts and profiles
- `conversations` - Chat conversations (direct and group)
- `conversation_participants` - Many-to-many relationship
- `messages` - Chat messages
- `starred_messages` - User starred messages
- `groups` - Group chat details
- `group_members` - Group membership
- `media_files` - Uploaded media metadata
- `verification_codes` - OTP codes for phone verification
- `device_tokens` - Push notification tokens
- `blocked_users` - User blocking relationships

## Frontend Integration

### Update React Native App Configuration

In your React Native app (`urge-talk-master`), update the API URLs:

```typescript
// src/constants/config.ts
export const API_CONFIG = {
  BASE_URL: __DEV__
    ? 'http://localhost:8080/api'  // Your backend URL
    : 'https://api.urge.app/api',
  SOCKET_URL: __DEV__
    ? 'http://localhost:8080'      // Your backend URL
    : 'https://api.urge.app',
  TIMEOUT: 30000,
  MAX_RETRIES: 3
}
```

### Testing the Integration

1. Start the backend server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
   ```

2. Start your React Native app:
   ```bash
   cd urge-talk-master
   npm start
   ```

3. Test authentication:
   - Register a new user
   - Receive OTP (check console in development mode)
   - Login and start messaging

## Development

### Project Structure

```
urge-backend/
├── app/
│   ├── api/
│   │   └── routes/          # API endpoint routes
│   ├── core/
│   │   ├── config.py       # Configuration settings
│   │   └── security.py     # JWT & security utilities
│   ├── db/
│   │   └── database.py     # Database connection
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic schemas
│   ├── services/           # Business logic services
│   ├── utils/              # Utility functions
│   └── main.py            # Application entry point
├── tests/                  # Test files
├── uploads/               # Uploaded media files
├── logs/                  # Application logs
├── init_db.py            # Database initialization
├── requirements.txt      # Python dependencies
├── .env.example         # Environment variables template
└── README.md           # This file
```

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
# Format code
black app/

# Check linting
flake8 app/
```

### Database Migrations

For production, use Alembic for database migrations:

```bash
# Initialize Alembic
alembic init alembic

# Create migration
alembic revision --autogenerate -m "Initial migration"

# Apply migration
alembic upgrade head
```

## Deployment

### Using Docker

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Build and run:

```bash
docker build -t urge-backend .
docker run -p 8080:8080 --env-file .env urge-backend
```

### Using Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: urge_db
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  api:
    build: .
    ports:
      - "8080:8080"
    env_file:
      - .env
    depends_on:
      - db
      - redis
    volumes:
      - ./uploads:/app/uploads

volumes:
  postgres_data:
```

Run:

```bash
docker-compose up -d
```

## Environment Variables

See `.env.example` for all available configuration options.

### Required Variables

- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - JWT signing secret
- `TWILIO_*` - Twilio credentials for SMS

### Optional Variables

- `AWS_*` - AWS S3 for media storage
- `FIREBASE_CREDENTIALS_PATH` - Firebase for push notifications
- `REDIS_URL` - Redis for WebSocket scaling

## Security Considerations

1. **Change SECRET_KEY** in production - Use a strong random string
2. **Enable HTTPS** - Always use TLS in production
3. **Rate Limiting** - Configure rate limits for sensitive endpoints
4. **Input Validation** - All inputs are validated with Pydantic
5. **SQL Injection** - Protected via SQLAlchemy ORM
6. **CORS** - Configure allowed origins properly

## Performance Optimization

1. **Database Indexing** - Key fields are indexed
2. **Connection Pooling** - Database pool configured
3. **Async Operations** - FastAPI async support
4. **Pagination** - All list endpoints support pagination
5. **Caching** - Add Redis caching for frequently accessed data

## Troubleshooting

### Database Connection Error

```bash
# Check PostgreSQL is running
pg_isready

# Check connection string in .env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE
```

### SMS Not Sending

In development mode, OTP codes are printed to console. For production:

1. Verify Twilio credentials
2. Check Twilio phone number is verified
3. Ensure destination numbers are verified (Twilio trial)

### WebSocket Connection Issues

1. Check CORS settings in `.env`
2. Ensure Socket.IO client version matches
3. Verify JWT token is being sent in auth

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is proprietary software for URGE Messaging Application.

## Support

For issues and questions:
- Email: support@urge.app
- Documentation: http://localhost:8080/docs

---

**Built with ❤️ for URGE Mobile App**
