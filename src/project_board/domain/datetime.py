"""Framework-independent datetime normalization."""

from datetime import UTC, datetime


def normalize_utc_datetime(value: datetime, field_name: str) -> datetime:
    """Return an aware datetime in UTC, rejecting naive values."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
