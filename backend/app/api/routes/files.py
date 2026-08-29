"""Local storage file serving.

Only used when STORAGE_PROVIDER=local (development). With S3/R2 the object store
serves files directly and this route is never hit.
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Response

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.services import storage_service

router = APIRouter(prefix="/api/files", tags=["Campaigns"])


@router.get("/{file_path:path}")
def get_file(file_path: str) -> Response:
    if settings.storage_provider != "local":
        raise NotFoundError("File serving is handled by the object store.")
    # Traversal is rejected here and again inside the provider.
    if ".." in file_path or file_path.startswith(("/", "\\")):
        raise ValidationError("Invalid file path.")
    try:
        content = storage_service.get_storage().get(file_path)
    except Exception as exc:
        raise NotFoundError("File not found.") from exc
    mime, _ = mimetypes.guess_type(file_path)
    return Response(
        content=content,
        media_type=mime or "application/octet-stream",
        headers={
            "Cache-Control": "public, max-age=86400",
            # Uploaded content is never executed in the browser's context.
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
