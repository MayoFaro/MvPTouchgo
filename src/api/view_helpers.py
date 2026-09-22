from datetime import datetime, timezone


def format_relative_time(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    seconds = int((now - dt).total_seconds())
    if seconds < 60:
        return "à l'instant"
    minutes = seconds // 60
    if minutes < 60:
        return f"il y a {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"il y a {hours} h"
    days = hours // 24
    return f"il y a {days} j"
