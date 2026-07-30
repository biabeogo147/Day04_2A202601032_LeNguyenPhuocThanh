import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent.shared.catalog import Catalog
from app.agent.shared.persistence import Database
from app.main import create_app


DATASET = Path(__file__).parents[2] / "shared_data" / "DataTPCN.csv"


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


def test_session_run_and_sse_replay(tmp_path):
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

        session = client.post(
            "/api/v1/sessions",
            json={
                "context": {"age_group": "adult", "goals": ["tim mạch"]},
                "version_id": "version_1",
                "provider": "openai",
            },
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

        with client.stream(
            "GET",
            f"/api/v1/runs/{run.json()['id']}/events?last_event_id=1",
        ) as response:
            query_replay = "".join(response.iter_text())
        assert "event: run.started" not in query_replay
        assert "event: answer.completed" in query_replay

    assert not (DATASET.parents[1] / "storage").exists()


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


def test_session_starts_without_context_and_resume_merges_context(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'anonymous.db'}")
    app = create_app(
        database=database,
        catalog=Catalog.from_csv(DATASET),
        runner=ImmediateRunner(database),
    )

    with TestClient(app) as client:
        session = client.post(
            "/api/v1/sessions",
            json={"version_id": "version_1", "provider": "openai"},
        )

        assert session.status_code == 201
        assert session.json()["context"] == {}

        run = client.post(
            f"/api/v1/sessions/{session.json()['id']}/runs",
            json={"message": "Tư vấn Omega-3 cho tôi"},
        )
        assert run.status_code == 202

        resumed = client.post(
            f"/api/v1/runs/{run.json()['id']}/resume",
            json={
                "context_patch": {
                    "age_group": "adult",
                    "conditions": [],
                    "medications": ["warfarin"],
                },
                "response": {"confirmed": True},
            },
        )
        assert resumed.status_code == 200

        refreshed = client.get(f"/api/v1/sessions/{session.json()['id']}")
        assert refreshed.json()["context"] == {
            "age_group": "adult",
            "conditions": [],
            "medications": ["warfarin"],
        }
