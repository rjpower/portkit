"""Test the LLM module with expected workflow."""

from portkit.tidyllm.library import FunctionLibrary
from portkit.tidyllm.llm import LLMClient, LLMHelper, LLMMessage, LLMResponse, Role, ToolCall
from portkit.tidyllm.registry import Registry


def test_conversation_workflow():
    """Test accumulating conversation history across multiple calls."""
    
    # Create a custom mock client that responds based on last user message
    class CustomMockClient:
        def completion(self, model, messages, tools, **kwargs):
            # Get the last user message
            last_user_msg = next((msg for msg in reversed(messages) if msg.role == Role.USER), None)
            if not last_user_msg:
                raise ValueError("No user message found")
                
            if "2+2" in last_user_msg.content:
                assistant_msg = LLMMessage(
                    role=Role.ASSISTANT,
                    content="I'll calculate that for you.",
                    tool_calls=[ToolCall(
                        tool_name="calculator",
                        tool_args={"expression": "2+2"},
                        tool_result=None,
                        id="call_1"
                    )]
                )
            elif "multiply" in last_user_msg.content:
                assistant_msg = LLMMessage(
                    role=Role.ASSISTANT,
                    content="I'll multiply the previous result by 3.",
                    tool_calls=[ToolCall(
                        tool_name="calculator",
                        tool_args={"expression": "4*3"},
                        tool_result=None,
                        id="call_2"
                    )]
                )
            else:
                assistant_msg = LLMMessage(
                    role=Role.ASSISTANT,
                    content="I don't understand."
                )
                
            return LLMResponse(
                messages=messages + [assistant_msg],
                tool_calls=assistant_msg.tool_calls,
                response_time_ms=0
            )
    
    client = CustomMockClient()
    
    # Create a test registry and register tools
    test_registry = Registry()
    
    def calculator(expression: str) -> float:
        """Calculate a math expression.
        
        Args:
            expression: Math expression to evaluate
        """
        return eval(expression)
    
    test_registry.register(calculator)
    
    # Create function library with the test registry
    library = FunctionLibrary(registry=test_registry)
    
    # Create LLM helper
    helper = LLMHelper("mock-gpt", library, client)
    
    # First call
    response1 = helper.ask("What's 2+2?")
    assert len(response1.tool_calls) == 1
    assert response1.tool_calls[0].tool_name == "calculator"
    assert response1.tool_calls[0].tool_result == 4
    
    # Check message history
    assert len(response1.messages) == 3  # system, user, assistant
    assert response1.messages[0].role == Role.SYSTEM
    assert response1.messages[1].role == Role.USER
    assert response1.messages[1].content == "What's 2+2?"
    assert response1.messages[2].role == Role.ASSISTANT
    assert len(response1.messages[2].tool_calls) == 1
    
    # Build conversation for second call
    conversation = response1.messages + [
        LLMMessage(
            role=Role.TOOL,
            content="4",
            tool_call_id="call_1"
        ),
        LLMMessage(
            role=Role.USER,
            content="Now multiply that by 3"
        )
    ]
    
    # Second call with accumulated history
    response2 = helper.ask(conversation)
    assert len(response2.tool_calls) == 1
    assert response2.tool_calls[0].tool_name == "calculator"
    assert response2.tool_calls[0].tool_result == 12
    
    # Check full conversation history
    assert len(response2.messages) == 6  # Previous 5 + new assistant
    assert response2.messages[-1].role == Role.ASSISTANT
    assert "multiply" in response2.messages[-1].content.lower()


def test_ask_with_conversation():
    """Test the ask_with_conversation method for multi-turn interactions."""
    
    # Create mock client that responds with tool calls then completion
    class ConversationMockClient(LLMClient):
        def __init__(self):
            self.call_count = 0
            
        def completion(self, model, messages, tools, **kwargs):
            self.call_count += 1
            
            if self.call_count == 1:
                # First call - read file
                assistant_msg = LLMMessage(
                    role=Role.ASSISTANT,
                    content="I'll read the file first.",
                    tool_calls=[ToolCall(
                        tool_name="read_file",
                        tool_args={"path": "test.txt"},
                        tool_result=None,
                        id="call_1"
                    )]
                )
                return LLMResponse(
                    messages=messages + [assistant_msg],
                    tool_calls=assistant_msg.tool_calls,
                    response_time_ms=0
                )
            elif self.call_count == 2:
                # Second call - patch file
                assistant_msg = LLMMessage(
                    role=Role.ASSISTANT,
                    content="Now I'll update the file.",
                    tool_calls=[ToolCall(
                        tool_name="patch_file",
                        tool_args={
                            "path": "test.txt",
                            "old": "Hello",
                            "new": "Hi"
                        },
                        tool_result=None,
                        id="call_2"
                    )]
                )
                return LLMResponse(
                    messages=messages + [assistant_msg],
                    tool_calls=assistant_msg.tool_calls,
                    response_time_ms=0
                )
            else:
                # Final call - done
                assistant_msg = LLMMessage(
                    role=Role.ASSISTANT,
                    content="I've successfully updated the file. <<DONE>>"
                )
                return LLMResponse(
                    messages=messages + [assistant_msg],
                    tool_calls=[],
                    response_time_ms=0
                )
    
    client = ConversationMockClient()
    
    # Create a test registry and register tools
    test_registry = Registry()
    
    def read_file(path: str) -> str:
        """Read a file.
        
        Args:
            path: Path to the file
        """
        return "Hello world"
    
    def patch_file(path: str, old: str, new: str) -> str:
        """Patch a file.
        
        Args:
            path: Path to the file
            old: Text to replace
            new: New text
        """
        return "File patched successfully"
    
    test_registry.register(read_file)
    test_registry.register(patch_file)
    
    # Create function library with the test registry
    library = FunctionLibrary(registry=test_registry)
    
    helper = LLMHelper(model="mock-gpt", function_library=library, llm_client=client)
    
    # Test conversation
    response = helper.ask_with_conversation(
        "Read test.txt and change 'Hello' to 'Hi'",
        max_rounds=5
    )
    
    assert len(response.tool_calls) == 2
    assert response.tool_calls[0].tool_name == "read_file"
    assert response.tool_calls[0].tool_result == "Hello world"
    assert response.tool_calls[1].tool_name == "patch_file"
    assert response.tool_calls[1].tool_result == "File patched successfully"
    
    # Check messages include all turns
    assert any("<<DONE>>" in msg.content for msg in response.messages if msg.role == Role.ASSISTANT)
    

def test_message_structure():
    """Test the LLMMessage structure and conversions."""
    
    # Create messages
    messages = [
        LLMMessage(role=Role.SYSTEM, content="You are helpful"),
        LLMMessage(role=Role.USER, content="Hello"),
        LLMMessage(
            role=Role.ASSISTANT,
            content="I'll help you",
            tool_calls=[
                ToolCall(
                    tool_name="test_tool",
                    tool_args={"param": "value"},
                    tool_result=None,
                    id="call_123"
                )
            ]
        ),
        LLMMessage(
            role=Role.TOOL,
            content="Tool result",
            tool_call_id="call_123"
        )
    ]
    
    # Convert to dicts
    from portkit.tidyllm.llm import _llm_messages_to_dicts
    dicts = _llm_messages_to_dicts(messages)
    
    assert len(dicts) == 4
    assert dicts[0] == {"role": "system", "content": "You are helpful"}
    assert dicts[1] == {"role": "user", "content": "Hello"}
    assert dicts[2]["role"] == "assistant"
    assert dicts[2]["content"] == "I'll help you"
    assert len(dicts[2]["tool_calls"]) == 1
    assert dicts[2]["tool_calls"][0]["id"] == "call_123"
    assert dicts[2]["tool_calls"][0]["function"]["name"] == "test_tool"
    assert dicts[3] == {"role": "tool", "content": "Tool result", "tool_call_id": "call_123"}


if __name__ == "__main__":
    test_message_structure()
    print("✓ Message structure test passed")
    
    test_conversation_workflow()
    print("✓ Conversation workflow test passed")
    
    test_ask_with_conversation()
    print("✓ Ask with conversation test passed")
    
    print("\nAll tests passed!")