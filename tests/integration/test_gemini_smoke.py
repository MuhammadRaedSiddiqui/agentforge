"""
Gemini compatibility smoke test for Agent Forge.

Verifies that Gemini 2.5 Pro works through OpenAI-compatible endpoint with:
- Explicit model selection
- Structured output parsing
- Function tool calls
- Multi-turn tool results
- Sanitized error handling
"""

import json
import os
from typing import Any

import pytest


@pytest.mark.integration
def test_gemini_smoke() -> None:
    """
    Smoke test for Gemini compatibility through OpenAI-compatible endpoint.

    This test MUST pass before dependency versions are locked.
    """
    # Check for API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not configured")

    # Import here to allow graceful skip if not configured
    from openai import OpenAI

    # Test 1: Explicit model selection
    client = OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    try:
        response = client.chat.completions.create(
            model="gemini-2.5-pro",
            messages=[
                {
                    "role": "user",
                    "content": "Respond with exactly: 'Model selection works'",
                }
            ],
            temperature=0.0,
            max_tokens=100,
        )

        assert response.choices[0].message.content is not None
        assert "Model selection works" in response.choices[0].message.content
        print("✓ Test 1: Explicit model selection works")

    except Exception as e:
        pytest.fail(f"Model selection test failed: {e}")

    # Test 2: Structured output parsing (using response_format if supported, or validate JSON)
    try:
        response = client.chat.completions.create(
            model="gemini-2.5-pro",
            messages=[
                {
                    "role": "user",
                    "content": 'Return a JSON object with exactly this structure: {"status": "ok", "value": 42}',
                }
            ],
            temperature=0.0,
            max_tokens=100,
        )

        content = response.choices[0].message.content
        assert content is not None

        # Parse as JSON
        parsed = json.loads(content)
        assert "status" in parsed
        assert "value" in parsed
        print("✓ Test 2: Structured output parsing works")

    except Exception as e:
        pytest.fail(f"Structured output test failed: {e}")

    # Test 3: Function tool call
    try:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_function",
                    "description": "A test function that returns a greeting",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "The name to greet",
                            }
                        },
                        "required": ["name"],
                    },
                },
            }
        ]

        response = client.chat.completions.create(
            model="gemini-2.5-pro",
            messages=[
                {
                    "role": "user",
                    "content": "Call the test_function with name='Agent Forge'",
                }
            ],
            tools=tools,
            temperature=0.0,
            max_tokens=200,
        )

        # Check if tool was called
        message = response.choices[0].message
        if message.tool_calls:
            assert len(message.tool_calls) > 0
            tool_call = message.tool_calls[0]
            assert tool_call.function.name == "test_function"
            args = json.loads(tool_call.function.arguments)
            assert "name" in args
            print("✓ Test 3: Function tool call works")
        else:
            pytest.fail("Model did not call the function tool")

    except Exception as e:
        pytest.fail(f"Function tool test failed: {e}")

    # Test 4: Multi-turn tool result
    try:
        # Simulate tool execution result
        tool_result = {"greeting": "Hello, Agent Forge!"}

        response = client.chat.completions.create(
            model="gemini-2.5-pro",
            messages=[
                {
                    "role": "user",
                    "content": "Call the test_function with name='Agent Forge'",
                },
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_test_1",
                            "type": "function",
                            "function": {
                                "name": "test_function",
                                "arguments": '{"name": "Agent Forge"}',
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "content": json.dumps(tool_result),
                    "tool_call_id": "call_test_1",
                },
                {"role": "user", "content": "What was the greeting?"},
            ],
            tools=tools,
            temperature=0.0,
            max_tokens=200,
        )

        content = response.choices[0].message.content
        assert content is not None
        assert "Agent Forge" in content or "Hello" in content
        print("✓ Test 4: Multi-turn tool result works")

    except Exception as e:
        pytest.fail(f"Multi-turn tool result test failed: {e}")

    # Test 5: Sanitized error handling (test with invalid request)
    try:
        # Intentionally invalid request - empty messages
        with pytest.raises(Exception) as exc_info:
            client.chat.completions.create(
                model="gemini-2.5-pro", messages=[], temperature=0.0, max_tokens=100
            )

        error_message = str(exc_info.value).lower()

        # Verify API key is NOT in error message
        if api_key and len(api_key) > 8:
            # Check a substring that would be recognizable
            key_fragment = api_key[4:12]
            assert key_fragment not in str(exc_info.value), "API key leaked in error message"

        print("✓ Test 5: Sanitized error handling works")

    except AssertionError:
        raise
    except Exception as e:
        pytest.fail(f"Error handling test failed: {e}")

    print("\n✅ Gemini compatibility: PASS")
    print("All smoke tests passed. Safe to lock dependency versions.")


if __name__ == "__main__":
    # Allow running directly for manual testing
    test_gemini_smoke()
