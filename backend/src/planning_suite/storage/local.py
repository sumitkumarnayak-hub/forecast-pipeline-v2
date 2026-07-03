"""Local filesystem storage — default backend (current behaviour)."""
from __future__ import annotations

from pathlib import Path

from planning_suite.storage.artifacts import resolve_local_path
from planning_suite.storage.base import StorageBackend


class LocalStorageBackend(StorageBackend):
    @property
    def name(self) -> str:
        return "local"

    def _path(self, key: str) -> Path:
        return resolve_local_path(key)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def write_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def list_keys(self, prefix: str = "") -> list[str]:
        from planning_suite.storage.artifacts import iter_artifact_keys

        keys = iter_artifact_keys()
        if not prefix:
            return keys
        p = prefix.rstrip("/") + "/"
        return [k for k in keys if k.startswith(p) or k == prefix.rstrip("/")]

    def sync_local_to_remote(self, key: str, local_path: str | Path) -> bool:
        """Local backend: file is already on disk at the canonical path."""
        return Path(local_path).is_file()

    def sync_remote_to_local(self, key: str, local_path: str | Path) -> bool:
        return Path(local_path).is_file()
