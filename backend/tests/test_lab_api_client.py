from __future__ import annotations

import json
import io

import httpx
import pytest

from version_1.agent import AgentApiError, ApiAgentClient, TraceEvent, configure_utf8_console


@pytest.fixture
def context_payload():
    return {
        "age_group": "adult",
        "goals": ["tim mạch"],
        "conditions": [],
        "medications": [],
        "allergies": [],
        "pregnancy_status": "not_applicable",
        "budget_max_vnd": 500_000,
        "preferred_dosage_forms": ["Viên nang mềm"],
    }


async def test_client_uses_public_session_and_run_contract(context_payload):
    requests: list[tuple[str, str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content or b"{}")
        requests.append((request.method, request.url.path, payload))
        if request.url.path == "/api/v1/sessions":
            return httpx.Response(201, json={"id": "s1"})
        return httpx.Response(202, json={"id": "r1", "status": "queued"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as http:
        client = ApiAgentClient("http://test", http_client=http)
        session = await client.create_session(context=context_payload)
        run = await client.start_run(session["id"], "Tư vấn Omega-3")

    assert run["id"] == "r1"
    assert requests == [
        (
            "POST",
            "/api/v1/sessions",
            {"context": context_payload, "version_id": "version_1", "provider": "openai"},
        ),
        (
            "POST",
            "/api/v1/sessions/s1/runs",
            {"message": "Tư vấn Omega-3"},
        ),
    ]


async def test_sse_stream_replays_after_last_event_id():
    seen_header: str | None = None
    sse = (
        'id: 5\nevent: tool.completed\ndata: {"tool":"search_product_catalog"}\n\n'
        'id: 6\nevent: answer.completed\ndata: {"status":"answered"}\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_header
        seen_header = request.headers.get("last-event-id")
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as http:
        client = ApiAgentClient("http://test", http_client=http)
        events = [event async for event in client.stream_events("r1", last_event_id=4)]

    assert seen_header == "4"
    assert events == [
        TraceEvent(5, "tool.completed", {"tool": "search_product_catalog"}),
        TraceEvent(6, "answer.completed", {"status": "answered"}),
    ]


async def test_resume_sends_structured_context_data():
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "r1", "status": "running"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as http:
        client = ApiAgentClient("http://test", http_client=http)
        await client.resume_run(
            "r1",
            context_patch={"goals": ["xương khớp"]},
            response={"context_patch": {"goals": ["xương khớp"]}},
        )

    assert bodies == [
        {
            "context_patch": {"goals": ["xương khớp"]},
            "response": {"context_patch": {"goals": ["xương khớp"]}},
        },
    ]


async def test_api_error_is_short_and_does_not_echo_provider_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="secret-provider-response")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as http:
        client = ApiAgentClient("http://test", http_client=http)
        with pytest.raises(AgentApiError, match="HTTP 500") as captured:
            await client.get_run("r1")

    assert "secret-provider-response" not in str(captured.value)


def test_console_boundary_can_print_vietnamese_on_legacy_windows_encoding():
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252")

    configure_utf8_console(stream)
    stream.write("thiếu API key")
    stream.flush()

    assert buffer.getvalue().decode("utf-8") == "thiếu API key"
