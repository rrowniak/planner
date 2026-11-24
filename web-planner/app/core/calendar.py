from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .errors import PlannerError, PlannerException
from .tomlutil import load_toml

DateRange = tuple[date, date]
_DATE_PATTERN = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")

WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

_WEEKDAY_LOOKUP = {name: index for index, name in enumerate(WEEKDAYS)}
_WEEKDAY_LOOKUP.update({name[:3]: index for index, name in enumerate(WEEKDAYS)})


def parse_date(value: object, *, source: str, path: str) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise PlannerException(
            [PlannerError(f"'{path}' must be a date string (YYYY-MM-DD)", source=source, path=path)]
        )
    match = _DATE_PATTERN.match(value.strip())
    try:
        if match is None:
            raise ValueError(value)
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError as exc:
        raise PlannerException(
            [
                PlannerError(
                    f"Invalid date '{value}' in '{path}', expected YYYY-MM-DD",
                    source=source,
                    path=path,
                )
            ]
        ) from exc


def parse_date_ranges(value: object, *, source: str, path: str) -> list[DateRange]:
    if value is None:
        return []
    if isinstance(value, date):
        return [(value, value)]
    if not isinstance(value, str):
        raise PlannerException(
            [PlannerError(f"'{path}' must be a date or date-range string", source=source, path=path)]
        )

    ranges: list[DateRange] = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.count(":") > 1:
            raise PlannerException(
                [PlannerError(f"Invalid date range '{chunk}' in '{path}'", source=source, path=path)]
            )
        if ":" in chunk:
            raw_start, raw_end = chunk.split(":", 1)
            start = parse_date(raw_start.strip(), source=source, path=path)
            end = parse_date(raw_end.strip(), source=source, path=path)
            if end < start:
                raise PlannerException(
                    [
                        PlannerError(
                            f"Date range '{chunk}' ends before it starts",
                            source=source,
                            path=path,
                        )
                    ]
                )
            ranges.append((start, end))
        else:
            day = parse_date(chunk, source=source, path=path)
            ranges.append((day, day))
    return ranges


def in_ranges(day: date, ranges: list[DateRange]) -> bool:
    return any(start <= day <= end for start, end in ranges)


@dataclass
class PublicHoliday:
    ranges: list[DateRange]
    name: str


@dataclass
class Calendar:
    name: str
    closed_days: set[int]
    working_hrs_in_day: float
    public_holidays: list[PublicHoliday]

    def is_closed_weekday(self, day: date) -> bool:
        return day.weekday() in self.closed_days

    def is_public_holiday(self, day: date) -> bool:
        return any(in_ranges(day, holiday.ranges) for holiday in self.public_holidays)

    def public_holiday_dates(self, start: date, end: date) -> set[date]:
        dates: set[date] = set()
        for holiday in self.public_holidays:
            for range_start, range_end in holiday.ranges:
                current = max(range_start, start)
                last = min(range_end, end)
                while current <= last:
                    dates.add(current)
                    current = date.fromordinal(current.toordinal() + 1)
        return dates


def parse_calendar(text: str, name: str) -> Calendar:
    data = load_toml(text, source=name)
    errors: list[PlannerError] = []

    closed_raw = data.get("closed_days")
    closed_days: set[int] = set()
    if not isinstance(closed_raw, list):
        errors.append(
            PlannerError("'closed_days' must be a list of weekday names", source=name, path="closed_days")
        )
    else:
        for index, value in enumerate(closed_raw):
            if not isinstance(value, str) or value.strip().lower() not in _WEEKDAY_LOOKUP:
                errors.append(
                    PlannerError(
                        f"Unknown weekday '{value}' in 'closed_days[{index}]'",
                        source=name,
                        path=f"closed_days[{index}]",
                        hint=f"Use one of: {', '.join(WEEKDAYS)}",
                    )
                )
            else:
                closed_days.add(_WEEKDAY_LOOKUP[value.strip().lower()])

    hours_raw = data.get("working_hrs_in_day")
    if isinstance(hours_raw, bool) or not isinstance(hours_raw, (int, float)) or hours_raw <= 0:
        errors.append(
            PlannerError(
                "'working_hrs_in_day' must be a positive number",
                source=name,
                path="working_hrs_in_day",
            )
        )
        working_hours = 8.0
    else:
        working_hours = float(hours_raw)

    public_holidays: list[PublicHoliday] = []
    holidays_raw = data.get("public_holidays", [])
    if not isinstance(holidays_raw, list):
        errors.append(
            PlannerError("'public_holidays' must be a list of tables", source=name, path="public_holidays")
        )
    else:
        for index, entry in enumerate(holidays_raw):
            path = f"public_holidays[{index}]"
            if not isinstance(entry, dict):
                errors.append(PlannerError(f"'{path}' must be a table", source=name, path=path))
                continue
            try:
                ranges = parse_date_ranges(entry.get("date"), source=name, path=f"{path}.date")
            except PlannerException as exc:
                errors.extend(exc.errors)
                continue
            holiday_name = entry.get("name", "")
            if not isinstance(holiday_name, str):
                errors.append(PlannerError(f"'{path}.name' must be a string", source=name, path=f"{path}.name"))
                continue
            public_holidays.append(PublicHoliday(ranges=ranges, name=holiday_name))

    if errors:
        raise PlannerException(errors)

    return Calendar(
        name=name,
        closed_days=closed_days,
        working_hrs_in_day=working_hours,
        public_holidays=public_holidays,
    )
