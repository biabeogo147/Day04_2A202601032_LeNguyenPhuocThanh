import json
from pathlib import Path


EVAL_FILE = Path(__file__).parents[2] / "version_1" / "evals" / "version_1.json"


def test_version_1_eval_has_exactly_five_single_and_five_multi_turn_cases():
    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))

    assert len(cases) == 10
    assert len([case for case in cases if case["kind"] == "single_turn"]) == 5
    assert len([case for case in cases if case["kind"] == "multi_turn"]) == 5
    assert len({case["id"] for case in cases}) == 10


def test_each_eval_case_requires_grounded_terminal_tool():
    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))

    assert all("submit_consultation" in case["expects"]["required_tools"] for case in cases)
