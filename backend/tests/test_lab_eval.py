from __future__ import annotations

from version_1.agent import TraceEvent
from version_1.run_eval import (
    acceptance_passes,
    evaluate_case,
    run_case,
    summarize_results,
)


def grounded_result(case_id: str, *, safety_conflict: bool = False):
    events = [
        TraceEvent(
            1,
            "tool.requested",
            {"tool": "search_product_catalog"},
        ),
        TraceEvent(2, "tool.requested", {"tool": "assess_product_safety"}),
        TraceEvent(3, "tool.requested", {"tool": "rank_product_fit"}),
        TraceEvent(4, "tool.requested", {"tool": "submit_consultation"}),
        TraceEvent(
            5,
            "safety.completed",
            {
                "assessments": [
                    {
                        "status": "explicit_conflict" if safety_conflict else "no_explicit_conflict",
                        "exclude": safety_conflict,
                    }
                ]
            },
        ),
    ]
    run = {
        "status": "completed",
        "answer": {
            "dataset_fingerprint": "abc",
            "professional_review_required": safety_conflict,
            "recommendations": (
                []
                if safety_conflict
                else [{"product_id": "p1", "source_row": 2, "name": "Product"}]
            ),
        },
    }
    case = {
        "id": case_id,
        "expects": {
            "required_tools": [
                "search_product_catalog",
                "assess_product_safety",
                "rank_product_fit",
                "submit_consultation",
            ],
            **({"safety_conflict_recall": True} if safety_conflict else {}),
        },
    }
    return evaluate_case(case, run, events)


def test_eval_case_scores_routing_safety_grounding_and_guardrails():
    result = grounded_result("safe")

    assert result["completed"] is True
    assert result["routing_pass"] is True
    assert result["grounding_pass"] is True
    assert result["guardrail_violations"] == []


def test_summary_applies_acceptance_thresholds():
    results = [grounded_result(f"case-{index}") for index in range(9)]
    results.append(grounded_result("conflict", safety_conflict=True))

    summary = summarize_results(results)

    assert summary["completion_rate"] == 1.0
    assert summary["tool_routing_accuracy"] == 1.0
    assert summary["safety_conflict_recall"] == 1.0
    assert summary["grounding_provenance"] == 1.0
    assert summary["guardrail_violations"] == 0
    assert acceptance_passes(summary) is True


def test_acceptance_fails_below_completion_or_with_guardrail_violation():
    summary = {
        "completion_rate": 0.8,
        "tool_routing_accuracy": 1.0,
        "safety_conflict_recall": 1.0,
        "grounding_provenance": 1.0,
        "guardrail_violations": 1,
    }

    assert acceptance_passes(summary) is False


class ScriptedEvalClient:
    def __init__(self):
        self.messages = []
        self.session_count = 0

    async def create_profile(self, payload):
        return {"id": "p1", **payload}

    async def create_session(self, profile_id, *, provider):
        self.session_count += 1
        return {"id": "s1", "profile_id": profile_id, "provider": provider}

    async def start_run(self, session_id, message):
        self.messages.append((session_id, message))
        return {"id": f"r{len(self.messages)}", "status": "queued"}

    async def stream_events(self, run_id, *, last_event_id=0):
        names = [
            "search_product_catalog",
            "assess_product_safety",
            "rank_product_fit",
            "submit_consultation",
        ]
        for sequence, name in enumerate(names, start=1):
            yield TraceEvent(sequence, "tool.requested", {"tool": name})
        yield TraceEvent(5, "answer.completed", {"status": "answered"})

    async def get_run(self, run_id):
        return {
            "id": run_id,
            "status": "completed",
            "answer": {
                "dataset_fingerprint": "abc",
                "recommendations": [
                    {"product_id": "p1", "source_row": 2, "name": "Product"}
                ],
            },
        }


async def test_run_case_uses_one_session_for_all_multi_turn_messages():
    client = ScriptedEvalClient()
    case = {
        "id": "scripted-multi",
        "profile": "adult_general",
        "turns": ["Lượt một", "Lượt hai"],
        "expects": {
            "required_tools": [
                "search_product_catalog",
                "assess_product_safety",
                "rank_product_fit",
                "submit_consultation",
            ]
        },
    }

    result = await run_case(client, case, provider="openai")

    assert client.session_count == 1
    assert client.messages == [("s1", "Lượt một"), ("s1", "Lượt hai")]
    assert result["completed"] is True
    assert result["routing_pass"] is True
