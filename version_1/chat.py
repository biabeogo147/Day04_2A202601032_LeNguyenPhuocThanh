"""Interactive multi-turn client for Version 1."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from .agent import ApiAgentClient, TraceEvent, configure_utf8_console
    from .profile_fields import (
        canonical_profile_field,
        canonical_profile_fields,
        coerce_profile_value,
    )
except ImportError:  # direct: python version_1/chat.py
    from agent import ApiAgentClient, TraceEvent, configure_utf8_console
    from profile_fields import (
        canonical_profile_field,
        canonical_profile_fields,
        coerce_profile_value,
    )
TERMINAL_EVENTS = {"answer.completed", "run.failed"}


def coerce_context_patch(
    fields: list[str], answers: dict[str, str]
) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for raw_field in fields:
        field = canonical_profile_field(raw_field)
        value = answers.get(raw_field, answers.get(field, ""))
        patch[field] = coerce_profile_value(field, value)
    return patch


async def run_chat_turn(
    client: ApiAgentClient,
    *,
    session_id: str,
    message: str,
    answer_provider: Callable[[str, str], str] = input,
    event_sink: Callable[[TraceEvent], None] | None = None,
) -> tuple[dict[str, Any], list[TraceEvent]]:
    created = await client.start_run(session_id, message)
    run_id = str(created["id"])
    cursor = 0
    events: list[TraceEvent] = []
    interrupt_replay_attempted = False

    while True:
        interrupted = False
        terminal = False
        async for event in client.stream_events(run_id, last_event_id=cursor):
            cursor = max(cursor, event.sequence)
            events.append(event)
            if event_sink is not None:
                event_sink(event)
            if event.type == "profile.required":
                raw_fields = event.payload.get("fields", [])
                fields = (
                    canonical_profile_fields(str(field) for field in raw_fields)
                    if isinstance(raw_fields, list)
                    else []
                )
                question = str(event.payload.get("question", "Bổ sung thông tin cần thiết"))
                answers = {
                    field: answer_provider(field, question)
                    for field in fields
                }
                patch = coerce_context_patch(fields, answers)
                await client.resume_run(
                    run_id,
                    context_patch=patch,
                    response={"context_patch": patch},
                )
                interrupt_replay_attempted = False
                interrupted = True
                break
            if event.type in TERMINAL_EVENTS:
                terminal = True
        if interrupted:
            continue
        run = await client.get_run(run_id)
        if terminal or run.get("status") in {"completed", "failed"}:
            return run, events
        if run.get("status") == "interrupted":
            if not interrupt_replay_attempted:
                interrupt_replay_attempted = True
                continue
            raise RuntimeError("Run interrupted without a profile.required event")


def write_transcript(
    directory: str | Path,
    *,
    session_id: str,
    turns: list[dict[str, Any]],
) -> Path:
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = target_dir / f"chat_{timestamp}.transcript.json"
    serializable_turns = []
    for turn in turns:
        serializable_turns.append(
            {
                **turn,
                "events": [
                    asdict(event) if isinstance(event, TraceEvent) else event
                    for event in turn.get("events", [])
                ],
            }
        )
    payload = {
        "version": "version_1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "turns": serializable_turns,
    }
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def _print_event(event: TraceEvent) -> None:
    if event.type in {
        "public.decision",
        "tool.requested",
        "tool.completed",
        "retrieval.candidates",
        "ranking.completed",
        "safety.completed",
        "answer.completed",
        "run.failed",
    }:
        print(f"[{event.sequence:02d}] {event.type}: {json.dumps(event.payload, ensure_ascii=False)}")


async def async_main(args: argparse.Namespace) -> int:
    turns: list[dict[str, Any]] = []
    async with ApiAgentClient(args.api_url) as client:
        session = await client.create_session(provider=args.provider)
        print("Hỏi ngay, không cần tạo hồ sơ. Nhập /exit để kết thúc.")
        while True:
            message = input("\nBạn: ").strip()
            if not message:
                continue
            if message == "/exit":
                break
            run, events = await run_chat_turn(
                client,
                session_id=session["id"],
                message=message,
                answer_provider=lambda field, question: input(f"{question} [{field}]: "),
                event_sink=_print_event,
            )
            turns.append({"message": message, "run": run, "events": events})
            if run.get("answer"):
                print(json.dumps(run["answer"], ensure_ascii=False, indent=2))
    if turns:
        path = write_transcript(
            Path(__file__).parent / "transcripts",
            session_id=session["id"],
            turns=turns,
        )
        print(f"Transcript: {path}")
    return 0


def main() -> int:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="Version 1 TPCN API chat")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--provider", choices=("openai", "gemini"), default="openai")
    return asyncio.run(async_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
