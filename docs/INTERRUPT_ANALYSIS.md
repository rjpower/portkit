# Analysis of Interrupt Handling Problem

## Problem Statement

The interrupt handling system in portkit should allow users to press ESC during LLM operations to interrupt the process, provide feedback, and continue with the conversation. Currently, the prompt appears but the process doesn't actually interrupt - it continues running in the background.

## Code Analysis

### Current Architecture

**Entry Point: `implfuzz.py`**
- `main()` → `main_with_editor()` → `run_traversal_pipeline()` → `port_symbol()` → `generate_unified_implementation()`
- Line 347: `await call_with_retry(messages, TOOL_HANDLER, _completion_fn, ctx=ctx)`

**Core LLM Loop: `tinyagent.py`**
- `call_with_retry()` (299-392): Main retry loop with task completion detection
- Line 340: `call_result = await run_interruptible_llm_call(ctx.console, call_with_tools, ...)`
- `call_with_tools()` (174-292): Actual LLM streaming and tool execution
- Lines 219-253: Streaming loop (`async for chunk in response`)
- Lines 284-290: Tool execution loop

**Interrupt System: `console.py`**
- `Console` class with threading-based interrupt monitoring
- `interruptible_context()` context manager starts monitoring thread
- `_monitor_input()` runs in separate thread, watches for ESC key
- `InterruptibleLLMCall` wraps LLM calls with async cancellation
- `run_interruptible_llm_call()` orchestrates the interruptible execution

### Current Flow

1. **Setup**: `interruptible_context()` starts `_monitor_input()` thread
2. **LLM Call**: `InterruptibleLLMCall.run()` creates two async tasks:
   - `_call_task`: Runs `call_with_tools()`
   - `interrupt_task`: Polls `console.check_interrupt()` every 0.1s
3. **Streaming**: `call_with_tools()` streams LLM response via `litellm.acompletion()`
4. **Interrupt Detection**: When ESC pressed:
   - Thread calls `_thread.interrupt_main()` 
   - Should raise `KeyboardInterrupt` in main thread
   - Async tasks should be cancelled

### Root Cause Analysis

The problem is in the **interrupt propagation mechanism**:

1. **Thread vs Async Mismatch**: The `_monitor_input()` thread calls `_thread.interrupt_main()`, but this may not properly interrupt the async streaming loop in `call_with_tools()`

2. **Streaming Loop Isolation**: The `async for chunk in response` loop (line 219) doesn't check for cancellation or interrupts. `litellm.acompletion()` may not handle `KeyboardInterrupt` or task cancellation properly.

3. **Tool Execution Gap**: If interrupt occurs during tool execution (lines 284-290), the synchronous `tools.run()` calls can't be cancelled by async mechanisms.

4. **Race Conditions**: Multiple interrupt mechanisms (flag-based, exception-based, task cancellation) create timing issues.

## Issues with Current Design

### 1. **Overcomplicated Architecture**
- Threading + async + flag-based + exception-based interrupts
- Multiple layers of abstraction (`Console`, `InterruptibleLLMCall`, `run_interruptible_llm_call`)
- Redundant interrupt checking mechanisms

### 2. **Poor Separation of Concerns**
- `Console` class mixes UI concerns with interrupt handling
- Threading logic embedded in console abstraction
- Interrupt logic scattered across multiple files

### 3. **Unreliable Cancellation**
- `_thread.interrupt_main()` doesn't guarantee async task cancellation
- `litellm` streaming may not respect `KeyboardInterrupt`
- Tool execution is synchronous and uninterruptible

### 4. **Complex Control Flow**
- Multiple exception types (`InterruptSignal`, `KeyboardInterrupt`)
- Complex async task orchestration in `InterruptibleLLMCall`
- Unclear error handling and recovery paths

## Proposed Solution: Simplified Interrupt Architecture

### Core Principle
**Use signal-based interruption with proper async/await patterns, eliminate threading complexity.**

### New Design

1. **Single Interrupt Mechanism**: Use `signal.SIGINT` with proper async handling
2. **Stream-Level Checking**: Add interrupt checks directly in the streaming loop
3. **Simplified Console**: Remove threading, focus on UI concerns
4. **Clean Exception Handling**: Single exception type with clear propagation

### Implementation Plan

#### Phase 1: Simplify Console Class
```python
class Console:
    def __init__(self):
        self._rich = RichConsole()
        self._interrupt_requested = False
        self._user_message = ""
    
    def request_interrupt(self, message: str = ""):
        """Called by signal handler to request interrupt."""
        self._interrupt_requested = True
        self._user_message = message
    
    def check_interrupt(self) -> str | None:
        """Check if interrupt was requested."""
        if self._interrupt_requested:
            self._interrupt_requested = False
            message = self._user_message
            self._user_message = ""
            return message
        return None
```

#### Phase 2: Signal-Based Interrupt Handler
```python
import signal
import sys

class InterruptHandler:
    def __init__(self, console: Console):
        self.console = console
        self.original_handler = None
    
    def setup(self):
        """Setup signal handler for SIGINT."""
        self.original_handler = signal.signal(signal.SIGINT, self._handle_interrupt)
    
    def cleanup(self):
        """Restore original signal handler."""
        if self.original_handler:
            signal.signal(signal.SIGINT, self.original_handler)
    
    def _handle_interrupt(self, signum, frame):
        """Handle SIGINT by prompting user and requesting interrupt."""
        print("\n⚠️  Process interrupted! Enter your message (or press Enter to continue):")
        try:
            user_input = input().strip()
            self.console.request_interrupt(user_input)
        except (EOFError, KeyboardInterrupt):
            self.console.request_interrupt("")
```

#### Phase 3: Modify Streaming Loop
```python
async def call_with_tools(...):
    # ... setup code ...
    
    async for chunk in response:
        # Check for interrupt at each chunk
        message = ctx.console.check_interrupt()
        if message is not None:
            raise InterruptSignal(message)
        
        # ... process chunk ...
```

#### Phase 4: Simplified Call Structure
```python
async def call_with_retry(...):
    handler = InterruptHandler(ctx.console)
    handler.setup()
    
    try:
        for attempt in range(max_llm_calls):
            try:
                messages = await call_with_tools(messages, tools, model, project_root, ctx=ctx)
                # ... rest of logic ...
            except InterruptSignal as e:
                if e.user_message:
                    messages.append({"role": "user", "content": e.user_message})
                # ... handle interrupt ...
                continue
    finally:
        handler.cleanup()
```

### Benefits of New Design

1. **Simplicity**: Single interrupt mechanism, no threading
2. **Reliability**: Direct signal handling, predictable cancellation
3. **Performance**: No polling, immediate interrupt detection
4. **Maintainability**: Clear separation of concerns, simple control flow
5. **Debuggability**: Fewer moving parts, easier to trace execution

### Migration Strategy

1. **Phase 1**: Implement new `Console` and `InterruptHandler` classes
2. **Phase 2**: Modify `call_with_tools()` to check interrupts in streaming loop
3. **Phase 3**: Update `call_with_retry()` to use new interrupt system
4. **Phase 4**: Remove old threading-based interrupt code
5. **Phase 5**: Test thoroughly and verify ESC key handling works

This approach eliminates the complex threading/async hybrid system and provides reliable, first-class interrupt support with a much simpler architecture.