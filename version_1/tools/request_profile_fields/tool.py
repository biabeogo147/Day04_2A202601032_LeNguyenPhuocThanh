from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from langgraph.types import interrupt

from version_1.profile_fields import canonical_profile_fields


def build(runtime: Any) -> StructuredTool:
    def request_profile_fields(fields: list[str], question: str) -> dict[str, Any]:
        """Pause and ask the user for missing structured profile fields."""
        canonical_fields = canonical_profile_fields(fields)
        if not canonical_fields:
            return {
                "resumed": False,
                "skipped": True,
                "reason": "already_known",
            }
        if not getattr(runtime, "context_requests_allowed", True):
            return {
                "resumed": False,
                "skipped": True,
                "reason": (
                    "Câu hỏi chỉ tra cứu thông tin nhãn/catalog nên không cần hồ sơ; "
                    "hãy trả lời bằng dữ liệu canonical đã truy xuất."
                ),
            }
        response = interrupt(
            {
                "fields": canonical_fields,
                "question": question,
            }
        )
        return {"resumed": True, "response": response}

    return StructuredTool.from_function(
        request_profile_fields,
        name="request_profile_fields",
        description="Pause and ask the user for missing profile fields.",
    )
