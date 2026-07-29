from pathlib import Path

from app.agent.shared.catalog import Catalog


DATASET = Path(__file__).parents[2] / "data" / "DataTPCN.csv"


def test_catalog_loads_the_supplied_21_column_dataset():
    catalog = Catalog.from_csv(DATASET)

    assert catalog.column_count == 21
    assert len(catalog.products) == 100
    assert catalog.dataset_fingerprint


def test_product_identity_is_stable_and_keeps_source_provenance():
    first = Catalog.from_csv(DATASET).products[0]
    again = Catalog.from_csv(DATASET).products[0]

    assert first.id == again.id
    assert first.source_row == 2
    assert first.name == "Blackmores Fish Oil 1000mg"
    assert first.price_vnd == 450_000
    assert first.raw["Tên thực phẩm chức năng"] == first.name


def test_catalog_normalizes_nutrients_without_inventing_empty_values():
    product = Catalog.from_csv(DATASET).products[0]

    nutrients = {item.name: (item.amount, item.unit) for item in product.nutrients}

    assert nutrients["Omega-3"] == (1000, "mg")
    assert "Vitamin C" not in nutrients
    assert product.special_ingredients == ""


def test_catalog_parses_package_and_daily_dosage_when_units_are_compatible():
    product = Catalog.from_csv(DATASET).products[0]

    assert product.package.quantity == 400
    assert product.package.unit == "viên"
    assert product.daily_dosage.minimum == 2
    assert product.daily_dosage.maximum == 2
    assert product.daily_dosage.unit == "viên"
    assert product.cost_per_day_vnd == (2_250.0, 2_250.0)


def test_catalog_reports_cost_unavailable_for_incompatible_units():
    catalog = Catalog.from_csv(DATASET)
    powder = next(item for item in catalog.products if item.package.unit == "g")

    assert powder.cost_per_day_vnd is None
