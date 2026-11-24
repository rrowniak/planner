from __future__ import annotations

import textwrap

import pytest

from app.core.calendar import parse_calendar
from app.core.errors import PlannerException
from app.core.project import parse_project
from app.core.scheduler import build_schedule

CUSTOM_CALENDAR = textwrap.dedent(
    """
    closed_days = ["saturday", "sunday"]
    working_hrs_in_day = 8
    public_holidays = []
    """
)


def build(project_toml: str, calendar_toml: str, name: str = "calendar_pl.toml") -> dict:
    project = parse_project(project_toml)
    return build_schedule(project, {name: parse_calendar(calendar_toml, name)})


def by_id(schedule: dict) -> dict[str, dict]:
    return {task["id"]: task for task in schedule["tasks"]}


def validation_project(*, base_calendar: str = "calendar_pl.toml", tasks: str, assignments: str) -> str:
    return textwrap.dedent(
        f"""
        project_name = "Validation"
        start_date = "2024-01-01"
        team = [{{ name="Dev", base_calendar="{base_calendar}", focus_factor=1.0, holidays="", other_duties="" }}]
        tasks = [{tasks}]
        assignments = [{assignments}]
        """
    )


def test_simple_project_dates(simple_project_toml: str, calendar_toml: str) -> None:
    schedule = build(simple_project_toml, calendar_toml)
    tasks = by_id(schedule)

    assert [task["id"] for task in schedule["tasks"]] == ["T1", "T2", "T3", "T4", "T5"]
    assert (tasks["T1"]["startDate"], tasks["T1"]["endDate"]) == ("2024-10-01", "2024-10-02")
    assert (tasks["T2"]["startDate"], tasks["T2"]["endDate"]) == ("2024-10-03", "2024-10-09")
    assert (tasks["T3"]["startDate"], tasks["T3"]["endDate"]) == ("2024-10-10", "2024-10-21")
    assert (tasks["T4"]["startDate"], tasks["T4"]["endDate"]) == ("2024-10-22", "2024-11-13")
    assert (tasks["T5"]["startDate"], tasks["T5"]["endDate"]) == ("2024-11-14", "2024-11-20")
    assert schedule["projectStart"] == "2024-10-01"
    assert schedule["projectEnd"] == "2024-11-20"
    assert schedule["axisEnd"] == "2024-11-20"
    assert schedule["warnings"] == []
    assert len(schedule["days"]) == 51
    assert len(schedule["workers"]) == 1
    assert len(schedule["workers"][0]["days"]) == 51


def test_simple_project_fractional_offsets(simple_project_toml: str, calendar_toml: str) -> None:
    tasks = by_id(build(simple_project_toml, calendar_toml))

    assert tasks["T1"]["startOffset"] == 0.0
    assert tasks["T1"]["finishOffset"] == 2.0
    assert tasks["T2"]["startOffset"] == 2.0
    assert tasks["T5"]["finishOffset"] == 50.375
    assert tasks["T5"]["segments"][-1]["end"] == 50.375
    assert tasks["T2"]["pauseDays"] == [
        "2024-10-05",
        "2024-10-06",
        "2024-10-07",
        "2024-10-08",
    ]

    for task in tasks.values():
        assert task["segments"], task["id"]
        assert task["segments"][0]["start"] == task["startOffset"]
        assert task["segments"][-1]["end"] == task["finishOffset"]
        for previous, following in zip(task["segments"], task["segments"][1:]):
            assert following["start"] >= previous["end"]


def test_simple_project_allocation(simple_project_toml: str, calendar_toml: str) -> None:
    schedule = build(simple_project_toml, calendar_toml)
    days = {cell["date"]: cell["type"] for cell in schedule["workers"][0]["days"]}

    assert days["2024-10-01"] == "fine"
    assert days["2024-10-02"] == "fine"
    assert days["2024-10-05"] == "pub_holiday"
    assert days["2024-10-07"] == "holiday"
    assert days["2024-10-08"] == "holiday"
    assert days["2024-10-09"] == "fine"
    assert days["2024-10-25"] == "holiday"
    assert days["2024-11-01"] == "pub_holiday"
    assert days["2024-11-11"] == "pub_holiday"
    assert days["2024-11-19"] == "fine"
    assert days["2024-11-20"] == "underloaded"

    legend_types = {entry["type"] for entry in schedule["legend"]}
    assert {"fine", "underloaded", "overloaded", "unassigned", "holiday", "other_duties", "pub_holiday"} <= legend_types


def test_complex_project_dates(complex_project_toml: str, calendar_toml: str) -> None:
    schedule = build(complex_project_toml, calendar_toml)
    tasks = by_id(schedule)

    expected = {
        "T1.0": ("2024-10-01", "2024-10-17"),
        "T1.1": ("2024-10-17", "2024-10-25"),
        "T1.2": ("2024-10-25", "2024-11-14"),
        "T2.1": ("2024-11-14", "2024-11-26"),
        "T2.2": ("2024-11-27", "2024-12-04"),
        "T3.1": ("2024-10-01", "2024-10-16"),
        "T3.2": ("2024-10-17", "2024-10-31"),
        "T3.3": ("2024-11-01", "2024-11-20"),
        "T4": ("2024-12-04", "2024-12-20"),
        "T5": ("2024-12-04", "2024-12-12"),
        "T6": ("2024-12-12", "2024-12-27"),
    }
    for task_id, (start, end) in expected.items():
        assert (tasks[task_id]["startDate"], tasks[task_id]["endDate"]) == (start, end), task_id

    assert [task["id"] for task in schedule["tasks"]] == [
        "T1.0",
        "T1.1",
        "T1.2",
        "T2.1",
        "T2.2",
        "T3.1",
        "T3.2",
        "T3.3",
        "T4",
        "T5",
        "T6",
    ]
    assert schedule["projectEnd"] == "2024-12-27"
    assert schedule["axisEnd"] == "2024-12-27"
    assert schedule["markers"] == [
        {
            "label": "Game exhibition",
            "color": "yellow",
            "from": "2024-12-09",
            "to": "2024-12-09",
        },
        {
            "label": "Critical path",
            "color": "navajowhite",
            "from": "2024-12-16",
            "to": "2024-12-25",
        },
    ]
    assert any("Adam" in warning and "overloaded" in warning for warning in schedule["warnings"])
    assert len(schedule["workers"]) == 3

    for task in tasks.values():
        for dependency in task["dependsOn"]:
            assert task["startOffset"] >= tasks[dependency]["finishOffset"] - 1e-6


def test_dependency_only_scheduling_allows_parallel_tasks() -> None:
    project = textwrap.dedent(
        """
        project_name = "Parallel"
        start_date = "2024-01-01"
        team = [
          { name="A", base_calendar="cal.toml", focus_factor=1.0, holidays="", other_duties="" },
          { name="B", base_calendar="cal.toml", focus_factor=1.0, holidays="", other_duties="" },
        ]
        tasks = [
          {id="T1", name="One", estimate=1},
          {id="T2", name="Two", estimate=1},
        ]
        assignments = [
          {task="T1", owner="A"},
          {task="T2", owner="B"},
        ]
        """
    )
    calendar = parse_calendar(CUSTOM_CALENDAR, "cal.toml")
    schedule = build_schedule(parse_project(project), {"cal.toml": calendar})
    tasks = by_id(schedule)
    assert tasks["T1"]["startDate"] == tasks["T2"]["startDate"] == "2024-01-01"
    assert all(cell["type"] == "fine" for cell in schedule["workers"][0]["days"])
    assert all(cell["type"] == "fine" for cell in schedule["workers"][1]["days"])


def test_cursor_does_not_drift_when_next_day_is_closed() -> None:
    project = textwrap.dedent(
        """
        project_name = "Fractional"
        start_date = "2024-10-07"
        team = [
          { name="A", base_calendar="cal.toml", focus_factor=1.0, holidays="", other_duties="" },
          { name="B", base_calendar="cal.toml", focus_factor=1.0, holidays="2024-10-11", other_duties="" },
        ]
        tasks = [
          {id="T1", name="One", estimate=4.5},
          {id="T2", name="Two", estimate=1, after="T1"},
        ]
        assignments = [
          {task="T1", owner="A"},
          {task="T2", owner="B"},
        ]
        """
    )
    calendar = parse_calendar(CUSTOM_CALENDAR, "cal.toml")
    tasks = by_id(build_schedule(parse_project(project), {"cal.toml": calendar}))

    assert tasks["T1"]["finishOffset"] == 4.5
    assert tasks["T1"]["endDate"] == "2024-10-11"
    assert tasks["T2"]["startOffset"] == 4.5
    assert tasks["T2"]["startDate"] == "2024-10-11"
    assert tasks["T2"]["segments"][0]["start"] == 7.0
    assert tasks["T2"]["finishOffset"] == 8.0
    assert tasks["T2"]["endDate"] == "2024-10-14"


def test_zero_estimate_is_warned_and_does_not_consume_a_day() -> None:
    project = textwrap.dedent(
        """
        project_name = "Zero"
        start_date = "2024-01-01"
        team = [{ name="Dev", base_calendar="cal.toml", focus_factor=1.0, holidays="", other_duties="" }]
        tasks = [
          {id="T1", name="None", estimate=0},
          {id="T2", name="One", estimate=1, after="T1"},
        ]
        assignments = [
          {task="T1", owner="Dev"},
          {task="T2", owner="Dev"},
        ]
        """
    )
    calendar = parse_calendar(CUSTOM_CALENDAR, "cal.toml")
    schedule = build_schedule(parse_project(project), {"cal.toml": calendar})
    tasks = by_id(schedule)

    assert tasks["T1"]["startOffset"] == tasks["T1"]["finishOffset"] == 0.0
    assert tasks["T1"]["segments"] == []
    assert tasks["T1"]["endDate"] == "2024-01-01"
    assert tasks["T2"]["startDate"] == "2024-01-01"
    assert any("zero estimate" in warning for warning in schedule["warnings"])


def test_unknown_calendar_lists_available_calendars(calendar_toml: str) -> None:
    project = validation_project(
        base_calendar="missing.toml",
        tasks='{id="T1", name="Do", estimate=1}',
        assignments='{task="T1", owner="Dev"}',
    )
    with pytest.raises(PlannerException) as excinfo:
        build(project, calendar_toml)
    errors = excinfo.value.errors
    assert any("Unknown calendar 'missing.toml'" in error.message for error in errors)
    assert any("calendar_pl.toml" in (error.hint or "") for error in errors)


@pytest.mark.parametrize(
    "tasks, assignments, message",
    [
        ('{id="T1", name="Do", estimate=1}', "", "is not assigned"),
        (
            '{id="T1", name="Do", estimate=1}',
            '{task="T1", owner="Dev"}, {task="T1", owner="Dev"}',
            "assigned more than once",
        ),
        ('{id="T1", name="Do", estimate=1}', '{task="T1", owner="Ghost"}', "Unknown team member 'Ghost'"),
        ('{id="T1", name="Do", estimate=1, after="T9"}', '{task="T1", owner="Dev"}', "unknown task 'T9'"),
        (
            '{id="T1", name="One", estimate=1, after="T2"}, {id="T2", name="Two", estimate=1, after="T1"}',
            '{task="T1", owner="Dev"}, {task="T2", owner="Dev"}',
            "cycle",
        ),
        ('{id="T1", name="Do", estimate=-1}', '{task="T1", owner="Dev"}', "must not be negative"),
        ('{id="T1", name="One", estimate=1}, {id="T1", name="Two", estimate=1}', '{task="T1", owner="Dev"}', "Duplicate task id"),
    ],
)
def test_validation_errors(
    calendar_toml: str,
    tasks: str,
    assignments: str,
    message: str,
) -> None:
    project = validation_project(tasks=tasks, assignments=assignments)
    with pytest.raises(PlannerException) as excinfo:
        build(project, calendar_toml)
    assert any(message in error.message for error in excinfo.value.errors)
