#!/bin/bash

# URGE Backend Run Script

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting URGE Backend...${NC}"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install -r requirements.txt --quiet

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env from .env.example...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}Please edit .env with your configuration${NC}"
fi

# Run the server with Socket.IO support
echo -e "${GREEN}Starting server on http://localhost:8080${NC}"
echo -e "${GREEN}API Docs: http://localhost:8080/docs${NC}"
echo -e "${GREEN}Socket.IO endpoint: ws://localhost:8080/socket.io${NC}"
uvicorn app.main:socket_app --reload --host 0.0.0.0 --port 8080
