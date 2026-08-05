"""Content-addressed raw response storage."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable
from inspect import isawaitable
from pathlib import Path
from typing import Protocol, TypedDict


class ObjectStore(Protocol):
    async def put(self, content: bytes, *, content_type: str | None = None) -> str:
        """Store bytes by their SHA-256 and return the immutable object key."""

    async def get(self, object_key: str) -> bytes: ...

    async def exists(self, object_key: str) -> bool: ...


class _R2Body(Protocol):
    def read(self) -> bytes | Awaitable[bytes]: ...


class _R2GetResponse(TypedDict):
    Body: _R2Body


class R2Client(Protocol):
    def put_object(self, **kwargs: object) -> object | Awaitable[object]: ...

    def get_object(self, **kwargs: object) -> _R2GetResponse | Awaitable[_R2GetResponse]: ...

    def head_object(self, **kwargs: object) -> object | Awaitable[object]: ...


async def _resolve[T](value: T | Awaitable[T]) -> T:
    if isawaitable(value):
        return await value
    return value


def object_key_for(content: bytes) -> str:
    return f"sha256/{hashlib.sha256(content).hexdigest()}"


class LocalObjectStore:
    """Filesystem implementation, useful for local/reproducible collection."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    async def put(self, content: bytes, *, content_type: str | None = None) -> str:
        key = object_key_for(content)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)
        return key

    async def get(self, object_key: str) -> bytes:
        return (self.root / object_key).read_bytes()

    async def exists(self, object_key: str) -> bool:
        return (self.root / object_key).is_file()


class R2ObjectStore:
    """Thin pluggable S3/R2 adapter; a compatible client is injected by the app."""

    def __init__(self, client: R2Client, bucket: str, prefix: str = ""):
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    def _key(self, object_key: str) -> str:
        return f"{self.prefix}/{object_key}" if self.prefix else object_key

    async def put(self, content: bytes, *, content_type: str | None = None) -> str:
        key = object_key_for(content)
        # boto3's client is deliberately injected so deployments may use an async wrapper.
        kwargs = {"Bucket": self.bucket, "Key": self._key(key), "Body": content}
        if content_type:
            kwargs["ContentType"] = content_type
        put_object = self.client.put_object
        await _resolve(put_object(**kwargs))
        return key

    async def get(self, object_key: str) -> bytes:
        result = await _resolve(
            self.client.get_object(Bucket=self.bucket, Key=self._key(object_key))
        )
        body = await _resolve(result["Body"].read())
        if not isinstance(body, bytes):
            raise TypeError("R2 object bodies must resolve to bytes")
        return body

    async def exists(self, object_key: str) -> bool:
        try:
            await _resolve(self.client.head_object(Bucket=self.bucket, Key=self._key(object_key)))
            return True
        except Exception as exc:  # client-specific not-found errors
            status = getattr(getattr(exc, "response", {}), "get", lambda _k, _d=None: _d)(
                "ResponseMetadata", {}
            ).get("HTTPStatusCode")
            if status == 404:
                return False
            raise
