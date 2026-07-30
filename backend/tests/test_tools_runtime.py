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


def test_terminal_submission_keeps_string_rationale_as_one_reason():
    tools = runtime()
    candidate = tools.search_product_catalog("Blackmores Fish Oil 1000mg", limit=1)["candidates"][0]
    product_id = candidate["product_id"]
    tools.get_product_details([product_id])
    tools.assess_product_safety([product_id])
    tools.rank_product_fit([product_id])

    answer = tools.submit_consultation(
        status="answered",
        selected_product_ids=[product_id],
        final_judgment="Thông tin dựa trên nhãn trong dataset.",
        rationale_by_product={product_id: "Có Omega-3 1000mg và liều 2 viên/ngày."},
        limitations=[],
    )

    assert answer["recommendations"][0]["reasons"] == [
        "Có Omega-3 1000mg và liều 2 viên/ngày."
    ]


def test_terminal_warning_requires_professional_review_when_safety_evidence_is_insufficient():
    tools = runtime()
    tools.profile = Profile(
        age_group=None,
        goals=None,
        conditions=None,
        medications=("warfarin",),
        allergies=None,
        pregnancy_status=None,
        budget_max_vnd=None,
        preferred_dosage_forms=None,
    )
    candidate = tools.search_product_catalog("Omega-3", limit=1)["candidates"][0]
    product_id = candidate["product_id"]
    tools.assess_product_safety([product_id])
    tools.rank_product_fit([product_id])

    answer = tools.submit_consultation(
        status="warning",
        selected_product_ids=[],
        final_judgment="Chưa đủ bằng chứng để chọn sản phẩm.",
        rationale_by_product={},
        limitations=["Cần hỏi bác sĩ hoặc dược sĩ."],
    )

    assert answer["professional_review_required"] is True


def test_terminal_submission_excludes_explicit_safety_conflict_without_fallback():
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

    answer = tools.submit_consultation(
        status="answered",
        selected_product_ids=[product_id],
        final_judgment="Không phù hợp vì có xung đột an toàn rõ ràng.",
        rationale_by_product={product_id: []},
        limitations=[],
    )

    assert answer["status"] == "not_recommended"
    assert answer["recommendations"] == []
    assert "Blackmores Fish Oil 1000mg" in answer["limitations"][0]
    assert answer["dataset_fingerprint"] == catalog.dataset_fingerprint


def test_terminal_submission_caps_selection_to_three_ranked_products():
    tools = runtime()
    candidates = tools.search_product_catalog("vitamin", limit=4)["candidates"]
    product_ids = [candidate["product_id"] for candidate in candidates]
    tools.assess_product_safety(product_ids)
    tools.rank_product_fit(
        product_ids,
        semantic_scores={product_id: 1 - index / 10 for index, product_id in enumerate(product_ids)},
    )

    answer = tools.submit_consultation(
        status="answered",
        selected_product_ids=product_ids,
        final_judgment="Chọn tối đa ba sản phẩm phù hợp nhất.",
        rationale_by_product={product_id: ["Ứng viên đã rank"] for product_id in product_ids},
        limitations=[],
    )

    assert len(answer["recommendations"]) == 3
    assert [item["product_id"] for item in answer["recommendations"]] == product_ids[:3]


def test_terminal_submission_normalizes_no_product_status():
    tools = runtime()

    answer = tools.submit_consultation(
        status="no_product_found",
        selected_product_ids=[],
        final_judgment="Không tìm thấy sản phẩm phù hợp trong dataset.",
        rationale_by_product={},
        limitations=["Không có candidate thỏa ràng buộc."],
    )

    assert answer["status"] == "no_match"


def test_exact_lookup_without_name_match_cannot_recommend_semantic_alternatives():
    tools = runtime()
    candidate = tools.search_product_catalog(
        "SuperDragon Omega Quantum 9999mg", limit=1
    )["candidates"][0]
    product_id = candidate["product_id"]
    tools.assess_product_safety([product_id])
    tools.rank_product_fit([product_id])
    tools.exact_lookup_required = True
    tools.exact_lookup_match_found = False

    answer = tools.submit_consultation(
        status="answered",
        selected_product_ids=[product_id],
        final_judgment="Đề xuất một sản phẩm gần giống.",
        rationale_by_product={product_id: ["Semantic candidate"]},
        limitations=[],
    )

    assert answer["status"] == "no_match"
    assert answer["recommendations"] == []
    assert "không tìm thấy" in answer["final_judgment"].casefold()
