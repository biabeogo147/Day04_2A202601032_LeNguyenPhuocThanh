MANIFEST = {
    "id": "version_1",
    "label": "Version 1 — Grounded Free-form ReAct",
    "description": "OpenAI-first ReAct advisor grounded only in DataTPCN.csv.",
    "enabled_tools": [
        "request_profile_fields",
        "search_product_catalog",
        "get_product_details",
        "assess_product_safety",
        "rank_product_fit",
        "compare_products",
        "submit_consultation",
    ],
    "max_rounds": 6,
    "max_tool_calls": 12,
    "repair_attempts": 1,
    "scoring_policy": "fit-v1",
    "safety_policy": "dataset-contraindication-v1",
}
