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


ROOT = Path(__file__).parents[2]
ARTIFACTS = ROOT / "version_1" / "artifacts"


def test_runtime_prompt_comes_from_version_1_artifact():
    expected_path = ARTIFACTS / "system_prompt.md"

    assert SYSTEM_PROMPT_PATH == expected_path
    assert SYSTEM_PROMPT == expected_path.read_text(encoding="utf-8")


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
