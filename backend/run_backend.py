"""
Run the FastAPI backend.
Usage: python run_backend.py
"""
import sys
import os
from pathlib import Path

# Make backend root importable
sys.path.insert(0, str(Path(__file__).parent))
os.chdir(Path(__file__).parent)  # so outputs/ and .env resolve correctly

import uvicorn

if __name__ == "__main__":
    backend_dir = Path(__file__).parent
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
