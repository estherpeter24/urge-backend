# API Testing Guide

Quick guide to test the URGE Backend API endpoints.

## Prerequisites

1. Server running on `http://localhost:8080`
2. PostgreSQL database set up
3. API testing tool (curl, Postman, or Thunder Client)

## 1. Register a New User

```bash
curl -X POST http://localhost:8080/api/auth/send-code \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+1234567890"
  }'
```

**Response:**
```json
{
  "success": true,
  "message": "Verification code sent to +1234567890"
}
```

**Note:** In development mode, the OTP will be printed in the server console.

## 2. Register with OTP

```bash
curl -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+1234567890",
    "password": "SecurePass123!",
    "display_name": "John Doe",
    "email": "john@example.com"
  }'
```

**Response:**
```json
{
  "user": {
    "id": "uuid",
    "phone_number": "+1234567890",
    "display_name": "John Doe",
    "email": "john@example.com",
    "role": "REGULAR",
    "is_verified": false,
    "is_online": false,
    ...
  },
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Save the token for subsequent requests!**

## 3. Login

```bash
curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+1234567890",
    "password": "SecurePass123!"
  }'
```

## 4. Get Current User Profile

```bash
curl -X GET http://localhost:8080/api/users/me \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## 5. Search Users

```bash
curl -X GET "http://localhost:8080/api/users/search?q=John&limit=10" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## 6. Create a Direct Conversation

```bash
curl -X POST http://localhost:8080/api/conversations \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "DIRECT",
    "participant_ids": ["other_user_uuid"]
  }'
```

## 7. Send a Message

```bash
curl -X POST http://localhost:8080/api/messages \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "conversation_uuid",
    "content": "Hello, this is my first message!",
    "message_type": "TEXT",
    "is_encrypted": false
  }'
```

## 8. Get Conversation Messages

```bash
curl -X GET "http://localhost:8080/api/conversations/{conversation_id}/messages?limit=50" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## 9. Create a Group

```bash
curl -X POST http://localhost:8080/api/groups \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Group",
    "description": "A cool group for friends",
    "member_ids": ["user_uuid_1", "user_uuid_2"],
    "is_public": false
  }'
```

## 10. Upload Media

```bash
curl -X POST http://localhost:8080/api/media/upload \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -F "file=@/path/to/image.jpg"
```

## WebSocket Testing (JavaScript)

```javascript
import io from 'socket.io-client';

// Connect to server
const socket = io('http://localhost:8080', {
  auth: {
    token: 'YOUR_JWT_TOKEN'
  }
});

// Listen for authentication
socket.on('authenticated', (data) => {
  console.log('Authenticated:', data);

  // Join a conversation
  socket.emit('join:conversation', {
    conversationId: 'conversation_uuid'
  });
});

// Listen for new messages
socket.on('message:received', (message) => {
  console.log('New message:', message);
});

// Send typing indicator
socket.emit('typing:start', {
  conversationId: 'conversation_uuid'
});

// Stop typing
setTimeout(() => {
  socket.emit('typing:stop', {
    conversationId: 'conversation_uuid'
  });
}, 3000);

// Listen for typing indicators
socket.on('typing:start', (data) => {
  console.log(`${data.userName} is typing...`);
});

socket.on('typing:stop', (data) => {
  console.log('User stopped typing');
});

// Listen for user status
socket.on('user:online', (data) => {
  console.log('User came online:', data.userId);
});

socket.on('user:offline', (data) => {
  console.log('User went offline:', data.userId);
});
```

## Testing with React Native App

1. Update your React Native app's API configuration:

```typescript
// src/constants/config.ts
export const API_CONFIG = {
  BASE_URL: 'http://YOUR_IP_ADDRESS:8080/api',
  SOCKET_URL: 'http://YOUR_IP_ADDRESS:8080',
  // ...
}
```

2. Ensure your phone/emulator can reach your computer:
   - Use your computer's local IP address (not localhost)
   - Example: `http://192.168.1.100:8080`

3. Make sure backend server is listening on `0.0.0.0`:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8080
   ```

## Common Issues

### 401 Unauthorized
- Check if token is included in Authorization header
- Verify token hasn't expired (15 minutes for access token)
- Use refresh token endpoint if expired

### 404 Not Found
- Verify the UUID in the request is correct
- Check if the resource exists in the database

### 403 Forbidden
- User doesn't have permission for this resource
- For conversations: user must be a participant
- For groups: user must be a member/admin

### Connection Refused
- Ensure server is running on the correct port
- Check firewall settings
- Verify DATABASE_URL in .env is correct

## Test Data Setup

Create a test script to populate sample data:

```python
# test_data.py
import requests

BASE_URL = "http://localhost:8080/api"

# Register 3 test users
users = []
for i in range(1, 4):
    response = requests.post(f"{BASE_URL}/auth/register", json={
        "phone_number": f"+123456789{i}",
        "password": "TestPass123!",
        "display_name": f"Test User {i}"
    })
    users.append(response.json())
    print(f"Created user {i}: {response.json()['user']['display_name']}")

# Get tokens
token1 = users[0]['token']

# Create a conversation
response = requests.post(
    f"{BASE_URL}/conversations",
    headers={"Authorization": f"Bearer {token1}"},
    json={
        "type": "DIRECT",
        "participant_ids": [users[1]['user']['id']]
    }
)
conversation = response.json()
print(f"Created conversation: {conversation['id']}")

# Send test messages
for i in range(5):
    requests.post(
        f"{BASE_URL}/messages",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "conversation_id": conversation['id'],
            "content": f"Test message {i + 1}",
            "message_type": "TEXT"
        }
    )

print("✅ Test data created successfully!")
```

Run it:
```bash
python test_data.py
```

## Performance Testing

Use Apache Bench (ab) to test API performance:

```bash
# Test login endpoint
ab -n 1000 -c 10 -p login.json -T application/json \
  http://localhost:8080/api/auth/login

# Test authenticated endpoint (with token)
ab -n 1000 -c 10 -H "Authorization: Bearer TOKEN" \
  http://localhost:8080/api/conversations
```

## Monitoring

Check server logs:
```bash
tail -f logs/app.log
```

Monitor database connections:
```sql
SELECT * FROM pg_stat_activity WHERE datname = 'urge_db';
```

---

Happy Testing! 🚀
