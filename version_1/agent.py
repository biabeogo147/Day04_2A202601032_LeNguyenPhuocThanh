"""HTTP/SSE client for the canonical FastAPI agent runtime."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx


class AgentApiError(RuntimeError):
    """Safe API boundary error that never echoes provider response bodies."""


def configure_utf8_console(*streams: Any) -> None:
    """Make Vietnamese CLI output reliable on legacy Windows code pages."""
    targets = streams or (sys.stdout, sys.stderr)
    for stream in targets:
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


@dataclass(frozen=True)
class TraceEvent:
    sequence: int
    type: str
    payload: dict[str, Any]


class ApiAgentClient:
    def __init__(
        self,
        api_url: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 70.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self._owns_client = http_client is None
        self.http = http_client or httpx.AsyncClient(
            base_url=self.api_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    async def __aenter__(self) -> "ApiAgentClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self.http.aclose()

    async def _request(
        self, method: str, path: str, *, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        try:
            response = await self.http.request(method, path, json=json_body)
        except httpx.HTTPError as exc:
            raise AgentApiError(f"Không thể kết nối FastAPI: {type(exc).__name__}") from exc
        if response.is_error:
            raise AgentApiError(f"FastAPI trả HTTP {response.status_code} cho {method} {path}")
        return response.json()

    async def create_session(
        self,
        *,
        context: dict[str, Any] | None = None,
        provider: str = "openai",
        version_id: str = "version_1",
    ) -> dict[str, Any]:
        result = await self._request(
            "POST",
            "/api/v1/sessions",
            json_body={
                "context": context or {},
                "version_id": version_id,
                "provider": provider,
            },
        )
        assert isinstance(result, dict)
        return result

    async def start_run(self, session_id: str, message: str) -> dict[str, Any]:
        result = await self._request(
            "POST",
            f"/api/v1/sessions/{session_id}/runs",
            json_body={"message": message},
        )
        assert isinstance(result, dict)
        return result

    async def get_run(self, run_id: str) -> dict[str, Any]:
        result = await self._request("GET", f"/api/v1/runs/{run_id}")
        assert isinstance(result, dict)
        return result

    async def resume_run(
        self,
        run_id: str,
        *,
        context_patch: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = await self._request(
            "POST",
            f"/api/v1/runs/{run_id}/resume",
            json_body={
                "context_patch": context_patch,
                "response": response or {},
            },
        )
        assert isinstance(result, dict)
        return result

    async def stream_events(
        self, run_id: str, *, last_event_id: int = 0
    ) -> AsyncIterator[TraceEvent]:
        headers = (
            {"Last-Event-ID": str(last_event_id)}
            if last_event_id > 0
            else {}
        )
        try:
            async with self.http.stream(
                "GET",
                f"/api/v1/runs/{run_id}/events",
                headers=headers,
            ) as response:
                if response.is_error:
                    raise AgentApiError(
                        f"FastAPI trả HTTP {response.status_code} cho SSE run {run_id}"
                    )
                event_id = 0
                event_type = "message"
                data_lines: list[str] = []
                async for line in response.aiter_lines():
                    if line == "":
                        event = _decode_event(event_id, event_type, data_lines)
                        if event is not None:
                            yield event
                        event_id = 0
                        event_type = "message"
                        data_lines = []
                    elif line.startswith("id:"):
                        event_id = int(line[3:].strip())
                    elif line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                event = _decode_event(event_id, event_type, data_lines)
                if event is not None:
                    yield event
        except AgentApiError:
            raise
        except httpx.HTTPError as exc:
            raise AgentApiError(f"Kết nối SSE thất bại: {type(exc).__name__}") from exc


def _decode_event(
    sequence: int, event_type: str, data_lines: list[str]
) -> TraceEvent | None:
    if not data_lines:
        return None
    try:
        payload = json.loads("\n".join(data_lines))
    except json.JSONDecodeError as exc:
        raise AgentApiError(f"SSE event {sequence} không phải JSON hợp lệ") from exc
    if not isinstance(payload, dict):
        payload = {"value": payload}
    return TraceEvent(sequence=sequence, type=event_type, payload=payload)
