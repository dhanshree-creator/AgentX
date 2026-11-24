"""Network-safety guard: only public HTTPS endpoints allowed through model use."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from agent.exceptions import ToolExecutionError

_BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "metadata.google.internal",
    "169.254.169.254",
}


def assert_public_url(url: str) -> None:
    """Raise ToolExecutionError unless url is a public HTTPS host."""
    try:
        p = urlparse(url)
    except ValueError:
        raise ToolExecutionError("Malformed URL.") from None
    if p.scheme != "https":
        raise ToolExecutionError("Only https:// URLs are allowed.")
    host = (p.hostname or "").lower()
    if not host:
        raise ToolExecutionError("URL has no hostname.")
    if host in _BLOCKED_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        raise ToolExecutionError(f"Host {host!r} is restricted (private/metadata/internal host).")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and not ip.is_global:
        raise ToolExecutionError(f"Host {host!r} resolves to a non-global IP (private network).")
    # Literal-IP hosts are fully validated above. For DNS hostnames we also do a
    # best-effort resolve check when DNS is available; if the network is offline
    # (common in tests/CI), the literal-IP and name-blocklist checks still apply.
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        return None  # offline environment: name checks above already passed
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if not ip.is_global:
            raise ToolExecutionError(
                f"Host {host!r} resolves to a non-global address ({addr}); blocked."
            )
