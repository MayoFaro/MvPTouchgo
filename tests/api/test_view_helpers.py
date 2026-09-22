from datetime import datetime, timedelta, timezone

from src.api.view_helpers import format_relative_time


def test_format_relative_time_under_a_minute():
    dt = datetime.now(timezone.utc) - timedelta(seconds=30)
    assert format_relative_time(dt) == "à l'instant"


def test_format_relative_time_in_minutes():
    dt = datetime.now(timezone.utc) - timedelta(minutes=37)
    assert format_relative_time(dt) == "il y a 37 min"


def test_format_relative_time_in_hours():
    dt = datetime.now(timezone.utc) - timedelta(hours=5)
    assert format_relative_time(dt) == "il y a 5 h"


def test_format_relative_time_in_days():
    dt = datetime.now(timezone.utc) - timedelta(days=2)
    assert format_relative_time(dt) == "il y a 2 j"
