"""FastAPI adapter for TidyLLM registry functions."""

from typing import Any

from fastapi import FastAPI, HTTPException

from portkit.tidyllm.library import FunctionLibrary
from portkit.tidyllm.models import ToolError


def create_fastapi_app(
    function_library: FunctionLibrary | None = None,
    title: str = "TidyLLM Tools API",
    description: str = "API for TidyLLM registered tools",
    version: str = "1.0.0",
) -> FastAPI:
    """
    Create a FastAPI application that exposes TidyLLM tools as individual endpoints.
    
    Each tool gets its own POST endpoint that accepts the tool's specific argument types
    directly, with FastAPI automatically generating the OpenAPI schema.
    
    Args:
        function_library: Optional FunctionLibrary instance to use for tool execution
        title: API title
        description: API description
        version: API version
        
    Returns:
        Configured FastAPI application with individual tool endpoints
        
    Example:
        from portkit.tidyllm.adapters.fastapi import create_fastapi_app
        from portkit.tidyllm import FunctionLibrary
        
        # Create library with context
        library = FunctionLibrary(context={"project_root": Path("/tmp")})
        
        # Create FastAPI app
        app = create_fastapi_app(library)
        
        # Run with: uvicorn module:app --reload
        # Tools will be available at /tools/{tool_name}
    """
    app = FastAPI(title=title, description=description, version=version)

    # Use provided library or create a default one
    if function_library is None:
        function_library = FunctionLibrary()

    @app.get("/", summary="API Information")
    async def root():
        """Get basic API information."""
        tool_names = [desc.name for desc in function_library.function_descriptions]
        return {
            "title": title,
            "description": description,
            "version": version,
            "tools": tool_names,
            "endpoints": {f"/tools/{name}" for name in tool_names}
        }

    @app.get("/health", summary="Health Check")
    async def health_check():
        """Simple health check endpoint."""
        return {
            "status": "healthy",
            "available_tools": len(function_library.function_descriptions)
        }

    # Create individual endpoints for each tool
    for tool_desc in function_library.function_descriptions:
        _create_tool_endpoint(app, tool_desc, function_library)

    return app


def _create_tool_endpoint(app: FastAPI, tool_desc, function_library: FunctionLibrary):
    """Create a FastAPI endpoint for a specific tool.""" 
    from inspect import Parameter, Signature
    
    tool_name = tool_desc.name
    args_model = tool_desc.args_model
    
    # Create the endpoint function dynamically
    def create_endpoint():
        async def tool_endpoint(args):
            """Execute the tool with the provided arguments."""
            try:
                # Convert Pydantic model to dict for function call
                result = function_library.call({
                    "name": tool_name,
                    "arguments": args.model_dump()
                })

                # Check if the result is a ToolError
                if isinstance(result, ToolError):
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": result.error,
                            "details": result.details
                        }
                    )

                return result

            except Exception as e:
                if isinstance(e, HTTPException):
                    raise
                # Handle unexpected errors
                raise HTTPException(
                    status_code=500,
                    detail=f"Unexpected error: {str(e)}"
                ) from e

        # Set function metadata
        tool_endpoint.__name__ = f"{tool_name}_endpoint"
        tool_endpoint.__doc__ = tool_desc.function.__doc__ or f"Execute {tool_name} tool"
        
        # Create signature with properly typed parameter
        param = Parameter('args', Parameter.POSITIONAL_OR_KEYWORD, annotation=args_model)
        tool_endpoint.__signature__ = Signature([param])
        
        return tool_endpoint
    
    endpoint_func = create_endpoint()

    # Add the endpoint to the FastAPI app
    app.post(
        f"/tools/{tool_name}",
        response_model=None,  # Let FastAPI infer from return type
        summary=f"Execute {tool_name}",
        description=tool_desc.function.__doc__ or f"Execute the {tool_name} tool",
        tags=["tools"]
    )(endpoint_func)


# Convenience function for common use case
def create_portkit_api(
    context: dict[str, Any] | None = None,
    title: str = "PortKit Tools API",
    description: str = "API for PortKit TinyAgent tools",
) -> FastAPI:
    """
    Create a FastAPI app specifically for PortKit tools.
    
    Args:
        context: Context dictionary for tools (e.g., {"project_root": Path("/tmp")})
        title: API title
        description: API description
        
    Returns:
        Configured FastAPI application with PortKit tools
        
    Example:
        from pathlib import Path
        from portkit.tidyllm.adapters.fastapi_adapter import create_portkit_api
        
        app = create_portkit_api(context={"project_root": Path("/my/project")})
    """
    def get_portkit_tools():
        """Get all registered PortKit tools as FunctionDescription objects."""
        from pathlib import Path
        from portkit.tidyllm.discover import discover_tools_in_directory
        
        tools_dir = Path(__file__).parent.parent.parent / "tools"
        return discover_tools_in_directory(
            tools_dir, 
            recursive=True,
        )

    # Discover PortKit tools
    portkit_tools = get_portkit_tools()

    # Create function library with PortKit tools
    library = FunctionLibrary(
        function_descriptions=portkit_tools,
        context=context or {}
    )

    return create_fastapi_app(library, title=title, description=description)
