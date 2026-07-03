"""Supabase Storage bucket backend."""
from __future__ import annotations

import logging
import os
from io import BytesIO
from pathlib import Path

import httpx

from planning_suite.storage.artifacts import resolve_local_path
from planning_suite.storage.base import StorageBackend, _guess_mime

logger = logging.getLogger(__name__)

# Supabase requires 6 MB chunks for TUS; standard POST fails above ~50 MB.
TUS_CHUNK_SIZE = 6 * 1024 * 1024
TUS_THRESHOLD_BYTES = int(os.getenv("SUPABASE_TUS_THRESHOLD_BYTES", str(TUS_CHUNK_SIZE)))


class SupabaseStorageBackend(StorageBackend):
    def __init__(
        self,
        *,
        url: str,
        service_role_key: str,
        bucket: str,
        timeout: float = 120.0,
        upload_timeout: float = 1800.0,
    ) -> None:
        self._url = url.rstrip("/")
        self._key = service_role_key
        self._bucket = bucket
        self._timeout = timeout
        self._upload_timeout = upload_timeout
        self._headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
        }

    @property
    def name(self) -> str:
        return "supabase"

    def _storage_base_url(self) -> str:
        """Direct storage hostname — faster for large uploads (Supabase docs)."""
        if ".storage.supabase.co" in self._url:
            return self._url
        host = self._url.removeprefix("https://").removeprefix("http://")
        if host.endswith(".supabase.co"):
            project = host.removesuffix(".supabase.co")
            return f"https://{project}.storage.supabase.co"
        return self._url

    def _tus_endpoint(self) -> str:
        return f"{self._storage_base_url()}/storage/v1/upload/resumable"

    def _object_url(self, key: str) -> str:
        clean = key.lstrip("/").replace("\\", "/")
        return f"{self._url}/storage/v1/object/{self._bucket}/{clean}"

    def _list_url(self) -> str:
        return f"{self._url}/storage/v1/object/list/{self._bucket}"

    def _httpx_timeout(self, *, upload: bool = False) -> httpx.Timeout:
        total = self._upload_timeout if upload else self._timeout
        return httpx.Timeout(connect=30.0, read=total, write=total, pool=30.0)

    def _tus_headers(self) -> dict[str, str]:
        return {
            **self._headers,
            "x-upsert": "true",
        }

    def _tus_upload_stream(
        self,
        key: str,
        stream,
        *,
        content_type: str,
        file_size: int | None = None,
    ) -> None:
        from tusclient import client as tus_client

        clean = key.lstrip("/").replace("\\", "/")
        tus = tus_client.TusClient(self._tus_endpoint(), headers=self._tus_headers())
        uploader = tus.uploader(
            file_stream=stream,
            chunk_size=TUS_CHUNK_SIZE,
            metadata={
                "bucketName": self._bucket,
                "objectName": clean,
                "contentType": content_type,
            },
        )
        if file_size is not None:
            logger.info(
                "TUS upload %s → supabase://%s/%s (%.1f MB, %s MB chunks)",
                "stream",
                self._bucket,
                clean,
                file_size / 1024 / 1024,
                TUS_CHUNK_SIZE // 1024 // 1024,
            )
        uploader.upload()

    def _tus_upload_path(self, key: str, path: Path, *, content_type: str) -> None:
        size = path.stat().st_size
        with path.open("rb") as stream:
            self._tus_upload_stream(key, stream, content_type=content_type, file_size=size)

    def exists(self, key: str) -> bool:
        clean = key.lstrip("/").replace("\\", "/")
        try:
            with httpx.Client(timeout=self._httpx_timeout()) as client:
                resp = client.post(
                    self._list_url(),
                    headers={**self._headers, "Content-Type": "application/json"},
                    json={"prefix": clean, "limit": 1, "search": Path(clean).name},
                )
            if resp.status_code != 200:
                return False
            items = resp.json()
            return any(item.get("name") == Path(clean).name for item in items)
        except Exception:
            return False

    def read_bytes(self, key: str) -> bytes:
        with httpx.Client(timeout=self._httpx_timeout(upload=True)) as client:
            resp = client.get(self._object_url(key), headers=self._headers)
        if resp.status_code == 404:
            raise FileNotFoundError(f"Supabase object not found: {key}")
        resp.raise_for_status()
        return resp.content

    def write_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        mime = content_type or "application/octet-stream"
        if len(data) >= TUS_THRESHOLD_BYTES:
            self._tus_upload_stream(
                key,
                BytesIO(data),
                content_type=mime,
                file_size=len(data),
            )
            return

        headers = {
            **self._headers,
            "Content-Type": mime,
            "x-upsert": "true",
        }
        with httpx.Client(timeout=self._httpx_timeout(upload=True)) as client:
            resp = client.post(self._object_url(key), headers=headers, content=data)
        resp.raise_for_status()

    def upload_file(
        self,
        key: str,
        local_path: str | Path,
        *,
        content_type: str | None = None,
    ) -> None:
        path = Path(local_path)
        mime = content_type or _guess_mime(path)
        if path.stat().st_size >= TUS_THRESHOLD_BYTES:
            self._tus_upload_path(key, path, content_type=mime)
            return
        self.write_bytes(key, path.read_bytes(), content_type=mime)

    def delete(self, key: str) -> None:
        with httpx.Client(timeout=self._httpx_timeout()) as client:
            resp = client.delete(self._object_url(key), headers=self._headers)
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()

    def list_keys(self, prefix: str = "") -> list[str]:
        body: dict = {"limit": 1000, "offset": 0}
        if prefix:
            body["prefix"] = prefix.rstrip("/")
        with httpx.Client(timeout=self._httpx_timeout()) as client:
            resp = client.post(
                self._list_url(),
                headers={**self._headers, "Content-Type": "application/json"},
                json=body,
            )
        resp.raise_for_status()
        prefix_norm = prefix.rstrip("/") + "/" if prefix else ""
        return [f"{prefix_norm}{item['name']}" for item in resp.json() if item.get("name")]

    def sync_local_to_remote(self, key: str, local_path: str | Path) -> bool:
        path = Path(local_path)
        if not path.is_file():
            return False
        self.upload_file(key, path, content_type=_guess_mime(path))
        logger.info("Uploaded %s → supabase://%s/%s", path, self._bucket, key)
        return True

    def sync_remote_to_local(self, key: str, local_path: str | Path) -> bool:
        path = Path(local_path)
        try:
            self.download_file(key, path)
            logger.info("Downloaded supabase://%s/%s → %s", self._bucket, key, path)
            return True
        except FileNotFoundError:
            return False
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return False
            raise

    def materialize_local(self, key: str) -> Path:
        """Ensure canonical local path exists, downloading from bucket when needed."""
        local = resolve_local_path(key)
        if local.is_file():
            return local
        if self.sync_remote_to_local(key, local):
            return local
        return local
