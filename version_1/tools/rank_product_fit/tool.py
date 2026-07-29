from langchain_core.tools import StructuredTool

from app.agent.shared.tools_runtime import ToolRuntime


def build(runtime: ToolRuntime) -> StructuredTool:
    return StructuredTool.from_function(
        runtime.rank_product_fit,
        name="rank_product_fit",
        description="Calculate deterministic fit scores and score breakdowns.",
    )
