"""
Business-day calendars shipped as MAYA data (§13.4, `core/calendars`).

A calendar is governance input: a resolution grid built on it becomes part of
a pin's evidence, so the holiday rules live here, computed deterministically
from the year, rather than being discovered at runtime from a package that may
be a version behind. Five calendars ship: ``natural_days``,
``ISO_business_days`` (Mon-Fri), ``NYSE``, ``LSE`` and ``TARGET``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Callable

from maya.core.errors import ValidationFailed


def easter_sunday(year: int) -> date:
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The n-th (1-based) given weekday of a month; n=-1 is the last."""
    if n > 0:
        first = date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + timedelta(days=offset + 7 * (n - 1))
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed_us(d: date) -> date:
    """US rule: Saturday holidays observed Friday, Sunday observed Monday."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _nyse_holidays(year: int) -> set[date]:
    easter = easter_sunday(year)
    days = {
        _nth_weekday(year, 1, 0, 3),   # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),   # Washington's Birthday
        easter - timedelta(days=2),    # Good Friday
        _nth_weekday(year, 5, 0, -1),  # Memorial Day
        _observed_us(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),   # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed_us(date(year, 12, 25)),
    }
    new_year = date(year, 1, 1)
    # NYSE does not observe a Saturday New Year on the preceding Friday.
    if new_year.weekday() == 6:
        days.add(new_year + timedelta(days=1))
    elif new_year.weekday() < 5:
        days.add(new_year)
    if year >= 2022:
        days.add(_observed_us(date(year, 6, 19)))
    return days


def _uk_substitute(d: date, taken: set[date]) -> date:
    """UK substitute day: next weekday not already a holiday."""
    while d.weekday() >= 5 or d in taken:
        d += timedelta(days=1)
    return d


def _lse_holidays(year: int) -> set[date]:
    easter = easter_sunday(year)
    days: set[date] = {
        easter - timedelta(days=2),
        easter + timedelta(days=1),
        _nth_weekday(year, 5, 0, 1),   # Early May bank holiday
        _nth_weekday(year, 5, 0, -1),  # Spring bank holiday
        _nth_weekday(year, 8, 0, -1),  # Summer bank holiday
    }
    days.add(_uk_substitute(date(year, 1, 1), days))
    days.add(_uk_substitute(date(year, 12, 25), days))
    days.add(_uk_substitute(date(year, 12, 26), days))
    return days


def _target_holidays(year: int) -> set[date]:
    easter = easter_sunday(year)
    return {
        date(year, 1, 1),
        easter - timedelta(days=2),
        easter + timedelta(days=1),
        date(year, 5, 1),
        date(year, 12, 25),
        date(year, 12, 26),
    }


HOLIDAY_RULES: dict[str, Callable[[int], set[date]]] = {
    "NYSE": _nyse_holidays,
    "LSE": _lse_holidays,
    "TARGET": _target_holidays,
}

CALENDARS: tuple[str, ...] = ("natural_days", "ISO_business_days", "NYSE", "LSE", "TARGET")


@lru_cache(maxsize=512)
def holidays(name: str, year: int) -> frozenset[date]:
    """Holidays of a named calendar in one year (empty for the plain calendars)."""
    rule = HOLIDAY_RULES.get(name)
    return frozenset(rule(year)) if rule else frozenset()


def is_business_day(name: str, d: date) -> bool:
    """True when ``d`` is an open day on calendar ``name``."""
    if name not in CALENDARS:
        raise ValidationFailed(f"unknown calendar '{name}'", known=list(CALENDARS))
    if name == "natural_days":
        return True
    if d.weekday() >= 5:
        return False
    return d not in holidays(name, d.year)


def business_days(name: str, start: date, end: date) -> list[date]:
    """Every open day of calendar ``name`` in the closed range [start, end]."""
    if name not in CALENDARS:
        raise ValidationFailed(f"unknown calendar '{name}'", known=list(CALENDARS))
    out: list[date] = []
    d = start
    while d <= end:
        if is_business_day(name, d):
            out.append(d)
        d += timedelta(days=1)
    return out
