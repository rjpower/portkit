# TinyAgent LLM Integration Improvement Specification

**Date**: 2025-06-23
**Author**: Analysis of portkit/tinyagent and portkit/tidyllm integration

## Current State Analysis

### TinyAgent LLM Management (portkit/tinyagent/agent.py)

The current TinyAgent implementation has several areas of complexity that could be simplified by enhancing the TidyLLM `llm.py` module:

#### Current LLM Integration Patterns:

1. **Direct LiteLLM Integration** (lines 129-261):
   - `call_with_tools()` function directly manages LiteLLM streaming API
   - Handles streaming response parsing manually 
   - Custom tool call aggregation logic
   - Manual usage tracking and cost calculation
   - Interrupt handling integrated into streaming loop

2. **Retry Logic** (lines 268-345):
   - `call_with_retry()` implements task completion detection
   - Manual completion status checking via `CompletionProtocol`
   - Custom retry loop with TASK COMPLETE/GIVE UP detection
   - Interrupt handling between retry attempts

3. **Tool Execution** (lines 86-127):
   - `Agent.run()` method handles tool dispatch manually
   - JSON argument parsing and error handling
   - Integration with PortKitAgent for actual tool execution

#### Current TidyLLM LLM Support (portkit/tidyllm/llm.py)

The existing `llm.py` provides basic infrastructure but lacks features needed by TinyAgent:

1. **LLMClient Interface** (lines 24-41):
   - Abstract interface for completion and model listing
   - No streaming support in interface

2. **LiteLLMClient** (lines 44-132):
   - Basic streaming implementation 
   - Simple tool call aggregation
   - No interrupt handling
   - No usage tracking or cost calculation
   - No retry logic

3. **LLMHelper** (lines 257-401):
   - Single-shot tool execution
   - Basic validation support
   - No streaming or interrupt support

## Proposed LLM.py Enhancements

### 1. Streaming Interface Enhancement

**Current Gap**: TinyAgent needs sophisticated streaming with interrupt support, but LLMClient interface doesn't support streaming.

**Proposed Addition**:
```python
@abstractmethod
async def stream_completion(
    self, 
    model: str, 
    messages: list[dict], 
    tools: list[dict],
    interrupt_handler: InterruptHandler | None = None,
    usage_callback: Callable[[dict], None] | None = None,
    **kwargs
) -> AsyncIterator[dict]:
    """Stream completion with interrupt and usage tracking support."""
    pass
```

### 2. Advanced Streaming Client

**Current Gap**: LiteLLMClient lacks interrupt handling, cost tracking, and sophisticated streaming features.

**Proposed Enhancement**:
```python
class AdvancedLiteLLMClient(LLMClient):
    """Enhanced LiteLLM client with streaming, interrupts, and cost tracking."""
    
    def __init__(self, cost_tracker: CostTracker | None = None):
        self.cost_tracker = cost_tracker
    
    async def stream_completion_with_tools(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        interrupt_handler: InterruptHandler | None = None,
        logging_config: LoggingConfig | None = None,
        **kwargs
    ) -> StreamingResponse:
        """Stream completion with full TinyAgent feature set."""
        # Implement sophisticated streaming with:
        # - Interrupt checking on every chunk
        # - Tool call aggregation 
        # - Usage tracking and cost calculation
        # - Request/response logging
        # - Thinking block handling
        # - Error recovery
```

### 3. Retry and Completion Framework

**Current Gap**: TinyAgent implements custom retry logic that could be generalized.

**Proposed Addition**:
```python
class CompletionFramework:
    """Framework for completion with retry, validation, and task tracking."""
    
    def __init__(
        self,
        llm_client: LLMClient,
        function_library: FunctionLibrary,
        completion_detector: CompletionDetector | None = None
    ):
        pass
    
    async def complete_with_retry(
        self,
        initial_messages: list[dict],
        completion_fn: Callable[[bool], TaskStatus],
        max_attempts: int = 25,
        model: str = "gpt-4",
        interrupt_handler: InterruptHandler | None = None
    ) -> CompletionResult:
        """Complete task with retry, validation, and completion detection."""
        # Implement generalized retry logic from TinyAgent
```

### 4. Cost and Usage Tracking

**Current Gap**: TinyAgent has custom cost tracking that could be abstracted.

**Proposed Addition**:
```python
class CostTracker:
    """Track LLM usage costs across completion sessions."""
    
    def __init__(self):
        self.running_cost: float = 0.0
        self.token_usage: dict[str, int] = {}
    
    def track_completion(self, response: dict, model: str) -> float:
        """Track cost and usage from completion response."""
        pass
    
    def get_session_summary(self) -> UsageSummary:
        """Get current session usage summary."""
        pass
```

### 5. Logging and Observability

**Current Gap**: TinyAgent has custom logging that could be standardized.

**Proposed Addition**:
```python
class LLMLogger:
    """Structured logging for LLM completions and tool calls."""
    
    def __init__(self, log_dir: Path = Path("logs/llm")):
        self.log_dir = log_dir
    
    def log_completion_request(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        metadata: dict = None
    ) -> str:
        """Log completion request and return log ID."""
        pass
    
    def log_completion_response(
        self,
        log_id: str,
        response: dict,
        usage: dict = None,
        error: Exception = None
    ):
        """Log completion response with usage data."""
        pass
```

## Files Requiring Updates

### Core Implementation Files:

1. **portkit/tidyllm/llm.py**
   - Add streaming interface methods to `LLMClient` abstract class
   - Implement `AdvancedLiteLLMClient` with full TinyAgent feature set
   - Add `CompletionFramework` class for retry and validation logic
   - Add `CostTracker` and `LLMLogger` utility classes

2. **portkit/tidyllm/__init__.py**
   - Export new classes: `AdvancedLiteLLMClient`, `CompletionFramework`, `CostTracker`, `LLMLogger`

### TinyAgent Migration Files:

3. **portkit/tinyagent/agent.py**
   - Replace `call_with_tools()` with `AdvancedLiteLLMClient.stream_completion_with_tools()`
   - Replace `call_with_retry()` with `CompletionFramework.complete_with_retry()`
   - Simplify `Agent` class to use TidyLLM abstractions
   - Remove direct LiteLLM management code (lines 129-345)

4. **portkit/tinyagent/context.py**
   - Update `PortKitContext` protocol to include cost tracker if needed
   - Consider adding logging configuration

### Integration Files:

5. **portkit/implfuzz.py**
   - Update to use new TidyLLM completion framework
   - Simplify LLM integration code

### Test Files:

6. **tests/test_tidyllm_llm.py** (new)
   - Comprehensive tests for new LLM framework features
   - Test streaming with interrupts
   - Test cost tracking
   - Test retry logic

7. **tests/test_tinyagent_integration.py** (new)
   - Integration tests for TinyAgent using new TidyLLM features
   - Ensure backward compatibility

## Implementation Priority

### Phase 1: Core Infrastructure
1. Enhance `LLMClient` interface with streaming support
2. Implement `AdvancedLiteLLMClient` with interrupt and cost tracking
3. Add comprehensive tests

### Phase 2: Framework Features  
1. Implement `CompletionFramework` with retry logic
2. Add `CostTracker` and `LLMLogger` utilities
3. Test framework integration

### Phase 3: TinyAgent Migration
1. Migrate TinyAgent to use new TidyLLM features
2. Remove redundant LLM management code
3. Ensure feature parity and backward compatibility

### Phase 4: Integration and Cleanup
1. Update implfuzz.py integration
2. Add comprehensive integration tests
3. Documentation updates

## Benefits

1. **Code Reduction**: Remove ~200 lines of complex LLM management from TinyAgent
2. **Reusability**: Other parts of PortKit can use the same LLM infrastructure
3. **Maintainability**: Centralized LLM logic in TidyLLM
4. **Testability**: Better separation of concerns for testing
5. **Extensibility**: Easy to add new LLM providers or features

## Backward Compatibility

- Existing TinyAgent API will remain unchanged
- Current tool registration and execution will work identically
- Migration will be internal implementation change only
- All current PortKit functionality preserved