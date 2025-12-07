# Deployment Guide

Guide for deploying URGE Backend to production.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Database Setup](#database-setup)
4. [Deployment Options](#deployment-options)
5. [Security Checklist](#security-checklist)
6. [Monitoring](#monitoring)

## Prerequisites

- Linux server (Ubuntu 20.04+ recommended)
- Python 3.9+
- PostgreSQL 12+
- Redis 6+ (for WebSocket scaling)
- Domain name with SSL certificate
- Firewall configured

## Environment Setup

### 1. System Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install -y python3-pip python3-venv postgresql postgresql-contrib redis-server nginx

# Install certbot for SSL
sudo apt install -y certbot python3-certbot-nginx
```

### 2. Create Application User

```bash
sudo useradd -m -s /bin/bash urge
sudo usermod -aG sudo urge
```

### 3. Clone Repository

```bash
sudo su - urge
git clone <your-repo-url> /home/urge/urge-backend
cd /home/urge/urge-backend
```

### 4. Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

## Database Setup

### 1. Create PostgreSQL Database

```bash
sudo -u postgres psql

CREATE DATABASE urge_production;
CREATE USER urge_user WITH ENCRYPTED PASSWORD 'strong_password_here';
GRANT ALL PRIVILEGES ON DATABASE urge_production TO urge_user;
\q
```

### 2. Configure PostgreSQL for Production

Edit `/etc/postgresql/12/main/postgresql.conf`:

```conf
max_connections = 100
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 2621kB
min_wal_size = 1GB
max_wal_size = 4GB
```

Restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

### 3. Initialize Database

```bash
cd /home/urge/urge-backend
source venv/bin/activate
python init_db.py
```

## Deployment Options

### Option 1: Systemd Service (Recommended)

#### 1. Create Service File

`/etc/systemd/system/urge-api.service`:

```ini
[Unit]
Description=URGE Backend API
After=network.target postgresql.service redis.service

[Service]
User=urge
Group=urge
WorkingDirectory=/home/urge/urge-backend
Environment="PATH=/home/urge/urge-backend/venv/bin"
ExecStart=/home/urge/urge-backend/venv/bin/gunicorn \
    -w 4 \
    -k uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8080 \
    --access-logfile /home/urge/urge-backend/logs/access.log \
    --error-logfile /home/urge/urge-backend/logs/error.log \
    app.main:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 2. Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable urge-api
sudo systemctl start urge-api
sudo systemctl status urge-api
```

### Option 2: Docker

#### 1. Build Image

```bash
docker build -t urge-backend:latest .
```

#### 2. Docker Compose for Production

`docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: urge_production
      POSTGRES_USER: urge_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: always
    networks:
      - urge-network

  redis:
    image: redis:7-alpine
    restart: always
    networks:
      - urge-network

  api:
    image: urge-backend:latest
    ports:
      - "8080:8080"
    environment:
      - DATABASE_URL=postgresql://urge_user:${DB_PASSWORD}@db:5432/urge_production
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
      - ENVIRONMENT=production
      - DEBUG=false
    volumes:
      - ./uploads:/app/uploads
      - ./logs:/app/logs
    depends_on:
      - db
      - redis
    restart: always
    networks:
      - urge-network

volumes:
  postgres_data:

networks:
  urge-network:
    driver: bridge
```

Run:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### Option 3: Kubernetes

Create deployment files in `k8s/` directory:

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: urge-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: urge-api
  template:
    metadata:
      labels:
        app: urge-api
    spec:
      containers:
      - name: urge-api
        image: urge-backend:latest
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: urge-secrets
              key: database-url
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: urge-secrets
              key: secret-key
```

Deploy:
```bash
kubectl apply -f k8s/
```

## Nginx Configuration

### 1. Configure Nginx as Reverse Proxy

`/etc/nginx/sites-available/urge`:

```nginx
upstream urge_api {
    server 127.0.0.1:8080;
}

server {
    listen 80;
    server_name api.urge.app;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.urge.app;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/api.urge.app/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.urge.app/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000" always;

    # Max upload size
    client_max_body_size 100M;

    # API endpoints
    location /api {
        proxy_pass http://urge_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    # WebSocket (Socket.IO)
    location /socket.io {
        proxy_pass http://urge_api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }

    # Media files
    location /uploads {
        alias /home/urge/urge-backend/uploads;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### 2. Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/urge /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. Setup SSL with Let's Encrypt

```bash
sudo certbot --nginx -d api.urge.app
```

## Environment Variables (Production)

Create `/home/urge/urge-backend/.env`:

```env
# Application
APP_NAME=URGE
APP_VERSION=1.0.0
DEBUG=False
ENVIRONMENT=production

# Server
HOST=0.0.0.0
PORT=8080

# Database
DATABASE_URL=postgresql://urge_user:STRONG_PASSWORD@localhost:5432/urge_production
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT & Security
SECRET_KEY=GENERATE_STRONG_RANDOM_KEY_HERE
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
ALLOWED_ORIGINS=https://urge.app,https://www.urge.app

# Twilio
TWILIO_ACCOUNT_SID=your_production_sid
TWILIO_AUTH_TOKEN=your_production_token
TWILIO_PHONE_NUMBER=+1234567890

# AWS S3
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_REGION=us-east-1
S3_BUCKET_NAME=urge-media-prod

# Firebase
FIREBASE_CREDENTIALS_PATH=/home/urge/urge-backend/firebase-prod.json

# Logging
LOG_LEVEL=INFO
LOG_FILE=/home/urge/urge-backend/logs/app.log

# Support
SUPPORT_EMAIL=support@urge.app
PRIVACY_POLICY_URL=https://urge.app/privacy
TERMS_URL=https://urge.app/terms
```

## Security Checklist

### ✅ Required

- [ ] Change default SECRET_KEY to strong random string
- [ ] Use HTTPS/TLS for all traffic
- [ ] Configure firewall (ufw/iptables)
- [ ] Disable root SSH login
- [ ] Use SSH keys instead of passwords
- [ ] Keep system packages updated
- [ ] Set strong database passwords
- [ ] Configure rate limiting
- [ ] Enable CORS only for trusted origins
- [ ] Disable DEBUG mode in production
- [ ] Set up regular backups
- [ ] Use environment variables for secrets
- [ ] Implement logging and monitoring

### Firewall Configuration

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### Generate Strong Secret Key

```python
import secrets
print(secrets.token_urlsafe(32))
```

## Monitoring

### 1. Application Logs

```bash
# View real-time logs
sudo journalctl -u urge-api -f

# View last 100 lines
sudo journalctl -u urge-api -n 100

# Application logs
tail -f /home/urge/urge-backend/logs/app.log
```

### 2. System Monitoring

Install monitoring tools:

```bash
sudo apt install -y htop iotop nethogs
```

### 3. Database Monitoring

Monitor PostgreSQL:

```bash
# Active connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# Slow queries
sudo -u postgres psql -c "SELECT pid, now() - pg_stat_activity.query_start AS duration, query FROM pg_stat_activity WHERE state != 'idle' ORDER BY duration DESC;"
```

### 4. Setup Prometheus + Grafana (Optional)

Install monitoring stack for metrics and dashboards.

## Backup Strategy

### 1. Database Backups

Create backup script `/home/urge/backup_db.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/home/urge/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="urge_db_${TIMESTAMP}.sql"

mkdir -p $BACKUP_DIR

pg_dump -U urge_user urge_production > "${BACKUP_DIR}/${FILENAME}"
gzip "${BACKUP_DIR}/${FILENAME}"

# Keep only last 7 days of backups
find $BACKUP_DIR -name "urge_db_*.sql.gz" -mtime +7 -delete

echo "Backup completed: ${FILENAME}.gz"
```

Schedule with cron:
```bash
crontab -e
# Add: 0 2 * * * /home/urge/backup_db.sh
```

### 2. Media Files Backup

Sync to S3:
```bash
aws s3 sync /home/urge/urge-backend/uploads s3://urge-backups/uploads/
```

## Scaling

### Horizontal Scaling

1. **Load Balancer**: Use Nginx or cloud load balancer
2. **Multiple Instances**: Run multiple Gunicorn instances
3. **Redis**: For WebSocket session management
4. **CDN**: CloudFlare or AWS CloudFront for media

### Vertical Scaling

Increase Gunicorn workers:

```bash
# In systemd service file
-w 8  # 2-4x CPU cores
```

## Troubleshooting

### Service won't start

```bash
# Check logs
sudo journalctl -u urge-api -n 50

# Check if port is in use
sudo netstat -tulpn | grep 8080

# Test manually
cd /home/urge/urge-backend
source venv/bin/activate
python -m app.main
```

### Database connection errors

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection
psql -U urge_user -d urge_production -h localhost
```

### High memory usage

```bash
# Check memory usage
free -h

# Reduce Gunicorn workers
# Optimize database queries
# Add Redis caching
```

## Updates and Maintenance

### Zero-Downtime Deployment

```bash
# Pull latest code
cd /home/urge/urge-backend
git pull origin main

# Install dependencies
source venv/bin/activate
pip install -r requirements.txt

# Run migrations (if any)
alembic upgrade head

# Reload service
sudo systemctl reload urge-api
```

### Rollback

```bash
# Revert to previous version
git reset --hard HEAD~1

# Restart service
sudo systemctl restart urge-api
```

---

## Support

For production issues:
- Check logs first
- Review monitoring dashboards
- Contact: support@urge.app

**🚀 Good luck with your deployment!**
