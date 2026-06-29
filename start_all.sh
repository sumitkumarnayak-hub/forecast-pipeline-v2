#!/bin/bash

echo "Starting Forecast Pipeline V2..."
echo "================================"

# Start backend
echo "[1/2] Starting FastAPI backend..."
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_backend.py &
BACKEND_PID=$!
cd ..

# Start frontend
echo "[2/2] Starting Next.js frontend..."
cd frontend
npm install
npm run dev &
FRONTEND_PID=$!
cd ..

echo "================================"
echo "Backend running on http://localhost:8000"
echo "Frontend running on http://localhost:3000"
echo "Press Ctrl+C to stop both servers"

# Wait for interrupt
trap "echo 'Stopping servers...'; kill $BACKEND_PID $FRONTEND_PID" INT
wait
