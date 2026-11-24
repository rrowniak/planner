from __future__ import annotations

import textwrap
from datetime import date

import pytest

from app.core.calendar import parse_calendar
from app.core.errors import PlannerException


def test_parses_example_calendar(calendar_toml: str) -> None:
    calendar = parse_calendar(calendar_toml, "calendar_pl.toml")
    assert len(calendar.public_holidays) == 26
    assert calendar.working_hrs_in_day == 8
    assert calendar.closed_days == {5, 6}


def test_day_classification(calendar_toml: str) -> None:
    calendar = parse_calendar(calendar_toml, "calendar_pl.toml")
    assert calendar.is_closed_weekday(date(2024, 10, 5))
    assert not calendar.is_closed_weekday(date(2024, 10, 7))
    assert calendar.is_public_holiday(date(2024, 11, 1))
    assert not calendar.is_public_holiday(date(2024, 11, 2))
    assert calendar.public_holiday_dates(date(2024, 11, 1), date(2024, 11, 12)) == {
        date(2024, 11, 1),
        date(2024, 11, 11),
    }


def test_public_holiday_ranges_are_inclusive() -> None:
    calendar = parse_calendar(
        textwrap.dedent(
            """
            closed_days = ["saturday", "sunday"]
            working_hrs_in_day = 8
            public_holidays = [
              {date="2024-05-01:2024-05-05", name="Long weekend"},
            ]
            """
        ),
        "range.toml",
    )
    for day in (1, 2, 3, 4, 5):
        assert calendar.is_public_holiday(date(2024, 5, day)), day
    assert not calendar.is_public_holiday(date(2024, 5, 6))
    assert not calendar.is_public_holiday(date(2024, 4, 30))


def test_single_digit_dates_are_accepted() -> None:
    calendar = parse_calendar(
        textwrap.dedent(
            """
            closed_days = ["saturday", "sunday"]
            working_hrs_in_day = 8
            public_holidays = [{date="2024-10-7", name="Bridge day"}]
            """
        ),
        "single.toml",
    )
    assert calendar.is_public_holiday(date(2024, 10, 7))


@pytest.mark.parametrize(
    "body, message",
    [
        ('closed_days = ["funday"]\nworking_hrs_in_day = 8', "Unknown weekday"),
        ('closed_days = ["saturday"]\nworking_hrs_in_day = 0', "positive number"),
        (
            'closed_days = ["saturday"]\nworking_hrs_in_day = 8\n'
            'public_holidays = [{date="2024-05-05:2024-05-01", name="Bad"}]',
            "ends before it starts",
        ),
    ],
)
def test_calendar_errors(body: str, message: str) -> None:
    with pytest.raises(PlannerException) as excinfo:
        parse_calendar(body, "broken.toml")
    assert any(message in error.message for error in excinfo.value.errors)
    assert all(error.source == "broken.toml" for error in excinfo.value.errors)


def test_toml_syntax_error_has_location() -> None:
    with pytest.raises(PlannerException) as excinfo:
        parse_calendar("closed_days = [\n", "broken.toml")
    error = excinfo.value.errors[0]
    assert error.source == "broken.toml"
    assert error.line is not None
    assert error.column is not None
