from langchain_core.tools import StructuredTool

from app.agent.shared.tools_runtime import ToolRuntime


def build(runtime: ToolRuntime) -> StructuredTool:
    return StructuredTool.from_function(
        runtime.assess_product_safety,
        name="assess_product_safety",
        description="Apply the explicit contraindication safety gate to product IDs.",
    )
