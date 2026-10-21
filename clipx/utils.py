"""Shared relative-time formatting."""
from datetime import datetime, timezone


def format_relative_time(dt_str: str) -> str:
    """Converts a SQLite UTC timestamp to a friendly relative time string."""
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
