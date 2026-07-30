from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Mapping

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from app.agent.shared.advisory import HybridRetriever, Profile
from app.agent.shared.catalog import Catalog
from app.agent.shared.persistence import Database
from app.agent.shared.providers import ProviderConfigurationError, ProviderFactory
from app.agent.shared.tools_runtime import ToolRuntime
from app.agent.shared.vector_store import ChromaProductIndex
from app.agent.version_1.graph import build_graph
from app.config import Settings


@dataclass
class RunContext:
    runtime: ToolRuntime
    model: Any
    thread_id: str


class AgentRunner:
    """Runs LangGraph in background tasks while persisting only public trace data."""

    def __init__(self, database: Database, catalog: Catalog, settings: Settings) -> None:
        self.database = database
        self.catalog = catalog
        self.settings = settings
        self.providers = ProviderFactory(settings)
        self._tasks: set[asyncio.Task[None]] = set()
        self._contexts: dict[str, RunContext] = {}

    async def start(self, run_id: str) -> None:
        task = asyncio.create_task(self._execute(run_id, resume_value=None))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        await asyncio.sleep(0)

    async def resume(self, run_id: str, response: dict[str, Any]) -> None:
        # Profile patches are applied by the API before resume; rebuild the
        # runtime so safety/scoring use the updated canonical profile.
        self._contexts.pop(run_id, None)
        task = asyncio.create_task(self._execute(run_id, resume_value=response))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        await asyncio.sleep(0)

    async def _make_context(self, run_id: str) -> RunContext:
        run = await self.database.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        session = await self.database.get_session(run.session_id)
        if session is None:
            raise KeyError(run.session_id)
        profile = _profile_from_context(session.context)
        provider = session.provider
        if provider not in {"openai", "gemini"}:
            raise ProviderConfigurationError(f"Provider không được hỗ trợ: {provider}")

        embeddings = self.providers.embeddings(provider)  # type: ignore[arg-type]
        vector_index = ChromaProductIndex(
            self.catalog,
            persist_directory=self.settings.resolved_path(
                self.settings.chroma_persist_directory
            ),
            embeddings=embeddings,
            embedding_provider=provider,
            embedding_model=session.embedding_model,
        )
        indexed = await asyncio.to_thread(vector_index.ensure_index)
        await self.database.append_trace(
            run_id,
            "retrieval.index.ready",
            {
                "collection": vector_index.collection_name,
                "product_count": indexed,
                "dataset_fingerprint": self.catalog.dataset_fingerprint,
            },
        )
        runtime = ToolRuntime(
            self.catalog,
            HybridRetriever(self.catalog, vector_index),
            profile,
        )
        return RunContext(
            runtime=runtime,
            model=self.providers.chat_model(provider),  # type: ignore[arg-type]
            thread_id=session.id,
        )

    async def _trace_update(
        self, run_id: str, node: str, update: Any, latency_ms: float
    ) -> None:
        node_payload: dict[str, Any] = {
            "node": node,
            "latency_ms": round(latency_ms, 1),
        }
        if isinstance(update, dict) and isinstance(update.get("rounds"), int):
            node_payload["rounds"] = update["rounds"]
        await self.database.append_trace(
            run_id,
            "node.completed",
            node_payload,
        )
        if not isinstance(update, dict):
            return
        messages = update.get("messages", [])
        if not isinstance(messages, list):
            messages = [messages]
        for message in messages:
            if isinstance(message, AIMessage) and message.tool_calls:
                await self.database.append_trace(
                    run_id,
                    "public.decision",
                    {
                        "summary": "Agent chọn công cụ tiếp theo dựa trên dữ liệu đã có.",
                        "tools": [call.get("name") for call in message.tool_calls],
                        "token_usage": getattr(message, "usage_metadata", None) or {},
                    },
                )
                for call in message.tool_calls:
                    await self.database.append_trace(
                        run_id,
                        "tool.requested",
                        {
                            "tool": call.get("name"),
                            "input": call.get("args", {}),
                        },
                    )
            elif isinstance(message, ToolMessage):
                payload = _parse_tool_output(message.content)
                await self.database.append_trace(
                    run_id,
                    "tool.completed",
                    {"tool": message.name, "output": payload},
                )
                special_type = {
                    "search_product_catalog": "retrieval.candidates",
                    "rank_product_fit": "ranking.completed",
                    "assess_product_safety": "safety.completed",
                }.get(message.name or "")
                if special_type:
                    await self.database.append_trace(run_id, special_type, payload)

    async def _execute(
        self, run_id: str, resume_value: dict[str, Any] | None
    ) -> None:
        try:
            run = await self.database.get_run(run_id)
            if run is None:
                return
            await self.database.update_run(run_id, status="running")
            await self.database.append_trace(
                run_id,
                "run.started" if resume_value is None else "run.resumed",
                {"version": "version_1"},
            )
            context = self._contexts.get(run_id)
            if context is None:
                context = await self._make_context(run_id)
                self._contexts[run_id] = context

            checkpoint_path = self.settings.resolved_path(
                self.settings.checkpoint_database_path
            )
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            async with AsyncSqliteSaver.from_conn_string(
                checkpoint_path.as_posix()
            ) as saver:
                await saver.setup()
                graph = build_graph(
                    model=context.model,
                    runtime=context.runtime,
                    checkpointer=saver,
                )
                graph_input: Any = (
                    {"messages": [HumanMessage(content=run.query)]}
                    if resume_value is None
                    else Command(resume=resume_value)
                )
                config = {
                    "configurable": {"thread_id": context.thread_id},
                    "recursion_limit": 30,
                }
                final_response: dict[str, Any] | None = None
                interrupted: Any = None
                node_started = time.perf_counter()
                async for event in graph.astream(
                    graph_input, config=config, stream_mode="updates"
                ):
                    for node, update in event.items():
                        if node == "__interrupt__":
                            interrupted = update
                            continue
                        now = time.perf_counter()
                        await self._trace_update(
                            run_id,
                            node,
                            update,
                            latency_ms=(now - node_started) * 1000,
                        )
                        node_started = now
                        if isinstance(update, dict) and update.get("final_response"):
                            final_response = update["final_response"]

                if interrupted is not None:
                    payload = _interrupt_payload(interrupted)
                    await self.database.append_trace(
                        run_id, "profile.required", payload
                    )
                    await self.database.update_run(run_id, status="interrupted")
                    return
                if final_response is None:
                    raise RuntimeError("Graph kết thúc mà không có final_response.")
                await self.database.append_trace(
                    run_id, "answer.completed", final_response
                )
                await self.database.update_run(
                    run_id, status="completed", answer=final_response
                )
                self._contexts.pop(run_id, None)
        except ProviderConfigurationError as exc:
            await self._fail(run_id, "provider_not_configured", str(exc))
        except asyncio.TimeoutError:
            await self._fail(run_id, "timeout", "Agent vượt quá thời gian cho phép.")
        except Exception:  # boundary: never persist prompts, provider bodies, or secrets
            await self._fail(
                run_id,
                "agent_execution_failed",
                "Agent không thể hoàn tất run. Kiểm tra cấu hình provider và thử lại.",
            )

    async def _fail(self, run_id: str, code: str, message: str) -> None:
        await self.database.append_trace(
            run_id, "run.failed", {"code": code, "message": message[:500]}
        )
        await self.database.update_run(run_id, status="failed", error_code=code)
        self._contexts.pop(run_id, None)


def _parse_tool_output(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else {"result": parsed}
        except json.JSONDecodeError:
            return {"summary": content[:1000]}
    return {"summary": str(content)[:1000]}


def _profile_from_context(context: Mapping[str, Any]) -> Profile:
    def tuple_value(name: str) -> tuple[str, ...] | None:
        if name not in context:
            return None
        value = context[name]
        return tuple(value or ())

    return Profile(
        age_group=context.get("age_group"),
        goals=tuple_value("goals"),
        conditions=tuple_value("conditions"),
        medications=tuple_value("medications"),
        allergies=tuple_value("allergies"),
        pregnancy_status=context.get("pregnancy_status"),
        budget_max_vnd=context.get("budget_max_vnd"),
        preferred_dosage_forms=tuple_value("preferred_dosage_forms"),
    )


def _interrupt_payload(value: Any) -> dict[str, Any]:
    item = value[0] if isinstance(value, (list, tuple)) and value else value
    payload = getattr(item, "value", item)
    return payload if isinstance(payload, dict) else {"request": str(payload)}
