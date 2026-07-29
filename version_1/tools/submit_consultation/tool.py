from langchain_core.tools import StructuredTool

from app.agent.shared.tools_runtime import ToolRuntime


def build(runtime: ToolRuntime) -> StructuredTool:
    return StructuredTool.from_function(
        runtime.submit_consultation,
        name="submit_consultation",
        description="Submit the terminal grounded consultation response.",
    )
