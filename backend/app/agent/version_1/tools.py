from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from langgraph.types import interrupt

from app.agent.shared.tools_runtime import ToolRuntime


def build_tools(runtime: ToolRuntime) -> list[StructuredTool]:
    def request_profile_fields(fields: list[str], question: str) -> dict[str, Any]:
        """Pause the run and request missing structured profile fields."""
        response = interrupt({"fields": fields, "question": question})
        return {"resumed": True, "response": response}

    return [
        StructuredTool.from_function(
            request_profile_fields,
            name="request_profile_fields",
            description="Pause and ask the user for missing profile fields.",
        ),
        StructuredTool.from_function(
            runtime.search_product_catalog,
            name="search_product_catalog",
            description="Search canonical catalog candidates by intent/name and optional filters.",
        ),
        StructuredTool.from_function(
            runtime.get_product_details,
            name="get_product_details",
            description="Load canonical label details for product IDs.",
        ),
        StructuredTool.from_function(
            runtime.assess_product_safety,
            name="assess_product_safety",
            description="Check explicit dataset contraindications against the current profile.",
        ),
        StructuredTool.from_function(
            runtime.rank_product_fit,
            name="rank_product_fit",
            description="Calculate deterministic product-fit scores with a breakdown.",
        ),
        StructuredTool.from_function(
            runtime.compare_products,
            name="compare_products",
            description="Build a grounded comparison focused on requested nutrients.",
        ),
        StructuredTool.from_function(
            runtime.submit_consultation,
            name="submit_consultation",
            description="Submit the terminal grounded consultation response.",
        ),
    ]
