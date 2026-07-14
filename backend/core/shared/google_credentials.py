"""Resolve Google service account credentials from env (JSON or file path)."""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent.parent
REPO_ROOT = BACKEND_DIR.parent

DEFAULT_CREDENTIALS_NAMES = (
    "causal-flame-452312-q9-1b4341ee87db.json",
    "google-service-account.json",
)

_cached_path: str | None = None


def _default_dest() -> Path:
    explicit = os.getenv("GOOGLE_CREDENTIALS_RENDER_PATH", "").strip()
    if explicit:
        return Path(explicit)
    if os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"):
        return Path("/tmp/google-credentials.json")
    return Path(tempfile.gettempdir()) / "google-credentials.json"


def _parse_credentials_json(raw: str) -> dict:
    text = raw.strip()
    if not text.startswith("{"):
        text = base64.b64decode(text).decode("utf-8")
    info = json.loads(text)
    if not isinstance(info, dict) or info.get("type") != "service_account":
        raise ValueError("GOOGLE_CREDENTIALS_JSON must be a service account JSON object")
    return info


def _materialize_json(raw: str) -> str:
    info = _parse_credentials_json(raw)
    dest = _default_dest()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(info), encoding="utf-8")
    return str(dest)


def _bundled_candidates() -> list[Path]:
    explicit = os.getenv("GOOGLE_CREDENTIALS_FILE", "").strip()
    names = (explicit,) if explicit else DEFAULT_CREDENTIALS_NAMES
    out: list[Path] = []
    for folder in (REPO_ROOT, BACKEND_DIR, BACKEND_DIR / "credentials"):
        for name in names:
            out.append(folder / name)
    return out


def _valid_json_env(raw: str) -> str | None:
    """Return raw JSON text if env value is parseable; None if broken/partial."""
    text = raw.strip()
    if not text or not text.startswith("{"):
        return None
    try:
        _parse_credentials_json(text)
        return text
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Ignoring invalid GOOGLE_CREDENTIALS_JSON: %s", exc)
        return None


def get_google_credentials_path() -> str:
    """
    Return a filesystem path to service account JSON.

    Priority:
      1. GOOGLE_CREDENTIALS_PATH if the file exists (local dev)
      2. GOOGLE_CREDENTIALS_JSON env (Render) — materialized to a temp file
      3. Bundled repo file (e.g. causal-flame-452312-q9-1b4341ee87db.json)
    """
    global _cached_path
    if _cached_path and Path(_cached_path).is_file():
        return _cached_path

    configured = os.getenv("GOOGLE_CREDENTIALS_PATH", "").strip()
    if configured:
        path_obj = Path(configured)
        if path_obj.is_file():
            try:
                content = path_obj.read_text(encoding="utf-8")
                data = json.loads(content)
                if isinstance(data, dict) and data.get("type") == "service_account" and "token_uri" in data and "private_key" in data:
                    _cached_path = configured
                    return configured
                else:
                    logger.warning("GOOGLE_CREDENTIALS_PATH file is invalid or missing key fields like token_uri. Falling back.")
            except Exception as exc:
                logger.warning("GOOGLE_CREDENTIALS_PATH file exists but is invalid: %s. Falling back.", exc)

    raw_json = _valid_json_env(os.getenv("GOOGLE_CREDENTIALS_JSON", ""))
    if raw_json:
        path = _materialize_json(raw_json)
        _cached_path = path
        os.environ["GOOGLE_CREDENTIALS_PATH"] = path
        logger.info("Google credentials loaded from GOOGLE_CREDENTIALS_JSON -> %s", path)
        return path

    if configured:
        logger.warning("GOOGLE_CREDENTIALS_PATH not found: %s", configured)

    for candidate in _bundled_candidates():
        if candidate.is_file():
            dest = _default_dest()
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, dest)
            _cached_path = str(dest)
            os.environ["GOOGLE_CREDENTIALS_PATH"] = _cached_path
            logger.info("Google credentials copied from %s → %s", candidate, dest)
            return _cached_path

    if configured:
        logger.warning(
            "Google credentials file not found: %s. "
            "Set GOOGLE_CREDENTIALS_JSON or fix GOOGLE_CREDENTIALS_PATH.",
            configured
        )
        return ""
    logger.warning("Google credentials not configured. Set GOOGLE_CREDENTIALS_JSON or GOOGLE_CREDENTIALS_PATH.")
    return ""


def load_service_account_credentials(scopes: list[str]):
    """Build oauth2client credentials from resolved credentials file."""
    from oauth2client.service_account import ServiceAccountCredentials

    path = get_google_credentials_path()
    if not path or not Path(path).is_file():
        raise ValueError(
            "Google credentials are not configured or the path is invalid. "
            "Please check GOOGLE_CREDENTIALS_JSON or GOOGLE_CREDENTIALS_PATH env variables."
        )

    return ServiceAccountCredentials.from_json_keyfile_name(
        path,
        scopes,
    )
