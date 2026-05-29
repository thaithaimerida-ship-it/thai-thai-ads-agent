from __future__ import annotations

import ipaddress
import urllib.parse
import urllib.request


class UnsafeUrlError(ValueError):
    """Raised when a URL is unsafe for outbound server-side requests."""


_BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
}


def _is_blocked_ip(hostname: str) -> bool:
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    )


def validate_external_http_url(
    url: str,
    *,
    allowed_hosts: set[str] | None = None,
    allow_http: bool = False,
) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme:
        raise UnsafeUrlError("url_scheme_required")
    if parsed.scheme not in {"https", "http"}:
        raise UnsafeUrlError("url_scheme_not_allowed")
    if parsed.scheme == "http" and not allow_http:
        raise UnsafeUrlError("http_not_allowed")
    try:
        hostname = parsed.hostname
    except ValueError as exc:
        raise UnsafeUrlError("url_hostname_invalid") from exc
    if not hostname:
        raise UnsafeUrlError("url_hostname_required")
    hostname = hostname.lower().rstrip(".")
    if hostname in _BLOCKED_HOSTS or _is_blocked_ip(hostname):
        raise UnsafeUrlError("url_host_not_allowed")
    if allowed_hosts is not None and hostname not in {host.lower().rstrip(".") for host in allowed_hosts}:
        raise UnsafeUrlError("url_host_not_allowlisted")
    return url


def safe_urlopen(
    url: str,
    *,
    allowed_hosts: set[str],
    timeout: int,
    headers: dict[str, str] | None = None,
    allow_http: bool = False,
):
    safe_url = validate_external_http_url(
        url,
        allowed_hosts=allowed_hosts,
        allow_http=allow_http,
    )
    request_or_url: str | urllib.request.Request = safe_url
    if headers:
        request_or_url = urllib.request.Request(safe_url, headers=headers)
    return urllib.request.urlopen(request_or_url, timeout=timeout)
