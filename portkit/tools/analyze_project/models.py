"""Pydantic models for project analysis tool."""

from pydantic import BaseModel, Field


class ModuleInfo(BaseModel):
    """Information about a logical module identified in the project."""

    name: str = Field(description="Module name/identifier")
    description: str = Field(description="Brief description of module purpose")
    estimated_loc: int = Field(description="Estimated lines of C code")
    c_files: list[str] = Field(description="C source files in this module")
    header_files: list[str] = Field(description="Header files for this module")
    key_functions: list[str] = Field(description="Main public functions")
    dependencies: list[str] = Field(description="Other modules this depends on")
    api_quality: str = Field(description="clean/moderate/tangled")
    notes: str = Field(description="Additional notes about the module")


class CircularDependency(BaseModel):
    """Information about circular dependencies between modules."""

    modules: list[str] = Field(description="Modules involved in the cycle")
    description: str = Field(description="Description of the dependency cycle")


class ModuleGroupingResult(BaseModel):
    """Result of Stage 1: Module identification."""

    modules: list[ModuleInfo] = Field(description="Identified modules")
    processing_order: list[str] = Field(description="Recommended order for processing modules")


class ProjectAnalysisArgs(BaseModel):
    """Arguments for project analysis tool."""

    sourcemap_path: str = Field(
        description="Path to sourcemap.txt file",
        examples=["/path/to/project/sourcemap.txt"],
    )
    output_dir: str = Field(
        description="Directory to write analysis results",
        examples=["/path/to/project/analysis"],
    )
    project_name: str = Field(
        description="Name of the project being analyzed",
        examples=["libxml2", "openssl", "sqlite"],
    )


class ProjectAnalysisResult(BaseModel):
    """Result of complete project analysis."""

    project_name: str = Field(description="Name of analyzed project")
    total_modules: int = Field(description="Number of modules identified")
    analysis_file: str = Field(description="Path to generated PROJECT_ANALYSIS.md")
    module_files: list[str] = Field(description="Paths to individual module YAML files")
    processing_order: list[str] = Field(description="Recommended module processing order")
