#!/bin/bash

# =============================================================================
# init.sh - Project Initialization Script
# =============================================================================
# Run this script at the start of every session to ensure the environment
# is properly set up and the development server is running.
# =============================================================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Initializing Spring FES Video project...${NC}"

# Install dependencies
echo "Installing dependencies..."
cd hello-nextjs && npm install && cd ..

# Start development server in background
echo "Starting development server..."
cd hello-nextjs
npm run dev &
SERVER_PID=$!
cd ..

# Wait for server to be ready
echo "Waiting for server to start..."
sleep 3

echo -e "${GREEN}✓ Initialization complete!${NC}"
echo -e "${GREEN}✓ Dev server running at http://localhost:3000 (PID: $SERVER_PID)${NC}"
echo ""
echo "Ready to continue development."
