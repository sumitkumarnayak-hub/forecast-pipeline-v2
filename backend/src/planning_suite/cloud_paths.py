"""Cloud deploy path helpers — ignore local G:\\ shortcuts on Render."""
from __future__ import annotations

import os
from pathlib import Path


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


def data_root(base_dir: Path) -> Path:
    explicit = os.getenv("DATA_ROOT", "").strip()
    if explicit and not (is_cloud_deploy() and is_legacy_windows_path(explicit)):
        return Path(explicit)
    if os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"):
        return Path("/var/data")
    return base_dir / "data"


def resolve_path_env(name: str, default_relative: str, *, base_dir: Path) -> str:
    """Use env value unless it is a Windows path on a cloud host."""
    raw = os.getenv(name, "").strip()
    if raw and not (is_cloud_deploy() and is_legacy_windows_path(raw)):
        return raw
    path = data_root(base_dir) / default_relative
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def resolve_output_path(base_dir: Path) -> Path:
    raw = os.getenv("OUTPUT_PATH", "").strip()
    if raw and not (is_cloud_deploy() and is_legacy_windows_path(raw)):
        out = Path(raw)
    elif is_cloud_deploy():
        out = data_root(base_dir) / "outputs"
    else:
        out = base_dir / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    return out
