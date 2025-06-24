"""Core implementation for project analysis tool."""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from tqdm.asyncio import tqdm

from portkit.tidyllm.llm import LiteLLMClient
from portkit.tools.summarize_module.lib import SummarizeModuleArgs, summarize_module

from .models import (
    ModuleGroupingResult,
    ModuleInfo,
    ProjectAnalysisArgs,
    ProjectAnalysisResult,
)


def read_sourcemap(sourcemap_path: str) -> str:
    """Read and return sourcemap content."""
    path = Path(sourcemap_path)
    if not path.exists():
        raise ValueError(f"Sourcemap file not found: {sourcemap_path}")

    return path.read_text(encoding="utf-8")


async def identify_modules(
    sourcemap_content: str, cache_dir: Path | None = None
) -> ModuleGroupingResult:
    """Stage 1: Identify logical module boundaries using LLM."""

    # Generate cache key from sourcemap content
    if cache_dir:
        content_hash = hashlib.sha256(sourcemap_content.encode()).hexdigest()[:16]
        cache_file = cache_dir / f"modules_{content_hash}.json"

        # Try to load from cache
        if cache_file.exists():
            try:
                cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
                return ModuleGroupingResult(**cached_data)
            except (json.JSONDecodeError, TypeError, ValueError):
                # Cache file corrupted, continue with fresh request
                pass

    # Read the module grouping prompt
    prompt_path = Path(__file__).parent / "prompts" / "group_modules.md"
    prompt_template = prompt_path.read_text(encoding="utf-8")

    # Substitute sourcemap content
    prompt = prompt_template.replace("{{sourcemap}}", sourcemap_content)

    # Use LiteLLM client with Gemini 2.5 Flash
    client = LiteLLMClient()

    messages = [{"role": "user", "content": prompt}]

    response = client.completion(
        model="gemini/gemini-2.5-flash",
        messages=messages,
        tools=[],
        temperature=0.1,
        timeout_seconds=120,
        response_format={"type": "json_object"},
    )

    # Extract and parse response
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise ValueError("Empty response from LLM during module identification")

    result_data = json.loads(content)
    result = ModuleGroupingResult(**result_data)

    # Save to cache
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(result_data, indent=2), encoding="utf-8")

    return result


MAX_CONCURRENT_SUMMARIES = 8


async def summarize_modules_parallel(
    modules: list[ModuleInfo],
    project_root: Path,
    max_concurrent: int = MAX_CONCURRENT_SUMMARIES,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    """Stage 2: Summarize modules in parallel using existing summarize_module tool."""

    semaphore = asyncio.Semaphore(max_concurrent)

    async def summarize_single_module(module: ModuleInfo) -> tuple[str, Any]:
        async with semaphore:
            # Check cache first
            if cache_dir:
                # Generate cache key from module files
                all_files = sorted(module.c_files + module.header_files)
                files_hash = hashlib.sha256("".join(all_files).encode()).hexdigest()[:16]
                cache_file = cache_dir / f"summary_{module.name}_{files_hash}.json"

                if cache_file.exists():
                    try:
                        cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
                        return module.name, cached_data
                    except (json.JSONDecodeError, TypeError, ValueError):
                        # Cache file corrupted, continue with fresh request
                        pass

            # Find full paths for module files
            file_paths = []

            # Add C files
            for c_file in module.c_files:
                file_path = project_root / c_file
                if file_path.exists():
                    file_paths.append(str(file_path))

            # Add header files
            for header_file in module.header_files:
                file_path = project_root / header_file
                if file_path.exists():
                    file_paths.append(str(file_path))

            if not file_paths:
                # Return minimal result if no files found
                result_data = {
                    "module_name": module.name,
                    "overview": f"Module {module.name} - files not found for analysis",
                    "key_structures": [],
                    "key_enums": [],
                    "public_functions": [],
                    "api_boundaries": "Unknown - files not accessible",
                    "dependencies": module.dependencies,
                    "analyzed_files": [],
                }
                return module.name, result_data

            # Use existing summarize_module function
            args = SummarizeModuleArgs(paths=file_paths)

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, summarize_module, args)

            result_data = result.model_dump()

            # Save to cache
            if cache_dir:
                cache_dir.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(result_data, indent=2), encoding="utf-8")

            return module.name, result_data

    # Run all module summarizations in parallel with progress tracking
    tasks = [summarize_single_module(module) for module in modules]

    # Use asyncio.gather with return_exceptions and wrap with tqdm
    with tqdm(total=len(tasks), desc="Summarizing modules") as pbar:
        results = []
        for task in asyncio.as_completed(tasks):
            try:
                result = await task
                results.append(result)
            except Exception as e:
                results.append(e)
            pbar.update(1)

    # Collect successful results
    module_summaries = {}
    for result in results:
        if isinstance(result, Exception):
            print(f"Warning: Module summarization failed: {result}")
            continue
        else:
            module_name, summary = result
            module_summaries[module_name] = summary

    return module_summaries


async def generate_project_summary(
    module_grouping: ModuleGroupingResult,
    module_summaries: dict[str, Any],
    project_name: str,
) -> str:
    """Stage 3: Generate overall project summary using LLM."""

    # Read the project summary prompt
    prompt_path = Path(__file__).parent / "prompts" / "project_summary.md"
    prompt_template = prompt_path.read_text(encoding="utf-8")

    # Format module summaries for inclusion
    summaries_text = ""
    for module_name, summary in module_summaries.items():
        summaries_text += f"\n## Module: {module_name}\n"
        summaries_text += f"**Overview**: {summary.get('overview', 'N/A')}\n"
        summaries_text += f"**Dependencies**: {', '.join(summary.get('dependencies', []))}\n"
        summaries_text += f"**Key Functions**: {', '.join(func.get('signature', '') for func in summary.get('public_functions', []))}\n"
        summaries_text += f"**API Boundaries**: {summary.get('api_boundaries', 'N/A')}\n\n"

    # Format module dependencies
    dependencies_text = "\n".join(
        [
            f"- **{module.name}**: depends on {', '.join(module.dependencies) if module.dependencies else 'none'}"
            for module in module_grouping.modules
        ]
    )

    # Substitute content into prompt
    prompt = prompt_template.replace("{{module_summaries}}", summaries_text)
    prompt = prompt.replace("{{module_dependencies}}", dependencies_text)
    prompt = prompt.replace("[Project Name]", project_name)

    # Use LiteLLM client
    client = LiteLLMClient()

    messages = [{"role": "user", "content": prompt}]

    response = client.completion(
        model="gemini/gemini-2.5-flash",
        messages=messages,
        tools=[],
        temperature=0.2,
        timeout_seconds=180,
    )

    # Extract response content
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise ValueError("Empty response from LLM during project summary generation")

    return content


def write_module_yaml_files(
    module_grouping: ModuleGroupingResult,
    module_summaries: dict[str, Any],
    output_dir: Path,
) -> list[str]:
    """Write individual module YAML files in dependency order."""

    # Create module_analysis directory
    module_dir = output_dir / "module_analysis"
    module_dir.mkdir(parents=True, exist_ok=True)

    written_files = []

    # Write modules in processing order
    for index, module_name in enumerate(module_grouping.processing_order):
        # Find the module info
        module_info = next((m for m in module_grouping.modules if m.name == module_name), None)
        if not module_info:
            continue

        # Get the module summary
        summary = module_summaries.get(module_name, {})

        # Create YAML content in the expected format
        yaml_content = {
            "module": {
                "name": module_info.name,
                "description": module_info.description,
                "estimated_loc": module_info.estimated_loc,
                "c_files": module_info.c_files,
                "header_files": module_info.header_files,
                "key_functions": module_info.key_functions,
                "dependencies": module_info.dependencies,
                "api_overview": summary.get("overview", module_info.notes),
            }
        }

        # Write YAML file
        filename = f"{index + 1:05d}-{module_name}.yaml"
        file_path = module_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(yaml_content, f, default_flow_style=False, sort_keys=False)

        written_files.append(str(file_path))

    return written_files


async def analyze_project(args: ProjectAnalysisArgs) -> ProjectAnalysisResult:
    """Main orchestration function for project analysis."""

    # Setup paths
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create cache directory
    cache_dir = output_dir / ".cache"

    project_root = Path(args.sourcemap_path).parent

    # Stage 1: Read sourcemap and identify modules
    print(f"Stage 1: Identifying modules in {args.project_name}...")
    sourcemap_content = read_sourcemap(args.sourcemap_path)
    module_grouping = await identify_modules(sourcemap_content, cache_dir)

    print(f"Identified {len(module_grouping.modules)} modules")

    # Stage 2: Summarize modules in parallel
    print("Stage 2: Summarizing modules...")
    module_summaries = await summarize_modules_parallel(
        module_grouping.modules, project_root, cache_dir=cache_dir
    )

    print(f"Successfully summarized {len(module_summaries)} modules")

    # Stage 3: Generate project summary
    print("Stage 3: Generating project summary...")
    project_summary = await generate_project_summary(
        module_grouping, module_summaries, args.project_name
    )

    # Write output files
    print("Writing output files...")

    # Write individual module YAML files
    module_files = write_module_yaml_files(module_grouping, module_summaries, output_dir)

    # Write main project analysis file
    analysis_file = output_dir / "PROJECT_ANALYSIS.md"

    # Add module links to the project summary
    module_links = "\n".join(
        [
            f"- [{module.name}](module_analysis/{Path(file).name})"
            for module, file in zip(module_grouping.modules, module_files, strict=False)
        ]
    )

    final_summary = project_summary + f"\n\n## Module Details\n{module_links}\n"

    analysis_file.write_text(final_summary, encoding="utf-8")

    print(f"Analysis complete! Results written to {output_dir}")

    return ProjectAnalysisResult(
        project_name=args.project_name,
        total_modules=len(module_grouping.modules),
        analysis_file=str(analysis_file),
        module_files=module_files,
        processing_order=module_grouping.processing_order,
    )
