from __future__ import annotations

import heapq
from collections import deque
from datetime import date, timedelta
from math import ceil, floor

from .. import theme
from .calendar import Calendar, in_ranges
from .errors import PlannerError, PlannerException
from .project import Project, TaskDef, TeamMember

EPS = 1e-9
MAX_TASK_DAYS = 200_000

WORKING = "working"
HOLIDAY = "holiday"
OTHER_DUTIES = "other_duties"
PUBLIC_HOLIDAY = "public_holiday"
CLOSED = "closed"


def _iso(day: date) -> str:
    return day.isoformat()


def _day_kind(day: date, calendar: Calendar, member: TeamMember) -> str:
    if calendar.is_closed_weekday(day):
        return CLOSED
    if calendar.is_public_holiday(day):
        return PUBLIC_HOLIDAY
    if in_ranges(day, member.holidays):
        return HOLIDAY
    if in_ranges(day, member.other_duties):
        return OTHER_DUTIES
    return WORKING


def _validate(
    project: Project,
    calendars: dict[str, Calendar],
    available_calendars: set[str] | None = None,
) -> None:
    errors: list[PlannerError] = []
    available = available_calendars if available_calendars is not None else set(calendars)

    team_by_name = {member.name: member for member in project.team}
    task_by_id = {task.id: task for task in project.tasks}

    for index, member in enumerate(project.team):
        if member.base_calendar not in calendars:
            errors.append(
                PlannerError(
                    f"Unknown calendar '{member.base_calendar}' for team member '{member.name}'",
                    source="calendar",
                    path=f"team[{index}].base_calendar",
                    hint=f"Available calendars: {', '.join(sorted(available)) or 'none'}",
                )
            )

    assignments: dict[str, object] = {}
    for index, assignment in enumerate(project.assignments):
        if assignment.task not in task_by_id:
            errors.append(
                PlannerError(
                    f"Assignment references unknown task '{assignment.task}'",
                    source="project",
                    path=f"assignments[{index}].task",
                )
            )
            continue
        if assignment.task in assignments:
            errors.append(
                PlannerError(
                    f"Task '{assignment.task}' is assigned more than once",
                    source="project",
                    path=f"assignments[{index}].task",
                )
            )
            continue
        if assignment.owner not in team_by_name:
            errors.append(
                PlannerError(
                    f"Unknown team member '{assignment.owner}' in assignment",
                    source="project",
                    path=f"assignments[{index}].owner",
                    hint=f"Defined team members: {', '.join(team_by_name) or 'none'}",
                )
            )
            continue
        assignments[assignment.task] = assignment

    for index, task in enumerate(project.tasks):
        if task.id not in assignments:
            errors.append(
                PlannerError(
                    f"Task '{task.name}' ({task.id}) is not assigned",
                    source="project",
                    path=f"tasks[{index}].id",
                )
            )
        for dependency in task.after:
            if dependency not in task_by_id:
                errors.append(
                    PlannerError(
                        f"Task '{task.id}' depends on unknown task '{dependency}'",
                        source="project",
                        path=f"tasks[{index}].after",
                    )
                )

    indegree = {task.id: 0 for task in project.tasks}
    children: dict[str, list[str]] = {task.id: [] for task in project.tasks}
    for task in project.tasks:
        for dependency in task.after:
            if dependency in task_by_id:
                indegree[task.id] += 1
                children[dependency].append(task.id)

    queue = deque(task.id for task in project.tasks if indegree[task.id] == 0)
    visited: list[str] = []
    while queue:
        node = queue.popleft()
        visited.append(node)
        for child in children[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(visited) != len(project.tasks):
        cycle = [task.id for task in project.tasks if indegree[task.id] > 0]
        errors.append(
            PlannerError(
                f"Dependency cycle detected involving: {', '.join(cycle)}",
                source="project",
                path="tasks[].after",
            )
        )

    if errors:
        raise PlannerException(errors)


def _topological_order(project: Project) -> list[TaskDef]:
    """Topological order that keeps tasks close to their input position."""
    task_by_id = {task.id: task for task in project.tasks}
    position = {task.id: index for index, task in enumerate(project.tasks)}
    indegree = {task.id: len([dep for dep in task.after if dep in task_by_id]) for task in project.tasks}
    children: dict[str, list[str]] = {task.id: [] for task in project.tasks}
    for task in project.tasks:
        for dependency in task.after:
            if dependency in task_by_id:
                children[dependency].append(task.id)

    queue = [(position[task.id], task.id) for task in project.tasks if indegree[task.id] == 0]
    heapq.heapify(queue)
    order: list[TaskDef] = []
    while queue:
        _, node = heapq.heappop(queue)
        order.append(task_by_id[node])
        for child in children[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(queue, (position[child], child))
    return order


def build_schedule(
    project: Project,
    calendars: dict[str, Calendar],
    *,
    available_calendars: set[str] | None = None,
) -> dict:
    _validate(project, calendars, available_calendars)

    team_by_name = {member.name: member for member in project.team}
    task_by_id = {task.id: task for task in project.tasks}
    assignments = {assignment.task: assignment for assignment in project.assignments}
    used_workers = [member for member in project.team if member.name in {a.owner for a in project.assignments}]

    project_start = project.start_date
    finish_offsets: dict[str, float] = {}
    work_hours: dict[tuple[str, date], float] = {}
    scheduled_tasks: list[dict] = []
    warnings: list[str] = []

    for task in _topological_order(project):
        assignment = assignments[task.id]
        member = team_by_name[assignment.owner]
        calendar = calendars[member.base_calendar]
        focus_factor = assignment.focus_factor if assignment.focus_factor is not None else member.focus_factor

        start_offset = max((finish_offsets[dep] for dep in task.after), default=0.0)
        cursor = start_offset
        day_index = floor(cursor + EPS)
        current = project_start + timedelta(days=day_index)
        budget = task.estimate * 8.0
        segments: list[dict[str, float]] = []
        pause_days: list[str] = []

        if budget <= EPS:
            warnings.append(f"Task '{task.name}' ({task.id}) has a zero estimate")
            finish_offset = cursor
        else:
            iterations = 0
            finish_offset = cursor
            while budget > EPS:
                iterations += 1
                if iterations > MAX_TASK_DAYS:
                    raise PlannerException(
                        [
                            PlannerError(
                                f"Task '{task.name}' ({task.id}) does not finish within {MAX_TASK_DAYS} days",
                                source="scheduler",
                            )
                        ]
                    )
                kind = _day_kind(current, calendar, member)
                if kind != WORKING:
                    pause_days.append(_iso(current))
                    # Skip to the end of this calendar day. Any fraction left
                    # over from a predecessor that finished mid-day is lost,
                    # otherwise the cursor would drift into the next day.
                    cursor = floor(cursor + EPS) + 1.0
                    current += timedelta(days=1)
                    continue

                day_index = floor(cursor + EPS)
                left_fraction = cursor - day_index
                if left_fraction < EPS:
                    left_fraction = 0.0
                remaining_fraction = 1.0 - left_fraction
                available = calendar.working_hrs_in_day * focus_factor * remaining_fraction
                if available <= EPS:
                    raise PlannerException(
                        [
                            PlannerError(
                                f"Task '{task.name}' ({task.id}) has no available working hours",
                                source="scheduler",
                            )
                        ]
                    )

                segment_start = cursor
                if budget >= available - EPS:
                    budget -= available
                    cursor += remaining_fraction
                    used_fraction = remaining_fraction
                    task_ends = budget <= EPS
                else:
                    fraction = budget / available
                    cursor += remaining_fraction * fraction
                    used_fraction = remaining_fraction * fraction
                    task_ends = True

                key = (member.name, current)
                work_hours[key] = work_hours.get(key, 0.0) + 8.0 * used_fraction
                segments.append({"start": round(segment_start, 6), "end": round(cursor, 6)})
                current += timedelta(days=1)
                if task_ends:
                    break

            finish_offset = cursor

        finish_offsets[task.id] = finish_offset
        if finish_offset > start_offset + EPS:
            end_index = ceil(finish_offset - EPS) - 1
        else:
            end_index = floor(start_offset + EPS)
        end_date = project_start + timedelta(days=max(end_index, 0))

        scheduled_tasks.append(
            {
                "id": task.id,
                "name": task.name,
                "assignee": member.name,
                "estimate": task.estimate,
                "startDate": _iso(project_start + timedelta(days=floor(start_offset + EPS))),
                "endDate": _iso(end_date),
                "startOffset": round(start_offset, 6),
                "finishOffset": round(finish_offset, 6),
                "segments": segments,
                "pauseDays": pause_days,
                "dependsOn": list(task.after),
            }
        )

    if scheduled_tasks:
        project_end = max(
            project_start + timedelta(days=ceil(task["finishOffset"] - EPS) - 1)
            for task in scheduled_tasks
        )
        if project_end < project_start:
            project_end = project_start
    else:
        project_end = project_start

    axis_end = project_end
    for marker in project.time_markers:
        for _range_start, range_end in marker.ranges:
            if range_end > axis_end:
                axis_end = range_end

    workers: list[dict] = []
    overloaded_counts: dict[str, int] = {}
    for member in used_workers:
        calendar = calendars[member.base_calendar]
        cells: list[dict] = []
        current = project_start
        while current <= project_end:
            kind = _day_kind(current, calendar, member)
            hours = work_hours.get((member.name, current), 0.0)
            if kind == HOLIDAY:
                day_type = "holiday"
            elif kind == OTHER_DUTIES:
                day_type = "other_duties"
            elif kind in (CLOSED, PUBLIC_HOLIDAY):
                day_type = "pub_holiday"
            elif hours >= 8.001:
                day_type = "overloaded"
            elif 0.001 <= hours <= 7.999:
                day_type = "underloaded"
            elif 7.999 < hours < 8.001:
                day_type = "fine"
            else:
                day_type = "unassigned"
            if day_type == "overloaded":
                overloaded_counts[member.name] = overloaded_counts.get(member.name, 0) + 1
            cells.append({"date": _iso(current), "hours": round(hours, 3), "type": day_type})
            current += timedelta(days=1)
        workers.append(
            {
                "name": member.name,
                "focusFactor": member.focus_factor,
                "days": cells,
            }
        )

    for worker_name, count in overloaded_counts.items():
        warnings.append(f"Worker '{worker_name}' is overloaded on {count} day(s)")

    used_calendar_names = {member.base_calendar for member in project.team}
    reference_calendar = (
        calendars[project.team[0].base_calendar] if project.team and project.team[0].base_calendar in calendars else None
    )
    public_holidays: set[date] = set()
    for calendar_name in used_calendar_names:
        calendar = calendars.get(calendar_name)
        if calendar is not None:
            public_holidays |= calendar.public_holiday_dates(project_start, axis_end)

    days: list[dict] = []
    current = project_start
    while current <= axis_end:
        days.append(
            {
                "date": _iso(current),
                "weekday": current.weekday(),
                "weekend": bool(reference_calendar and reference_calendar.is_closed_weekday(current)),
                "publicHoliday": current in public_holidays,
            }
        )
        current += timedelta(days=1)

    years = set(range(project_start.year, axis_end.year + 1))
    for calendar_name in sorted(used_calendar_names):
        calendar = calendars.get(calendar_name)
        if calendar is None:
            continue
        covered: set[int] = set()
        for holiday in calendar.public_holidays:
            for range_start, range_end in holiday.ranges:
                covered.update(range(range_start.year, range_end.year + 1))
        missing = sorted(years - covered)
        if missing:
            warnings.append(
                f"Calendar '{calendar_name}' lists no public holidays for: {', '.join(map(str, missing))}"
            )

    markers: list[dict] = []
    for marker in project.time_markers:
        for range_start, range_end in marker.ranges:
            start = max(range_start, project_start)
            end = max(range_end, project_start)
            markers.append(
                {
                    "label": marker.label,
                    "color": marker.color or theme.MARKER_COLOR,
                    "from": _iso(start),
                    "to": _iso(end),
                }
            )

    legend = [
        {"type": day_type, "label": theme.DAY_TYPE_LABELS[day_type], "color": color}
        for day_type, color in theme.DAY_TYPE_COLORS.items()
    ]

    return {
        "title": project.project_name,
        "projectStart": _iso(project_start),
        "projectEnd": _iso(project_end),
        "axisEnd": _iso(axis_end),
        "days": days,
        "tasks": scheduled_tasks,
        "workers": workers,
        "markers": markers,
        "legend": legend,
        "markerColor": theme.MARKER_COLOR,
        "taskColors": theme.TASK_BAR_COLORS,
        "warnings": warnings,
    }


def render_project(project_toml: str, calendar_toml: str | None = None) -> dict:
    """Convenience helper used by tests: one project and one calendar."""
    from .calendar import parse_calendar
    from .project import parse_project

    project = parse_project(project_toml)
    calendars: dict[str, Calendar] = {}
    if calendar_toml is not None:
        for member in project.team:
            calendars[member.base_calendar] = parse_calendar(calendar_toml, member.base_calendar)
    return build_schedule(project, calendars)
