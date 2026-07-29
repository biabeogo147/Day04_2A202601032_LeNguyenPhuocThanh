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
except ImportError:  # direct: python version_1/chat.py
    from agent import ApiAgentClient, TraceEvent, configure_utf8_console


LIST_FIELDS = {
    "goals",
    "conditions",
    "medications",
    "allergies",
    "preferred_dosage_forms",
}
TERMINAL_EVENTS = {"answer.completed", "run.failed"}


def coerce_profile_patch(
    fields: list[str], answers: dict[str, str]
) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for field in fields:
        value = answers[field].strip()
        if field in LIST_FIELDS:
            patch[field] = [item.strip() for item in value.split(",") if item.strip()]
        elif field == "budget_max_vnd":
            patch[field] = int(value)
        else:
            patch[field] = value
    return patch


async def run_chat_turn(
    client: ApiAgentClient,
    *,
    session_id: str,
    profile_id: str,
    message: str,
    answer_provider: Callable[[str, str], str] = input,
    event_sink: Callable[[TraceEvent], None] | None = None,
) -> tuple[dict[str, Any], list[TraceEvent]]:
    created = await client.start_run(session_id, message)
    run_id = str(created["id"])
    cursor = 0
    events: list[TraceEvent] = []

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
                fields = [str(field) for field in raw_fields] if isinstance(raw_fields, list) else []
                question = str(event.payload.get("question", "Bổ sung thông tin hồ sơ"))
                answers = {
                    field: answer_provider(field, question)
                    for field in fields
                }
                patch = coerce_profile_patch(fields, answers)
                await client.patch_profile(profile_id, patch)
                await client.resume_run(
                    run_id,
                    response={"profile_patch": patch},
                )
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
            raise RuntimeError("Run interrupted without a profile.required event")


def write_transcript(
    directory: str | Path,
    *,
    profile_id: str,
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
        "profile_id": profile_id,
        "session_id": session_id,
        "turns": serializable_turns,
    }
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def _new_profile_from_input() -> dict[str, Any]:
    def values(prompt: str) -> list[str]:
        return [item.strip() for item in input(prompt).split(",") if item.strip()]

    return {
        "display_name": input("Tên profile: ").strip() or "CLI user",
        "age_group": input("Nhóm tuổi [adult]: ").strip() or "adult",
        "goals": values("Mục tiêu (cách nhau bằng dấu phẩy): "),
        "conditions": values("Bệnh nền: "),
        "medications": values("Thuốc đang dùng: "),
        "allergies": values("Dị ứng: "),
        "pregnancy_status": (
            input("Thai/cho con bú [not_applicable]: ").strip() or "not_applicable"
        ),
        "budget_max_vnd": int(input("Ngân sách tối đa [500000]: ").strip() or "500000"),
        "preferred_dosage_forms": values("Dạng bào chế ưu tiên: "),
    }


async def _select_profile(client: ApiAgentClient, profile_id: str | None) -> dict[str, Any]:
    profiles = await client.list_profiles()
    if profile_id is not None:
        for profile in profiles:
            if profile.get("id") == profile_id:
                return profile
        raise ValueError(f"Không tìm thấy profile {profile_id}")
    if profiles:
        print("Profiles:")
        for index, profile in enumerate(profiles, start=1):
            print(f"  {index}. {profile['display_name']} ({profile['id']})")
        choice = input("Chọn số profile hoặc Enter để tạo mới: ").strip()
        if choice:
            return profiles[int(choice) - 1]
    return await client.create_profile(_new_profile_from_input())


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
        profile = await _select_profile(client, args.profile_id)
        session = await client.create_session(profile["id"], provider=args.provider)
        print("Nhập /exit để kết thúc.")
        while True:
            message = input("\nBạn: ").strip()
            if not message:
                continue
            if message == "/exit":
                break
            run, events = await run_chat_turn(
                client,
                session_id=session["id"],
                profile_id=profile["id"],
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
            profile_id=profile["id"],
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
    parser.add_argument("--profile-id")
    return asyncio.run(async_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
