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


def test_multi_turn_guardrails_are_measured_per_run_not_per_case():
    events = []
    sequence = 0
    for _ in range(2):
        sequence += 1
        events.append(TraceEvent(sequence, "run.started", {}))
        for _ in range(6):
            sequence += 1
            events.append(TraceEvent(sequence, "node.completed", {"node": "agent"}))
        for _ in range(12):
            sequence += 1
            events.append(
                TraceEvent(sequence, "tool.requested", {"tool": "search_product_catalog"})
            )
    run = {
        "status": "completed",
        "answer": {"dataset_fingerprint": "abc", "recommendations": []},
    }
    case = {"id": "multi", "expects": {"required_tools": ["search_product_catalog"]}}

    result = evaluate_case(case, run, events)

    assert result["guardrail_violations"] == []


def test_guard_terminal_node_without_round_counter_is_not_an_extra_agent_round():
    events = [TraceEvent(1, "run.started", {})]
    for round_number in range(1, 7):
        events.append(
            TraceEvent(
                round_number + 1,
                "node.completed",
                {"node": "agent", "rounds": round_number},
            )
        )
    events.append(TraceEvent(8, "node.completed", {"node": "agent"}))
    run = {
        "status": "completed",
        "answer": {"dataset_fingerprint": "abc", "recommendations": []},
    }
    case = {"id": "guard", "expects": {}}

    result = evaluate_case(case, run, events)

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

    async def create_session(self, *, context, provider):
        self.session_count += 1
        return {"id": "s1", "context": context, "provider": provider}

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
        "context_fixture": "adult_general",
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


class InterruptingEvalClient(ScriptedEvalClient):
    def __init__(self):
        super().__init__()
        self.stream_count = 0
        self.resumes = []

    async def stream_events(self, run_id, *, last_event_id=0):
        self.stream_count += 1
        if self.stream_count == 1:
            yield TraceEvent(
                1,
                "profile.required",
                {
                    "fields": ["nhóm tuổi", "mục tiêu", "bệnh nền"],
                    "question": "Bổ sung hồ sơ",
                },
            )
            return
        yield TraceEvent(
            2, "tool.requested", {"tool": "search_product_catalog"}
        )
        yield TraceEvent(
            3, "tool.requested", {"tool": "assess_product_safety"}
        )
        yield TraceEvent(4, "tool.requested", {"tool": "rank_product_fit"})
        yield TraceEvent(5, "tool.requested", {"tool": "submit_consultation"})
        yield TraceEvent(6, "answer.completed", {"status": "answered"})

    async def resume_run(self, run_id, *, context_patch, response):
        self.resumes.append((context_patch, response))
        return {"id": run_id, "status": "running"}


async def test_eval_uses_fixture_when_unplanned_context_interrupt_occurs():
    client = InterruptingEvalClient()
    case = {
        "id": "single_goal_search",
        "context_fixture": "adult_general",
        "query": "Tôi muốn hỗ trợ sức khỏe tim mạch",
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

    assert result["completed"] is True
    assert client.resumes[0][0] == {
        "age_group": "adult",
        "goals": ["tim mạch"],
        "conditions": [],
    }
