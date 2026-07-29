from langchain_core.tools import StructuredTool

from app.agent.shared.tools_runtime import ToolRuntime


def build(runtime: ToolRuntime) -> StructuredTool:
    return StructuredTool.from_function(
        runtime.search_product_catalog,
        name="search_product_catalog",
        description="Search canonical catalog candidates by intent or product name.",
    )
