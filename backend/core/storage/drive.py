"""Google Drive storage backend for pipeline artifacts."""
from __future__ import annotations

import io
import logging
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload
from core.shared.google_credentials import load_service_account_credentials
from core.storage.artifacts import resolve_local_path

from core.storage.base import StorageBackend, _guess_mime


logger = logging.getLogger(__name__)

_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
_FOLDER_MIME = "application/vnd.google-apps.folder"

_DRIVE_QUOTA_HELP = (
    "Google service accounts cannot upload to a regular My Drive folder. Fix one of:\n"
    "  1. Use a Shared Drive folder (Google Workspace) and add the service account as Content manager, OR\n"
    "  2. Set GOOGLE_DRIVE_IMPERSONATE_EMAIL to a Workspace user (domain-wide delegation), OR\n"
    "  3. Upload files manually into the shared folder (pipeline can still download them).\n"
    "See: https://developers.google.com/workspace/drive/api/guides/about-shareddrives"
)


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _is_storage_quota_error(exc: HttpError) -> bool:
    try:
        details = exc.error_details if hasattr(exc, "error_details") else []
        for item in details:
            if item.get("reason") == "storageQuotaExceeded":
                return True
    except Exception:
        pass
    return "storage quota" in str(exc).lower()


class DriveStorageBackend(StorageBackend):
    """
    Store pipeline files under a single Drive folder (PIPELINE_DRIVE_FOLDER_URL).

    Logical keys like ``masters/Product_Masters.xlsx`` map to subfolders under that root.
    Uses GOOGLE_CREDENTIALS_PATH (same service account as Google Sheets).
    """

    def __init__(
        self,
        *,
        root_folder_id: str,
        credentials_path: str,
        impersonate_email: str = "",
    ) -> None:
        self._root_folder_id = root_folder_id
        self._credentials_path = credentials_path
        self._impersonate_email = impersonate_email.strip()
        self._folder_cache: dict[tuple[str, str], str] = {}
        self._service = self._build_service()
        self._validate_root_access()

    @property
    def name(self) -> str:
        return "drive"

    def _build_service(self):
        creds = load_service_account_credentials(_DRIVE_SCOPES)
        if self._impersonate_email:
            creds = creds.create_delegated(self._impersonate_email)
            logger.info("Drive API using delegated user: %s", self._impersonate_email)
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def _list_params(self) -> dict:
        return {
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }

    def _write_params(self) -> dict:
        return {"supportsAllDrives": True}

    def _validate_root_access(self) -> None:
        try:
            meta = (
                self._service.files()
                .get(
                    fileId=self._root_folder_id,
                    fields="id,name,mimeType,driveId,capabilities",
                    **self._write_params(),
                )
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status == 404:
                raise RuntimeError(
                    f"Drive folder not found or not shared with the service account: {self._root_folder_id}\n"
                    "Share the folder with the service account email (Editor)."
                ) from exc
            raise

        if meta.get("mimeType") != _FOLDER_MIME:
            raise RuntimeError(f"PIPELINE_DRIVE_FOLDER_URL must point to a folder, got: {meta.get('mimeType')}")

        if meta.get("driveId"):
            logger.info("Drive root is on Shared Drive %s (%s)", meta.get("driveId"), meta.get("name"))
        elif not self._impersonate_email:
            logger.warning(
                "Drive root '%s' is a regular My Drive folder. "
                "Uploads may fail unless you use a Shared Drive or GOOGLE_DRIVE_IMPERSONATE_EMAIL.",
                meta.get("name"),
            )

    def _split_key(self, key: str) -> tuple[list[str], str]:
        clean = key.lstrip("/").replace("\\", "/")
        parts = [p for p in clean.split("/") if p]
        if not parts:
            raise ValueError(f"Invalid storage key: {key!r}")
        return parts[:-1], parts[-1]

    def _find_child(
        self,
        parent_id: str,
        name: str,
        *,
        folder: bool = False,
    ) -> dict | None:
        q = (
            f"name = '{_escape_query(name)}' and '{parent_id}' in parents "
            f"and trashed = false"
        )
        if folder:
            q += f" and mimeType = '{_FOLDER_MIME}'"
        else:
            q += f" and mimeType != '{_FOLDER_MIME}'"

        resp = (
            self._service.files()
            .list(
                q=q,
                fields="files(id,name,mimeType)",
                pageSize=10,
                **self._list_params(),
            )
            .execute()
        )
        files = resp.get("files", [])
        return files[0] if files else None

    def _ensure_folder(self, parent_id: str, name: str) -> str:
        cache_key = (parent_id, name)
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        existing = self._find_child(parent_id, name, folder=True)
        if existing:
            folder_id = existing["id"]
        else:
            body = {
                "name": name,
                "mimeType": _FOLDER_MIME,
                "parents": [parent_id],
            }
            try:
                created = (
                    self._service.files()
                    .create(body=body, fields="id", **self._write_params())
                    .execute()
                )
            except HttpError as exc:
                if _is_storage_quota_error(exc):
                    raise RuntimeError(_DRIVE_QUOTA_HELP) from exc
                raise
            folder_id = created["id"]
            logger.info("Created Drive folder %s", name)

        self._folder_cache[cache_key] = folder_id
        return folder_id

    def _parent_for_key(self, key: str) -> tuple[str, str]:
        folder_parts, filename = self._split_key(key)
        parent_id = self._root_folder_id
        for part in folder_parts:
            parent_id = self._ensure_folder(parent_id, part)
        return parent_id, filename

    def _file_id_for_key(self, key: str) -> str | None:
        parent_id, filename = self._parent_for_key(key)
        found = self._find_child(parent_id, filename, folder=False)
        return found["id"] if found else None

    def exists(self, key: str) -> bool:
        return self._file_id_for_key(key) is not None

    def read_bytes(self, key: str) -> bytes:
        file_id = self._file_id_for_key(key)
        if not file_id:
            raise FileNotFoundError(f"Drive object not found: {key}")

        request = self._service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()

    def _create_or_update(self, parent_id: str, filename: str, media) -> None:
        existing = self._find_child(parent_id, filename, folder=False)
        try:
            if existing:
                (
                    self._service.files()
                    .update(fileId=existing["id"], media_body=media, **self._write_params())
                    .execute()
                )
            else:
                body = {"name": filename, "parents": [parent_id]}
                (
                    self._service.files()
                    .create(body=body, media_body=media, fields="id", **self._write_params())
                    .execute()
                )
        except HttpError as exc:
            if _is_storage_quota_error(exc):
                raise RuntimeError(_DRIVE_QUOTA_HELP) from exc
            raise

    def write_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        parent_id, filename = self._parent_for_key(key)
        mime = content_type or "application/octet-stream"
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=True)
        self._create_or_update(parent_id, filename, media)

    def upload_file(
        self,
        key: str,
        local_path: str | Path,
        *,
        content_type: str | None = None,
    ) -> None:
        path = Path(local_path)
        parent_id, filename = self._parent_for_key(key)
        mime = content_type or _guess_mime(path)
        media = MediaFileUpload(str(path), mimetype=mime, resumable=True)
        self._create_or_update(parent_id, filename, media)

    def delete(self, key: str) -> None:
        file_id = self._file_id_for_key(key)
        if file_id:
            self._service.files().delete(fileId=file_id, **self._write_params()).execute()

    def list_keys(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        self._walk_folder(self._root_folder_id, "", keys)
        if not prefix:
            return sorted(keys)
        norm = prefix.rstrip("/") + "/"
        return sorted(k for k in keys if k.startswith(norm) or k == prefix.rstrip("/"))

    def _walk_folder(self, folder_id: str, current_path: str, out: list[str]) -> None:
        page_token = None
        while True:
            resp = (
                self._service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="nextPageToken,files(id,name,mimeType)",
                    pageSize=1000,
                    pageToken=page_token,
                    **self._list_params(),
                )
                .execute()
            )
            for item in resp.get("files", []):
                name = item["name"]
                rel = f"{current_path}/{name}" if current_path else name
                if item.get("mimeType") == _FOLDER_MIME:
                    self._walk_folder(item["id"], rel, out)
                else:
                    out.append(rel.replace("\\", "/"))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    def sync_local_to_remote(self, key: str, local_path: str | Path) -> bool:
        path = Path(local_path)
        if not path.is_file():
            return False
        self.upload_file(key, path, content_type=_guess_mime(path))
        logger.info("Uploaded %s → drive://%s", path, key)
        return True

    def sync_remote_to_local(self, key: str, local_path: str | Path) -> bool:
        path = Path(local_path)
        try:
            if not self.exists(key):
                return False
            self.download_file(key, path)
            logger.info("Downloaded drive://%s → %s", key, path)
            return True
        except FileNotFoundError:
            return False

    def materialize_local(self, key: str) -> Path:
        local = resolve_local_path(key)
        if local.is_file():
            return local
        if self.sync_remote_to_local(key, local):
            return local
        return local
