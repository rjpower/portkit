"""Adapters for integrating TidyLLM with different frameworks."""

# FastAPI adapter (optional dependency)
try:
    from .fastapi_adapter import create_fastapi_app, create_portkit_api
    __all__ = ["create_fastapi_app", "create_portkit_api"]
except ImportError:
    # FastAPI not available
    __all__ = []