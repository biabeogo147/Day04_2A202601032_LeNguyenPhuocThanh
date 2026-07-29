from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path


PRODUCT_NAMESPACE = uuid.UUID("3a3c1158-1159-4a89-8eeb-5c0a397d6be1")
BASE_COLUMNS = {
    "Tên thực phẩm chức năng",
    "Giá tiền",
    "Cách dùng",
    "Chống chỉ định",
    "Liều dùng",
    "Chức năng sản phẩm",
    "Quy cách đóng gói",
    "Đối tượng sử dụng",
    "Dạng bào chế",
}
NUTRIENT_COLUMNS = (
    "Vitamin C",
    "Canxi",
    "Vitamin D3",
    "Sắt",
    "Kẽm",
    "Vitamin E",
    "Omega-3",
    "Biotin",
    "Lợi khuẩn",
    "Protein",
    "Vitamin A",
)
AMOUNT_PATTERN = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*([^\d\s].*?)?\s*$")
PACKAGE_PATTERN = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*([^/]+?)(?:/.*)?$")
DOSAGE_PATTERN = re.compile(
    r"^\s*(\d+(?:[.,]\d+)?)\s*(?:-\s*(\d+(?:[.,]\d+)?))?\s*([^/]+?)(?:/.*)?$"
)


def fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()


def _number(value: str) -> float:
    return float(value.replace(",", "."))


def _display_number(value: float) -> float | int:
    return int(value) if value.is_integer() else value


@dataclass(frozen=True)
class Nutrient:
    name: str
    amount: float | int
    unit: str


@dataclass(frozen=True)
class Package:
    quantity: float | int
    unit: str
    raw: str


@dataclass(frozen=True)
class DailyDosage:
    minimum: float | int
    maximum: float | int
    unit: str
    raw: str


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    price_vnd: int
    usage: str
    contraindications: str
    dosage: str
    function: str
    packaging: str
    audience: str
    dosage_form: str
    nutrients: tuple[Nutrient, ...]
    special_ingredients: str
    package: Package | None
    daily_dosage: DailyDosage | None
    source_row: int
    raw: dict[str, str]

    @property
    def cost_per_day_vnd(self) -> tuple[float, float] | None:
        if not self.package or not self.daily_dosage:
            return None
        if fold_text(self.package.unit) != fold_text(self.daily_dosage.unit):
            return None
        if self.package.quantity <= 0:
            return None
        factor = self.price_vnd / float(self.package.quantity)
        return (
            round(factor * float(self.daily_dosage.minimum), 2),
            round(factor * float(self.daily_dosage.maximum), 2),
        )

    def embedding_text(self) -> str:
        nutrient_text = ", ".join(
            f"{item.name} {_display_number(float(item.amount))} {item.unit}".strip()
            for item in self.nutrients
        )
        return "\n".join(
            part
            for part in (
                f"Tên: {self.name}",
                f"Chức năng: {self.function}",
                f"Đối tượng: {self.audience}",
                f"Dạng bào chế: {self.dosage_form}",
                f"Thành phần: {nutrient_text}",
                f"Thành phần khác: {self.special_ingredients}",
            )
            if part.split(":", 1)[-1].strip()
        )


def parse_price_vnd(raw: str) -> int:
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        raise ValueError(f"Giá tiền không hợp lệ: {raw!r}")
    return int(digits)


def parse_package(raw: str) -> Package | None:
    match = PACKAGE_PATTERN.match(raw)
    if not match:
        return None
    quantity = _number(match.group(1))
    return Package(_display_number(quantity), match.group(2).strip(), raw)


def parse_daily_dosage(raw: str) -> DailyDosage | None:
    match = DOSAGE_PATTERN.match(raw)
    if not match:
        return None
    minimum = _number(match.group(1))
    maximum = _number(match.group(2)) if match.group(2) else minimum
    return DailyDosage(
        _display_number(minimum),
        _display_number(maximum),
        match.group(3).strip(),
        raw,
    )


def parse_nutrient(name: str, raw: str) -> Nutrient | None:
    value = raw.strip()
    if not value:
        return None
    match = AMOUNT_PATTERN.match(value)
    if not match:
        return Nutrient(name=name, amount=1, unit=value)
    amount = _number(match.group(1))
    return Nutrient(name=name, amount=_display_number(amount), unit=(match.group(2) or "").strip())


class Catalog:
    def __init__(
        self,
        *,
        products: tuple[Product, ...],
        dataset_fingerprint: str,
        column_count: int,
        path: Path,
    ) -> None:
        self.products = products
        self.dataset_fingerprint = dataset_fingerprint
        self.column_count = column_count
        self.path = path
        self._by_id = {product.id: product for product in products}

    @classmethod
    def from_csv(cls, path: str | Path) -> "Catalog":
        source = Path(path)
        content = source.read_bytes()
        fingerprint = hashlib.sha256(content).hexdigest()
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = tuple(reader.fieldnames or ())
            missing = BASE_COLUMNS - set(fieldnames)
            if missing:
                raise ValueError(f"CSV thiếu cột bắt buộc: {', '.join(sorted(missing))}")
            rows = list(reader)

        products: list[Product] = []
        for source_row, raw_row in enumerate(rows, start=2):
            row = {key: (value or "").strip() for key, value in raw_row.items() if key}
            name = row["Tên thực phẩm chức năng"]
            product_id = str(uuid.uuid5(PRODUCT_NAMESPACE, fold_text(name)))
            nutrients = tuple(
                nutrient
                for column in NUTRIENT_COLUMNS
                if (nutrient := parse_nutrient(column, row.get(column, ""))) is not None
            )
            products.append(
                Product(
                    id=product_id,
                    name=name,
                    price_vnd=parse_price_vnd(row["Giá tiền"]),
                    usage=row["Cách dùng"],
                    contraindications=row["Chống chỉ định"],
                    dosage=row["Liều dùng"],
                    function=row["Chức năng sản phẩm"],
                    packaging=row["Quy cách đóng gói"],
                    audience=row["Đối tượng sử dụng"],
                    dosage_form=row["Dạng bào chế"],
                    nutrients=nutrients,
                    special_ingredients=row.get("Thành phần đặc biệt khác", ""),
                    package=parse_package(row["Quy cách đóng gói"]),
                    daily_dosage=parse_daily_dosage(row["Liều dùng"]),
                    source_row=source_row,
                    raw=row,
                )
            )
        return cls(
            products=tuple(products),
            dataset_fingerprint=fingerprint,
            column_count=len(fieldnames),
            path=source.resolve(),
        )

    def get(self, product_id: str) -> Product:
        try:
            return self._by_id[product_id]
        except KeyError as exc:
            raise KeyError(f"Không tìm thấy product_id: {product_id}") from exc
