#!/usr/bin/env python3

import json
import re
from collections import defaultdict
from pathlib import Path

import litellm
from litellm import token_counter


def get_precise_token_counts(model, messages):
    """Get precise token counts using litellm.token_counter."""
    try:
        # Separate prompt tokens (non-assistant messages) and completion tokens
        prompt_messages = [msg for msg in messages if msg.get("role") != "assistant"]
        completion_messages = [msg for msg in messages if msg.get("role") == "assistant"]

        prompt_tokens = token_counter(model=model, messages=prompt_messages) if prompt_messages else 0
        completion_tokens = token_counter(model=model, messages=completion_messages) if completion_messages else 0

        return prompt_tokens, completion_tokens
    except Exception:
        # Fallback to character-based estimation if token_counter fails
        prompt_chars = sum(len(str(msg.get("content", ""))) for msg in messages if msg.get("role") != "assistant")
        completion_chars = sum(len(str(msg.get("content", ""))) for msg in messages if msg.get("role") == "assistant")
        return prompt_chars // 4, max(completion_chars // 4, 1)


def analyze_costs_by_operation():
    """Analyze costs broken down by operation type and symbol."""
    logs_dir = Path("logs/litellm")

    # Find all log files
    log_files = list(logs_dir.glob("*.json"))
    regular_logs = [log for log in log_files]

    print(f"Analyzing {len(regular_logs)} LLM sessions for detailed cost breakdown")

    # Categorize by operation type
    operation_costs = defaultdict(float)
    operation_calls = defaultdict(int)
    operation_tokens = defaultdict(lambda: {"prompt": 0, "completion": 0})

    symbol_costs = defaultdict(float)
    symbol_calls = defaultdict(int)

    model_costs = defaultdict(float)
    model_calls = defaultdict(int)

    for log_file in sorted(regular_logs):
        try:
            with open(log_file) as f:
                log_data = json.load(f)

            model = log_data.get("model", "unknown")
            messages = log_data.get("messages", [])

            # Get precise token counts
            prompt_tokens, completion_tokens = get_precise_token_counts(model, messages)

            # Use litellm.completion_cost for accurate pricing
            # Create a mock response object for cost calculation
            mock_response = {
                "model": model,
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }
            cost = litellm.completion_cost(completion_response=mock_response)  # type: ignore

            # Categorize by operation type
            operation_type = "unknown"
            symbol_name = "unknown"

            # Look for operation indicators in messages
            for msg in messages:
                content = str(msg.get("content", ""))

                if "STUB implementations" in content:
                    operation_type = "stub_generation"
                elif "fuzz test" in content:
                    operation_type = "fuzz_test_generation"
                elif "implementation for the following C symbol" in content:
                    operation_type = "full_implementation"
                elif "system" in msg.get("role", ""):
                    if "STUB" in content:
                        operation_type = "stub_generation"
                    elif "fuzz test" in content:
                        operation_type = "fuzz_test_generation"
                    elif "implementation" in content:
                        operation_type = "full_implementation"

                # Extract symbol name
                symbol_match = re.search(r"Symbol:\s*(\w+)", content)
                if symbol_match:
                    symbol_name = symbol_match.group(1)

            # Aggregate data
            operation_costs[operation_type] += cost
            operation_calls[operation_type] += 1
            operation_tokens[operation_type]["prompt"] += prompt_tokens
            operation_tokens[operation_type]["completion"] += completion_tokens

            symbol_costs[symbol_name] += cost
            symbol_calls[symbol_name] += 1

            model_costs[model] += cost
            model_calls[model] += 1

        except Exception as e:
            print(f"Error processing {log_file}: {e}")
            continue

    # Print detailed analysis
    print("\n=== DETAILED COST ANALYSIS ===")

    total_cost = sum(operation_costs.values())
    total_calls = sum(operation_calls.values())

    print(f"Total estimated cost: ${total_cost:.4f}")
    print(f"Total calls: {total_calls}")
    print(f"Average cost per call: ${total_cost/total_calls:.4f}")

    print("\n--- COST BY OPERATION TYPE ---")
    for op_type in sorted(
        operation_costs.keys(), key=lambda x: operation_costs[x], reverse=True
    ):
        cost = operation_costs[op_type]
        calls = operation_calls[op_type]
        tokens = operation_tokens[op_type]

        print(f"{op_type}:")
        print(f"  Total cost: ${cost:.4f} ({cost/total_cost*100:.1f}%)")
        print(f"  Calls: {calls} ({calls/total_calls*100:.1f}%)")
        print(f"  Avg cost per call: ${cost/calls:.4f}")
        print(
            f"  Estimated tokens: {tokens['prompt'] + tokens['completion']:,} (prompt: {tokens['prompt']:,}, completion: {tokens['completion']:,})"
        )
        print()

    print("--- COST BY MODEL ---")
    for model in sorted(model_costs.keys(), key=lambda x: model_costs[x], reverse=True):
        cost = model_costs[model]
        calls = model_calls[model]
        print(f"{model}:")
        print(f"  Total cost: ${cost:.4f} ({cost/total_cost*100:.1f}%)")
        print(f"  Calls: {calls} ({calls/total_calls*100:.1f}%)")
        print(f"  Avg cost per call: ${cost/calls:.4f}")
        print()

    print("--- TOP 10 MOST EXPENSIVE SYMBOLS ---")
    top_symbols = sorted(symbol_costs.items(), key=lambda x: x[1], reverse=True)[:10]
    for symbol, cost in top_symbols:
        calls = symbol_calls[symbol]
        print(f"{symbol}: ${cost:.4f} ({calls} calls, ${cost/calls:.4f} avg)")

    print("\n--- COST EFFICIENCY ANALYSIS ---")
    if operation_calls["stub_generation"] > 0:
        stub_cost = (
            operation_costs["stub_generation"] / operation_calls["stub_generation"]
        )
        print(f"Stub generation avg cost: ${stub_cost:.4f}")

    if operation_calls["fuzz_test_generation"] > 0:
        fuzz_cost = (
            operation_costs["fuzz_test_generation"]
            / operation_calls["fuzz_test_generation"]
        )
        print(f"Fuzz test generation avg cost: ${fuzz_cost:.4f}")

    if operation_calls["full_implementation"] > 0:
        impl_cost = (
            operation_costs["full_implementation"]
            / operation_calls["full_implementation"]
        )
        print(f"Full implementation avg cost: ${impl_cost:.4f}")


if __name__ == "__main__":
    analyze_costs_by_operation()
