from langchain_core.tools import StructuredTool

from app.agent.shared.tools_runtime import ToolRuntime


def build(runtime: ToolRuntime) -> StructuredTool:
    return StructuredTool.from_function(
        runtime.get_product_details,
        name="get_product_details",
        description="Read canonical CSV label details for retrieved product IDs.",
    )
