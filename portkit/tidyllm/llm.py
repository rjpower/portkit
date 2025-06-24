"""LLM integration helper for TidyAgent tools."""

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

import litellm
import litellm.types.utils


@dataclass
class ToolCall:
    tool_name: str
    tool_args: dict[str, Any]
    tool_result: Any


@dataclass
class LLMResponse:
    """Response from LLM with tool calling details."""

    success: bool
    tool_calls: list[ToolCall] = field(default_factory=list)
    error_message: str | None = None
    response_time_ms: int = 0
    raw_response: dict | None = None


class LLMClient(ABC):
    """Abstract interface for LLM clients."""

    @abstractmethod
    def completion(self, model: str, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        """Get completion with tool calling support."""
        pass

    @abstractmethod
    def list_models(self) -> list[str]:
        """List available models for testing."""
        pass


class LiteLLMClient(LLMClient):
    """LiteLLM client for multiple LLM providers."""

    def completion(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.1,
        timeout_seconds: int = 30,
        print_output: bool = False,
        **kwargs,
    ) -> dict:
        """Get completion using LiteLLM with streaming."""

        if print_output:
            _write = lambda content: print(content, end="", flush=True)
        else:
            _write = lambda content: None

        _write("Starting LLM request...\n")

        # Use streaming mode like tinyagent
        response = litellm.completion(
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            timeout=timeout_seconds,
            stream=True,
            stream_options={"include_usage": True},
            tool_choice="auto",
            **kwargs,
        )

        content_parts = []
        tool_calls_by_index = {}
        usage_data = None

        for chunk in cast(litellm.CustomStreamWrapper, response):
            # Handle content
            choice = cast(litellm.types.utils.StreamingChoices, chunk.choices[0])
            if choice.delta.role == "user":
                continue

            if choice.delta.content is not None:
                content = choice.delta.content
                content_parts.append(content)
                _write(content)

            # Handle tool calls
            if choice.delta.tool_calls:
                for tool_call_delta in choice.delta.tool_calls:
                    index = tool_call_delta.index
                    if index not in tool_calls_by_index:
                        tool_calls_by_index[index] = {
                            "id": tool_call_delta.id,
                            "type": tool_call_delta.type,
                            "function": {"name": None, "arguments": ""},
                        }

                    tool_call = tool_calls_by_index[index]

                    # Accumulate function arguments
                    if tool_call_delta.function and tool_call_delta.function.arguments:
                        tool_call["function"]["arguments"] += tool_call_delta.function.arguments

                    # Update name if provided
                    if tool_call_delta.function and tool_call_delta.function.name:
                        tool_call["function"]["name"] = tool_call_delta.function.name

            # Handle usage data
            if hasattr(chunk, "usage") and chunk.usage is not None:  # type: ignore
                usage_data = chunk.usage  # type: ignore

        # Convert to standard format
        assistant_message = {"role": "assistant", "content": "".join(content_parts)}

        # Convert tool calls to list format
        tool_calls = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index.keys())]

        if tool_calls:
            assistant_message["tool_calls"] = tool_calls

        # Return in the format expected by the rest of the code
        return {"choices": [{"message": assistant_message}], "usage": usage_data}

    def list_models(self) -> list[str]:
        """List commonly available models."""
        return [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
            "claude-3-sonnet",
            "claude-3-haiku",
            "claude-3-opus",
        ]


class MockLLMClient(LLMClient):
    """Mock LLM client for testing."""

    def __init__(self, mock_responses: dict[str, dict] = None):
        """Initialize with mock responses.

        Args:
            mock_responses: Map of prompt -> mock response dict
        """
        self.mock_responses = mock_responses or {}

    def completion(self, model: str, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        """Return mock response based on prompt."""
        prompt = messages[-1]["content"] if messages else ""

        # Return pre-configured response or default
        if prompt in self.mock_responses:
            return self.mock_responses[prompt]

        # Default response calls tool based on prompt keywords or first available
        if tools:
            tool_name = tools[0]["function"]["name"]
            selected_tool = next((t for t in tools if t["function"]["name"] == tool_name), tools[0])
            default_args = selected_tool["function"]["arguments"]

            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "mock_call_1",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(default_args),
                                    },
                                }
                            ]
                        }
                    }
                ]
            }

        # No tools available - just return text response
        return {
            "choices": [
                {"message": {"content": "I don't have access to any tools to help with that."}}
            ]
        }

    def list_models(self) -> list[str]:
        """List mock models."""
        return ["mock-gpt-4", "mock-claude"]


class LLMHelper:
    """Helper for testing tools with LLM integration."""

    def __init__(
        self,
        model: str,
        function_library,
        llm_client: LLMClient,
        default_system_prompt: str = "You are a helpful assistant with access to tools.",
    ):
        """Initialize LLM helper.

        Args:
            model: LLM model name to use
            function_library: FunctionLibrary with registered tools
            llm_client: LLM client implementation
            default_system_prompt: Default system prompt for tool usage
        """
        self.model = model
        self.function_library = function_library
        self.llm_client = llm_client
        self.default_system_prompt = default_system_prompt

    def ask(
        self,
        prompt: str,
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        **llm_kwargs,
    ) -> LLMResponse:
        """Ask LLM to perform a task using available tools.

        Args:
            prompt: User prompt describing the task
            tools: Available tool schemas (defaults to all library tools)
            system_prompt: System prompt override
            **llm_kwargs: Additional arguments passed to LLM client

        Returns:
            LLMResponse with tool call and execution details
        """
        start_time = time.time()

        # Use provided tools or get all from library
        if tools is None:
            tools = self.function_library.get_schemas()

        # Prepare messages
        messages = [
            {"role": "system", "content": system_prompt or self.default_system_prompt},
            {"role": "user", "content": prompt},
        ]

        try:
            # Get LLM response
            response = self.llm_client.completion(
                model=self.model, messages=messages, tools=tools, **llm_kwargs
            )

            response_time = int((time.time() - start_time) * 1000)

            # Check if tool was called
            tool_calls = response.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])

            if not tool_calls:
                return LLMResponse(
                    success=False,
                    error_message="No tool was called",
                    response_time_ms=response_time,
                    raw_response=response,
                )

            tool_calls = []
            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_args_str = tool_call["function"]["arguments"]
                tool_args = json.loads(tool_args_str)

                # Execute tool through function library
                tool_result = self.function_library.call(
                    {"name": tool_name, "arguments": tool_args}
                )

                tool_calls.append(ToolCall(tool_name, tool_args, tool_result))

            return LLMResponse(
                success=True,
                tool_calls=tool_calls,
                response_time_ms=response_time,
                raw_response=response,
            )

        except json.JSONDecodeError as e:
            return LLMResponse(
                success=False,
                error_message=f"Invalid JSON in tool arguments: {str(e)}",
                response_time_ms=int((time.time() - start_time) * 1000),
            )
        except Exception as e:
            return LLMResponse(
                success=False,
                error_message=f"LLM request failed: {str(e)}",
                response_time_ms=int((time.time() - start_time) * 1000),
            )

    def ask_and_validate(
        self,
        prompt: str,
        expected_tool: str,
        validation_fn: Callable | None = None,
        **llm_kwargs,
    ) -> LLMResponse:
        """Ask LLM and validate the response.

        Args:
            prompt: User prompt
            expected_tool: Expected tool name to be called
            validation_fn: Optional function to validate tool result
            **llm_kwargs: Additional LLM arguments

        Returns:
            LLMResponse with validation status
        """
        response = self.ask(prompt, **llm_kwargs)

        if not response.success:
            return response

        # Validate tool name
        if response.tool_calls[0].tool_name != expected_tool:
            response.success = False
            response.error_message = f"Expected tool '{expected_tool}', got '{response.tool_calls[0].tool_name}'"
            return response

        # Validate result if function provided
        if validation_fn and not validation_fn(response):
            response.success = False
            response.error_message = "Tool result validation failed"

        return response


def create_llm_client(client_type: str = "litellm", **kwargs) -> LLMClient:
    """Factory function to create LLM clients.

    Args:
        client_type: Type of client ("litellm" or "mock")
        **kwargs: Client-specific arguments

    Returns:
        LLM client instance
    """
    if client_type == "litellm":
        return LiteLLMClient()
    elif client_type == "mock":
        return MockLLMClient(kwargs.get("mock_responses", {}))
    else:
        raise ValueError(f"Unknown client type: {client_type}")
