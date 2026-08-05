"""URL and usage policy checks; never resolve arbitrary discovered hosts."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable
from typing import cast
from urllib.parse import urlsplit


class PolicyDenied(ValueError):
    """The configured collection policy does not permit this request."""


UsageHook = Callable[[str], bool | Awaitable[bool]]
Resolver = Callable[[str], Iterable[str]]


def _system_resolver(host: str) -> Iterable[str]:
    return {
        cast(str, item[4][0])
        for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    }


class AllowlistPolicy:
    """Allow HTTPS URLs on reviewed official hosts only.

    Host comparison is exact (or an explicit subdomain), preventing lookalike and
    user-info SSRF forms such as ``official.gov.co@127.0.0.1``.
    """

    def __init__(
        self,
        official_hosts: set[str] | frozenset[str],
        usage_hook: UsageHook | None = None,
        *,
        resolver: Resolver = _system_resolver,
    ):
        self.official_hosts = frozenset(host.lower().rstrip(".") for host in official_hosts)
        if not self.official_hosts:
            raise ValueError("at least one official host must be configured")
        self.usage_hook = usage_hook
        self.resolver = resolver

    def permits(self, url: str) -> bool:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
        return (
            parts.scheme == "https"
            and not parts.username
            and not parts.password
            and bool(host)
            and host in self.official_hosts
        )

    @staticmethod
    def _is_public(address: str) -> bool:
        parsed = ipaddress.ip_address(address)
        return not (
            parsed.is_private or parsed.is_loopback or parsed.is_link_local or parsed.is_multicast
            or parsed.is_reserved or parsed.is_unspecified
        )

    async def check(self, url: str) -> None:
        if not self.permits(url):
            raise PolicyDenied(f"URL is outside the official-host allowlist: {url}")
        parts = urlsplit(url)
        try:
            port = parts.port
        except ValueError as exc:
            raise PolicyDenied("URL has an invalid port") from exc
        if port not in (None, 443):
            raise PolicyDenied("official URL must use the default HTTPS port")
        host = (parts.hostname or "").lower().rstrip(".")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise PolicyDenied("IP-literal official hosts are forbidden")
        try:
            addresses = tuple(self.resolver(host))
        except (OSError, ValueError, socket.gaierror) as exc:
            raise PolicyDenied("official host could not be resolved safely") from exc
        if not addresses or any(not self._is_public(address) for address in addresses):
            raise PolicyDenied("official host resolved to a non-public address")
        if self.usage_hook is not None:
            decision = self.usage_hook(url)
            if hasattr(decision, "__await__"):
                decision = await decision
            if not decision:
                raise PolicyDenied(f"usage policy denied request: {url}")
