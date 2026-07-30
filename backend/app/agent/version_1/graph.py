from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.agent.shared.catalog import fold_text
from app.agent.shared.tools_runtime import DISCLAIMER, GroundingError, ToolRuntime

from .manifest import MANIFEST
from version_1.tools import build_tools


REPO_ROOT = Path(__file__).resolve().parents[4]
SYSTEM_PROMPT_PATH = REPO_ROOT / "version_1" / "artifacts" / "system_prompt.md"
SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

FACTUAL_LOOKUP_MARKERS = (
    "thanh phan",
    "ham luong",
    "lieu dung",
    "gia",
    "quy cach",
    "dong goi",
    "cong dung",
    "doi tuong su dung",
    "dang bao che",
)
PERSONALIZED_MARKERS = (
    "phu hop",
    "nen chon",
    "nen dung",
    "an toan",
    "can luu y",
    "toi dang",
    "cho toi",
    "benh nen",
    "di ung",
    "mang thai",
    "cho con bu",
    "thuoc dang dung",
    "warfarin",
)


def _is_factual_catalog_lookup(messages: list[AnyMessage]) -> bool:
    latest_user_text = next(
        (
            message.content
            for message in reversed(messages)
            if isinstance(message, HumanMessage) and isinstance(message.content, str)
        ),
        "",
    )
    normalized = fold_text(latest_user_text)
    return (
        any(marker in normalized for marker in FACTUAL_LOOKUP_MARKERS)
        and not any(marker in normalized for marker in PERSONALIZED_MARKERS)
    )


def _merge_batch_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    batchable = {
        "get_product_details",
        "assess_product_safety",
        "rank_product_fit",
    }
    merged: list[dict[str, Any]] = []
    positions: dict[str, int] = {}

    def extend_unique(target: list[Any], values: Any) -> None:
        if not isinstance(values, list):
            return
        for value in values:
            if value not in target:
                target.append(value)

    for original in calls:
        call = {**original, "args": dict(original.get("args", {}))}
        name = str(call.get("name", ""))
        if name not in batchable or name not in positions:
            positions.setdefault(name, len(merged))
            merged.append(call)
            continue

        target_args = merged[positions[name]]["args"]
        incoming_args = call["args"]
        for key in ("product_ids", "focus_nutrients", "requested_nutrients"):
            existing = target_args.setdefault(key, [])
            if isinstance(existing, list):
                extend_unique(existing, incoming_args.get(key, []))
        if isinstance(incoming_args.get("semantic_scores"), dict):
            target_args.setdefault("semantic_scores", {}).update(
                incoming_args["semantic_scores"]
            )
        for key, value in incoming_args.items():
            target_args.setdefault(key, value)
    return merged


def _hydrate_catalog_state(runtime: ToolRuntime, messages: list[AnyMessage]) -> None:
    for message in messages:
        if not isinstance(message, ToolMessage) or not isinstance(message.content, str):
            continue
        try:
            payload = json.loads(message.content)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if message.name == "search_product_catalog":
            for candidate in payload.get("candidates", []):
                if not isinstance(candidate, dict) or not candidate.get("product_id"):
                    continue
                runtime.retrieved.setdefault(
                    str(candidate["product_id"]),
                    float(candidate.get("similarity", 0.0)),
                )
        elif message.name == "get_product_details":
            for product in payload.get("products", []):
                if isinstance(product, dict) and product.get("product_id"):
                    runtime.details.add(str(product["product_id"]))


def _grounding_prerequisite_calls(
    calls: list[dict[str, Any]], runtime: ToolRuntime
) -> list[dict[str, Any]]:
    if len(calls) != 1 or calls[0].get("name") != "submit_consultation":
        return calls
    selected = [
        str(product_id)
        for product_id in calls[0].get("args", {}).get("selected_product_ids", [])
    ]
    if not selected or any(product_id not in runtime.retrieved for product_id in selected):
        return calls

    prefix = str(calls[0].get("id", "submit"))
    prerequisites: list[dict[str, Any]] = []
    missing_details = [product_id for product_id in selected if product_id not in runtime.details]
    missing_safety = [product_id for product_id in selected if product_id not in runtime.safety]
    missing_ranking = [product_id for product_id in selected if product_id not in runtime.ranking]
    if missing_details:
        prerequisites.append(
            {
                "name": "get_product_details",
                "args": {"product_ids": missing_details},
                "id": f"{prefix}-details",
                "type": "tool_call",
            }
        )
    if missing_safety:
        prerequisites.append(
            {
                "name": "assess_product_safety",
                "args": {"product_ids": missing_safety},
                "id": f"{prefix}-safety",
                "type": "tool_call",
            }
        )
    if missing_ranking:
        prerequisites.append(
            {
                "name": "rank_product_fit",
                "args": {
                    "product_ids": missing_ranking,
                    "semantic_scores": {
                        product_id: runtime.retrieved[product_id]
                        for product_id in missing_ranking
                    },
                },
                "id": f"{prefix}-ranking",
                "type": "tool_call",
            }
        )
    return prerequisites or calls


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    rounds: int
    repair_count: int
    tool_call_count: int
    tool_call_signatures: list[str]
    final_response: dict[str, Any]


def _fallback(reason: str) -> dict[str, Any]:
    return {
        "status": "safe_fallback",
        "final_judgment": "Chưa thể hoàn tất tư vấn có căn cứ trong giới hạn của phiên này.",
        "recommendations": [],
        "limitations": [reason],
        "follow_up_question": None,
        "professional_review_required": True,
        "disclaimer": DISCLAIMER,
    }


def build_graph(*, model: Any, runtime: ToolRuntime, checkpointer: Any | None = None):
    tools = build_tools(runtime)
    bound_model = model.bind_tools(tools)
    known_context = {
        key: value
        for key, value in asdict(runtime.profile).items()
        if value is not None
    }
    profile_context = json.dumps(
        known_context,
        ensure_ascii=False,
        sort_keys=True,
    )

    def prepare_context(state: AgentState) -> dict[str, Any]:
        runtime.context_requests_allowed = not _is_factual_catalog_lookup(
            state.get("messages", [])
        )
        return {
            "rounds": 0,
            "repair_count": 0,
            "tool_call_count": 0,
            "tool_call_signatures": [],
            "final_response": None,
        }

    async def agent_node(state: AgentState) -> dict[str, Any]:
        _hydrate_catalog_state(runtime, state.get("messages", []))
        rounds = int(state.get("rounds", 0))
        if rounds >= int(MANIFEST["max_rounds"]):
            return {"final_response": _fallback("Đã đạt giới hạn 6 vòng ReAct.")}
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            SystemMessage(
                content=(
                    "CANONICAL_CONTEXT_JSON: "
                    f"{profile_context}\n"
                    "Chỉ các khóa xuất hiện mới là thông tin người dùng đã xác nhận. "
                    "Mảng rỗng nghĩa là người dùng đã khai báo không có/không ưu tiên; "
                    "không hỏi lại trường đó. Khóa không xuất hiện là chưa biết. "
                    "Chỉ gọi request_profile_fields cho dữ liệu thật sự cần để trả lời "
                    "câu hỏi hiện tại và luôn dùng tên field canonical."
                )
            ),
            *state.get("messages", []),
        ]
        response = await bound_model.ainvoke(messages)
        raw_calls = getattr(response, "tool_calls", []) or []
        calls = _merge_batch_tool_calls(raw_calls)
        calls = _grounding_prerequisite_calls(calls, runtime)
        if calls != raw_calls:
            response = response.model_copy(update={"tool_calls": calls})
        total_calls = int(state.get("tool_call_count", 0)) + len(calls)
        if total_calls > int(MANIFEST["max_tool_calls"]):
            return {"final_response": _fallback("Đã đạt giới hạn 12 tool call.")}
        previous_signatures = set(state.get("tool_call_signatures", []))
        signatures = [
            json.dumps(
                {"name": call.get("name"), "args": call.get("args", {})},
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            for call in calls
        ]
        if any(signature in previous_signatures for signature in signatures):
            return {
                "final_response": _fallback(
                    "Phát hiện tool call lặp lại với cùng tham số."
                )
            }
        blocked_context_only = (
            not runtime.context_requests_allowed
            and bool(calls)
            and all(call.get("name") == "request_profile_fields" for call in calls)
        )
        return {
            "messages": [response],
            "rounds": rounds if blocked_context_only else rounds + 1,
            "tool_call_count": total_calls,
            "tool_call_signatures": [*previous_signatures, *signatures],
        }

    def route_agent(state: AgentState) -> str:
        if state.get("final_response") is not None:
            return "end"
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", []) or []
        if not calls:
            return "repair"
        if any(call["name"] == "submit_consultation" for call in calls):
            return "finalize"
        return "tools"

    def repair_node(state: AgentState) -> dict[str, Any]:
        repairs = int(state.get("repair_count", 0))
        if repairs >= int(MANIFEST["repair_attempts"]):
            return {
                "repair_count": repairs,
                "final_response": _fallback(
                    "Model không gọi submit_consultation sau một lần yêu cầu sửa."
                ),
            }
        return {
            "repair_count": repairs + 1,
            "messages": [
                HumanMessage(
                    content=(
                        "FORMAT_REPAIR: Không trả lời tự do. Hãy gọi các tool còn thiếu và "
                        "kết thúc bằng submit_consultation."
                    )
                )
            ],
        }

    def route_repair(state: AgentState) -> str:
        return "end" if state.get("final_response") is not None else "agent"

    def finalize_node(state: AgentState) -> dict[str, Any]:
        message = state["messages"][-1]
        submit_calls = [
            call for call in getattr(message, "tool_calls", []) or []
            if call["name"] == "submit_consultation"
        ]
        if len(submit_calls) != 1:
            return {"final_response": _fallback("Terminal response phải có đúng một submit call.")}
        call = submit_calls[0]
        try:
            response = runtime.submit_consultation(**call["args"])
        except (GroundingError, KeyError, TypeError, ValueError) as exc:
            repairs = int(state.get("repair_count", 0))
            if repairs >= int(MANIFEST["repair_attempts"]):
                return {"final_response": _fallback(str(exc))}
            return {
                "repair_count": repairs + 1,
                "messages": [
                    ToolMessage(
                        content=f"GROUNDING_ERROR: {exc}",
                        tool_call_id=call["id"],
                        name="submit_consultation",
                    )
                ],
            }
        return {
            "messages": [
                ToolMessage(
                    content=json.dumps(response, ensure_ascii=False),
                    tool_call_id=call["id"],
                    name="submit_consultation",
                )
            ],
            "final_response": response,
        }

    def route_finalize(state: AgentState) -> str:
        return "end" if state.get("final_response") is not None else "agent"

    builder = StateGraph(AgentState)
    builder.add_node("prepare_context", prepare_context)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("repair", repair_node)
    builder.add_node("finalize", finalize_node)
    builder.add_edge(START, "prepare_context")
    builder.add_edge("prepare_context", "agent")
    builder.add_conditional_edges(
        "agent",
        route_agent,
        {"tools": "tools", "repair": "repair", "finalize": "finalize", "end": END},
    )
    builder.add_edge("tools", "agent")
    builder.add_conditional_edges("repair", route_repair, {"agent": "agent", "end": END})
    builder.add_conditional_edges("finalize", route_finalize, {"agent": "agent", "end": END})
    return builder.compile(checkpointer=checkpointer)
