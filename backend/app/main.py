from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Protocol

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from app.agent.shared.catalog import Catalog
from app.agent.shared.persistence import Database
from app.agent.registry import VERSION_REGISTRY
from app.config import Settings
from version_1.tools import validate_tool_contract
from app.schemas import (
    ProfileCreate,
    ProfilePatch,
    ProfileRead,
    ResumeRunRequest,
    RunCreate,
    RunRead,
    SessionCreate,
    SessionRead,
)


ROOT = Path(__file__).resolve().parents[2]
TERMINAL_RUN_STATES = {"completed", "failed", "interrupted"}


class RunController(Protocol):
    async def start(self, run_id: str) -> None: ...

    async def resume(self, run_id: str, response: dict[str, Any]) -> None: ...


class UnconfiguredRunner:
    """Fail clearly when the API is started without provider configuration."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def start(self, run_id: str) -> None:
        await self.database.append_trace(
            run_id,
            "run.failed",
            {"code": "runner_not_configured", "message": "Agent runner is not configured."},
        )
        await self.database.update_run(
            run_id, status="failed", error_code="runner_not_configured"
        )

    async def resume(self, run_id: str, response: dict[str, Any]) -> None:
        await self.start(run_id)


def _upgrade_default_database() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    command.upgrade(config, "head")


def create_app(
    *,
    database: Database | None = None,
    catalog: Catalog | None = None,
    runner: RunController | None = None,
) -> FastAPI:
    settings = Settings()
    validate_tool_contract(VERSION_REGISTRY["version_1"]["manifest"])
    owns_database = database is None
    db = database or Database(settings.app_database_url)
    product_catalog = catalog or Catalog.from_csv(
        settings.resolved_path(settings.dataset_path)
    )
    if runner is None:
        from app.services import AgentRunner

        run_controller: RunController = AgentRunner(db, product_catalog, settings)
    else:
        run_controller = runner

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        settings.resolved_path(settings.checkpoint_database_path).parent.mkdir(
            parents=True, exist_ok=True
        )
        if owns_database:
            await asyncio.to_thread(_upgrade_default_database)
        else:
            await db.create_schema()
        await db.interrupt_unfinished_runs()
        yield
        if owns_database:
            await db.close()

    app = FastAPI(
        title="Day04 TPCN ReAct Advisor",
        version="0.1.0",
        description="Local, dataset-grounded dietary supplement consultation API.",
        lifespan=lifespan,
    )
    app.state.database = db
    app.state.catalog = product_catalog
    app.state.runner = run_controller
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "product_count": len(product_catalog.products),
            "dataset_fingerprint": product_catalog.dataset_fingerprint,
        }

    @app.get("/api/v1/versions")
    async def versions() -> list[dict[str, Any]]:
        return [item["manifest"] for item in VERSION_REGISTRY.values()]

    @app.post(
        "/api/v1/profiles",
        response_model=ProfileRead,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_profile(payload: ProfileCreate) -> ProfileRead:
        return await db.create_profile(payload)

    @app.get("/api/v1/profiles", response_model=list[ProfileRead])
    async def list_profiles() -> list[ProfileRead]:
        return await db.list_profiles()

    @app.get("/api/v1/profiles/{profile_id}", response_model=ProfileRead)
    async def get_profile(profile_id: str) -> ProfileRead:
        profile = await db.get_profile(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        return profile

    @app.patch("/api/v1/profiles/{profile_id}", response_model=ProfileRead)
    async def patch_profile(profile_id: str, payload: ProfilePatch) -> ProfileRead:
        try:
            return await db.update_profile(
                profile_id, payload.model_dump(exclude_unset=True)
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Profile not found") from exc

    @app.delete("/api/v1/profiles/{profile_id}", status_code=204)
    async def delete_profile(profile_id: str) -> Response:
        if not await db.delete_profile(profile_id):
            raise HTTPException(status_code=404, detail="Profile not found")
        return Response(status_code=204)

    @app.post(
        "/api/v1/sessions",
        response_model=SessionRead,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_session(payload: SessionCreate) -> SessionRead:
        if await db.get_profile(payload.profile_id) is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        if payload.version_id not in VERSION_REGISTRY:
            raise HTTPException(status_code=422, detail="Unknown agent version")
        chat_model = "gpt-4o-mini" if payload.provider == "openai" else "gemini-2.5-flash"
        embedding_model = (
            "text-embedding-3-small"
            if payload.provider == "openai"
            else "gemini-embedding-001"
        )
        return await db.create_session(
            profile_id=payload.profile_id,
            version_id=payload.version_id,
            provider=payload.provider,
            chat_model=chat_model,
            embedding_provider=payload.provider,
            embedding_model=embedding_model,
            dataset_fingerprint=product_catalog.dataset_fingerprint,
        )

    @app.get("/api/v1/sessions/{session_id}", response_model=SessionRead)
    async def get_session(session_id: str) -> SessionRead:
        session = await db.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    @app.get("/api/v1/sessions", response_model=list[SessionRead])
    async def list_sessions(profile_id: str | None = None) -> list[SessionRead]:
        return await db.list_sessions(profile_id)

    @app.post(
        "/api/v1/sessions/{session_id}/runs",
        response_model=RunRead,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_run(session_id: str, payload: RunCreate) -> RunRead:
        if await db.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session not found")
        run = await db.create_run(session_id, payload.message)
        await run_controller.start(run.id)
        return run

    @app.get("/api/v1/runs/{run_id}", response_model=RunRead)
    async def get_run(run_id: str) -> RunRead:
        run = await db.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    @app.get("/api/v1/runs/{run_id}/events")
    async def run_events(
        run_id: str,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> EventSourceResponse:
        if await db.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="Run not found")
        try:
            cursor = max(0, int(last_event_id or 0))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Last-Event-ID") from exc

        async def generate() -> AsyncIterator[dict[str, str]]:
            nonlocal cursor
            while True:
                events = await db.list_trace(run_id, after_sequence=cursor)
                for event in events:
                    cursor = event.sequence
                    yield {
                        "id": str(event.sequence),
                        "event": event.type,
                        "data": json.dumps(event.payload, ensure_ascii=False),
                    }
                run = await db.get_run(run_id)
                if run is None or (run.status in TERMINAL_RUN_STATES and not events):
                    break
                await asyncio.sleep(0.15)

        return EventSourceResponse(generate())

    @app.post("/api/v1/runs/{run_id}/resume", response_model=RunRead)
    async def resume_run(run_id: str, payload: ResumeRunRequest) -> RunRead:
        run = await db.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        session = await db.get_session(run.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if payload.profile_patch is not None:
            await db.update_profile(
                session.profile_id,
                payload.profile_patch.model_dump(exclude_unset=True),
            )
        await run_controller.resume(run_id, payload.response)
        refreshed = await db.get_run(run_id)
        assert refreshed is not None
        return refreshed

    return app


app = create_app()
