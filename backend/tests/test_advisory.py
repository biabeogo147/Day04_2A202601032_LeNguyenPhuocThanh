from pathlib import Path

from app.agent.shared.advisory import (
    HybridRetriever,
    Profile,
    assess_product_safety,
    compare_products,
    rank_product_fit,
)
from app.agent.shared.catalog import Catalog


DATASET = Path(__file__).parents[2] / "data" / "DataTPCN.csv"


def catalog() -> Catalog:
    return Catalog.from_csv(DATASET)


def product_named(name: str):
    return next(item for item in catalog().products if item.name == name)


def adult_profile(**overrides) -> Profile:
    data = {
        "age_group": "adult",
        "goals": ("tim mạch",),
        "conditions": (),
        "medications": (),
        "allergies": (),
        "pregnancy_status": "not_applicable",
        "budget_max_vnd": 500_000,
        "preferred_dosage_forms": ("Viên nang mềm",),
    }
    data.update(overrides)
    return Profile(**data)


def test_exact_product_name_is_ranked_first_without_vector_backend():
    retriever = HybridRetriever(catalog())

    results = retriever.search("Blackmores Fish Oil 1000mg", limit=5)

    assert results[0].product.name == "Blackmores Fish Oil 1000mg"
    assert results[0].match_type == "exact"
    assert results[0].similarity == 1.0


def test_exact_name_retrieval_top_one_is_perfect_for_entire_catalog():
    product_catalog = catalog()
    retriever = HybridRetriever(product_catalog)

    correct = sum(
        retriever.search(product.name, limit=1)[0].product.id == product.id
        for product in product_catalog.products
    )

    assert correct == len(product_catalog.products) == 100


def test_vector_candidates_are_resolved_back_to_canonical_products():
    source = catalog()
    target = product_named("Blackmores Fish Oil 1000mg")

    class FakeVectorIndex:
        def search(self, query: str, limit: int):
            assert query == "hỗ trợ tim mạch"
            return [(target.id, 0.92)]

    results = HybridRetriever(source, FakeVectorIndex()).search("hỗ trợ tim mạch", limit=3)

    assert results[0].product is source.get(target.id)
    assert results[0].similarity == 0.92
    assert results[0].match_type == "semantic"


def test_fish_allergy_is_an_explicit_conflict_for_fish_oil():
    product = product_named("Blackmores Fish Oil 1000mg")

    result = assess_product_safety(
        product,
        adult_profile(allergies=("cá",)),
    )

    assert result.status == "explicit_conflict"
    assert result.exclude is True
    assert "dị ứng" in " ".join(result.matched_rules).casefold()


def test_warfarin_maps_to_anticoagulant_contraindication():
    product = next(
        item for item in catalog().products if "chảy máu" in item.contraindications.casefold()
    )

    result = assess_product_safety(
        product,
        adult_profile(medications=("warfarin",)),
    )

    assert result.status == "explicit_conflict"
    assert result.professional_review_required is True


def test_unknown_medication_evidence_requires_professional_review():
    product = product_named("Blackmores Fish Oil 1000mg")

    result = assess_product_safety(
        product,
        adult_profile(medications=("metformin",)),
    )

    assert result.status == "insufficient_evidence"
    assert result.exclude is False
    assert result.professional_review_required is True


def test_fit_score_has_explainable_weighted_breakdown():
    product = product_named("Blackmores Fish Oil 1000mg")

    result = rank_product_fit(
        product,
        adult_profile(),
        semantic_similarity=0.9,
        requested_nutrients=("Omega-3",),
    )

    assert result.total == 96.5
    assert result.breakdown == {
        "semantic_goal": 31.5,
        "audience": 20.0,
        "nutrients": 20.0,
        "budget": 10.0,
        "dosage_form": 10.0,
        "data_completeness": 5.0,
    }
    assert result.safety.status == "no_dataset_conflict_found"


def test_comparison_focuses_on_requested_nutrients_and_keeps_provenance():
    first = product_named("Blackmores Fish Oil 1000mg")
    second = next(item for item in catalog().products if any(n.name == "Omega-3" for n in item.nutrients) and item.id != first.id)

    comparison = compare_products((first, second), focus_nutrients=("Omega-3",))

    assert comparison["products"][0]["source_row"] == first.source_row
    assert comparison["rows"][0]["label"] == "Omega-3"
    assert len(comparison["rows"]) == 1
    assert comparison["products"][0]["daily_dosage"] == first.dosage
