"""C module summarization tool using LLM analysis."""

from portkit.tools.summarize_module.lib import (
    SummarizeModuleArgs,
    SummarizeModuleResult,
    summarize_module,
)

__all__ = ["SummarizeModuleArgs", "SummarizeModuleResult", "summarize_module"]
