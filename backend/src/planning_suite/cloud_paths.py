"""Cloud deploy path helpers — ignore local G:\\ shortcuts on Render."""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def is_legacy_windows_path(value: str) -> bool:
    v = value.strip().replace("/", "\\")
    if len(v) >= 2 and v[1] == ":":
        return True
    lowered = v.lower()
    return "shortcut-targets-by-id" in lowered or lowered.startswith("g\\")


def is_cloud_deploy() -> bool:
    """True on Render/production hosts — not local dev with STORAGE_BACKEND=drive."""
    if os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"):
        return True
    return os.getenv("APP_ENV", "").strip().lower() in {"production", "prod"}


def _mkdir_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        test = path / ".write_test"
        test.write_text("ok", encoding="utf-8")
        test.unlink(missing_ok=True)
        return True
    except (OSError, PermissionError):
        return False


def data_root(base_dir: Path) -> Path:
    """
    Writable data directory.

    Render free tier has no /var/data unless you attach a persistent disk.
    Default: ``backend/data`` (ephemeral, writable under the project tree).
    """
    explicit = os.getenv("DATA_ROOT", "").strip()
    if explicit and not (is_cloud_deploy() and is_legacy_windows_path(explicit)):
        candidate = Path(explicit)
        if _mkdir_writable(candidate):
            return candidate
        logger.warning("DATA_ROOT not writable (%s) — using backend/data", candidate)

    fallback = base_dir / "data"
    _mkdir_writable(fallback)
    return fallback


def resolve_path_env(name: str, default_relative: str, *, base_dir: Path) -> str:
    """Use env value unless it is a Windows path on a cloud host."""
    raw = os.getenv(name, "").strip()
    if raw and not (is_cloud_deploy() and is_legacy_windows_path(raw)):
        path = Path(raw)
        if path.is_dir() or path.is_file():
            return str(path)
        if _mkdir_writable(path.parent):
            return str(path)
        logger.warning("%s not writable (%s) — using data_root default", name, raw)
    path = data_root(base_dir) / default_relative
    _mkdir_writable(path.parent)
    return str(path)


def resolve_output_path(base_dir: Path) -> Path:
    raw = os.getenv("OUTPUT_PATH", "").strip()
    if raw and not (is_cloud_deploy() and is_legacy_windows_path(raw)):
        out = Path(raw)
        if _mkdir_writable(out):
            return out
        logger.warning("OUTPUT_PATH not writable (%s) — using backend/data/outputs", raw)
    if is_cloud_deploy():
        out = data_root(base_dir) / "outputs"
    else:
        out = base_dir / "outputs"
    _mkdir_writable(out)
    return out
