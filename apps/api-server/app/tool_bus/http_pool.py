"""Process-wide HTTP client for connector calls. Implements: ADR-0002."""

import httpx

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    return _client


def set_http_client(client: httpx.AsyncClient | None) -> None:
    global _client
    _client = client
