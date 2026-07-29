from __future__ import annotations

import json

from version_1.agent import TraceEvent
from version_1.chat import (
    coerce_profile_patch,
    run_chat_turn,
    write_transcript,
)


def test_profile_answers_are_coerced_to_api_schema():
    patch = coerce_profile_patch(
        ["goals", "budget_max_vnd", "pregnancy_status"],
        {
            "goals": "xương khớp, vitamin D",
            "budget_max_vnd": "450000",
            "pregnancy_status": "none",
        },
    )

    assert patch == {
        "goals": ["xương khớp", "vitamin D"],
        "budget_max_vnd": 450000,
        "pregnancy_status": "none",
    }


class InterruptingClient:
    def __init__(self):
        self.stream_count = 0
        self.patches = []
        self.resumes = []

    async def start_run(self, session_id, message):
        return {"id": "r1", "query": message, "status": "queued"}

    async def stream_events(self, run_id, *, last_event_id=0):
        self.stream_count += 1
        if self.stream_count == 1:
            yield TraceEvent(
                1,
                "profile.required",
                {"fields": ["goals"], "question": "Mục tiêu của bạn là gì?"},
            )
        else:
            assert last_event_id == 1
            yield TraceEvent(
                2,
                "answer.completed",
                {"status": "answered", "final_judgment": "Có căn cứ."},
            )

    async def patch_profile(self, profile_id, patch):
        self.patches.append((profile_id, patch))
        return {"id": profile_id, **patch}

    async def resume_run(self, run_id, *, response):
        self.resumes.append((run_id, response))
        return {"id": run_id, "status": "running"}

    async def get_run(self, run_id):
        return {
            "id": run_id,
            "status": "completed",
            "answer": {"status": "answered", "final_judgment": "Có căn cứ."},
        }


async def test_chat_turn_patches_profile_and_resumes_same_run():
    client = InterruptingClient()

    run, events = await run_chat_turn(
        client,
        session_id="s1",
        profile_id="p1",
        message="Tư vấn giúp tôi",
        answer_provider=lambda field, question: "xương khớp",
    )

    assert run["status"] == "completed"
    assert [event.sequence for event in events] == [1, 2]
    assert client.patches == [("p1", {"goals": ["xương khớp"]})]
    assert client.resumes == [
        ("r1", {"profile_patch": {"goals": ["xương khớp"]}})
    ]


def test_transcript_contains_public_events_but_no_secret(tmp_path):
    target = write_transcript(
        tmp_path,
        profile_id="p1",
        session_id="s1",
        turns=[
            {
                "message": "Omega-3",
                "run": {"id": "r1", "status": "completed"},
                "events": [TraceEvent(1, "public.decision", {"tools": ["search"]})],
            }
        ],
    )

    content = target.read_text(encoding="utf-8")
    payload = json.loads(content)
    assert payload["profile_id"] == "p1"
    assert payload["turns"][0]["events"][0]["type"] == "public.decision"
    assert "OPENAI_API_KEY" not in content
    assert "chain-of-thought" not in content.casefold()
