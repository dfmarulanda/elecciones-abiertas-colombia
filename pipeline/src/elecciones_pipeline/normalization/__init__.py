"""Strict source-shape adapters and source-local election facts."""

from .act import ActSchemaError, SourceSnapshot, canonical_mesa_id, parse_precount_act
from .aggregate import AggregationError, aggregate_complete_mesa_facts
from .values import LocalizedValueError, parse_localized_integer, parse_localized_percentage

__all__ = [
    "ActSchemaError",
    "AggregationError",
    "LocalizedValueError",
    "SourceSnapshot",
    "canonical_mesa_id",
    "aggregate_complete_mesa_facts",
    "parse_localized_integer",
    "parse_localized_percentage",
    "parse_precount_act",
]
