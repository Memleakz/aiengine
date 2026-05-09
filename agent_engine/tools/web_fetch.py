import ipaddress
import urllib.error
import urllib.request
from urllib.parse import urlparse

_PRIVATE_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / cloud metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_ssrf_blocked(hostname: str) -> bool:
    """Return True if the hostname resolves to a private/loopback address."""
    import socket
    try:
        addr = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(addr)
        return any(ip in net for net in _PRIVATE_RANGES)
    except Exception:
        return False


async def web_fetch(url: str) -> str:
    """Fetch the contents of a URL and return it as text."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Error: Unsupported scheme '{parsed.scheme}'. Only http and https are allowed."

    hostname = parsed.hostname or ""
    if not hostname:
        return "Error: URL has no hostname."
    if _is_ssrf_blocked(hostname):
        return f"Error: Access to '{hostname}' is blocked (private/internal address)."

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Agent/1.0"}
    )

    try:
        # urllib is synchronous, but for simple fetching in a demo this is acceptable.
        # For true async, we'd use aiohttp or run_in_executor.
        import asyncio
        loop = asyncio.get_event_loop()

        def _fetch():
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read()

        data = await loop.run_in_executor(None, _fetch)
        text = data.decode("utf-8", errors="replace")

        # simple truncation to avoid overwhelming the context
        if len(text) > 8000:
            return text[:8000] + "\n... [content truncated]"
        return text

    except urllib.error.URLError as e:
        return f"Error fetching {url}: {e.reason}"
    except Exception as e:
        return f"Error: {e}"
