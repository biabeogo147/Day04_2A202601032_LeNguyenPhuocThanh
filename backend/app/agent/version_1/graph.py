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
from version_1.profile_fields import canonical_profile_fields
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
    "benh nen",
    "di ung",
    "mang thai",
    "cho con bu",
    "thuoc dang dung",
    "warfarin",
)
EXPLICIT_PRODUCT_LOOKUP_MARKERS = (
    "cho toi thong tin",
    "tra cuu chinh xac",
    "tra cuu san pham",
    "thong tin san pham",
)


def _latest_user_text(messages: list[AnyMessage]) -> str:
    return next(
        (
            message.content
            for message in reversed(messages)
            if isinstance(message, HumanMessage) and isinstance(message.content, str)
        ),
        "",
    )


def _is_factual_catalog_lookup(messages: list[AnyMessage]) -> bool:
    normalized = fold_text(_latest_user_text(messages))
    # Context interrupts are only useful when the user actually asks for a
    # personalized fit/safety decision. Catalog, scope and adversarial prompts
    # must never trigger collection of unrelated personal information.
    return not any(marker in normalized for marker in PERSONALIZED_MARKERS)


def _is_explicit_product_lookup(messages: list[AnyMessage]) -> bool:
    normalized = fold_text(_latest_user_text(messages))
    return any(marker in normalized for marker in EXPLICIT_PRODUCT_LOOKUP_MARKERS)


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


def _has_resumed_profile_context(messages: list[AnyMessage]) -> bool:
    for message in messages:
        if not isinstance(message, ToolMessage) or message.name != "request_profile_fields":
            continue
        try:
            payload = json.loads(message.content) if isinstance(message.content, str) else {}
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("resumed") is True:
            return True
    return False


def _resolved_profile_context(
    base_context: dict[str, Any], messages: list[AnyMessage]
) -> dict[str, Any]:
    """Merge canonical context patches returned by completed interrupts.

    The graph object survives an interrupt, so the profile captured when it was
    built can be stale after resume. Empty arrays are intentionally retained:
    they mean the user explicitly confirmed "none", not "unknown".
    """
    resolved = dict(base_context)
    for message in messages:
        if not isinstance(message, ToolMessage) or message.name != "request_profile_fields":
            continue
        try:
            payload = json.loads(message.content) if isinstance(message.content, str) else {}
        except json.JSONDecodeError:
            continue
        response = payload.get("response", {}) if isinstance(payload, dict) else {}
        patch = response.get("context_patch", {}) if isinstance(response, dict) else {}
        if isinstance(patch, dict):
            resolved.update(patch)
    return resolved


def _replace_unresolved_catalog_calls(
    calls: list[dict[str, Any]],
    runtime: ToolRuntime,
    messages: list[AnyMessage],
) -> list[dict[str, Any]]:
    """Force a canonical search when the model trusts a fake/unseen product ID."""
    if runtime.retrieved or any(call.get("name") == "search_product_catalog" for call in calls):
        return calls
    unresolved = any(
        call.get("name")
        in {
            "get_product_details",
            "assess_product_safety",
            "rank_product_fit",
            "compare_products",
        }
        and not call.get("args", {}).get("product_ids")
        for call in calls
    )
    if not unresolved:
        return calls
    query = next(
        (
            message.content
            for message in reversed(messages)
            if isinstance(message, HumanMessage)
            and isinstance(message.content, str)
            and not message.content.startswith(("FORMAT_REPAIR:", "CONTEXT_REPAIR:"))
        ),
        "",
    )
    if not query:
        return calls
    return [
        {
            "name": "search_product_catalog",
            "args": {"query": query, "limit": 10},
            "id": "grounding-search",
            "type": "tool_call",
        }
    ]


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


def _normalize_context_requests(
    calls: list[dict[str, Any]], known_context: dict[str, Any]
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for original in calls:
        call = {**original, "args": dict(original.get("args", {}))}
        if call.get("name") == "request_profile_fields":
            fields = canonical_profile_fields(call["args"].get("fields", []))
            call["args"]["fields"] = [
                field for field in fields if field not in known_context
            ]
        normalized.append(call)
    return normalized


def _sanitize_tool_calls(
    calls: list[dict[str, Any]],
    runtime: ToolRuntime,
    allowed_arguments: dict[str, set[str]],
) -> list[dict[str, Any]]:
    catalog_tools = {
        "get_product_details",
        "assess_product_safety",
        "rank_product_fit",
        "compare_products",
    }
    sanitized: list[dict[str, Any]] = []
    for original in calls:
        name = str(original.get("name", ""))
        allowed = allowed_arguments.get(name, set())
        args = {
            key: value
            for key, value in dict(original.get("args", {})).items()
            if key in allowed
        }
        if name in catalog_tools and isinstance(args.get("product_ids"), list):
            args["product_ids"] = [
                str(product_id)
                for product_id in args["product_ids"]
                if str(product_id) in runtime.retrieved
            ]
            if isinstance(args.get("semantic_scores"), dict):
                allowed_ids = set(args["product_ids"])
                args["semantic_scores"] = {
                    str(product_id): score
                    for product_id, score in args["semantic_scores"].items()
                    if str(product_id) in allowed_ids
                }
        sanitized.append({**original, "args": args})
    return sanitized


def _tool_call_signature(call: dict[str, Any]) -> str:
    args = call.get("args", {})
    if call.get("name") == "request_profile_fields":
        args = {"fields": sorted(canonical_profile_fields(args.get("fields", [])))}
    return json.dumps(
        {"name": call.get("name"), "args": args},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    rounds: int
    repair_count: int
    tool_call_count: int
    tool_call_signatures: list[str]
    context_repair: bool
    context_revision_applied: bool
    final_response: dict[str, Any]


def _fallback(reason: str, dataset_fingerprint: str = "") -> dict[str, Any]:
    return {
        "status": "safe_fallback",
        "final_judgment": "Chưa thể hoàn tất tư vấn có căn cứ trong giới hạn của phiên này.",
        "recommendations": [],
        "limitations": [reason],
        "follow_up_question": None,
        "professional_review_required": True,
        "disclaimer": DISCLAIMER,
        "dataset_fingerprint": dataset_fingerprint,
    }


def build_graph(*, model: Any, runtime: ToolRuntime, checkpointer: Any | None = None):
    tools = build_tools(runtime)
    allowed_arguments = {
        tool.name: set(tool.args_schema.model_fields)
        for tool in tools
        if tool.args_schema is not None
    }
    bound_model = model.bind_tools(tools)
    known_context = {
        key: value
        for key, value in asdict(runtime.profile).items()
        if value is not None
    }
    def fallback(reason: str) -> dict[str, Any]:
        return _fallback(reason, runtime.catalog.dataset_fingerprint)

    def prepare_context(state: AgentState) -> dict[str, Any]:
        runtime.context_requests_allowed = not _is_factual_catalog_lookup(
            state.get("messages", [])
        )
        runtime.exact_lookup_required = _is_explicit_product_lookup(
            state.get("messages", [])
        )
        runtime.exact_lookup_match_found = None
        return {
            "rounds": 0,
            "repair_count": 0,
            "tool_call_count": 0,
            "tool_call_signatures": [],
            "context_repair": False,
            "context_revision_applied": False,
            "final_response": None,
        }

    async def agent_node(state: AgentState) -> dict[str, Any]:
        _hydrate_catalog_state(runtime, state.get("messages", []))
        resolved_context = _resolved_profile_context(
            known_context, state.get("messages", [])
        )
        rounds = int(state.get("rounds", 0))
        if rounds >= int(MANIFEST["max_rounds"]):
            return {"final_response": fallback("Đã đạt giới hạn 6 vòng ReAct.")}
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            SystemMessage(
                content=(
                    "CANONICAL_CONTEXT_JSON: "
                    f"{json.dumps(resolved_context, ensure_ascii=False, sort_keys=True)}\n"
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
        calls = _sanitize_tool_calls(calls, runtime, allowed_arguments)
        calls = _replace_unresolved_catalog_calls(
            calls, runtime, state.get("messages", [])
        )
        calls = _grounding_prerequisite_calls(calls, runtime)
        calls = _normalize_context_requests(calls, resolved_context)
        if calls != raw_calls:
            response = response.model_copy(update={"tool_calls": calls})
        total_calls = int(state.get("tool_call_count", 0)) + len(calls)
        if total_calls > int(MANIFEST["max_tool_calls"]):
            return {"final_response": fallback("Đã đạt giới hạn 12 tool call.")}
        resumed_profile_context = _has_resumed_profile_context(
            state.get("messages", [])
        )
        context_revision_pending = (
            resumed_profile_context
            and not bool(state.get("context_revision_applied", False))
        )
        previous_signatures = set(state.get("tool_call_signatures", []))
        if context_revision_pending:
            # Context-sensitive safety/ranking calls may legitimately repeat
            # once after resume. Keep only profile-request signatures so the
            # same missing fields can never interrupt twice.
            previous_signatures = {
                signature
                for signature in previous_signatures
                if '"name": "request_profile_fields"' in signature
            }
        signatures = [_tool_call_signature(call) for call in calls]
        if any(signature in previous_signatures for signature in signatures):
            repeated_known_context = bool(calls) and all(
                call.get("name") == "request_profile_fields"
                and not call.get("args", {}).get("fields")
                for call in calls
            )
            repairs = int(state.get("repair_count", 0))
            if (
                repeated_known_context or resumed_profile_context
            ) and repairs < int(MANIFEST["repair_attempts"]):
                return {
                    "messages": [
                        HumanMessage(
                            content=(
                                "CONTEXT_REPAIR: Ngữ cảnh vừa được cập nhật. Không lặp "
                                "lại tool call đã hoàn tất; hãy dùng kết quả tool trong "
                                "messages để tiếp tục và kết thúc bằng submit_consultation."
                            )
                        )
                    ],
                    "repair_count": repairs + 1,
                    "context_repair": True,
                    "context_revision_applied": True,
                }
            return {
                "final_response": fallback(
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
            "context_repair": False,
            "context_revision_applied": (
                bool(state.get("context_revision_applied", False))
                or context_revision_pending
            ),
        }

    def route_agent(state: AgentState) -> str:
        if state.get("final_response") is not None:
            return "end"
        if state.get("context_repair"):
            return "agent"
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
                "final_response": fallback(
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
            return {"final_response": fallback("Terminal response phải có đúng một submit call.")}
        call = submit_calls[0]
        try:
            response = runtime.submit_consultation(**call["args"])
        except (GroundingError, KeyError, TypeError, ValueError) as exc:
            repairs = int(state.get("repair_count", 0))
            if repairs >= int(MANIFEST["repair_attempts"]):
                return {"final_response": fallback(str(exc))}
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
        {
            "agent": "agent",
            "tools": "tools",
            "repair": "repair",
            "finalize": "finalize",
            "end": END,
        },
    )
    builder.add_edge("tools", "agent")
    builder.add_conditional_edges("repair", route_repair, {"agent": "agent", "end": END})
    builder.add_conditional_edges("finalize", route_finalize, {"agent": "agent", "end": END})
    return builder.compile(checkpointer=checkpointer)
