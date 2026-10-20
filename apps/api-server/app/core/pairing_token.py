"""Local MCP Daemon pairing tokens; only their SHA-256 digest is stored. Implements: REQ-005."""

import hashlib
import secrets


def new_pairing_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
