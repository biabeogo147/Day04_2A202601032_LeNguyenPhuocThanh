"""Canonical LangChain tool registry for Version 1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .assess_product_safety.tool import build as build_assess_product_safety
from .compare_products.tool import build as build_compare_products
from .get_product_details.tool import build as build_get_product_details
from .rank_product_fit.tool import build as build_rank_product_fit
from .request_profile_fields.tool import build as build_request_profile_fields
from .search_product_catalog.tool import build as build_search_product_catalog
from .submit_consultation.tool import build as build_submit_consultation


ARTIFACT_PATH = Path(__file__).parents[1] / "artifacts" / "tools.yaml"
TOOL_NAMES = (
    "request_profile_fields",
    "search_product_catalog",
    "get_product_details",
    "assess_product_safety",
    "rank_product_fit",
    "compare_products",
    "submit_consultation",
)
TOOL_FACTORIES = (
    build_request_profile_fields,
    build_search_product_catalog,
    build_get_product_details,
    build_assess_product_safety,
    build_rank_product_fit,
    build_compare_products,
    build_submit_consultation,
)


def load_tool_declarations() -> list[dict[str, Any]]:
    payload = yaml.safe_load(ARTIFACT_PATH.read_text(encoding="utf-8"))
    declarations = payload.get("tools") if isinstance(payload, dict) else None
    if not isinstance(declarations, list):
        raise ValueError("version_1/artifacts/tools.yaml must contain a tools list")
    return declarations


def validate_tool_contract(manifest: dict[str, Any]) -> None:
    declared = tuple(item.get("name") for item in load_tool_declarations())
    enabled = tuple(manifest.get("enabled_tools", ()))
    if declared != TOOL_NAMES or enabled != TOOL_NAMES:
        raise ValueError(
            "version_1 tool contract mismatch: manifest, tools.yaml, and registry "
            "must contain the same ordered names"
        )


def build_tools(runtime: Any):
    from app.agent.version_1.manifest import MANIFEST

    validate_tool_contract(MANIFEST)
    return [factory(runtime) for factory in TOOL_FACTORIES]


__all__ = [
    "ARTIFACT_PATH",
    "TOOL_NAMES",
    "build_tools",
    "load_tool_declarations",
    "validate_tool_contract",
]
