"""Tests for the secure transport layer and SSRF firewall (_transport.py)."""

import ipaddress
import pytest

from server.toolkit.tools._transport import (
    BROWSER_USER_AGENT,
    HONEST_AGENT_USER_AGENT,
    PayloadTooLargeError,
    RedirectSecurityError,
    SSRFSecurityError,
    TransportResponse,
    is_cloudflare_challenge,
    is_ip_blocked,
    secure_fetch,
    validate_url_target,
)


class TestSSRFValidation:
    """Validate that private, loopback, link-local, and cloud metadata targets are rejected."""

    def test_empty_url_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            import asyncio
            asyncio.run(validate_url_target(""))

    def test_unsupported_schemes_rejected(self):
        for url in ("ftp://example.com", "file:///etc/passwd", "gopher://evil.com"):
            with pytest.raises(ValueError, match="Unsupported URL scheme"):
                import asyncio
                asyncio.run(validate_url_target(url))

    def test_loopback_ips_blocked(self):
        for ip in ("127.0.0.1", "127.0.1.5", "127.255.255.255"):
            url = f"http://{ip}:8080/test"
            with pytest.raises(SSRFSecurityError, match="restricted or private"):
                import asyncio
                asyncio.run(validate_url_target(url))

    def test_ipv6_loopback_blocked(self):
        url = "http://[::1]:8080/api"
        with pytest.raises(SSRFSecurityError, match="restricted or private"):
            import asyncio
            asyncio.run(validate_url_target(url))

    def test_localhost_hostname_blocked(self):
        for host in ("localhost", "api.localhost", "LOCALhost"):
            url = f"http://{host}:3000/metrics"
            with pytest.raises(SSRFSecurityError, match="localhost is blocked"):
                import asyncio
                asyncio.run(validate_url_target(url))

    def test_rfc1918_private_ips_blocked(self):
        private_ips = [
            "10.0.0.1",
            "10.254.0.1",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.0.1",
            "192.168.1.254",
        ]
        for ip in private_ips:
            url = f"http://{ip}/admin"
            with pytest.raises(SSRFSecurityError, match="restricted or private"):
                import asyncio
                asyncio.run(validate_url_target(url))

    def test_cloud_metadata_ips_blocked(self):
        # AWS, GCP, Azure, DigitalOcean instance metadata service
        url = "http://169.254.169.254/latest/meta-data/"
        with pytest.raises(SSRFSecurityError, match="restricted or private"):
            import asyncio
            asyncio.run(validate_url_target(url))

    def test_carrier_grade_nat_blocked(self):
        url = "http://100.64.0.1/status"
        with pytest.raises(SSRFSecurityError, match="restricted or private"):
            import asyncio
            asyncio.run(validate_url_target(url))

    @pytest.mark.asyncio
    async def test_public_domain_resolves_cleanly(self):
        # example.com is a dedicated IANA documentation domain that resolves to public IPs
        url = "https://example.com/docs"
        validated = await validate_url_target(url)
        assert validated == "https://example.com/docs"


class TestCloudflareChallengeDetection:
    """Test recognition of Cloudflare bot challenge markers."""

    def test_detects_cf_mitigated_header(self):
        headers = {"cf-mitigated": "challenge", "server": "cloudflare"}
        assert is_cloudflare_challenge(403, headers, "") is True

    def test_detects_cf_ray_with_challenge_body(self):
        headers = {"cf-ray": "8c59123-SJC", "server": "cloudflare"}
        body = "<html><body>Please enable cookies and complete the challenge cf-chl-opt</body></html>"
        assert is_cloudflare_challenge(403, headers, body) is True

    def test_ignores_standard_403(self):
        headers = {"server": "nginx"}
        body = "403 Forbidden: Invalid permissions"
        assert is_cloudflare_challenge(403, headers, body) is False

    def test_ignores_standard_200(self):
        headers = {"cf-ray": "8c59123-SJC"}
        body = "Normal page content with challenge mention in text"
        assert is_cloudflare_challenge(200, headers, body) is False


class TestMockedSecureFetch:
    """Test transport execution, retry logic, and payload limit enforcement."""

    @pytest.mark.asyncio
    async def test_challenge_retry_fallback(self, monkeypatch):
        # Track dispatched requests and headers
        dispatched_uas = []

        import httpx

        async def mock_send(client, request, **kwargs):
            ua = request.headers.get("User-Agent", "")
            dispatched_uas.append(ua)

            if ua == BROWSER_USER_AGENT:
                # First attempt with Chrome UA triggers challenge
                return httpx.Response(
                    status_code=403,
                    headers={"cf-mitigated": "challenge", "content-type": "text/html"},
                    content=b"Cloudflare challenge",
                    request=request,
                )
            else:
                # Fallback attempt with honest agent succeeds
                return httpx.Response(
                    status_code=200,
                    headers={"content-type": "text/markdown"},
                    content=b"# Success with honest agent",
                    request=request,
                )

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

        # Bypass DNS check for the test domain
        async def mock_dns(url):
            return url

        monkeypatch.setattr("server.toolkit.tools._transport.validate_url_target", mock_dns)

        response = await secure_fetch("https://docs.example.com/api")
        assert response.status_code == 200
        assert response.text == "# Success with honest agent"
        assert len(dispatched_uas) == 2
        assert dispatched_uas[0] == BROWSER_USER_AGENT
        assert dispatched_uas[1] == HONEST_AGENT_USER_AGENT

    @pytest.mark.asyncio
    async def test_content_length_exceeded_aborts(self, monkeypatch):
        import httpx

        async def mock_send(client, request, **kwargs):
            return httpx.Response(
                status_code=200,
                headers={"content-length": str(10 * 1024 * 1024)},  # 10MB
                content=b"large",
                request=request,
            )

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

        async def mock_dns(url):
            return url

        monkeypatch.setattr("server.toolkit.tools._transport.validate_url_target", mock_dns)

        with pytest.raises(PayloadTooLargeError, match="exceeds limit"):
            await secure_fetch("https://example.com/huge-file.iso")

    @pytest.mark.asyncio
    async def test_redirect_limit_enforced(self, monkeypatch):
        import httpx

        async def mock_send(client, request, **kwargs):
            # Infinite redirect loop
            return httpx.Response(
                status_code=302,
                headers={"Location": "/redirect-target"},
                request=request,
            )

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

        async def mock_dns(url):
            return url

        monkeypatch.setattr("server.toolkit.tools._transport.validate_url_target", mock_dns)

        with pytest.raises(RedirectSecurityError, match="Too many redirects"):
            await secure_fetch("https://example.com/loop")
