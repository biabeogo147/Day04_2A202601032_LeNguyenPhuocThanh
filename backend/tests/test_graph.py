from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent.shared.advisory import HybridRetriever, Profile
from app.agent.shared.catalog import Catalog
from app.agent.shared.tools_runtime import ToolRuntime
from app.agent.version_1.graph import _merge_batch_tool_calls, build_graph
from app.services import _profile_from_context


DATASET = Path(__file__).parents[2] / "shared_data" / "DataTPCN.csv"


class ScriptedModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.bound_tool_names = []
        self.invocations = []

    def bind_tools(self, tools):
        self.bound_tool_names = [tool.name for tool in tools]
        return self

    async def ainvoke(self, messages):
        self.invocations.append(messages)
        return next(self.responses)


def call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


def test_same_batch_tool_calls_are_merged_before_guardrail_counting():
    merged = _merge_batch_tool_calls(
        [
            {"name": "get_product_details", "args": {"product_ids": ["p1"]}, "id": "c1"},
            {"name": "get_product_details", "args": {"product_ids": ["p2"]}, "id": "c2"},
            {"name": "get_product_details", "args": {"product_ids": ["p1", "p3"]}, "id": "c3"},
        ]
    )

    assert len(merged) == 1
    assert merged[0]["id"] == "c1"
    assert merged[0]["args"]["product_ids"] == ["p1", "p2", "p3"]


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
    assert isinstance(result["messages"][-1], ToolMessage)
    assert result["messages"][-1].name == "submit_consultation"


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


async def test_graph_supplies_canonical_profile_context_to_model():
    catalog = Catalog.from_csv(DATASET)
    runtime = ToolRuntime(
        catalog,
        HybridRetriever(catalog),
        Profile(
            "adult",
            ("tim mạch",),
            (),
            (),
            (),
            "not_applicable",
            500_000,
            ("Viên nang mềm",),
        ),
    )
    model = ScriptedModel(
        [
            AIMessage(content="Không có terminal tool."),
            AIMessage(content="Vẫn không có terminal tool."),
        ]
    )

    await build_graph(model=model, runtime=runtime).ainvoke(
        {"messages": [HumanMessage(content="Tư vấn Omega-3")]}
    )

    system_contents = [
        message.content
        for message in model.invocations[0]
        if message.type == "system"
    ]
    assert any("CANONICAL_CONTEXT_JSON" in content for content in system_contents)
    assert any('"age_group": "adult"' in content for content in system_contents)
    assert any('"goals": ["tim mạch"]' in content for content in system_contents)


def test_session_context_preserves_unknown_vs_explicit_empty_fields():
    profile = _profile_from_context(
        {
            "goals": ["tim mạch"],
            "conditions": [],
            "budget_max_vnd": 450_000,
        }
    )

    assert profile.goals == ("tim mạch",)
    assert profile.conditions == ()
    assert profile.medications is None
    assert profile.age_group is None
    assert profile.budget_max_vnd == 450_000


async def test_prepare_context_resets_transient_state_from_previous_run():
    catalog = Catalog.from_csv(DATASET)
    runtime = ToolRuntime(
        catalog,
        HybridRetriever(catalog),
        Profile("adult", ("tim mạch",), (), (), (), "not_applicable", 500_000, ()),
    )
    model = ScriptedModel(
        [
            AIMessage(content="Không có terminal tool."),
            AIMessage(content="Vẫn không có terminal tool."),
        ]
    )

    result = await build_graph(model=model, runtime=runtime).ainvoke(
        {
            "messages": [HumanMessage(content="Lượt hội thoại mới")],
            "rounds": 6,
            "repair_count": 1,
            "tool_call_count": 12,
            "tool_call_signatures": ["stale"],
            "final_response": {"status": "stale"},
        }
    )

    assert len(model.invocations) == 2
    assert result["rounds"] == 2
    assert result["repair_count"] == 1
    assert result["tool_call_count"] == 0
    assert result["tool_call_signatures"] == []
    assert result["final_response"]["status"] == "safe_fallback"
    assert "submit_consultation" in result["final_response"]["limitations"][0]


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


async def test_factual_label_lookup_cannot_be_interrupted_for_profile_fields():
    catalog = Catalog.from_csv(DATASET)
    runtime = ToolRuntime(
        catalog,
        HybridRetriever(catalog),
        Profile(None, None, None, None, None, None, None, None),
    )
    product = catalog.products[0]
    model = ScriptedModel(
        [
            call(
                "request_profile_fields",
                {
                    "fields": ["age_group", "conditions"],
                    "question": "Bạn bao nhiêu tuổi?",
                },
                "c1",
            ),
            call("search_product_catalog", {"query": product.name, "limit": 1}, "c2"),
            call(
                "get_product_details",
                {"product_ids": [product.id], "focus_nutrients": []},
                "c3",
            ),
            call("assess_product_safety", {"product_ids": [product.id]}, "c4"),
            call(
                "rank_product_fit",
                {"product_ids": [product.id], "semantic_scores": {product.id: 1.0}},
                "c5",
            ),
            call(
                "submit_consultation",
                {
                    "status": "answered",
                    "selected_product_ids": [product.id],
                    "final_judgment": "Thông tin nhãn sản phẩm đã được tra cứu.",
                    "rationale_by_product": {product.id: ["Khớp tên sản phẩm"]},
                    "limitations": ["Chỉ mô tả dữ liệu trong catalog."],
                },
                "c6",
            ),
        ]
    )

    result = await build_graph(model=model, runtime=runtime).ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "Blackmores Fish Oil 1000mg có thành phần và liều dùng "
                        "thế nào?"
                    )
                )
            ]
        }
    )

    assert "__interrupt__" not in result
    assert result["final_response"]["status"] == "answered"
    assert result["rounds"] == 5
    skipped_request = next(
        message
        for message in result["messages"]
        if isinstance(message, ToolMessage) and message.tool_call_id == "c1"
    )
    assert "không cần hồ sơ" in skipped_request.content


async def test_graph_inserts_fresh_safety_and_ranking_before_stale_session_submit():
    catalog = Catalog.from_csv(DATASET)
    product = catalog.products[0]
    runtime = ToolRuntime(
        catalog,
        HybridRetriever(catalog),
        Profile("adult", ("tim mạch",), (), ("warfarin",), (), "not_applicable", 500_000, ()),
    )
    runtime.retrieved[product.id] = 1.0
    runtime.details.add(product.id)
    submit_args = {
        "status": "warning",
        "selected_product_ids": [product.id],
        "final_judgment": "Cần đánh giá lại theo ngữ cảnh mới.",
        "rationale_by_product": {product.id: ["Đã có trong phiên"]},
        "limitations": ["Cần hỏi bác sĩ hoặc dược sĩ."],
    }
    model = ScriptedModel(
        [
            call("submit_consultation", submit_args, "premature"),
            call("submit_consultation", submit_args, "terminal"),
        ]
    )

    result = await build_graph(model=model, runtime=runtime).ainvoke(
        {"messages": [HumanMessage(content="Tôi đang dùng warfarin")]}
    )

    assert result["final_response"]["status"] == "warning"
    assert product.id in runtime.safety
    assert product.id in runtime.ranking
    requested = [
        message.name
        for message in result["messages"]
        if isinstance(message, ToolMessage)
    ]
    assert "assess_product_safety" in requested
    assert "rank_product_fit" in requested


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
