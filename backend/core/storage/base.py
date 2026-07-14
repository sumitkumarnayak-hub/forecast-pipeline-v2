"""Abstract storage backend for pipeline artifacts (local, Supabase, future Drive)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    """CRUD for pipeline files addressed by logical object keys (POSIX-style paths)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier: local | supabase | drive."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True if the object exists in this backend."""

    @abstractmethod
    def read_bytes(self, key: str) -> bytes:
        """Read full object bytes."""

    @abstractmethod
    def write_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        """Create or replace object."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove object if present."""

    @abstractmethod
    def list_keys(self, prefix: str = "") -> list[str]:
        """List object keys under optional prefix."""

    def read_text(self, key: str, *, encoding: str = "utf-8") -> str:
        return self.read_bytes(key).decode(encoding)

    def write_text(self, key: str, text: str, *, encoding: str = "utf-8") -> None:
        self.write_bytes(key, text.encode(encoding), content_type="text/plain; charset=utf-8")

    def upload_file(
        self,
        key: str,
        local_path: str | Path,
        *,
        content_type: str | None = None,
    ) -> None:
        path = Path(local_path)
        self.write_bytes(key, path.read_bytes(), content_type=content_type or _guess_mime(path))

    def download_file(self, key: str, local_path: str | Path) -> Path:
        path = Path(local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.read_bytes(key))
        return path

    def sync_local_to_remote(self, key: str, local_path: str | Path) -> bool:
        """Upload local file if it exists. Returns True when uploaded."""
        path = Path(local_path)
        if not path.is_file():
            return False
        self.upload_file(key, path)
        return True

    def sync_remote_to_local(self, key: str, local_path: str | Path) -> bool:
        """Download remote object if it exists. Returns True when downloaded."""
        if not self.exists(key):
            return False
        self.download_file(key, local_path)
        return True


def _guess_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".parquet": "application/octet-stream",
        ".json": "application/json",
        ".csv": "text/csv",
        ".rds": "application/octet-stream",
    }.get(suffix, "application/octet-stream")
