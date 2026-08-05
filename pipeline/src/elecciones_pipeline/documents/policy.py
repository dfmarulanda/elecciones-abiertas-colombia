"""Exact-host validation for external, index-only document references."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

from elecciones_pipeline.ingest.policy import AllowlistPolicy, PolicyDenied

Resolver = Callable[[str], Iterable[str]]


class DocumentURLPolicy:
    """Allow only exact reviewed HTTPS hosts for public outbound links.

    Validation is deliberately local: index-only handling must not resolve or
    request an election document merely to validate its external reference.
    ``resolver`` remains an ignored compatibility argument for callers built
    before this policy change.
    """

    def __init__(
        self,
        official_hosts: set[str] | frozenset[str],
        *,
        resolver: Resolver | None = None,
    ):
        self.official_hosts = frozenset(host.lower().rstrip(".") for host in official_hosts)
        if not self.official_hosts:
            raise ValueError("at least one official host must be configured")
        self._ingest_policy = AllowlistPolicy(self.official_hosts)

    def check(self, url: str) -> None:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme != "https" or parts.username or parts.password or not host:
            raise PolicyDenied("document URL must be an HTTPS URL without user-info")
        try:
            port = parts.port
        except ValueError as exc:
            raise PolicyDenied("document URL has an invalid port") from exc
        if port not in (None, 443):
            raise PolicyDenied("document URL must use the default HTTPS port")
        if host.replace(".", "").isdigit():
            raise PolicyDenied("IP-literal document hosts are forbidden")
        if host not in self.official_hosts:
            raise PolicyDenied("document URL host is not an exact official allowlist member")
        # Keep the shared ingestion predicate in the path as a defence against
        # accidental divergence in generic URL parsing rules. It makes no
        # network request.
        if not self._ingest_policy.permits(url):
            raise PolicyDenied("document URL is outside the ingestion allowlist")
