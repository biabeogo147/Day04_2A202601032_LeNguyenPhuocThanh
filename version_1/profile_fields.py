"""Canonical profile-field names and user-friendly CLI value parsing."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any


PROFILE_FIELDS = (
    "age_group",
    "goals",
    "conditions",
    "medications",
    "allergies",
    "pregnancy_status",
    "budget_max_vnd",
    "preferred_dosage_forms",
)

LIST_FIELDS = {
    "goals",
    "conditions",
    "medications",
    "allergies",
    "preferred_dosage_forms",
}


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold().strip())
    without_marks = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    without_marks = without_marks.replace("đ", "d")
    return re.sub(r"[\s_-]+", " ", without_marks).strip()


_FIELD_ALIASES = {
    "age group": "age_group",
    "nhom tuoi": "age_group",
    "tuoi": "age_group",
    "goals": "goals",
    "muc tieu": "goals",
    "conditions": "conditions",
    "benh nen": "conditions",
    "medications": "medications",
    "thuoc": "medications",
    "thuoc dang dung": "medications",
    "allergies": "allergies",
    "di ung": "allergies",
    "pregnancy status": "pregnancy_status",
    "thai/cho con bu": "pregnancy_status",
    "thai va cho con bu": "pregnancy_status",
    "tinh trang thai/cho con bu": "pregnancy_status",
    "budget max vnd": "budget_max_vnd",
    "ngan sach": "budget_max_vnd",
    "ngan sach toi da": "budget_max_vnd",
    "preferred dosage forms": "preferred_dosage_forms",
    "dang dung ua thich": "preferred_dosage_forms",
    "dang bao che ua thich": "preferred_dosage_forms",
    "dang bao che": "preferred_dosage_forms",
}

_EMPTY_MARKERS = {
    "",
    "any",
    "khong",
    "khong co",
    "khong dung",
    "khong uu tien",
    "loai nao cung duoc",
    "n/a",
    "no",
    "none",
}

_AGE_ALIASES = {
    "infant": "infant",
    "so sinh": "infant",
    "tre so sinh": "infant",
    "child": "child",
    "tre em": "child",
    "adolescent": "adolescent",
    "thieu nien": "adolescent",
    "vi thanh nien": "adolescent",
    "adult": "adult",
    "nguoi lon": "adult",
    "truong thanh": "adult",
    "older adult": "older_adult",
    "cao tuoi": "older_adult",
    "nguoi cao tuoi": "older_adult",
}

_PREGNANCY_ALIASES = {
    "not applicable": "not_applicable",
    "khong ap dung": "not_applicable",
    "none": "none",
    "khong": "none",
    "khong co": "none",
    "khong mang thai": "none",
    "pregnant": "pregnant",
    "mang thai": "pregnant",
    "breastfeeding": "breastfeeding",
    "cho con bu": "breastfeeding",
    "prefer not to say": "prefer_not_to_say",
    "khong muon tra loi": "prefer_not_to_say",
}


def canonical_profile_field(field: str) -> str:
    key = _fold(field)
    canonical = _FIELD_ALIASES.get(key)
    if canonical is None:
        raise ValueError(
            f"Trường hồ sơ không được hỗ trợ: {field!r}. "
            f"Chỉ dùng: {', '.join(PROFILE_FIELDS)}"
        )
    return canonical


def canonical_profile_fields(fields: Iterable[str]) -> list[str]:
    canonical: list[str] = []
    for field in fields:
        name = canonical_profile_field(str(field))
        if name not in canonical:
            canonical.append(name)
    return canonical


def parse_list_value(value: str) -> list[str]:
    if _fold(value) in _EMPTY_MARKERS:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_age_group(value: str) -> str:
    folded = _fold(value)
    if folded in _AGE_ALIASES:
        return _AGE_ALIASES[folded]
    match = re.fullmatch(r"(\d{1,3})(?:\s*tuoi)?", folded)
    if match is None:
        raise ValueError(
            "Nhập tuổi dạng số hoặc một trong infant, child, adolescent, "
            "adult, older_adult."
        )
    age = int(match.group(1))
    if not 0 <= age <= 120:
        raise ValueError("Tuổi phải nằm trong khoảng 0–120.")
    if age <= 1:
        return "infant"
    if age <= 11:
        return "child"
    if age <= 17:
        return "adolescent"
    if age <= 64:
        return "adult"
    return "older_adult"


def parse_pregnancy_status(value: str) -> str:
    folded = _fold(value)
    status = _PREGNANCY_ALIASES.get(folded)
    if status is None:
        raise ValueError(
            "Nhập none/không có, pregnant/mang thai, breastfeeding/cho con bú, "
            "not_applicable hoặc prefer_not_to_say."
        )
    return status


def parse_budget_vnd(value: str) -> int:
    normalized = value.strip().replace(".", "").replace(",", "").replace(" ", "")
    if not normalized.isdecimal():
        raise ValueError("Ngân sách phải là số nguyên VND, ví dụ 500000.")
    budget = int(normalized)
    if budget <= 0:
        raise ValueError("Ngân sách phải lớn hơn 0.")
    return budget


def coerce_profile_value(field: str, value: str) -> Any:
    if field in LIST_FIELDS:
        return parse_list_value(value)
    if field == "age_group":
        return parse_age_group(value)
    if field == "pregnancy_status":
        return parse_pregnancy_status(value)
    if field == "budget_max_vnd":
        return parse_budget_vnd(value)
    return value.strip()
