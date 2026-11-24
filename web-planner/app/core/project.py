from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .calendar import DateRange, parse_date, parse_date_ranges
from .errors import PlannerError, PlannerException
from .tomlutil import load_toml

SOURCE = "project"


@dataclass
class TeamMember:
    name: str
    base_calendar: str
    focus_factor: float
    holidays: list[DateRange] = field(default_factory=list)
    other_duties: list[DateRange] = field(default_factory=list)


@dataclass
class TaskDef:
    id: str
    name: str
    estimate: float
    after: list[str] = field(default_factory=list)


@dataclass
class Assignment:
    task: str
    owner: str
    focus_factor: float | None = None


@dataclass
class TimeMarker:
    ranges: list[DateRange]
    label: str
    color: str | None = None


@dataclass
class Project:
    project_name: str
    start_date: date
    team: list[TeamMember]
    tasks: list[TaskDef]
    assignments: list[Assignment]
    time_markers: list[TimeMarker]


def _require_table(entry: object, path: str, errors: list[PlannerError]) -> bool:
    if not isinstance(entry, dict):
        errors.append(PlannerError(f"'{path}' must be a table", source=SOURCE, path=path))
        return False
    return True


def _string(entry: dict, key: str, path: str, errors: list[PlannerError], *, required: bool = True) -> str | None:
    value = entry.get(key)
    if value is None:
        if required:
            errors.append(PlannerError(f"Missing required field '{path}.{key}'", source=SOURCE, path=f"{path}.{key}"))
        return None
    if not isinstance(value, str):
        errors.append(PlannerError(f"'{path}.{key}' must be a string", source=SOURCE, path=f"{path}.{key}"))
        return None
    return value


def _number(
    entry: dict,
    key: str,
    path: str,
    errors: list[PlannerError],
    *,
    required: bool = True,
    positive: bool = False,
) -> float | None:
    value = entry.get(key)
    if value is None:
        if required:
            errors.append(PlannerError(f"Missing required field '{path}.{key}'", source=SOURCE, path=f"{path}.{key}"))
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(PlannerError(f"'{path}.{key}' must be a number", source=SOURCE, path=f"{path}.{key}"))
        return None
    if positive and value <= 0:
        errors.append(PlannerError(f"'{path}.{key}' must be greater than zero", source=SOURCE, path=f"{path}.{key}"))
        return None
    return float(value)


def _after_list(value: object, path: str, errors: list[PlannerError]) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        if not all(isinstance(item, str) for item in value):
            errors.append(PlannerError(f"'{path}' must contain only strings", source=SOURCE, path=path))
            return []
        return [item.strip() for item in value if item.strip()]
    errors.append(PlannerError(f"'{path}' must be a comma-separated string or a list", source=SOURCE, path=path))
    return []


def parse_project(text: str) -> Project:
    data = load_toml(text, source=SOURCE)
    errors: list[PlannerError] = []

    project_name = _string(data, "project_name", "project", errors)
    start_date = None
    try:
        start_date = parse_date(data.get("start_date"), source=SOURCE, path="start_date")
    except PlannerException as exc:
        errors.extend(exc.errors)

    team: list[TeamMember] = []
    team_raw = data.get("team")
    if not isinstance(team_raw, list):
        errors.append(PlannerError("'team' must be a list of tables", source=SOURCE, path="team"))
    else:
        seen: set[str] = set()
        for index, entry in enumerate(team_raw):
            path = f"team[{index}]"
            if not _require_table(entry, path, errors):
                continue
            name = _string(entry, "name", path, errors)
            base_calendar = _string(entry, "base_calendar", path, errors)
            focus_factor = _number(entry, "focus_factor", path, errors, positive=True)
            holidays: list[DateRange] = []
            other_duties: list[DateRange] = []
            for key in ("holidays", "other_duties"):
                try:
                    parsed = parse_date_ranges(entry.get(key, ""), source=SOURCE, path=f"{path}.{key}")
                except PlannerException as exc:
                    errors.extend(exc.errors)
                    continue
                if key == "holidays":
                    holidays = parsed
                else:
                    other_duties = parsed
            if name is not None:
                if name in seen:
                    errors.append(
                        PlannerError(f"Duplicate team member '{name}'", source=SOURCE, path=f"{path}.name")
                    )
                    continue
                seen.add(name)
            if name is None or base_calendar is None or focus_factor is None:
                continue
            team.append(
                TeamMember(
                    name=name,
                    base_calendar=base_calendar,
                    focus_factor=focus_factor,
                    holidays=holidays,
                    other_duties=other_duties,
                )
            )

    tasks: list[TaskDef] = []
    tasks_raw = data.get("tasks")
    if not isinstance(tasks_raw, list):
        errors.append(PlannerError("'tasks' must be a list of tables", source=SOURCE, path="tasks"))
    else:
        seen_ids: set[str] = set()
        for index, entry in enumerate(tasks_raw):
            path = f"tasks[{index}]"
            if not _require_table(entry, path, errors):
                continue
            task_id = _string(entry, "id", path, errors)
            name = _string(entry, "name", path, errors)
            estimate = _number(entry, "estimate", path, errors)
            if estimate is not None and estimate < 0:
                errors.append(
                    PlannerError(f"'{path}.estimate' must not be negative", source=SOURCE, path=f"{path}.estimate")
                )
                estimate = None
            after = _after_list(entry.get("after"), f"{path}.after", errors)
            if task_id is not None:
                if task_id in seen_ids:
                    errors.append(
                        PlannerError(f"Duplicate task id '{task_id}'", source=SOURCE, path=f"{path}.id")
                    )
                    continue
                seen_ids.add(task_id)
            if task_id is None or name is None or estimate is None:
                continue
            tasks.append(TaskDef(id=task_id, name=name, estimate=estimate, after=after))

    assignments: list[Assignment] = []
    assignments_raw = data.get("assignments")
    if not isinstance(assignments_raw, list):
        errors.append(PlannerError("'assignments' must be a list of tables", source=SOURCE, path="assignments"))
    else:
        for index, entry in enumerate(assignments_raw):
            path = f"assignments[{index}]"
            if not _require_table(entry, path, errors):
                continue
            task = _string(entry, "task", path, errors)
            owner = _string(entry, "owner", path, errors)
            focus_factor = _number(entry, "focus_factor", path, errors, required=False, positive=True)
            if focus_factor is None and entry.get("focus_factor") is not None:
                continue
            if task is None or owner is None:
                continue
            assignments.append(Assignment(task=task, owner=owner, focus_factor=focus_factor))

    time_markers: list[TimeMarker] = []
    markers_raw = data.get("time_markers", [])
    if markers_raw is not None:
        if not isinstance(markers_raw, list):
            errors.append(
                PlannerError("'time_markers' must be a list of tables", source=SOURCE, path="time_markers")
            )
        else:
            for index, entry in enumerate(markers_raw):
                path = f"time_markers[{index}]"
                if not _require_table(entry, path, errors):
                    continue
                label = _string(entry, "label", path, errors)
                color = _string(entry, "color", path, errors, required=False)
                try:
                    ranges = parse_date_ranges(entry.get("time"), source=SOURCE, path=f"{path}.time")
                except PlannerException as exc:
                    errors.extend(exc.errors)
                    continue
                if not ranges:
                    errors.append(
                        PlannerError(f"'{path}.time' must not be empty", source=SOURCE, path=f"{path}.time")
                    )
                    continue
                if label is None:
                    continue
                time_markers.append(TimeMarker(ranges=ranges, label=label, color=color))

    if errors:
        raise PlannerException(errors)

    assert project_name is not None and start_date is not None
    return Project(
        project_name=project_name,
        start_date=start_date,
        team=team,
        tasks=tasks,
        assignments=assignments,
        time_markers=time_markers,
    )
