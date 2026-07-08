---
title: Planning Suite API
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Forecast Pipeline V2

A complete, optimized migration of the original Forecast Pipeline (Streamlit) to a decoupled Next.js + FastAPI architecture.

## Architecture

- **Frontend:** Next.js 15 (React 19), App Router, Tailwind CSS (with a custom premium dark-mode design system).
- **Backend:** FastAPI, preserving 100% of the original `planning_suite` business logic, SQLite/Supabase, Google Sheets API.

## Features

- **Decoupled:** The frontend and backend run on different ports and communicate via REST APIs and Server-Sent Events (SSE).
- **Premium UI:** Dark mode with micro-animations, glassmorphism, and responsive layout.
- **Headless Auto-Pilot:** The complex baseline automation runs asynchronously in the backend, streaming status directly to the UI without blocking.
- **Role-Based Access:** JWT authentication preserving Admin/Viewer roles.

## Quick Start

### 1. Backend (FastAPI)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start the API on port 8000
python run_backend.py
```

*Note: Ensure your `.env` and Google credentials JSON are properly placed in the `backend/` directory, just as they were in the original codebase.*

### 2. Frontend (Next.js)

Open a new terminal window:

```bash
cd frontend
npm install

# Start the dev server on port 3000
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000) to log in and use the pipeline.

## Production & onboarding

- **Deploy:** See [`DEPLOY.md`](DEPLOY.md) (Vercel + Render + Postgres).
- **Operations:** [`OPS_RUNBOOK.md`](OPS_RUNBOOK.md), [`DATA_SOURCES.md`](DATA_SOURCES.md).
- **Team guide:** After login, open **About & Guide** in the sidebar (`/about`) for a plain-language walkthrough of the weekly workflow and each page.
