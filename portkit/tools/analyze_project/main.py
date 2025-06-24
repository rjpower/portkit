#!/usr/bin/env python3
"""
Project Analysis Tool for C-to-Rust Migration

This tool performs hierarchical analysis of C projects to identify logical
module boundaries and generate migration strategies.

Usage:
    python -m portkit.tools.analyze_project --sourcemap path/to/sourcemap.txt --output analysis/ --project libxml2
"""

import asyncio
import sys
from pathlib import Path

import click

from portkit.tools.analyze_project.lib import analyze_project
from portkit.tools.analyze_project.models import ProjectAnalysisArgs


@click.command()
@click.option(
    "--sourcemap",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to sourcemap.txt file",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory for analysis results",
)
@click.option("--project", required=True, help="Name of the project being analyzed")
def cli(sourcemap: Path, output: Path, project: str):
    """Analyze C project structure for Rust migration planning."""

    async def run_analysis():
        try:
            # Validate sourcemap is a file
            if not sourcemap.is_file():
                click.echo(f"Error: Sourcemap path is not a file: {sourcemap}", err=True)
                sys.exit(1)

            # Create args
            args = ProjectAnalysisArgs(
                sourcemap_path=str(sourcemap), output_dir=str(output), project_name=project
            )

            # Run analysis
            result = await analyze_project(args)

            # Print summary
            click.echo("\n" + "=" * 60)
            click.echo(f"PROJECT ANALYSIS COMPLETE: {result.project_name}")
            click.echo("=" * 60)
            click.echo(f"Total modules identified: {result.total_modules}")
            click.echo(f"Processing order: {' → '.join(result.processing_order)}")
            click.echo(f"Main analysis: {result.analysis_file}")
            click.echo(f"Module files: {len(result.module_files)} files in module_analysis/")
            click.echo("=" * 60)

        except KeyboardInterrupt:
            click.echo("\nAnalysis interrupted by user", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

    asyncio.run(run_analysis())


if __name__ == "__main__":
    cli()
