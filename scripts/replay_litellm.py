#!/usr/bin/env python3

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, cast

import litellm


async def replay_completion(log_data: dict[str, Any]) -> None:
    """Replay a single completion request from logged data."""
    print(f"Replaying completion from {log_data['timestamp']}")
    print(f"Model: {log_data['model']}")
    print(f"Messages: {len(log_data['messages'])} messages")
    print(f"Tools: {len(log_data.get('tools', []))} tools")
    print("-" * 80)

    # Extract the completion parameters
    model = log_data["model"]
    messages = log_data["messages"]
    tools = log_data.get("tools", [])
    stream = log_data.get("stream", True)

    try:
        # Make the completion request
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            tools=tools if tools else None,
            stream=stream,
        )

        if stream:
            # Handle streaming response
            content_parts = []
            tool_calls = []

            async for chunk in cast(litellm.CustomStreamWrapper, response):
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    content_parts.append(content)
                    sys.stdout.write(content)
                    sys.stdout.flush()
                if chunk.choices[0].delta.tool_calls:
                    for tool_call in chunk.choices[0].delta.tool_calls:
                        tool_calls.append(tool_call)

            print()  # New line after streaming

            if tool_calls:
                print("\nTool calls detected:")
                for tool_call in tool_calls:
                    print(f"  - {tool_call.function.name}: {tool_call.function.arguments}")

        else:
            # Handle non-streaming response
            message = response.choices[0].message  # type: ignore
            if hasattr(message, 'content') and message.content:
                print(message.content)
            if hasattr(message, 'tool_calls') and message.tool_calls:
                print("\nTool calls detected:")
                for tool_call in message.tool_calls:
                    print(f"  - {tool_call.function.name}: {tool_call.function.arguments}")

    except Exception as e:
        print(f"Error during completion: {e}")
        return

    print("\n" + "=" * 80)


async def main():
    parser = argparse.ArgumentParser(description="Replay logged litellm completion requests")
    parser.add_argument(
        "log_files",
        nargs="+",
        help="JSON log files to replay",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between replays in seconds (default: 2.0)",
    )

    args = parser.parse_args()

    for log_file_path in args.log_files:
        log_file = Path(log_file_path)
        
        if not log_file.exists():
            print(f"Error: Log file {log_file} does not exist")
            continue

        try:
            with open(log_file) as f:
                log_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {log_file}: {e}")
            continue
        except Exception as e:
            print(f"Error reading {log_file}: {e}")
            continue

        await replay_completion(log_data)
        
        # Add delay between replays if there are more files
        if log_file_path != args.log_files[-1]:
            print(f"Waiting {args.delay} seconds before next replay...")
            await asyncio.sleep(args.delay)


if __name__ == "__main__":
    asyncio.run(main())
