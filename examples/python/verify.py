from __future__ import annotations

import hashlib
import hmac
import re

_SIGNATURE_PATTERN = re.compile(r"^sha256=[0-9a-f]{64}$")


def verify_github_webhook(
    payload: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Verify a GitHub X-Hub-Signature-256 value against the raw request body."""
    if (
        not secret
        or signature_header is None
        or not _SIGNATURE_PATTERN.fullmatch(signature_header)
    ):
        return False

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)
