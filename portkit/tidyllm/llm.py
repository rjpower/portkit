"""LLM integration helper for TidyAgent tools."""

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast

import litellm
import litellm.types.utils


class Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCall:
    tool_name: str
    tool_args: dict[str, Any]
    tool_result: Any
    id: str | None = None


@dataclass
class LLMMessage:
    role: Role
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass
class LLMResponse:
    """Response from LLM with tool calling details."""

    messages: list[LLMMessage]
    tool_calls: list[ToolCall]
    response_time_ms: int = 0
    raw_response: dict | None = None


def _llm_messages_to_dicts(messages: list[LLMMessage]) -> list[dict]:
    """Convert LLMMessage objects to dict format for LiteLLM."""
    result = []

    for msg in messages:
        msg_dict: dict[str, Any] = {"role": msg.role.value, "content": msg.content}

        if msg.tool_calls:
            # Convert tool calls to LiteLLM format
            msg_dict["tool_calls"] = []
            for tc in msg.tool_calls:
                # Use the tool call's stored ID if available
                tc_dict = {
                    "type": "function",
                    "function": {"name": tc.tool_name, "arguments": json.dumps(tc.tool_args)},
                }
                # Add ID if we have one stored
                if hasattr(tc, "id") and tc.id:
                    tc_dict["id"] = tc.id
                msg_dict["tool_calls"].append(tc_dict)

        if msg.tool_call_id:
            msg_dict["tool_call_id"] = msg.tool_call_id

        result.append(msg_dict)

    return result


class LLMClient(ABC):
    """Abstract interface for LLM clients."""

    @abstractmethod
    def completion(
        self, model: str, messages: list[LLMMessage], tools: list[dict], **kwargs
    ) -> LLMResponse:
        """Get completion with tool calling support.

        Args:
            model: Model name
            messages: List of LLMMessage objects
            tools: Tool schemas
            **kwargs: Additional arguments

        Returns:
            LLMResponse with processed results
        """
        pass


class LiteLLMClient(LLMClient):
    """LiteLLM client for multiple LLM providers."""

    def completion(
        self,
        model: str,
        messages: list[LLMMessage],
        tools: list[dict],
        temperature: float = 0.1,
        timeout_seconds: int = 30,
        print_output: bool = False,
        **kwargs,
    ) -> LLMResponse:
        """Get completion using LiteLLM with streaming."""
        start_time = time.time()

        if print_output:
            _write = lambda content: print(content, end="", flush=True)
        else:
            _write = lambda content: None

        _write("Starting LLM request...\n")

        message_dicts = _llm_messages_to_dicts(messages)

        # Use streaming mode like tinyagent
        response = litellm.completion(
            model=model,
            messages=message_dicts,
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
        assistant_message: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts)}

        # Convert tool calls to list format
        tool_calls = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index.keys())]

        if tool_calls:
            assistant_message["tool_calls"] = tool_calls

        # Create assistant message and add tool calls
        assistant_msg = LLMMessage(role=Role.ASSISTANT, content="".join(content_parts))

        # Convert tool calls to ToolCall objects
        processed_tool_calls = []
        if tool_calls:
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                tool_args = json.loads(tc["function"]["arguments"])
                processed_tool_calls.append(
                    ToolCall(
                        tool_name=tool_name, tool_args=tool_args, tool_result=None, id=tc.get("id")
                    )
                )
            assistant_msg.tool_calls = processed_tool_calls

        response_messages = messages + [assistant_msg]
        response_time = int((time.time() - start_time) * 1000)

        return LLMResponse(
            messages=response_messages,
            tool_calls=processed_tool_calls,
            response_time_ms=response_time,
            raw_response={"choices": [{"message": assistant_message}], "usage": usage_data},
        )


class MockLLMClient(LLMClient):
    """Mock LLM client for testing."""

    def __init__(self, mock_responses: dict[str, dict] | None = None):
        """Initialize with mock responses.

        Args:
            mock_responses: Map of prompt -> mock response dict
        """
        self.mock_responses = mock_responses or {}

    def completion(
        self, model: str, messages: list[LLMMessage], tools: list[dict], **kwargs
    ) -> LLMResponse:
        """Return mock response based on prompt."""
        # Create assistant response
        assistant_msg = LLMMessage(role=Role.ASSISTANT, content="")
        processed_tool_calls = []

        # Default response calls tool based on prompt keywords or first available
        if tools:
            tool_name = tools[0]["function"]["name"]
            selected_tool = next((t for t in tools if t["function"]["name"] == tool_name), tools[0])
            default_args = selected_tool["function"]["arguments"]

            tool_call = ToolCall(
                tool_name=tool_name, tool_args=default_args, tool_result=None, id="mock_call_1"
            )
            processed_tool_calls.append(tool_call)
            assistant_msg.tool_calls = [tool_call]
        else:
            # No tools available - just return text response
            assistant_msg.content = "I don't have access to any tools to help with that."

        response_messages = messages + [assistant_msg]

        return LLMResponse(
            messages=response_messages, tool_calls=processed_tool_calls, response_time_ms=0
        )


class LLMHelper:
    """Helper for testing tools with LLM integration."""

    def __init__(
        self,
        model: str,
        function_library,
        llm_client: LLMClient,
        default_system_prompt: str = "You are a helpful assistant with access to tools. Always use the appropriate tool to complete the user's request. For patching or modifying text, use the patch_file tool.",
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
        prompt: str | list[LLMMessage],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        **llm_kwargs,
    ) -> LLMResponse:
        """Ask LLM to perform a task using available tools.

        Args:
            prompt: User prompt string or list of LLMMessage objects
            tools: Available tool schemas (defaults to all library tools)
            system_prompt: System prompt override
            **llm_kwargs: Additional arguments passed to LLM client

        Returns:
            LLMResponse with tool call and execution details
        """
        # Use provided tools or get all from library
        if tools is None:
            tools = self.function_library.get_schemas()

        # Prepare messages
        if isinstance(prompt, str):
            messages = [
                LLMMessage(role=Role.SYSTEM, content=system_prompt or self.default_system_prompt),
                LLMMessage(role=Role.USER, content=prompt),
            ]
        else:
            messages = prompt

        # Get LLM response
        response = self.llm_client.completion(
            model=self.model, messages=messages, tools=tools, **llm_kwargs
        )

        # Execute any tool calls that were returned
        for tool_call in response.tool_calls:
            if tool_call.tool_result is None:
                tool_call.tool_result = self.function_library.call(tool_call.tool_name, tool_call.tool_args)

        return response

    def ask_and_validate(
        self,
        prompt: str | list[LLMMessage],
        expected_tool: str,
        validation_fn: Callable | None = None,
        **llm_kwargs,
    ) -> LLMResponse:
        """Ask LLM and validate the response.

        Args:
            prompt: User prompt string or list of LLMMessage objects
            expected_tool: Expected tool name to be called
            validation_fn: Optional function to validate tool result
            **llm_kwargs: Additional LLM arguments

        Returns:
            LLMResponse with validation status
        """
        response = self.ask(prompt, **llm_kwargs)

        # Validate tool name
        if not response.tool_calls or response.tool_calls[0].tool_name != expected_tool:
            raise ValueError(
                f"Expected tool '{expected_tool}', got '{response.tool_calls[0].tool_name if response.tool_calls else 'none'}'"
            )

        # Validate result if function provided
        if validation_fn and not validation_fn(response):
            raise ValueError("Tool result validation failed")

        return response

    def ask_with_conversation(
        self,
        prompt: str | list[LLMMessage],
        max_rounds: int = 5,
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        is_finished_callback: Callable[[list[LLMMessage]], bool] | None = None,
        **llm_kwargs,
    ) -> LLMResponse:
        """Ask LLM with conversational flow allowing multiple tool calls.

        Args:
            prompt: User prompt string or list of LLMMessage objects
            max_rounds: Maximum conversation rounds (default 5)
            tools: Available tool schemas (defaults to all library tools)
            system_prompt: System prompt override
            is_finished_callback: Optional callback to check if task is complete
            **llm_kwargs: Additional arguments passed to LLM client

        Returns:
            LLMResponse with all tool calls and conversation history
        """
        start_time = time.time()

        # Use provided tools or get all from library
        if tools is None:
            tools = self.function_library.get_schemas()

        # Initialize conversation
        if isinstance(prompt, str):
            messages = [
                LLMMessage(role=Role.SYSTEM, content=system_prompt or self.default_system_prompt),
                LLMMessage(role=Role.USER, content=prompt),
            ]
        else:
            messages = prompt

        all_tool_calls = []

        for _ in range(max_rounds):
            # Get LLM response
            response = self.llm_client.completion(
                model=self.model, messages=messages, tools=tools, **llm_kwargs
            )

            # Add assistant message to conversation
            messages.extend(response.messages[len(messages) :])

            # Check if task is finished using callback or completion marker
            if is_finished_callback and is_finished_callback(messages):
                break

            # Check for completion marker in response content
            if response.messages and "<<DONE>>" in response.messages[-1].content:
                break

            # If no tool calls, conversation is done
            if not response.tool_calls:
                break

            # Execute each tool call and add results to conversation
            for tool_call in response.tool_calls:
                if tool_call.tool_result is None:
                    tool_call.tool_result = self.function_library.call(tool_call.tool_name, tool_call.tool_args)

                all_tool_calls.append(tool_call)

                # Add tool result to conversation
                if isinstance(tool_call.tool_result, str):
                    tool_result_str = tool_call.tool_result
                else:
                    try:
                        # Try to convert to dict if it's a Pydantic model
                        if hasattr(tool_call.tool_result, "model_dump"):
                            tool_result_str = json.dumps(tool_call.tool_result.model_dump())
                        elif hasattr(tool_call.tool_result, "__dict__"):
                            tool_result_str = json.dumps(tool_call.tool_result.__dict__)
                        else:
                            tool_result_str = str(tool_call.tool_result)
                    except (TypeError, AttributeError):
                        tool_result_str = str(tool_call.tool_result)

                messages.append(
                    LLMMessage(
                        role=Role.TOOL,
                        content=tool_result_str,
                        tool_call_id=tool_call.id or f"call_{len(all_tool_calls)}",
                    )
                )

        response_time = int((time.time() - start_time) * 1000)

        return LLMResponse(
            messages=messages,
            tool_calls=all_tool_calls,
            response_time_ms=response_time,
            raw_response=response.raw_response,
        )


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
