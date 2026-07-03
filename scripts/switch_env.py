#!/usr/bin/env python3
"""Switch local vs Render env profiles (repo root: python scripts/switch_env.py local|render|status|init)."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
PROFILES_DIR = BACKEND_DIR / "dotenv-profiles"
FRONTEND_PROFILES_DIR = FRONTEND_DIR / "dotenv-profiles"
ACTIVE_MARKER = PROFILES_DIR / ".active"
PROFILES = ("local", "render")


def _be(profile: str) -> Path:
    return PROFILES_DIR / f"{profile}.env"


def _fe(profile: str) -> Path:
    return FRONTEND_PROFILES_DIR / f"{profile}.env"


def _activate(profile: str) -> None:
    src = _be(profile)
    if not src.is_file():
        raise SystemExit(f"Missing {src} — copy from {src.with_suffix('.env.example')}")

    shutil.copy2(src, BACKEND_DIR / ".env")
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_MARKER.write_text(profile + "\n", encoding="utf-8")
    print(f"[ok] backend/.env <- dotenv-profiles/{profile}.env")

    fe = _fe(profile)
    if fe.is_file():
        shutil.copy2(fe, FRONTEND_DIR / ".env.local")
        print(f"[ok] frontend/.env.local <- dotenv-profiles/{profile}.env")


def _status() -> None:
    active = ACTIVE_MARKER.read_text(encoding="utf-8").strip() if ACTIVE_MARKER.is_file() else "(unknown)"
    print(f"Active profile: {active}")
    for name in PROFILES:
        print(f"  {name:6}  backend={'yes' if _be(name).is_file() else 'no'}  frontend={'yes' if _fe(name).is_file() else 'no'}")


def _init() -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    FRONTEND_PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    for profile in PROFILES:
        dst = _be(profile)
        if not dst.is_file() and (ex := dst.with_suffix(".env.example")).is_file():
            shutil.copy2(ex, dst)
            print(f"[ok] created dotenv-profiles/{profile}.env from example")

        fe_dst = _fe(profile)
        if not fe_dst.is_file() and (ex := fe_dst.with_suffix(".env.example")).is_file():
            shutil.copy2(ex, fe_dst)
            print(f"[ok] created frontend/dotenv-profiles/{profile}.env from example")

    if not ACTIVE_MARKER.is_file() and _be("local").is_file():
        _activate("local")
        print("[ok] activated local (default)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Switch local vs Render env profiles")
    parser.add_argument("profile", nargs="?", choices=[*PROFILES, "status", "init"])
    args = parser.parse_args()

    if not args.profile or args.profile == "status":
        _status()
        return 0
    if args.profile == "init":
        _init()
        return 0

    _activate(args.profile)
    if args.profile == "local":
        print("\nLocal: cd backend && uvicorn app.main:app --reload --port 8000")
        print("       cd frontend && npm run dev")
    else:
        print("\nImport backend/dotenv-profiles/render.env on Render dashboard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
