from datetime import UTC, datetime


async def get_time() -> str:
    """Get the current system date and time in UTC (ISO 8601 format)."""
    return datetime.now(tz=UTC).isoformat()
