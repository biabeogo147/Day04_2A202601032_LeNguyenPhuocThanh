from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.version_1.graph import SYSTEM_PROMPT, SYSTEM_PROMPT_PATH
from app.agent.version_1.manifest import MANIFEST
from version_1.tools import (
    TOOL_NAMES,
    load_tool_declarations,
    validate_tool_contract,
)
from version_1.tools.request_profile_fields import tool as request_profile_tool


ROOT = Path(__file__).parents[2]
ARTIFACTS = ROOT / "version_1" / "artifacts"


def test_runtime_prompt_comes_from_version_1_artifact():
    expected_path = ARTIFACTS / "system_prompt.md"

    assert SYSTEM_PROMPT_PATH == expected_path
    assert SYSTEM_PROMPT == expected_path.read_text(encoding="utf-8")


def test_system_prompt_never_requests_context_for_factual_label_lookup():
    assert "TUYỆT ĐỐI KHÔNG gọi `request_profile_fields`" in SYSTEM_PROMPT
    normalized = " ".join(SYSTEM_PROMPT.split())
    assert "thành phần, hàm lượng, giá, quy cách, liều dùng" in normalized


def test_manifest_yaml_and_registry_have_the_same_ordered_tool_names():
    declarations = load_tool_declarations()
    declared_names = tuple(item["name"] for item in declarations)

    assert declared_names == TOOL_NAMES
    assert list(TOOL_NAMES) == MANIFEST["enabled_tools"]
    validate_tool_contract(MANIFEST)


def test_each_tool_package_has_documentation_and_factory():
    for name in TOOL_NAMES:
        package = ROOT / "version_1" / "tools" / name
        assert (package / "TOOL.md").is_file()
        assert (package / "tool.py").is_file()


def test_contract_validation_fails_fast_on_manifest_drift():
    invalid = {**MANIFEST, "enabled_tools": ["search_product_catalog"]}

    with pytest.raises(ValueError, match="tool contract mismatch"):
        validate_tool_contract(invalid)


def test_request_profile_tool_emits_canonical_field_names(monkeypatch):
    captured = {}

    def fake_interrupt(payload):
        captured.update(payload)
        return {"profile_patch": {}}

    monkeypatch.setattr(request_profile_tool, "interrupt", fake_interrupt)
    tool = request_profile_tool.build(runtime=None)

    tool.invoke(
        {
            "fields": ["nhóm tuổi", "mục tiêu", "thai/cho con bú"],
            "question": "Bổ sung hồ sơ",
        }
    )

    assert captured["fields"] == [
        "age_group",
        "goals",
        "pregnancy_status",
    ]
