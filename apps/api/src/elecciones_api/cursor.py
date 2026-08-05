"""Opaque, signed cursors bound to a release and a normalized filter set."""

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping


class CursorError(ValueError):
    pass


_MAX_CURSOR_BYTES = 1024
_CURSOR_VERSION = 1


def scope_for(filters: Mapping[str, object]) -> str:
    payload = json.dumps(filters, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def encode_cursor(offset: int, scope: str, secret: str) -> str:
    body = json.dumps(
        {"v": _CURSOR_VERSION, "o": offset, "s": scope}, separators=(",", ":"), sort_keys=True
    ).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(body + signature).decode().rstrip("=")


def decode_cursor(cursor: str, expected_scope: str, secret: str) -> int:
    try:
        if len(cursor) > _MAX_CURSOR_BYTES:
            raise CursorError("The cursor is too large.")
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        body, signature = raw[:-32], raw[-32:]
        expected = hmac.new(secret.encode(), body, hashlib.sha256).digest()
        value = json.loads(body)
        if (
            not hmac.compare_digest(signature, expected)
            or value["v"] != _CURSOR_VERSION
            or value["s"] != expected_scope
        ):
            raise CursorError("The cursor does not match this query.")
        offset = value["o"]
        if not isinstance(offset, int) or offset < 0:
            raise CursorError("The cursor offset is invalid.")
        return offset
    except CursorError:
        raise
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise CursorError("The cursor is invalid or has been tampered with.") from exc


def encode_keyset_cursor(position: tuple[str, ...], scope: str, secret: str) -> str:
    """Encode a stable SQL seek position, never a release-sized OFFSET."""
    body = json.dumps(
        {"v": _CURSOR_VERSION, "k": position, "s": scope}, separators=(",", ":"), sort_keys=True
    ).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(body + signature).decode().rstrip("=")


def decode_keyset_cursor(cursor: str, expected_scope: str, secret: str) -> tuple[str, ...]:
    try:
        if len(cursor) > _MAX_CURSOR_BYTES:
            raise CursorError("The cursor is too large.")
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        body, signature = raw[:-32], raw[-32:]
        value = json.loads(body)
        expected = hmac.new(secret.encode(), body, hashlib.sha256).digest()
        position = value["k"]
        if (
            not hmac.compare_digest(signature, expected)
            or value["v"] != _CURSOR_VERSION
            or value["s"] != expected_scope
        ):
            raise CursorError("The cursor does not match this query.")
        if (
            not isinstance(position, list)
            or not position
            or not all(isinstance(item, str) for item in position)
        ):
            raise CursorError("The cursor position is invalid.")
        return tuple(position)
    except CursorError:
        raise
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise CursorError("The cursor is invalid or has been tampered with.") from exc
