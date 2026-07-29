from langchain_core.tools import StructuredTool

from app.agent.shared.tools_runtime import ToolRuntime


def build(runtime: ToolRuntime) -> StructuredTool:
    return StructuredTool.from_function(
        runtime.compare_products,
        name="compare_products",
        description="Compare canonical products on user-requested nutrients.",
    )
