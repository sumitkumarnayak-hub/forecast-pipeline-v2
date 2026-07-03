#!/usr/bin/env python3
"""
Switch between local and Render environment profiles.

Usage (from repo root):
  python scripts/switch_env.py local     # G:\\ paths, local backend, localhost API proxy
  python scripts/switch_env.py render    # production-like env (Render paths + remote API)
  python scripts/switch_env.py status    # show active profile
  python scripts/switch_env.py init      # seed profile files from current .env / examples

Copies:
  backend/dotenv-profiles/{profile}.env  ->  backend/.env
  frontend/dotenv-profiles/{profile}.env   ->  frontend/.env.local
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
PROFILES_DIR = BACKEND_DIR / "dotenv-profiles"
FRONTEND_PROFILES_DIR = FRONTEND_DIR / "dotenv-profiles"
ACTIVE_MARKER = BACKEND_DIR / "dotenv-profiles" / ".active"
VALID_PROFILES = ("local", "render")


def _profile_path(profile: str) -> Path:
    return PROFILES_DIR / f"{profile}.env"


def _frontend_profile_path(profile: str) -> Path:
    return FRONTEND_PROFILES_DIR / f"{profile}.env"


def _copy_profile(profile: str) -> None:
    backend_src = _profile_path(profile)
    if not backend_src.is_file():
        example = PROFILES_DIR / f"{profile}.env.example"
        raise SystemExit(
            f"Missing {backend_src}\n"
            f"  Run: python scripts/switch_env.py init\n"
            f"  Or copy: {example} -> {backend_src}"
        )

    shutil.copy2(backend_src, BACKEND_DIR / ".env")
    ACTIVE_MARKER.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_MARKER.write_text(profile + "\n", encoding="utf-8")
    print(f"[ok] backend/.env  <-  dotenv-profiles/{profile}.env")

    fe_src = _frontend_profile_path(profile)
    if fe_src.is_file():
        shutil.copy2(fe_src, FRONTEND_DIR / ".env.local")
        print(f"[ok] frontend/.env.local  <-  dotenv-profiles/{profile}.env")
    else:
        fe_example = FRONTEND_PROFILES_DIR / f"{profile}.env.example"
        if fe_example.is_file():
            shutil.copy2(fe_example, FRONTEND_DIR / ".env.local")
            print(f"[ok] frontend/.env.local  <-  dotenv-profiles/{profile}.env.example")
        else:
            print(f"[warn] No frontend profile for '{profile}'")


def _status() -> None:
    active = ACTIVE_MARKER.read_text(encoding="utf-8").strip() if ACTIVE_MARKER.is_file() else "(unknown)"
    print(f"Active profile: {active}")
    for name in VALID_PROFILES:
        be = "yes" if _profile_path(name).is_file() else "no"
        fe = "yes" if _frontend_profile_path(name).is_file() else "no"
        print(f"  {name:6}  backend={be}  frontend={fe}")


def _init() -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    FRONTEND_PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    local_dst = _profile_path("local")
    if not local_dst.is_file():
        legacy = BACKEND_DIR / ".env"
        if legacy.is_file():
            shutil.copy2(legacy, local_dst)
            print("[ok] Created dotenv-profiles/local.env from backend/.env")
        elif (PROFILES_DIR / "local.env.example").is_file():
            shutil.copy2(PROFILES_DIR / "local.env.example", local_dst)
            print("[ok] Created dotenv-profiles/local.env from local.env.example")

    render_dst = _profile_path("render")
    if not render_dst.is_file():
        for candidate in (
            BACKEND_DIR / ".env.render.example",
            PROFILES_DIR / "render.env.example",
        ):
            if candidate.is_file():
                shutil.copy2(candidate, render_dst)
                print(f"[ok] Created dotenv-profiles/render.env from {candidate.name}")
                break

    for profile in VALID_PROFILES:
        fe_dst = _frontend_profile_path(profile)
        if not fe_dst.is_file():
            fe_example = FRONTEND_PROFILES_DIR / f"{profile}.env.example"
            if fe_example.is_file():
                shutil.copy2(fe_example, fe_dst)
                print(f"[ok] Created frontend/dotenv-profiles/{profile}.env")

    if not ACTIVE_MARKER.is_file() and local_dst.is_file():
        shutil.copy2(local_dst, BACKEND_DIR / ".env")
        ACTIVE_MARKER.write_text("local\n", encoding="utf-8")
        if _frontend_profile_path("local").is_file():
            shutil.copy2(_frontend_profile_path("local"), FRONTEND_DIR / ".env.local")
        print("[ok] Activated local profile (default)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Switch local vs Render env profiles")
    parser.add_argument(
        "profile",
        nargs="?",
        choices=[*VALID_PROFILES, "status", "init"],
        help="Profile to activate, or status/init",
    )
    args = parser.parse_args()

    if args.profile is None or args.profile == "status":
        _status()
        return 0
    if args.profile == "init":
        _init()
        return 0

    _copy_profile(args.profile)
    print()
    if args.profile == "local":
        print("Local mode:")
        print("  Backend:  cd backend && uvicorn app.main:app --reload --port 8000")
        print("  Frontend: cd frontend && npm run dev")
    else:
        print("Render profile active locally.")
        print("  Import backend/dotenv-profiles/render.env on Render dashboard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
