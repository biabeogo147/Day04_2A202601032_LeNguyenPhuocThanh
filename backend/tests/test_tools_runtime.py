from pathlib import Path

import pytest

from app.agent.shared.advisory import HybridRetriever, Profile
from app.agent.shared.catalog import Catalog
from app.agent.shared.tools_runtime import GroundingError, ToolRuntime


DATASET = Path(__file__).parents[2] / "shared_data" / "DataTPCN.csv"


def runtime() -> ToolRuntime:
    catalog = Catalog.from_csv(DATASET)
    return ToolRuntime(
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


def test_terminal_submission_rejects_products_without_required_evidence():
    tools = runtime()
    product_id = tools.catalog.products[0].id

    with pytest.raises(GroundingError, match="retrieve"):
        tools.submit_consultation(
            status="answered",
            selected_product_ids=[product_id],
            final_judgment="Phù hợp nhất trong dữ liệu.",
            rationale_by_product={product_id: ["Phù hợp mục tiêu"]},
            limitations=[],
        )


def test_tools_build_grounded_terminal_response_from_canonical_data():
    tools = runtime()
    search = tools.search_product_catalog("Blackmores Fish Oil 1000mg", limit=3)
    product_id = search["candidates"][0]["product_id"]
    tools.get_product_details([product_id], focus_nutrients=["Omega-3"])
    tools.assess_product_safety([product_id])
    tools.rank_product_fit(
        [product_id],
        semantic_scores={product_id: 1.0},
        requested_nutrients=["Omega-3"],
    )

    answer = tools.submit_consultation(
        status="answered",
        selected_product_ids=[product_id],
        final_judgment="Đây là lựa chọn phù hợp nhất trong dữ liệu hiện có.",
        rationale_by_product={product_id: ["Khớp mục tiêu tim mạch và Omega-3"]},
        limitations=["Dataset không có chứng nhận kiểm nghiệm."],
    )

    recommendation = answer["recommendations"][0]
    assert recommendation["name"] == "Blackmores Fish Oil 1000mg"
    assert recommendation["price_vnd"] == 450_000
    assert recommendation["source_row"] == 2
    assert recommendation["fit_score"] > 0
    assert "không phải là thuốc" in answer["disclaimer"].casefold()


def test_terminal_submission_rejects_explicit_safety_conflict():
    catalog = Catalog.from_csv(DATASET)
    tools = ToolRuntime(
        catalog,
        HybridRetriever(catalog),
        Profile(
            age_group="adult",
            goals=("tim mạch",),
            conditions=(),
            medications=(),
            allergies=("cá",),
            pregnancy_status="not_applicable",
            budget_max_vnd=500_000,
            preferred_dosage_forms=("Viên nang mềm",),
        ),
    )
    candidate = tools.search_product_catalog("Blackmores Fish Oil 1000mg", limit=1)["candidates"][0]
    product_id = candidate["product_id"]
    tools.assess_product_safety([product_id])
    tools.rank_product_fit([product_id], semantic_scores={product_id: 1.0})

    with pytest.raises(GroundingError, match="xung đột"):
        tools.submit_consultation(
            status="answered",
            selected_product_ids=[product_id],
            final_judgment="Không hợp lệ.",
            rationale_by_product={product_id: []},
            limitations=[],
        )
