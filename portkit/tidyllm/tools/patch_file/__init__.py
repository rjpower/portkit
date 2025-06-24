"""Patch file tool for applying text modifications."""

from portkit.tidyllm.prompt import module_dir, read_prompt
from portkit.tidyllm.registry import register
from portkit.tidyllm.tools.patch_file.lib import PatchArgs, PatchResult, apply_patch


@register(doc=read_prompt(module_dir(__file__) / "prompt.md"))
def patch_file(args: PatchArgs) -> PatchResult:
    """Apply unified diff patches to text content."""
    return apply_patch(args)
