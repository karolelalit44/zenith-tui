"""Secure HTTP transport and SSRF firewall for Zenith web tools.

Provides:
- Pre-flight asynchronous DNS validation against private, loopback, and metadata subnets.
- Safe redirect validation with per-hop IP verification (preventing DNS rebinding).
- Quality-weighted content negotiation (Accept: text/markdown > text/html).
- Dual-profile User-Agent strategy with Cloudflare 403 challenge auto-recovery.
- Bounded chunk streaming with hard payload ceiling (5MB).
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Hard security and resource boundaries
MAX_PAYLOAD_BYTES = 5 * 1024 * 1024  # 5 Megabytes
MAX_REDIRECTS = 5
DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 25.0

# User-Agent profiles
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)
HONEST_AGENT_USER_AGENT = "Zenith-Agent/1.0 (Automated Research Engine; +https://github.com/zenith-ai/zenith)"

# Content-negotiated Accept header favoring Markdown documentation
MARKDOWN_ACCEPT_HEADER = (
    "text/markdown;q=1.0, text/x-markdown;q=0.9, text/plain;q=0.8, text/html;q=0.7, */*;q=0.1"
)
PLAIN_TEXT_ACCEPT_HEADER = (
    "text/plain;q=1.0, text/markdown;q=0.9, text/html;q=0.8, */*;q=0.1"
)
HTML_ACCEPT_HEADER = (
    "text/html;q=1.0, application/xhtml+xml;q=0.9, text/plain;q=0.8, text/markdown;q=0.7, */*;q=0.1"
)

# Blocked subnets for SSRF protection
BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    # IPv4 loopback, unspecified, broadcast
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("255.255.255.255/32"),
    # RFC 1918 Private subnets
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # RFC 3927 Link-local & Cloud Metadata (AWS, GCP, Azure, DigitalOcean)
    ipaddress.ip_network("169.254.0.0/16"),
    # Carrier-grade NAT and documentation testnets
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    # Multicast and reserved
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    # IPv6 loopback, unspecified, link-local, unique-local
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
)


class TransportSecurityError(Exception):
    """Base exception for transport and SSRF security violations."""


class SSRFSecurityError(TransportSecurityError):
    """Raised when an attempt is made to access a loopback, private, or metadata address."""


class RedirectSecurityError(TransportSecurityError):
    """Raised when a redirect target violates security rules or exceeds maximum hops."""


class PayloadTooLargeError(TransportSecurityError):
    """Raised when a response payload exceeds the maximum byte limit."""


@dataclass
class TransportResponse:
    """Standardized response container for secure web fetches."""

    url: str
    status_code: int
    headers: dict[str, str]
    content_type: str
    charset: str
    body_bytes: bytes
    text: str
    is_markdown: bool = False
    is_image: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def is_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the IP address belongs to any blocked subnet."""
    for network in BLOCKED_NETWORKS:
        if ip in network:
            return True
    return False


async def validate_url_target(url: str) -> str:
    """Validate that the URL uses http/https and does not resolve to restricted networks.

    Returns the normalized URL on success; raises SSRFSecurityError or ValueError on violation.
    """
    cleaned = (url or "").strip()
    if not cleaned:
        raise ValueError("URL cannot be empty")

    parsed = urllib.parse.urlsplit(cleaned)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme '{scheme}'. Only http and https are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Invalid URL: missing hostname in '{url}'")

    # Clean brackets for IPv6 literals
    raw_host = hostname.strip("[]")

    # 1. Direct IP check if hostname is already a numeric IP literal
    try:
        ip_addr = ipaddress.ip_address(raw_host)
        if is_ip_blocked(ip_addr):
            raise SSRFSecurityError(
                f"Access to restricted or private network address is blocked: {ip_addr}"
            )
        return cleaned
    except ValueError:
        # Hostname is a domain name, proceed to DNS resolution
        pass

    # 2. Block localhost domain variants explicitly
    lower_host = hostname.lower()
    if lower_host == "localhost" or lower_host.endswith(".localhost"):
        raise SSRFSecurityError(f"Access to localhost is blocked: {hostname}")

    # 3. Asynchronous DNS resolution check
    loop = asyncio.get_running_loop()
    try:
        addr_info = await loop.getaddrinfo(
            raw_host,
            parsed.port or (443 if scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as err:
        raise SSRFSecurityError(f"Failed to resolve host '{hostname}': {err}") from err

    if not addr_info:
        raise SSRFSecurityError(f"DNS resolution returned no addresses for host '{hostname}'")

    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            if is_ip_blocked(ip_obj):
                raise SSRFSecurityError(
                    f"Host '{hostname}' resolved to blocked address {ip_obj}"
                )
        except ValueError:
            continue

    return cleaned


def is_cloudflare_challenge(status_code: int, headers: dict[str, str], body_sample: str) -> bool:
    """Detect if an HTTP response represents a Cloudflare bot/TLS challenge."""
    if status_code not in (403, 503):
        return False
    lower_headers = {k.lower(): v.lower() for k, v in headers.items()}
    if lower_headers.get("cf-mitigated") == "challenge":
        return True
    if "cf-ray" in lower_headers and status_code == 403:
        if "challenge" in body_sample.lower() or "cf-chl-opt" in body_sample.lower():
            return True
    return False


async def secure_fetch(
    url: str,
    *,
    format: str = "markdown",
    timeout: float | None = None,
    max_payload_bytes: int = MAX_PAYLOAD_BYTES,
    user_agent: str | None = None,
) -> TransportResponse:
    """Execute a secure, SSRF-guarded HTTP request with anti-bot challenge fallback.

    Enforces:
    - Pre-flight DNS & IP validation.
    - Strict per-hop redirect validation.
    - Quality-weighted content negotiation.
    - Cloudflare 403 challenge detection and retry with honest agent identity.
    - 5MB bounded streaming consumption.
    """
    initial_url = await validate_url_target(url)
    timeout_val = float(timeout or DEFAULT_READ_TIMEOUT)

    # Determine Accept header based on requested format
    fmt = format.lower().strip()
    if fmt == "markdown":
        accept_header = MARKDOWN_ACCEPT_HEADER
    elif fmt == "text":
        accept_header = PLAIN_TEXT_ACCEPT_HEADER
    elif fmt == "html":
        accept_header = HTML_ACCEPT_HEADER
    else:
        accept_header = MARKDOWN_ACCEPT_HEADER

    def _build_headers(ua: str) -> dict[str, str]:
        headers = {
            "User-Agent": ua,
            "Accept": accept_header,
            "Accept-Language": "en-US,en;q=0.9",
        }
        if ua == BROWSER_USER_AGENT:
            headers.update({
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            })
        return headers

    primary_ua = user_agent or BROWSER_USER_AGENT

    async def _execute_single_attempt(target_url: str, current_ua: str) -> TransportResponse:
        current_url = target_url
        headers = _build_headers(current_ua)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_val, connect=DEFAULT_CONNECT_TIMEOUT),
            follow_redirects=False,
            headers=headers,
        ) as client:
            hops = 0
            while True:
                # Validate URL before every dispatch (including redirect hops)
                validated_url = await validate_url_target(current_url)

                req = client.build_request("GET", validated_url)
                response = await client.send(req, stream=True)

                # Check for redirects
                if response.status_code in (301, 302, 303, 307, 308):
                    hops += 1
                    if hops > MAX_REDIRECTS:
                        await response.aclose()
                        raise RedirectSecurityError(
                            f"Too many redirects (exceeded maximum of {MAX_REDIRECTS})"
                        )
                    location = response.headers.get("Location")
                    if not location:
                        await response.aclose()
                        raise RedirectSecurityError("Redirect status received without Location header")
                    current_url = urllib.parse.urljoin(current_url, location)
                    await response.aclose()
                    continue

                # Not a redirect: consume response body with strict byte cap
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > max_payload_bytes:
                            await response.aclose()
                            raise PayloadTooLargeError(
                                f"Response Content-Length ({content_length} bytes) exceeds limit of {max_payload_bytes} bytes"
                            )
                    except ValueError:
                        pass

                chunks: list[bytes] = []
                total_bytes = 0
                try:
                    async for chunk in response.aiter_bytes():
                        total_bytes += len(chunk)
                        if total_bytes > max_payload_bytes:
                            raise PayloadTooLargeError(
                                f"Response stream exceeded maximum allowed size of {max_payload_bytes} bytes"
                            )
                        chunks.append(chunk)
                finally:
                    await response.aclose()

                raw_bytes = b"".join(chunks)
                content_type_raw = response.headers.get("content-type", "").lower()
                mime = content_type_raw.split(";")[0].strip()

                # Determine charset
                charset = "utf-8"
                if "charset=" in content_type_raw:
                    charset_part = content_type_raw.split("charset=")[-1].split(";")[0].strip()
                    if charset_part:
                        charset = charset_part

                try:
                    text_content = raw_bytes.decode(charset, errors="replace")
                except Exception:
                    text_content = raw_bytes.decode("utf-8", errors="replace")

                is_md = "markdown" in mime or "markdown" in content_type_raw
                is_img = mime.startswith("image/")

                return TransportResponse(
                    url=current_url,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    content_type=mime,
                    charset=charset,
                    body_bytes=raw_bytes,
                    text=text_content,
                    is_markdown=is_md,
                    is_image=is_img,
                    metadata={"hops": hops, "user_agent": current_ua},
                )

    # First attempt with primary User-Agent
    res = await _execute_single_attempt(initial_url, primary_ua)

    # Check if Cloudflare or anti-bot challenge was encountered
    body_sample = res.text[:1000]
    if (
        primary_ua == BROWSER_USER_AGENT
        and is_cloudflare_challenge(res.status_code, res.headers, body_sample)
    ):
        logger.info(
            "Anti-bot challenge detected on %s (HTTP %s). Retrying with honest agent profile.",
            initial_url,
            res.status_code,
        )
        fallback_res = await _execute_single_attempt(initial_url, HONEST_AGENT_USER_AGENT)
        return fallback_res

    return res
