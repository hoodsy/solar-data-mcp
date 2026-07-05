"""Download-safety guard for the sync_* tools.

The `source` argument of a sync tool is agent-controlled, so a prompt-injected
agent could aim it at internal services or cloud-metadata endpoints. Bulk
downloads are therefore restricted to each dataset's official host over https,
with a non-routable-address backstop against misconfiguration/rebinding.
Redirects are refused (see fetch_to_tempfile), so the host validated here is the
host actually connected to.
"""

import ipaddress
import socket
from urllib.parse import urlparse

from solar_mcp_core.config import SourceConfig
from solar_mcp_core.errors import BadInput


def official_host(config: SourceConfig) -> str:
    """The one host a dataset's bulk file may be fetched from (its API base)."""
    return (urlparse(config.base_url).hostname or "").lower()


def assert_allowed_download_url(url: str, config: SourceConfig) -> None:
    """Allow only https URLs on the dataset's official host that resolve to a
    public address. Raises BadInput (naming the fix) on any violation."""
    parsed = urlparse(url)
    allowed = official_host(config)
    if parsed.scheme != "https":
        raise BadInput(
            field="source",
            value=url,
            allowed=f"an https:// URL on {allowed}, or a local file path",
        )
    host = (parsed.hostname or "").lower()
    if host != allowed:
        raise BadInput(
            field="source",
            value=url,
            allowed=(
                f"a URL on the official host {allowed} "
                "(download the file yourself and pass a local path to use any other source)"
            ),
        )
    _assert_public_host(host)


def _assert_public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise BadInput(field="source", value=host, allowed=f"a resolvable host ({exc})") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local  # blocks 169.254.169.254 cloud metadata
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise BadInput(
                field="source",
                value=host,
                allowed="a public host (it resolved to a non-routable address; refusing to fetch)",
            )
