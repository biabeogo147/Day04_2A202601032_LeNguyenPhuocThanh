from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent.shared.advisory import HybridRetriever, Profile
from app.agent.shared.catalog import Catalog
from app.agent.shared.tools_runtime import ToolRuntime
from app.agent.version_1.graph import build_graph


DATASET = Path(__file__).parents[2] / "shared_data" / "DataTPCN.csv"


class ScriptedModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.bound_tool_names = []

    def bind_tools(self, tools):
        self.bound_tool_names = [tool.name for tool in tools]
        return self

    async def ainvoke(self, messages):
        return next(self.responses)


def call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


async def test_free_form_react_graph_executes_tools_and_returns_grounded_answer():
    catalog = Catalog.from_csv(DATASET)
    product = catalog.products[0]
    runtime = ToolRuntime(
        catalog,
        HybridRetriever(catalog),
        Profile(
            age_group="adult",
            goals=("tim mạch",),
            conditions=(),
            medications=(),
            allergies=(),
            pregnancy_status="not_applicable",
            budget_max_vnd=500_000,
            preferred_dosage_forms=("Viên nang mềm",),
        ),
    )
    model = ScriptedModel(
        [
            call("search_product_catalog", {"query": product.name, "limit": 3}, "c1"),
            call(
                "get_product_details",
                {"product_ids": [product.id], "focus_nutrients": ["Omega-3"]},
                "c2",
            ),
            call("assess_product_safety", {"product_ids": [product.id]}, "c3"),
            call(
                "rank_product_fit",
                {
                    "product_ids": [product.id],
                    "semantic_scores": {product.id: 1.0},
                    "requested_nutrients": ["Omega-3"],
                },
                "c4",
            ),
            call(
                "submit_consultation",
                {
                    "status": "answered",
                    "selected_product_ids": [product.id],
                    "final_judgment": "Phù hợp nhất trong dữ liệu hiện có.",
                    "rationale_by_product": {product.id: ["Khớp mục tiêu"]},
                    "limitations": ["Không có bằng chứng lâm sàng ngoài dataset."],
                },
                "c5",
            ),
        ]
    )

    graph = build_graph(model=model, runtime=runtime)
    result = await graph.ainvoke({"messages": [HumanMessage(content="Tư vấn Omega-3")]})

    assert {
        "search_product_catalog",
        "get_product_details",
        "assess_product_safety",
        "rank_product_fit",
        "compare_products",
        "request_profile_fields",
        "submit_consultation",
    } == set(model.bound_tool_names)
    assert result["final_response"]["recommendations"][0]["product_id"] == product.id
    assert result["rounds"] == 5


async def test_graph_stops_after_one_repair_when_model_never_submits():
    catalog = Catalog.from_csv(DATASET)
    runtime = ToolRuntime(
        catalog,
        HybridRetriever(catalog),
        Profile(
            age_group="adult",
            goals=("miễn dịch",),
            conditions=(),
            medications=(),
            allergies=(),
            pregnancy_status="not_applicable",
            budget_max_vnd=500_000,
            preferred_dosage_forms=("Viên nén",),
        ),
    )
    model = ScriptedModel(
        [
            AIMessage(content="Câu trả lời không có terminal tool."),
            AIMessage(content="Vẫn không gọi terminal tool."),
        ]
    )

    result = await build_graph(model=model, runtime=runtime).ainvoke(
        {"messages": [HumanMessage(content="Tư vấn miễn dịch")]}
    )

    assert result["final_response"]["status"] == "safe_fallback"
    assert result["repair_count"] == 1


async def test_graph_detects_repeated_identical_tool_call():
    catalog = Catalog.from_csv(DATASET)
    runtime = ToolRuntime(
        catalog,
        HybridRetriever(catalog),
        Profile("adult", ("tim mạch",), (), (), (), "not_applicable", 500_000, ()),
    )
    repeated = {"query": "Omega-3", "limit": 3}
    model = ScriptedModel(
        [
            call("search_product_catalog", repeated, "c1"),
            call("search_product_catalog", repeated, "c2"),
        ]
    )

    result = await build_graph(model=model, runtime=runtime).ainvoke(
        {"messages": [HumanMessage(content="Tìm Omega-3")]}
    )

    assert result["final_response"]["status"] == "safe_fallback"
    assert "lặp" in result["final_response"]["limitations"][0]


async def test_graph_writes_sqlite_checkpoint(tmp_path):
    catalog = Catalog.from_csv(DATASET)
    runtime = ToolRuntime(
        catalog,
        HybridRetriever(catalog),
        Profile("adult", ("miễn dịch",), (), (), (), "not_applicable", 500_000, ()),
    )
    model = ScriptedModel(
        [
            AIMessage(content="Không có terminal tool."),
            AIMessage(content="Vẫn không có terminal tool."),
        ]
    )
    checkpoint_path = tmp_path / "checkpoints.db"
    config = {"configurable": {"thread_id": "checkpoint-test"}}

    async with AsyncSqliteSaver.from_conn_string(checkpoint_path.as_posix()) as saver:
        await saver.setup()
        graph = build_graph(model=model, runtime=runtime, checkpointer=saver)
        await graph.ainvoke(
            {"messages": [HumanMessage(content="Tư vấn miễn dịch")]},
            config=config,
        )
        checkpoint = await saver.aget_tuple(config)

    assert checkpoint is not None
    assert checkpoint_path.exists()
