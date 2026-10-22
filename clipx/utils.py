"""Shared relative-time formatting.

Provides a single helper that renders SQLite UTC timestamps as short,
localized relative-time strings for the history list.
"""
from datetime import datetime, timezone


def format_relative_time(dt_str: str) -> str:
    """Convert a SQLite UTC timestamp to a friendly relative time string.

    The timestamp is treated as UTC. Labels are in Portuguese: "agora" below
    one minute, "Nm atrás" below one hour, "Nh atrás" below one day, "ontem"
    for one day, "Nd atrás" below a week, and ``DD/MM`` beyond that.

    Args:
        dt_str (str): Timestamp in SQLite ``YYYY-MM-DD HH:MM:SS`` format.

    Returns:
        str: Relative time label, or the original input string when it cannot
        be parsed.
    """
    try:
        # SQLite CURRENT_TIMESTAMP is in UTC: 'YYYY-MM-DD HH:MM:SS'
        dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = now - dt

        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "agora"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m atrás"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h atrás"
        days = hours // 24
        if days == 1:
            return "ontem"
        if days < 7:
            return f"{days}d atrás"
        return dt.strftime("%d/%m")
    except Exception:
        return dt_str
