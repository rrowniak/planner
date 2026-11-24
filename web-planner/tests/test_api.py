from __future__ import annotations

import textwrap

import pytest
from fastapi.testclient import TestClient

from app.main import app

MINIMAL_CALENDAR = textwrap.dedent(
    """
    closed_days = ["saturday", "sunday"]
    working_hrs_in_day = 8
    public_holidays = []
    """
)

MINIMAL_PROJECT = textwrap.dedent(
    """
    project_name = "Tiny"
    start_date = "2024-01-01"
    team = [{ name="Dev", base_calendar="custom.toml", focus_factor=1.0, holidays="", other_duties="" }]
    tasks = [{ id="T1", name="Do", estimate=1 }]
    assignments = [{ task="T1", owner="Dev" }]
    """
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_index_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "project-toml" in response.text
    assert "Render chart" in response.text


def test_lists_calendars(client: TestClient) -> None:
    response = client.get("/api/calendars")
    assert response.status_code == 200
    calendars = {item["name"]: item for item in response.json()["calendars"]}
    assert "calendar_pl.toml" in calendars
    assert "closed_days" in calendars["calendar_pl.toml"]["content"]


def test_lists_examples(client: TestClient) -> None:
    response = client.get("/api/examples")
    assert response.status_code == 200
    examples = {item["id"]: item for item in response.json()["examples"]}
    assert "simple_project" in examples
    assert "complex_project" in examples
    assert "calendar_pl" not in examples


def test_parse_returns_definition(client: TestClient, simple_project_toml: str) -> None:
    response = client.post("/api/parse", json={"project_toml": simple_project_toml})
    assert response.status_code == 200
    definition = response.json()["definition"]
    assert definition["project_name"] == "Web notes assistant"
    assert definition["start_date"] == "2024-10-01"
    assert len(definition["team"]) == 1
    assert definition["team"][0]["focus_factor"] == 0.5
    assert len(definition["tasks"]) == 5
    assert definition["tasks"][1]["after"] == "T1"
    assert definition["assignments"][-1]["focus_factor"] == 0.8
    assert definition["time_markers"] == []


def test_parse_normalizes_dates_and_dependency_lists(client: TestClient) -> None:
    project = textwrap.dedent(
        """
        project_name = "Dates"
        start_date = 2024-01-01
        team = [{ name="Dev", base_calendar="custom.toml", focus_factor=1, holidays="", other_duties="" }]
        tasks = [
          { id="T1", name="A", estimate=1 },
          { id="T2", name="B", estimate=2, after=["T1"] },
        ]
        assignments = [{ task="T1", owner="Dev" }]
        time_markers = [{ time=2024-12-09, label="Expo" }]
        """
    )
    response = client.post("/api/parse", json={"project_toml": project})
    assert response.status_code == 200
    definition = response.json()["definition"]
    assert definition["start_date"] == "2024-01-01"
    assert definition["tasks"][1]["after"] == "T1"
    assert definition["time_markers"][0]["time"] == "2024-12-09"
    assert definition["time_markers"][0]["color"] == ""


def test_parse_reports_toml_errors(client: TestClient) -> None:
    response = client.post("/api/parse", json={"project_toml": "project_name = [\n"})
    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["source"] == "project"
    assert error["line"] is not None


def test_render_simple_project(client: TestClient, simple_project_toml: str) -> None:
    response = client.post("/api/render", json={"project_toml": simple_project_toml})
    assert response.status_code == 200
    schedule = response.json()["schedule"]
    assert schedule["title"] == "Web notes assistant"
    assert len(schedule["tasks"]) == 5
    assert schedule["tasks"][0]["startDate"] == "2024-10-01"
    assert schedule["tasks"][-1]["endDate"] == "2024-11-20"
    assert schedule["legend"]


def test_render_reports_toml_errors(client: TestClient) -> None:
    response = client.post("/api/render", json={"project_toml": "project_name = [\n"})
    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["source"] == "project"
    assert error["line"] is not None
    assert error["column"] is not None


def test_render_reports_unknown_calendar(client: TestClient) -> None:
    project = textwrap.dedent(
        """
        project_name = "Broken"
        start_date = "2024-01-01"
        team = [{ name="Dev", base_calendar="missing.toml", focus_factor=1.0, holidays="", other_duties="" }]
        tasks = [{ id="T1", name="Do", estimate=1 }]
        assignments = [{ task="T1", owner="Dev" }]
        """
    )
    response = client.post("/api/render", json={"project_toml": project})
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any("Unknown calendar 'missing.toml'" in error["message"] for error in errors)
    assert any("calendar_pl.toml" in (error.get("hint") or "") for error in errors)


def test_render_accepts_uploaded_calendar(client: TestClient) -> None:
    response = client.post(
        "/api/render",
        json={"project_toml": MINIMAL_PROJECT, "calendars": {"custom.toml": MINIMAL_CALENDAR}},
    )
    assert response.status_code == 200
    task = response.json()["schedule"]["tasks"][0]
    assert task["startDate"] == task["endDate"] == "2024-01-01"


def test_render_rejects_unsafe_calendar_names(client: TestClient) -> None:
    response = client.post(
        "/api/render",
        json={"project_toml": MINIMAL_PROJECT, "calendars": {"../evil.toml": MINIMAL_CALENDAR}},
    )
    assert response.status_code == 422
    assert any("Invalid calendar name" in error["message"] for error in response.json()["errors"])


def test_uploaded_calendar_overrides_builtin(client: TestClient, simple_project_toml: str) -> None:
    baseline = client.post("/api/render", json={"project_toml": simple_project_toml})
    assert baseline.status_code == 200
    baseline_end = baseline.json()["schedule"]["tasks"][-1]["endDate"]

    response = client.post(
        "/api/render",
        json={
            "project_toml": simple_project_toml,
            "calendars": {"calendar_pl.toml": MINIMAL_CALENDAR},
        },
    )
    assert response.status_code == 200
    overridden_end = response.json()["schedule"]["tasks"][-1]["endDate"]
    assert overridden_end != baseline_end
    assert overridden_end < baseline_end
