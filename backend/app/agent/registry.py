from __future__ import annotations

from app.agent.version_1.graph import build_graph
from app.agent.version_1.manifest import MANIFEST


VERSION_REGISTRY = {
    "version_1": {
        "manifest": MANIFEST,
        "build_graph": build_graph,
    }
}


def get_version(version_id: str):
    try:
        return VERSION_REGISTRY[version_id]
    except KeyError as exc:
        raise ValueError(f"Unknown agent version: {version_id}") from exc
