from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .core.calendar import parse_calendar
from .core.definition import definition_from_toml
from .core.errors import PlannerError, PlannerException
from .core.project import parse_project
from .core.scheduler import build_schedule
from .core.tomlutil import load_toml

APP_DIR = Path(__file__).resolve().parent
WEB_ROOT = APP_DIR.parent
REPO_ROOT = WEB_ROOT.parent
CALENDARS_DIR = WEB_ROOT / "calendars"
EXAMPLES_DIR = REPO_ROOT / "examples"

MAX_PROJECT_BYTES = 1_000_000
MAX_CALENDARS_BYTES = 2_000_000

logger = logging.getLogger("web_planner")

app = FastAPI(title="planner web", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


class RenderRequest(BaseModel):
    project_toml: str
    calendars: dict[str, str] = Field(default_factory=dict)


class ParseRequest(BaseModel):
    project_toml: str


def _load_builtin_calendars() -> dict[str, str]:
    calendars: dict[str, str] = {}
    if CALENDARS_DIR.is_dir():
        for path in sorted(CALENDARS_DIR.glob("*.toml")):
            calendars[path.name] = path.read_text(encoding="utf-8")
    return calendars


def _error_response(errors: list[PlannerError], status_code: int = 422) -> JSONResponse:
    return JSONResponse({"errors": [error.to_dict() for error in errors]}, status_code=status_code)


def _valid_calendar_name(name: str) -> bool:
    return (
        bool(name)
        and name not in {".", ".."}
        and name.endswith(".toml")
        and Path(name).name == name
        and not name.startswith(".")
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html", context={"title": "planner web"})


@app.get("/api/calendars")
def calendars() -> dict:
    return {
        "calendars": [
            {"name": name, "content": content}
            for name, content in _load_builtin_calendars().items()
        ]
    }


@app.get("/api/examples")
def examples() -> dict:
    result: list[dict] = []
    if EXAMPLES_DIR.is_dir():
        for path in sorted(EXAMPLES_DIR.glob("*.toml")):
            try:
                content = path.read_text(encoding="utf-8")
                data = load_toml(content, source=path.name)
            except (OSError, PlannerException):
                continue
            if not isinstance(data, dict) or "project_name" not in data or "tasks" not in data:
                continue
            result.append(
                {
                    "id": path.stem,
                    "name": str(data.get("project_name", path.stem)),
                    "content": content,
                }
            )
    return {"examples": result}


@app.post("/api/parse", response_model=None)
def parse(payload: ParseRequest):
    if len(payload.project_toml.encode("utf-8")) > MAX_PROJECT_BYTES:
        return _error_response(
            [PlannerError(f"Project definition exceeds {MAX_PROJECT_BYTES} bytes", source="project")],
            status_code=413,
        )
    try:
        definition = definition_from_toml(payload.project_toml)
    except PlannerException as exc:
        return _error_response(exc.errors)
    return {"definition": definition}


@app.post("/api/render", response_model=None)
def render(payload: RenderRequest):
    if len(payload.project_toml.encode("utf-8")) > MAX_PROJECT_BYTES:
        return _error_response(
            [PlannerError(f"Project definition exceeds {MAX_PROJECT_BYTES} bytes", source="project")],
            status_code=413,
        )

    calendars = _load_builtin_calendars()
    total = 0
    for name, content in payload.calendars.items():
        if not _valid_calendar_name(name):
            return _error_response(
                [
                    PlannerError(
                        f"Invalid calendar name '{name}'",
                        source="calendar",
                        hint="Calendar names must be plain .toml filenames.",
                    )
                ]
            )
        total += len(content.encode("utf-8"))
        calendars[name] = content
    if total > MAX_CALENDARS_BYTES:
        return _error_response(
            [PlannerError(f"Calendar definitions exceed {MAX_CALENDARS_BYTES} bytes", source="calendar")],
            status_code=413,
        )

    try:
        project = parse_project(payload.project_toml)
        needed = {member.base_calendar for member in project.team}
        parsed = {
            name: parse_calendar(calendars[name], name)
            for name in needed
            if name in calendars
        }
        schedule = build_schedule(project, parsed, available_calendars=set(calendars))
    except PlannerException as exc:
        return _error_response(exc.errors)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Unexpected error while building the schedule")
        return _error_response([PlannerError("Unexpected internal error", source="server")], status_code=500)

    return {"schedule": schedule}
