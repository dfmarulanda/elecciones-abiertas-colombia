"""Parsing for values as published in Colombian election source documents."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


class LocalizedValueError(ValueError):
    """A source value cannot be interpreted without guessing."""


_INTEGER = re.compile(r"^[+-]?\d{1,3}(?:[.\s]\d{3})*$|^[+-]?\d+$")
_PERCENTAGE = re.compile(r"^[+-]?(?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d+)?%?$")


def _text(value: object) -> str:
    if isinstance(value, bool) or value is None:
        raise LocalizedValueError("value is missing or not numeric")
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        raise LocalizedValueError("value must be an integer or localized string")
    text = value.strip().replace("\u00a0", " ")
    if not text:
        raise LocalizedValueError("value is blank")
    return text


def parse_localized_integer(value: object) -> int:
    """Parse a non-negative integer; punctuation is only accepted as a thousands separator."""
    text = _text(value)
    if not _INTEGER.fullmatch(text):
        raise LocalizedValueError(f"invalid localized integer {value!r}")
    parsed = int(text.replace(".", "").replace(" ", ""))
    if parsed < 0:
        raise LocalizedValueError("count cannot be negative")
    return parsed


def parse_localized_percentage(value: object) -> Decimal:
    """Parse Colombian percentage notation (``12,5 %``) without lossy float conversion."""
    text = _text(value).replace(" ", "")
    if not _PERCENTAGE.fullmatch(text):
        raise LocalizedValueError(f"invalid localized percentage {value!r}")
    normalized = text.removesuffix("%").replace(".", "").replace(",", ".")
    try:
        parsed = Decimal(normalized)
    except InvalidOperation as exc:  # pragma: no cover - regex is the primary guard
        raise LocalizedValueError(f"invalid localized percentage {value!r}") from exc
    if not Decimal("0") <= parsed <= Decimal("100"):
        raise LocalizedValueError("percentage must be between 0 and 100")
    return parsed
