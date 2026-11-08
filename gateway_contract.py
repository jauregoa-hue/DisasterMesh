"""Shared GPS policy. A location is a fix at event time, never an invented point."""
import math
from datetime import datetime, timezone


def utc(value: datetime) -> datetime:
    # SQLAlchemy's SQLite adapter returns naive UTC, unlike PostgreSQL.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def position_status(latitude, longitude, timestamp, event_time, max_age=300):
    if latitude is None or longitude is None:
        return "missing"
    if (isinstance(latitude, bool) or isinstance(longitude, bool)
            or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float))
            or not math.isfinite(latitude) or not math.isfinite(longitude)
            or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
            or (latitude == 0 and longitude == 0)):
        return "invalid"
    if timestamp is None:
        return "unknown_time"
    age = (utc(event_time) - utc(timestamp)).total_seconds()
    if age < 0:
        return "future"
    if age > max_age:
        return "stale"
    return "valid"
