import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent.shared.catalog import Catalog
from app.agent.shared.persistence import Database
from app.main import create_app


DATASET = Path(__file__).parents[2] / "data" / "DataTPCN.csv"


class ImmediateRunner:
    def __init__(self, database: Database):
        self.database = database

    async def start(self, run_id: str) -> None:
        await self.database.append_trace(run_id, "run.started", {"runner": "fake"})
        await self.database.append_trace(
            run_id,
            "answer.completed",
            {"status": "answered", "final_judgment": "Test answer"},
        )
        await self.database.update_run(
            run_id,
            status="completed",
            answer={"status": "answered", "final_judgment": "Test answer"},
        )

    async def resume(self, run_id: str, response: dict) -> None:
        await self.start(run_id)


def test_profile_session_run_and_sse_replay(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    app = create_app(
        database=database,
        catalog=Catalog.from_csv(DATASET),
        runner=ImmediateRunner(database),
    )

    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["product_count"] == 100

        profile = client.post(
            "/api/v1/profiles",
            json={
                "display_name": "Mentor",
                "age_group": "adult",
                "goals": ["tim mạch"],
                "conditions": [],
                "medications": [],
                "allergies": [],
                "pregnancy_status": "not_applicable",
                "budget_max_vnd": 500000,
                "preferred_dosage_forms": ["Viên nang mềm"],
            },
        )
        assert profile.status_code == 201

        session = client.post(
            "/api/v1/sessions",
            json={"profile_id": profile.json()["id"], "version_id": "version_1", "provider": "openai"},
        )
        assert session.status_code == 201

        run = client.post(
            f"/api/v1/sessions/{session.json()['id']}/runs",
            json={"message": "Tư vấn Omega-3"},
        )
        assert run.status_code == 202

        result = client.get(f"/api/v1/runs/{run.json()['id']}")
        assert result.json()["status"] == "completed"
        assert result.json()["answer"]["final_judgment"] == "Test answer"

        with client.stream("GET", f"/api/v1/runs/{run.json()['id']}/events") as response:
            body = "".join(response.iter_text())
        assert "event: run.started" in body
        assert "event: answer.completed" in body
        assert "id: 1" in body

        with client.stream(
            "GET",
            f"/api/v1/runs/{run.json()['id']}/events",
            headers={"Last-Event-ID": "1"},
        ) as response:
            replay = "".join(response.iter_text())
        assert "event: run.started" not in replay
        assert "event: answer.completed" in replay
        assert "id: 2" in replay


def test_versions_endpoint_exposes_only_version_1(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    app = create_app(
        database=database,
        catalog=Catalog.from_csv(DATASET),
        runner=ImmediateRunner(database),
    )

    with TestClient(app) as client:
        versions = client.get("/api/v1/versions")

    assert versions.status_code == 200
    assert [item["id"] for item in versions.json()] == ["version_1"]
