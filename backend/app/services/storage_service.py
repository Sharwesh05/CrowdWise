"""Object storage abstraction.

Application code never knows whether a file is on local disk, S3, R2 or Supabase.
Security rules live here rather than in routers: MIME allowlist, extension
allowlist, size cap, and a randomised storage key so a user-supplied filename can
never become a path component.
"""

from __future__ import annotations

import io as io_module
import mimetypes
import os
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.errors import ExternalServiceError, ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
}

# Anything executable or script-like is rejected outright, whatever the MIME says.
BLOCKED_EXTENSIONS = {
    ".exe", ".dll", ".bat", ".cmd", ".sh", ".ps1", ".js", ".jsx", ".ts", ".php",
    ".py", ".rb", ".jar", ".com", ".msi", ".scr", ".vbs", ".svg", ".html", ".htm",
}


@dataclass(slots=True)
class StoredFile:
    storage_key: str
    url: str
    mime_type: str
    size: int
    original_name: str


class StorageProvider(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, mime_type: str) -> str:
        """Persist bytes and return a retrievable URL."""

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def url_for(self, key: str) -> str: ...


class LocalStorageProvider(StorageProvider):
    """Development driver: writes under STORAGE_LOCAL_DIR, served by the API."""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or settings.storage_local_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Resolve and confine: a crafted key must not escape the storage root.
        target = (self.base_dir / key).resolve()
        if not str(target).startswith(str(self.base_dir)):
            raise ValidationError("Invalid storage key.")
        return target

    def put(self, key: str, data: bytes, mime_type: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self.url_for(key)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise ExternalServiceError(f"Stored object not found: {key}")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def url_for(self, key: str) -> str:
        """A path, not a host, unless one is explicitly configured.

        `BACKEND_URL` is a single address, and this app is deliberately reachable
        at several — localhost, the LAN IP, the HTTPS front door. Baking one of
        them into a stored `cover_image_url` would mean an image that loads on
        the machine that uploaded it and nowhere else (and is blocked as mixed
        content over HTTPS). Returning a relative path lets the client resolve it
        against whichever origin it is actually talking to, exactly as it already
        does for every API call.
        """
        if settings.storage_public_base_url:
            return f"{settings.storage_public_base_url.rstrip('/')}/{key}"
        return f"/api/files/{key}"


class S3StorageProvider(StorageProvider):
    """S3-compatible driver (AWS S3, Cloudflare R2, Supabase Storage, MinIO).

    boto3 is imported lazily so the dev environment never needs the dependency.
    """

    def __init__(self):
        try:
            import boto3  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ExternalServiceError(
                "S3 storage selected but boto3 is not installed."
            ) from exc
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint or None,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            region_name=settings.storage_region,
        )
        self._bucket = settings.storage_bucket

    def put(self, key: str, data: bytes, mime_type: str) -> str:
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=mime_type
            )
        except Exception as exc:  # pragma: no cover - network path
            logger.error("storage_put_failed", key=key, error=str(exc))
            raise ExternalServiceError("Upload failed. Please try again.") from exc
        return self.url_for(key)

    def get(self, key: str) -> bytes:
        try:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except Exception as exc:  # pragma: no cover - network path
            raise ExternalServiceError(f"Could not read object {key}") from exc

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def url_for(self, key: str) -> str:
        if settings.storage_public_base_url:
            return f"{settings.storage_public_base_url.rstrip('/')}/{key}"
        return f"{settings.storage_endpoint.rstrip('/')}/{self._bucket}/{key}"


_provider: StorageProvider | None = None


def get_storage() -> StorageProvider:
    global _provider
    if _provider is None:
        _provider = (
            S3StorageProvider() if settings.storage_provider == "s3" else LocalStorageProvider()
        )
        logger.info("storage_provider_selected", provider=settings.storage_provider)
    return _provider


def validate_upload(filename: str, content: bytes, declared_mime: str | None) -> str:
    """Validate an upload and return the trusted MIME type."""
    if not content:
        raise ValidationError("Uploaded file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise ValidationError(f"File exceeds the {settings.max_upload_mb}MB limit.")

    ext = os.path.splitext(filename or "")[1].lower()
    if ext in BLOCKED_EXTENSIONS:
        raise ValidationError(f"File type {ext} is not allowed.")

    guessed, _ = mimetypes.guess_type(filename or "")
    mime = declared_mime or guessed or "application/octet-stream"
    if mime not in ALLOWED_MIME_TYPES:
        raise ValidationError(
            "Unsupported file type. Allowed: JPEG, PNG, WebP, PDF, TXT.",
            details={"received": mime},
        )
    # The declared MIME must agree with the extension we will actually store.
    if ext and ALLOWED_MIME_TYPES[mime] != ext and not (mime == "image/jpeg" and ext == ".jpeg"):
        raise ValidationError("File extension does not match its content type.")
    _assert_magic_bytes(mime, content)
    return mime


def _assert_magic_bytes(mime: str, content: bytes) -> None:
    """Cheap content sniff so a renamed executable cannot masquerade as an image."""
    signatures = {
        "image/jpeg": (b"\xff\xd8\xff",),
        "image/png": (b"\x89PNG\r\n\x1a\n",),
        "application/pdf": (b"%PDF-",),
        "image/webp": (b"RIFF",),
    }
    expected = signatures.get(mime)
    if expected and not any(content.startswith(sig) for sig in expected):
        raise ValidationError("File content does not match its declared type.")


# --------------------------------------------------------------------------
# Text extraction — what the AI analyst actually reads
# --------------------------------------------------------------------------
# A generous cap. Long enough for a budget sheet or a project plan, short enough
# that one uploaded book cannot crowd the proposal itself out of the prompt.
MAX_EXTRACTED_CHARS = 20_000


def extract_text(mime_type: str, content: bytes) -> tuple[str | None, str | None]:
    """Pull readable text out of an upload.

    Returns `(text, note)`. Exactly one is set: `note` explains, in words meant
    for the creator, why a file yielded nothing — an image, a scanned PDF with no
    text layer, a corrupt file. Silence is the one thing this must not return,
    because a creator who uploads evidence should never be left assuming the
    model read it.
    """
    if mime_type == "text/plain":
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("utf-8", errors="replace")
        return _capped(text) or (None, "The file is empty.")

    if mime_type == "application/pdf":
        try:
            from pypdf import PdfReader  # noqa: PLC0415
        except ImportError:  # pragma: no cover - dependency is pinned
            return None, "PDF text extraction is unavailable on this server."
        try:
            reader = PdfReader(io_module.BytesIO(content))
            if reader.is_encrypted:
                return None, "The PDF is password protected, so its text cannot be read."
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            logger.warning("pdf_extract_failed", error=str(exc))
            return None, "The PDF could not be parsed, so the AI cannot read it."
        joined = "\n\n".join(part.strip() for part in pages if part.strip())
        if not joined.strip():
            return None, (
                "No text layer was found — this looks like a scanned PDF. "
                "Upload a text-based version for the AI to read it."
            )
        return _capped(joined)

    return None, "The AI reads PDF and text files; this file is stored but not read."


def _capped(text: str) -> tuple[str | None, str | None]:
    text = text.strip()
    if not text:
        return None, "The file is empty."
    if len(text) > MAX_EXTRACTED_CHARS:
        return (
            text[:MAX_EXTRACTED_CHARS],
            f"Only the first {MAX_EXTRACTED_CHARS:,} characters are given to the AI.",
        )
    return text, None


def store_upload(
    filename: str, content: bytes, declared_mime: str | None, prefix: str = "uploads"
) -> StoredFile:
    mime = validate_upload(filename, content, declared_mime)
    ext = ALLOWED_MIME_TYPES[mime]
    # Randomised key: the user-supplied name is kept as metadata only.
    key = f"{prefix}/{secrets.token_urlsafe(24)}{ext}"
    url = get_storage().put(key, content, mime)
    logger.info("file_stored", key=key, mime=mime, size=len(content))
    return StoredFile(
        storage_key=key,
        url=url,
        mime_type=mime,
        size=len(content),
        original_name=os.path.basename(filename or "upload"),
    )
