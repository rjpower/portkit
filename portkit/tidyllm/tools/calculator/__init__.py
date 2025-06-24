"""Calculator tool for basic mathematical operations."""

from portkit.tidyllm.prompt import module_dir, read_prompt
from portkit.tidyllm.registry import register

from .lib import CalculatorArgs, CalculatorResult, perform_calculation


@register(doc=read_prompt(module_dir(__file__) / "prompt.md"))
def calculator(args: CalculatorArgs) -> CalculatorResult:
    """Perform basic mathematical operations."""
    return perform_calculation(args)
