"""Deny path traversal and sensitive local files. Implements: REQ-012, TC-M3-03."""

import re

_SENSITIVE_FILE = re.compile(
    r"(^|/)\.env($|\.)|\.pem$|\.pfx$|(^|/)id_rsa($|\.)|(^|/)\.git(/|$)|(^|/)node_modules(/|$)",
    re.IGNORECASE,
)


def local_path_violation(path: str) -> str | None:
    """Return PATH_TRAVERSAL or SENSITIVE_FILE, or None when the relative path is allowed."""

    normalized = path.replace("\\", "/").strip()
    if not normalized:
        return None
    segments = [segment for segment in normalized.split("/") if segment]
    if any(segment == ".." for segment in segments):
        return "PATH_TRAVERSAL"
    if _SENSITIVE_FILE.search(normalized):
        return "SENSITIVE_FILE"
    return None
