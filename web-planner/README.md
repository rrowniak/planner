# planner web

A small, local, single-user web front end for the `planner` TOML format. It parses the
same project and calendar files as the Rust CLI and renders the Gantt chart natively in
the browser (HTML/CSS/SVG) — no PlantUML or Java required.

## Run

```bash
cd web-planner
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Open <http://127.0.0.1:8000>.

Use **Render chart** (or Ctrl+Enter) to recalculate. Pick a built-in example from the
buttons in the editor header.

Switch between the **TOML** and **Definition** tabs. The Definition tab shows the project
as editable sections (project, team, tasks, assignments, time markers) and rewrites the
TOML as you type. Team holidays and other duties are edited as add/remove date ranges
using the browser's date picker. Regeneration is intentional: comments and formatting in
the TOML are not preserved once you edit through the Definition tab.

## What it does

- Parses `project_name`, `start_date`, `team`, `tasks`, `assignments`, and `time_markers`.
- Validates the definition and reports every problem with its source, TOML path, and
  line/column where available.
- Schedules tasks from dependencies only (like the Rust version) using each owner's
  calendar, focus factor, holidays, and other duties.
- Shows task bars with dashed continuation across paused/non-working days, dependency
  arrows, weekend/public-holiday shading, time markers, and per-worker allocation rows
  (fine / underloaded / overloaded / holiday / other duties / unassigned).
- Displays inclusive end dates and supports fractional day positions.

## Calendars

Built-in calendars live in `calendars/`. The page also accepts uploaded `.toml`
calendars. An uploaded file overrides a built-in calendar with the same filename for that
render only — nothing is written to disk.

A task owner whose `base_calendar` cannot be found is a validation error listing the
available calendars.

## API

- `GET /` — page
- `GET /api/calendars` — built-in calendars (`{name, content}`)
- `GET /api/examples` — runnable examples from `../examples`
- `POST /api/parse` — `{"project_toml": "..."}` returns `{"definition": {...}}` for the
  structured editor, or `{"errors": [...]}` with status 422/413
- `POST /api/render` — `{"project_toml": "...", "calendars": {"file.toml": "..."}}`
  returns `{"schedule": {...}}`, or `{"errors": [...]}` with status 422/413.

Limits: 1 MB for the project definition and 2 MB total for uploaded calendars.

## Intentional differences from the Rust CLI

These are fixes/robustness changes, not strict output parity:

- The working-day membership check is a proper `start <= day <= end` test (the Rust code
  used `start <= day || day >= end`, which effectively matched almost every date).
- When a task starts mid-day and the next day is closed, the cursor moves to the next day
  boundary instead of accumulating a fractional drift.
- A zero-estimate task does not silently consume a whole day; it is reported as a warning
  and rendered as a tick.
- Worker allocation is filled across the whole project range, so idle/absent days are
  visible outside task spans.
- Output task order follows the input order (still topologically valid) so related tasks
  stay together in the chart.

## Tests

```bash
.venv/bin/python -m pytest -q
```

Tests cover calendar parsing, validation errors, scheduling against both bundled
examples, fractional-day/holiday edge cases, and the HTTP API.
