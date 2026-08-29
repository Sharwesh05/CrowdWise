"""Structured logging.

Rules enforced here: no passwords, no payment secrets, no private keys and no KYC
payloads ever reach the log stream. `redact()` is the single helper services use
before logging anything that came from a user or an integration.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "new_password",
    "current_password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "secret",
    "key_secret",
    "webhook_secret",
    "private_key",
    "blockchain_private_key",
    "razorpay_key_secret",
    "razorpay_signature",
    "pan",
    "pan_number",
    "aadhaar",
    "aadhaar_number",
    "account_number",
    "bank_account",
    "ifsc",
    "date_of_birth",
    "dob",
    "address",
    "metadata_json",
}

_REDACTED = "[redacted]"


def redact(payload: Any) -> Any:
    """Recursively strip sensitive values before they reach a log line."""
    if isinstance(payload, dict):
        return {
            k: (_REDACTED if k.lower() in _SENSITIVE_KEYS else redact(v))
            for k, v in payload.items()
        }
    if isinstance(payload, (list, tuple)):
        return [redact(v) for v in payload]
    return payload


def _drop_sensitive(_logger, _name, event_dict):
    return redact(event_dict)


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _drop_sensitive,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "crowdwise"):
    return structlog.get_logger(name)
