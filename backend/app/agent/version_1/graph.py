from __future__ import annotations

from pathlib import Path
import json
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.agent.shared.tools_runtime import DISCLAIMER, GroundingError, ToolRuntime

from .manifest import MANIFEST
from version_1.tools import build_tools


REPO_ROOT = Path(__file__).resolve().parents[4]
SYSTEM_PROMPT_PATH = REPO_ROOT / "version_1" / "artifacts" / "system_prompt.md"
SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


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

    async def agent_node(state: AgentState) -> dict[str, Any]:
        rounds = int(state.get("rounds", 0))
        if rounds >= int(MANIFEST["max_rounds"]):
            return {"final_response": _fallback("Đã đạt giới hạn 6 vòng ReAct.")}
        messages = [SystemMessage(content=SYSTEM_PROMPT), *state.get("messages", [])]
        response = await bound_model.ainvoke(messages)
        calls = getattr(response, "tool_calls", []) or []
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
        return {
            "messages": [response],
            "rounds": rounds + 1,
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
        return {"final_response": response}

    def route_finalize(state: AgentState) -> str:
        return "end" if state.get("final_response") is not None else "agent"

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("repair", repair_node)
    builder.add_node("finalize", finalize_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        route_agent,
        {"tools": "tools", "repair": "repair", "finalize": "finalize", "end": END},
    )
    builder.add_edge("tools", "agent")
    builder.add_conditional_edges("repair", route_repair, {"agent": "agent", "end": END})
    builder.add_conditional_edges("finalize", route_finalize, {"agent": "agent", "end": END})
    return builder.compile(checkpointer=checkpointer)
