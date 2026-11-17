"""Pure functions for study statistics. No Flask or database access, so they are easy to test."""
from datetime import date, timedelta


def streak(days, today):
    """Consecutive days with at least one session, ending today (or yesterday if today has none yet)."""
    days = set(days)
    d = today if today in days else today - timedelta(days=1)
    n = 0
    while d in days:
        n += 1
        d -= timedelta(days=1)
    return n


def daily_series(minutes_by_day, today, n=14):
    """Oldest to newest list of {day, minutes} for the last n days, filling gaps with 0."""
    out = []
    for i in range(n - 1, -1, -1):
        d = today - timedelta(days=i)
        out.append({"day": d.isoformat(), "minutes": minutes_by_day.get(d, 0)})
    return out


def window_total(minutes_by_day, today, n=7):
    """Total minutes over the last n days including today."""
    return sum(minutes_by_day.get(today - timedelta(days=i), 0) for i in range(n))


def goal_pct(minutes, goal):
    return 0 if goal <= 0 else min(100, round(minutes * 100 / goal))


def parse_day(value):
    """'YYYY-MM-DD' -> date, or None if it is not a real date."""
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
