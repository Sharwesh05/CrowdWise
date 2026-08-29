"""Campaign QR generation.

The QR encodes the campaign's *public URL* and nothing else. It carries no money,
no token and no personal data — it is a router from the physical world (posters,
slides, events) and the online world (social, video, sites) to one campaign page.
"""

from __future__ import annotations

import base64
import io
import secrets

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from app.core.config import settings


def new_qr_token() -> str:
    """Unguessable token stored alongside the campaign for QR verification."""
    return secrets.token_urlsafe(24)


def campaign_url(public_id: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}/campaign/{public_id}"


def build_qr_png(data: str, box_size: int = 10, border: int = 4) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,  # tolerates print wear and camera angles
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#0F172A", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def build_campaign_qr(public_id: str) -> tuple[str, bytes]:
    url = campaign_url(public_id)
    return url, build_qr_png(url)


def qr_data_uri(public_id: str) -> str:
    _, png = build_campaign_qr(public_id)
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
