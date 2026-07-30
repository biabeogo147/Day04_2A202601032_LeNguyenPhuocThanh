from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .catalog import Catalog, Product, fold_text


@dataclass(frozen=True)
class Profile:
    age_group: str | None
    goals: tuple[str, ...] | None
    conditions: tuple[str, ...] | None
    medications: tuple[str, ...] | None
    allergies: tuple[str, ...] | None
    pregnancy_status: str | None
    budget_max_vnd: int | None
    preferred_dosage_forms: tuple[str, ...] | None


@dataclass(frozen=True)
class SearchResult:
    product: Product
    similarity: float
    match_type: str


@dataclass(frozen=True)
class SafetyAssessment:
    status: str
    exclude: bool
    professional_review_required: bool
    matched_rules: tuple[str, ...]
    evidence: str


@dataclass(frozen=True)
class FitScore:
    total: float
    breakdown: dict[str, float]
    safety: SafetyAssessment


class VectorIndex(Protocol):
    def search(self, query: str, limit: int) -> Sequence[tuple[str, float]]: ...


class HybridRetriever:
    def __init__(self, catalog: Catalog, vector_index: VectorIndex | None = None) -> None:
        self.catalog = catalog
        self.vector_index = vector_index

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        if not query.strip():
            return []
        normalized_query = fold_text(query)
        query_terms = set(normalized_query.split())
        results: dict[str, SearchResult] = {}

        for product in self.catalog.products:
            normalized_name = fold_text(product.name)
            if normalized_query == normalized_name:
                results[product.id] = SearchResult(product, 1.0, "exact")
                continue
            if normalized_query in normalized_name or normalized_name in normalized_query:
                results[product.id] = SearchResult(product, 0.98, "lexical")
                continue
            document_terms = set(fold_text(product.embedding_text()).split())
            overlap = len(query_terms & document_terms) / max(len(query_terms), 1)
            if overlap:
                results[product.id] = SearchResult(product, round(min(overlap, 0.9), 4), "lexical")

        if self.vector_index:
            for product_id, similarity in self.vector_index.search(query, max(limit * 2, 10)):
                product = self.catalog.get(product_id)
                current = results.get(product_id)
                candidate = SearchResult(
                    product=product,
                    similarity=round(max(0.0, min(float(similarity), 1.0)), 4),
                    match_type="semantic",
                )
                if current is None or candidate.similarity > current.similarity:
                    results[product_id] = candidate

        return sorted(results.values(), key=lambda item: (-item.similarity, item.product.name))[:limit]


MEDICATION_SYNONYMS = {
    "warfarin": ("chong dong", "roi loan dong mau", "chay mau"),
    "thuoc chong dong": ("chong dong", "roi loan dong mau", "chay mau"),
}
ALLERGY_SYNONYMS = {
    "hai san": ("hai san", "ca", "tom", "cua"),
    "sua": ("sua", "lactose", "dam sua"),
}
PREGNANCY_TERMS = ("phu nu co thai", "phu nu mang thai", "thai ky")
AGE_TERMS = {
    "infant": ("tre so sinh", "tre duoi 6 thang", "tre duoi 2 tuoi"),
    "child": ("tre em", "tre duoi 12 tuoi"),
    "adolescent": ("tre em",),
}


def _contains_term(text: str, term: str) -> bool:
    value = f" {fold_text(text)} "
    needle = f" {fold_text(term)} "
    return needle in value


def assess_product_safety(product: Product, profile: Profile) -> SafetyAssessment:
    contraindications = fold_text(product.contraindications)
    matched: list[str] = []

    for allergy in profile.allergies or ():
        folded_allergy = fold_text(allergy)
        terms = ALLERGY_SYNONYMS.get(folded_allergy, (folded_allergy,))
        if (
            any(_contains_term(contraindications, term) for term in terms)
            and "di ung" in contraindications
        ):
            matched.append(f"Dị ứng: {allergy}")

    for condition in profile.conditions or ():
        if _contains_term(contraindications, condition):
            matched.append(f"Bệnh nền: {condition}")

    for medication in profile.medications or ():
        folded_medication = fold_text(medication)
        terms = MEDICATION_SYNONYMS.get(folded_medication, (folded_medication,))
        if any(_contains_term(contraindications, term) for term in terms):
            matched.append(f"Thuốc đang dùng: {medication}")

    if profile.pregnancy_status in {"pregnant", "breastfeeding"} and any(
        _contains_term(contraindications, term) for term in PREGNANCY_TERMS
    ):
        matched.append(f"Thai/cho con bú: {profile.pregnancy_status}")

    if any(_contains_term(contraindications, term) for term in AGE_TERMS.get(profile.age_group or "", ())):
        matched.append(f"Nhóm tuổi: {profile.age_group}")

    if matched:
        return SafetyAssessment(
            status="explicit_conflict",
            exclude=True,
            professional_review_required=True,
            matched_rules=tuple(matched),
            evidence=product.contraindications,
        )

    unknown_fields = [
        name
        for name in (
            "age_group",
            "conditions",
            "medications",
            "allergies",
            "pregnancy_status",
        )
        if getattr(profile, name) is None
    ]
    if unknown_fields:
        return SafetyAssessment(
            status="insufficient_evidence",
            exclude=False,
            professional_review_required=True,
            matched_rules=(),
            evidence=f"Thiếu thông tin hồ sơ: {', '.join(unknown_fields)}.",
        )

    limited_evidence = bool(
        profile.conditions
        or profile.medications
        or profile.pregnancy_status in {"pregnant", "breastfeeding"}
    )
    if limited_evidence:
        return SafetyAssessment(
            status="insufficient_evidence",
            exclude=False,
            professional_review_required=True,
            matched_rules=(),
            evidence=product.contraindications,
        )

    return SafetyAssessment(
        status="no_dataset_conflict_found",
        exclude=False,
        professional_review_required=False,
        matched_rules=(),
        evidence=product.contraindications,
    )


def _audience_match(product: Product, age_group: str) -> float:
    audience = fold_text(product.audience)
    expected = {
        "infant": ("tre so sinh", "tre em tu 6 thang"),
        "child": ("tre em", "tre em va nguoi lon", "moi lua tuoi"),
        "adolescent": ("tre em", "moi lua tuoi"),
        "adult": ("nguoi truong thanh", "nguoi lon", "moi lua tuoi"),
        "older_adult": ("nguoi cao tuoi", "nguoi lon tuoi", "nguoi tren 50"),
    }.get(age_group, ())
    return 1.0 if any(term in audience for term in expected) else 0.0


def rank_product_fit(
    product: Product,
    profile: Profile,
    *,
    semantic_similarity: float,
    requested_nutrients: Sequence[str] = (),
) -> FitScore:
    safety = assess_product_safety(product, profile)
    nutrient_names = {fold_text(item.name) for item in product.nutrients}
    requested = {fold_text(item) for item in requested_nutrients if item.strip()}
    nutrient_match = (
        len(nutrient_names & requested) / len(requested)
        if requested
        else 0.0
    )
    completeness_fields = (
        product.name,
        product.function,
        product.audience,
        product.dosage,
        product.packaging,
        product.contraindications,
    )
    completeness = sum(bool(item.strip()) for item in completeness_fields) / len(completeness_fields)

    weighted_scores: dict[str, float] = {
        "semantic_goal": round(max(0.0, min(semantic_similarity, 1.0)) * 35, 2),
        "data_completeness": round(completeness * 5, 2),
    }
    available_weight = 40.0
    if profile.age_group:
        weighted_scores["audience"] = round(_audience_match(product, profile.age_group) * 20, 2)
        available_weight += 20
    if requested:
        weighted_scores["nutrients"] = round(nutrient_match * 20, 2)
        available_weight += 20
    if profile.budget_max_vnd is not None:
        weighted_scores["budget"] = 10.0 if product.price_vnd <= profile.budget_max_vnd else 0.0
        available_weight += 10
    if profile.preferred_dosage_forms:
        preferred_forms = {fold_text(item) for item in profile.preferred_dosage_forms}
        weighted_scores["dosage_form"] = (
            10.0 if fold_text(product.dosage_form) in preferred_forms else 0.0
        )
        available_weight += 10

    breakdown = {
        name: weighted_scores[name]
        for name in (
            "semantic_goal",
            "audience",
            "nutrients",
            "budget",
            "dosage_form",
            "data_completeness",
        )
        if name in weighted_scores
    }
    total = (
        0.0
        if safety.exclude
        else round(sum(breakdown.values()) / available_weight * 100, 2)
    )
    return FitScore(total=total, breakdown=breakdown, safety=safety)


def _format_nutrient(product: Product, name: str) -> str:
    expected = fold_text(name)
    for nutrient in product.nutrients:
        if fold_text(nutrient.name) == expected:
            amount = f"{float(nutrient.amount):g}"
            return f"{amount} {nutrient.unit}".strip()
    return "Không có trong dữ liệu nhãn"


def compare_products(
    products: Sequence[Product],
    *,
    focus_nutrients: Sequence[str] = (),
) -> dict[str, object]:
    product_items = []
    for product in products:
        cost = product.cost_per_day_vnd
        product_items.append(
            {
                "product_id": product.id,
                "name": product.name,
                "price_vnd": product.price_vnd,
                "daily_dosage": product.dosage,
                "usage": product.usage,
                "dosage_form": product.dosage_form,
                "cost_per_day_vnd": cost,
                "source_row": product.source_row,
            }
        )
    rows = [
        {
            "label": nutrient,
            "values": {
                product.id: _format_nutrient(product, nutrient)
                for product in products
            },
        }
        for nutrient in focus_nutrients
    ]
    return {"products": product_items, "rows": rows}
