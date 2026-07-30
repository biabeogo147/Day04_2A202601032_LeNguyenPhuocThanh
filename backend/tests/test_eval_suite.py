import json
from pathlib import Path


EVAL_FILE = Path(__file__).parents[2] / "version_1" / "evals" / "version_1.json"


def test_version_1_eval_has_exactly_thirty_diverse_cases():
    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))

    assert len(cases) == 30
    assert len({case["id"] for case in cases}) == 30
    assert {case["category"] for case in cases} == {
        "retrieval",
        "context",
        "safety",
        "grounding",
        "injection",
    }
    assert sum(case["category"] == "injection" for case in cases) == 7


def test_each_eval_case_uses_inline_context_turns_and_structured_oracles():
    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))

    for case in cases:
        assert isinstance(case["title"], str) and case["title"]
        assert isinstance(case["tags"], list) and case["tags"]
        assert isinstance(case["initial_context"], dict)
        assert isinstance(case["turns"], list) and case["turns"]
        assert all(isinstance(turn["message"], str) and turn["message"] for turn in case["turns"])
        assert isinstance(case["expects"], dict)
        assert case["expects"].get("grounded") is True


def test_each_eval_case_requires_grounded_terminal_tool():
    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))

    assert all("submit_consultation" in case["expects"]["required_tools"] for case in cases)
