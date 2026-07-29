from __future__ import annotations

import hashlib
from pathlib import Path

from app.config import Settings


ROOT = Path(__file__).parents[2]
VERSION_DIR = ROOT / "version_1"


ORIGINAL_GUIDE_SHA256 = {
    "README.md": "2d3af83d552427632c5f44f3d37ebe71f580d0870bf1960fa81f6107a399df54",
    "TOOL-SETUP.md": "ea3e1e62d2ad7d009ddcfdfa90fa3bb081b6ba218ddb33e0e6084b49bfda2c7b",
}


def _normalized_sha256(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def test_version_1_lab_shell_has_required_top_level_contract():
    required = {
        "artifacts",
        "samples",
        "tools",
        "evals",
        "agent.py",
        "chat.py",
        "run_eval.py",
        ".env.example",
        "README.md",
        "TOOL-SETUP.md",
    }

    assert required <= {path.name for path in VERSION_DIR.iterdir()}


def test_root_dataset_is_renamed_to_shared_data():
    assert (ROOT / "shared_data" / "DataTPCN.csv").is_file()
    assert not (ROOT / "data").exists()


def test_settings_use_version_1_environment_and_runtime_storage():
    settings = Settings()

    assert settings.model_config["env_file"] == VERSION_DIR / ".env"
    assert settings.resolved_path(settings.dataset_path) == (
        ROOT / "shared_data" / "DataTPCN.csv"
    )
    assert settings.resolved_path(settings.checkpoint_database_path).is_relative_to(
        VERSION_DIR / "storage"
    )
    assert settings.resolved_path(settings.chroma_persist_directory).is_relative_to(
        VERSION_DIR / "storage"
    )


def test_root_guides_are_restored_exactly_to_original_content():
    for name, expected in ORIGINAL_GUIDE_SHA256.items():
        assert _normalized_sha256(ROOT / name) == expected
