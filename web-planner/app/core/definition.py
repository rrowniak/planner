from __future__ import annotations

from datetime import date, datetime

from .tomlutil import load_toml


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _number(value: object, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _tables(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _after(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(_text(item) for item in value if _text(item))
    return ""


def definition_from_toml(text: str) -> dict:
    data = load_toml(text, source="project")
    if not isinstance(data, dict):
        data = {}

    team = [
        {
            "name": _text(entry.get("name")),
            "base_calendar": _text(entry.get("base_calendar")),
            "focus_factor": _number(entry.get("focus_factor"), 1.0),
            "holidays": _text(entry.get("holidays")),
            "other_duties": _text(entry.get("other_duties")),
        }
        for entry in _tables(data.get("team"))
    ]
    tasks = [
        {
            "id": _text(entry.get("id")),
            "name": _text(entry.get("name")),
            "estimate": _number(entry.get("estimate"), 0.0),
            "after": _after(entry.get("after")),
        }
        for entry in _tables(data.get("tasks"))
    ]
    assignments = [
        {
            "task": _text(entry.get("task")),
            "owner": _text(entry.get("owner")),
            "focus_factor": (
                None if entry.get("focus_factor") is None else _number(entry.get("focus_factor"), 1.0)
            ),
        }
        for entry in _tables(data.get("assignments"))
    ]
    time_markers = [
        {
            "time": _text(entry.get("time")),
            "label": _text(entry.get("label")),
            "color": _text(entry.get("color")),
        }
        for entry in _tables(data.get("time_markers"))
    ]

    return {
        "project_name": _text(data.get("project_name")),
        "start_date": _text(data.get("start_date")),
        "team": team,
        "tasks": tasks,
        "assignments": assignments,
        "time_markers": time_markers,
    }
