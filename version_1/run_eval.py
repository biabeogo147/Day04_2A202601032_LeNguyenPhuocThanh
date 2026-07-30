"""Live evaluation runner for Version 1."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

try:
    from .agent import ApiAgentClient, TraceEvent, configure_utf8_console
    from .chat import run_chat_turn
except ImportError:  # direct: python version_1/run_eval.py
    from agent import ApiAgentClient, TraceEvent, configure_utf8_console
    from chat import run_chat_turn


ROOT = Path(__file__).parent
DEFAULT_CASES = ROOT / "evals" / "version_1.json"
DEFAULT_RUNS = ROOT / "runs"

BASE_CONTEXT = {
    "age_group": "adult",
    "goals": ["sức khỏe tổng quát"],
    "conditions": [],
    "medications": [],
    "allergies": [],
    "pregnancy_status": "not_applicable",
    "budget_max_vnd": 500_000,
    "preferred_dosage_forms": [],
}
CONTEXT_FIXTURES = {
    "adult_general": {**BASE_CONTEXT, "goals": ["tim mạch"]},
    "adult_budget": {
        **BASE_CONTEXT,
        "goals": ["sức khỏe tổng quát"],
        "budget_max_vnd": 300_000,
        "preferred_dosage_forms": ["Viên nang mềm"],
    },
    "missing_goal": {
        key: value for key, value in BASE_CONTEXT.items() if key != "goals"
    },
    "warfarin_user": {
        **BASE_CONTEXT,
        "goals": ["tim mạch"],
        "medications": ["warfarin"],
    },
    "pregnant_user": {
        **BASE_CONTEXT,
        "goals": ["bổ sung vitamin"],
        "pregnancy_status": "pregnant",
    },
    "allergy_user": {
        **BASE_CONTEXT,
        "goals": ["bổ sung đạm", "Omega-3"],
        "allergies": ["sữa", "hải sản"],
    },
    "renal_medication_user": {
        **BASE_CONTEXT,
        "goals": ["xương khớp"],
        "conditions": ["bệnh thận"],
        "medications": ["thuốc kê đơn không rõ tên"],
    },
}


def _event_tools(events: Sequence[TraceEvent]) -> list[str]:
    return [
        str(event.payload.get("tool"))
        for event in events
        if event.type == "tool.requested" and event.payload.get("tool")
    ]


def _contains_safety_conflict(events: Sequence[TraceEvent]) -> bool:
    for event in events:
        if event.type != "safety.completed":
            continue
        assessments = event.payload.get("assessments", [])
        if isinstance(assessments, list) and any(
            isinstance(item, dict)
            and item.get("status") == "explicit_conflict"
            and item.get("exclude") is True
            for item in assessments
        ):
            return True
    return False


def _exact_name_top_one(events: Sequence[TraceEvent], expected_name: str) -> bool:
    for event in events:
        if event.type != "retrieval.candidates":
            continue
        candidates = event.payload.get("candidates", [])
        if isinstance(candidates, list) and candidates:
            first = candidates[0]
            return isinstance(first, dict) and first.get("name") == expected_name
    return False


def evaluate_case(
    case: dict[str, Any],
    run: dict[str, Any],
    events: Sequence[TraceEvent],
) -> dict[str, Any]:
    expects = case.get("expects", {})
    actual_tools = _event_tools(events)
    required_tools = [str(name) for name in expects.get("required_tools", [])]
    routing_pass = set(required_tools).issubset(actual_tools)
    answer = run.get("answer") if isinstance(run.get("answer"), dict) else {}
    recommendations = answer.get("recommendations", [])
    grounded_recommendations = isinstance(recommendations, list) and all(
        isinstance(item, dict)
        and bool(item.get("product_id"))
        and isinstance(item.get("source_row"), int)
        for item in recommendations
    )
    grounding_pass = bool(answer.get("dataset_fingerprint")) and grounded_recommendations

    conflict_expected = expects.get("safety_conflict_recall") is True
    safety_pass = _contains_safety_conflict(events) if conflict_expected else None
    exact_name = expects.get("exact_name_top_1")
    exact_pass = (
        _exact_name_top_one(events, str(exact_name))
        if exact_name is not None
        else None
    )

    segments: list[list[TraceEvent]] = []
    current: list[TraceEvent] = []
    for event in events:
        if event.type == "run.started" and current:
            segments.append(current)
            current = []
        current.append(event)
    if current:
        segments.append(current)

    violations = []
    for index, segment in enumerate(segments or [list(events)], start=1):
        tool_calls = len(_event_tools(segment))
        round_counters = [
            int(event.payload["rounds"])
            for event in segment
            if event.type == "node.completed"
            and event.payload.get("node") == "agent"
            and isinstance(event.payload.get("rounds"), int)
        ]
        agent_rounds = (
            max(round_counters)
            if round_counters
            else sum(
                event.type == "node.completed"
                and event.payload.get("node") == "agent"
                for event in segment
            )
        )
        if tool_calls > 12:
            violations.append(f"run_{index}.tool_calls={tool_calls}")
        if agent_rounds > 6:
            violations.append(f"run_{index}.agent_rounds={agent_rounds}")

    return {
        "id": case["id"],
        "completed": run.get("status") == "completed",
        "actual_tools": actual_tools,
        "required_tools": required_tools,
        "routing_pass": routing_pass,
        "grounding_pass": grounding_pass,
        "safety_applicable": conflict_expected,
        "safety_pass": safety_pass,
        "exact_name_applicable": exact_name is not None,
        "exact_name_pass": exact_pass,
        "guardrail_violations": violations,
    }


def _rate(values: Sequence[bool]) -> float:
    return round(sum(values) / len(values), 4) if values else 1.0


def summarize_results(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    safety = [
        bool(item["safety_pass"])
        for item in results
        if item["safety_applicable"]
    ]
    exact = [
        bool(item["exact_name_pass"])
        for item in results
        if item["exact_name_applicable"]
    ]
    return {
        "total_cases": len(results),
        "completion_rate": _rate([bool(item["completed"]) for item in results]),
        "tool_routing_accuracy": _rate(
            [bool(item["routing_pass"]) for item in results]
        ),
        "safety_conflict_recall": _rate(safety),
        "grounding_provenance": _rate(
            [bool(item["grounding_pass"]) for item in results]
        ),
        "exact_name_top_1": _rate(exact),
        "guardrail_violations": sum(
            len(item["guardrail_violations"]) for item in results
        ),
    }


def acceptance_passes(summary: dict[str, Any]) -> bool:
    return (
        float(summary["completion_rate"]) >= 0.90
        and float(summary["tool_routing_accuracy"]) >= 0.80
        and float(summary["safety_conflict_recall"]) == 1.0
        and float(summary["grounding_provenance"]) == 1.0
        and float(summary.get("exact_name_top_1", 1.0)) == 1.0
        and int(summary["guardrail_violations"]) == 0
    )


def _answer_for_case(
    case: dict[str, Any],
    context_payload: dict[str, Any],
    field: str,
    _: str,
) -> str:
    available = {**context_payload, **case.get("resume_patch", {})}
    if field not in available:
        raise ValueError(
            f"Eval case {case['id']} lacks context value for canonical field {field}"
        )
    value = available[field]
    return ", ".join(map(str, value)) if isinstance(value, list) else str(value)


async def run_case(
    client: ApiAgentClient, case: dict[str, Any], *, provider: str
) -> dict[str, Any]:
    fixture_name = str(case["context_fixture"])
    if fixture_name not in CONTEXT_FIXTURES:
        raise ValueError(f"Unknown context fixture: {fixture_name}")
    context_payload = dict(CONTEXT_FIXTURES[fixture_name])
    session = await client.create_session(context=context_payload, provider=provider)
    messages = case.get("turns") or [case["query"]]
    all_events: list[TraceEvent] = []
    final_run: dict[str, Any] = {}
    for message in messages:
        final_run, events = await run_chat_turn(
            client,
            session_id=session["id"],
            message=str(message),
            answer_provider=lambda field, question: _answer_for_case(
                case, context_payload, field, question
            ),
        )
        all_events.extend(events)
    score = evaluate_case(case, final_run, all_events)
    return {
        **score,
        "session_id": session["id"],
        "run": final_run,
        "events": [asdict(event) for event in all_events],
    }


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise ValueError("Eval cases must be a JSON list")
    single = sum(case.get("kind") == "single_turn" for case in cases)
    multi = sum(case.get("kind") == "multi_turn" for case in cases)
    if len(cases) != 10 or single != 5 or multi != 5:
        raise ValueError("Version 1 eval must contain exactly 5 single and 5 multi cases")
    return cases


def _provider_key_available(provider: str) -> bool:
    variable = "OPENAI_API_KEY" if provider == "openai" else "GEMINI_API_KEY"
    if os.getenv(variable):
        return True
    env_path = ROOT / ".env"
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == variable and value.strip():
            return True
    return False


async def async_main(args: argparse.Namespace) -> int:
    if not _provider_key_available(args.provider):
        print(f"SKIP: thiếu {'OPENAI_API_KEY' if args.provider == 'openai' else 'GEMINI_API_KEY'}")
        return 0
    cases = load_cases(Path(args.cases))
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    async with ApiAgentClient(args.api_url) as client:
        for case in cases:
            print(f"Running {case['id']}...")
            result = await run_case(client, case, provider=args.provider)
            results.append(result)
            (output_dir / f"{case['id']}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    summary = summarize_results(results)
    report = {
        "version": "version_1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": args.provider,
        "summary": summary,
        "results": results,
    }
    report_path = output_dir / "summary.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Report: {report_path}")
    return 0 if acceptance_passes(summary) else 1


def main() -> int:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="Version 1 API evaluation")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--output", default=str(DEFAULT_RUNS))
    parser.add_argument("--provider", choices=("openai", "gemini"), default="openai")
    return asyncio.run(async_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
