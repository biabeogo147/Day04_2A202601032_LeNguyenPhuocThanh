from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping, Sequence

from .advisory import (
    FitScore,
    HybridRetriever,
    Profile,
    SafetyAssessment,
    assess_product_safety,
    compare_products,
    rank_product_fit,
)
from .catalog import Catalog, Product, fold_text


DISCLAIMER = (
    "Thực phẩm chức năng không phải là thuốc và không có tác dụng thay thế thuốc chữa bệnh. "
    "Thông tin chỉ dựa trên dataset; hãy hỏi bác sĩ hoặc dược sĩ khi có bệnh nền, đang dùng "
    "thuốc, mang thai, cho con bú hoặc có phản ứng bất thường."
)


class GroundingError(ValueError):
    pass


def _product_payload(product: Product, focus_nutrients: Sequence[str] = ()) -> dict[str, Any]:
    requested = {fold_text(item) for item in focus_nutrients if item.strip()}
    nutrients = [
        asdict(item)
        for item in product.nutrients
        if not requested or fold_text(item.name) in requested
    ]
    return {
        "product_id": product.id,
        "name": product.name,
        "price_vnd": product.price_vnd,
        "usage": product.usage,
        "contraindications": product.contraindications,
        "daily_dosage": product.dosage,
        "function": product.function,
        "packaging": product.packaging,
        "audience": product.audience,
        "dosage_form": product.dosage_form,
        "nutrients": nutrients,
        "special_ingredients": product.special_ingredients,
        "cost_per_day_vnd": product.cost_per_day_vnd,
        "source_row": product.source_row,
    }


class ToolRuntime:
    def __init__(self, catalog: Catalog, retriever: HybridRetriever, profile: Profile) -> None:
        self.catalog = catalog
        self.retriever = retriever
        self.profile = profile
        self.retrieved: dict[str, float] = {}
        self.details: set[str] = set()
        self.safety: dict[str, SafetyAssessment] = {}
        self.ranking: dict[str, FitScore] = {}
        self.context_requests_allowed = True
        self.exact_lookup_required = False
        self.exact_lookup_match_found: bool | None = None

    def request_profile_fields(self, fields: Sequence[str], question: str) -> dict[str, Any]:
        return {
            "awaiting_user": True,
            "fields": list(fields),
            "question": question.strip(),
        }

    def search_product_catalog(
        self,
        query: str,
        *,
        limit: int = 10,
        max_price_vnd: int | None = None,
        dosage_forms: Sequence[str] = (),
    ) -> dict[str, Any]:
        allowed_forms = {fold_text(item) for item in dosage_forms if item.strip()}
        candidates = []
        exact_name_match_found = False
        for result in self.retriever.search(query, limit=max(limit * 2, limit)):
            product = result.product
            if max_price_vnd is not None and product.price_vnd > max_price_vnd:
                continue
            if allowed_forms and fold_text(product.dosage_form) not in allowed_forms:
                continue
            self.retrieved[product.id] = result.similarity
            if result.match_type == "exact" or (
                result.match_type == "lexical" and result.similarity >= 0.9
            ):
                exact_name_match_found = True
            candidates.append(
                {
                    "product_id": product.id,
                    "name": product.name,
                    "similarity": result.similarity,
                    "match_type": result.match_type,
                    "price_vnd": product.price_vnd,
                    "dosage_form": product.dosage_form,
                    "source_row": product.source_row,
                }
            )
            if len(candidates) >= limit:
                break
        if self.exact_lookup_required:
            self.exact_lookup_match_found = bool(
                self.exact_lookup_match_found or exact_name_match_found
            )
        return {
            "query": query,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "dataset_fingerprint": self.catalog.dataset_fingerprint,
        }

    def get_product_details(
        self,
        product_ids: Sequence[str],
        *,
        focus_nutrients: Sequence[str] = (),
    ) -> dict[str, Any]:
        products = []
        for product_id in dict.fromkeys(product_ids):
            product = self.catalog.get(product_id)
            self.details.add(product_id)
            products.append(_product_payload(product, focus_nutrients))
        return {"products": products}

    def assess_product_safety(self, product_ids: Sequence[str]) -> dict[str, Any]:
        results = []
        for product_id in dict.fromkeys(product_ids):
            assessment = assess_product_safety(self.catalog.get(product_id), self.profile)
            self.safety[product_id] = assessment
            results.append({"product_id": product_id, **asdict(assessment)})
        return {"assessments": results}

    def rank_product_fit(
        self,
        product_ids: Sequence[str],
        *,
        semantic_scores: Mapping[str, float] | None = None,
        requested_nutrients: Sequence[str] = (),
    ) -> dict[str, Any]:
        rankings = []
        for product_id in dict.fromkeys(product_ids):
            if product_id not in self.safety:
                self.safety[product_id] = assess_product_safety(
                    self.catalog.get(product_id), self.profile
                )
            similarity = (
                float(semantic_scores.get(product_id, 0.0))
                if semantic_scores is not None
                else self.retrieved.get(product_id, 0.0)
            )
            score = rank_product_fit(
                self.catalog.get(product_id),
                self.profile,
                semantic_similarity=similarity,
                requested_nutrients=requested_nutrients,
            )
            self.ranking[product_id] = score
            rankings.append(
                {
                    "product_id": product_id,
                    "name": self.catalog.get(product_id).name,
                    "fit_score": score.total,
                    "breakdown": score.breakdown,
                    "safety": asdict(score.safety),
                }
            )
        rankings.sort(key=lambda item: (-float(item["fit_score"]), str(item["name"])))
        return {"rankings": rankings}

    def compare_products(
        self,
        product_ids: Sequence[str],
        *,
        focus_nutrients: Sequence[str] = (),
    ) -> dict[str, Any]:
        products = [self.catalog.get(product_id) for product_id in dict.fromkeys(product_ids)]
        return compare_products(products, focus_nutrients=focus_nutrients)

    def submit_consultation(
        self,
        *,
        status: str,
        selected_product_ids: Sequence[str],
        final_judgment: str,
        rationale_by_product: Mapping[str, Sequence[str] | str],
        limitations: Sequence[str],
        follow_up_question: str | None = None,
    ) -> dict[str, Any]:
        status = {
            "no_product_found": "no_match",
            "not_found": "no_match",
        }.get(status.strip().casefold(), status.strip())
        selected = list(dict.fromkeys(selected_product_ids))
        exact_lookup_missed = (
            self.exact_lookup_required and self.exact_lookup_match_found is False
        )
        if exact_lookup_missed:
            status = "no_match"
            selected = []
            final_judgment = "Không tìm thấy sản phẩm được yêu cầu trong dataset hiện có."
            limitations = [
                *limitations,
                "Không dùng các semantic candidate gần nghĩa để thay thế một tên sản phẩm không tồn tại.",
            ]
        selection_truncated = len(selected) > 3
        conflicted: list[str] = []
        for product_id in selected:
            if product_id not in self.retrieved:
                raise GroundingError(f"Sản phẩm {product_id} chưa được retrieve.")
            if product_id not in self.safety:
                raise GroundingError(f"Sản phẩm {product_id} chưa được safety-check.")
            if product_id not in self.ranking:
                raise GroundingError(f"Sản phẩm {product_id} chưa được rank.")
            if self.safety[product_id].exclude:
                conflicted.append(product_id)
        selected = [product_id for product_id in selected if product_id not in conflicted]
        grounded_limitations = list(limitations)
        if selection_truncated:
            selected = selected[:3]
            grounded_limitations.append(
                "Chỉ hiển thị tối đa 3 sản phẩm theo thứ tự lựa chọn đã được rank."
            )
        for product_id in conflicted:
            product = self.catalog.get(product_id)
            grounded_limitations.append(
                f"Đã loại {product.name} vì {self.safety[product_id].evidence}"
            )
        if status == "answered" and not selected:
            if conflicted:
                status = "not_recommended"
            else:
                raise GroundingError("Câu trả lời tư vấn phải có ít nhất một sản phẩm đã kiểm chứng.")
        if not final_judgment.strip():
            raise GroundingError("Thiếu nhận định cuối cùng.")

        recommendations = []
        professional_review_required = any(
            assessment.professional_review_required
            for assessment in self.safety.values()
        )
        for product_id in selected:
            product = self.catalog.get(product_id)
            assessment = self.safety[product_id]
            professional_review_required |= assessment.professional_review_required
            raw_reasons = rationale_by_product.get(product_id, ())
            reasons = [raw_reasons] if isinstance(raw_reasons, str) else list(raw_reasons)
            recommendations.append(
                {
                    **_product_payload(product),
                    "fit_score": self.ranking[product_id].total,
                    "score_breakdown": self.ranking[product_id].breakdown,
                    "safety": asdict(assessment),
                    "reasons": reasons,
                }
            )
        return {
            "status": status,
            "final_judgment": final_judgment.strip(),
            "recommendations": recommendations,
            "limitations": grounded_limitations,
            "follow_up_question": follow_up_question,
            "professional_review_required": professional_review_required,
            "disclaimer": DISCLAIMER,
            "dataset_fingerprint": self.catalog.dataset_fingerprint,
        }
