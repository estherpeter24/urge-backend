#!/bin/bash

# URGE Backend Quick Start Script

echo "🚀 Starting URGE Backend Server..."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Copying from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your configuration before running!"
    exit 1
fi

# Create uploads directory
mkdir -p uploads
mkdir -p logs

# Initialize database
echo "Initializing database..."
python init_db.py

# Start server
echo ""
echo "✅ Starting server on http://localhost:8080"
echo "📚 API Documentation: http://localhost:8080/docs"
echo ""

python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
