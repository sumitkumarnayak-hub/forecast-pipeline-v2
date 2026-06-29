"""
Run the FastAPI backend.
Usage: python run_backend.py
"""
import sys
import os
from pathlib import Path

# Make src/ importable
sys.path.insert(0, str(Path(__file__).parent / "src"))
os.chdir(Path(__file__).parent)  # so outputs/ and .env resolve correctly

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"],
    )
