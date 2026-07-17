"""
Model provider smoke test for Agent Forge.

Verifies that the configured model provider works through OpenAI-compatible endpoint with:
- Explicit model selection
- Structured output parsing
- Function tool calls
- Multi-turn tool results
- Sanitized error handling
"""

import json
import os

import pytest
from dotenv import load_dotenv


def _get_model_config() -> tuple[str, str, str, str]:
    """Get model configuration from environment."""
    load_dotenv()

    provider = os.getenv("MODEL_PROVIDER", "gemini").lower()

    if provider == "meta":
        api_key = os.getenv("META_API_KEY", "")
        model_id = os.getenv("MODEL_NAME", "muse-spark-1.1")
        base_url = os.getenv("MODEL_BASE_URL", "https://api.meta.ai/v1/")
    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "")
        model_id = os.getenv("MODEL_NAME", "gemini-2.5-pro")
        base_url = os.getenv(
            "MODEL_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        model_id = os.getenv("MODEL_NAME", "gpt-4")
        base_url = os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1/")
    else:
        api_key = os.getenv(f"{provider.upper()}_API_KEY", "")
        model_id = os.getenv("MODEL_NAME", "")
        base_url = os.getenv("MODEL_BASE_URL", "")

    return provider, api_key, model_id, base_url


@pytest.mark.integration
def test_gemini_smoke() -> None:
    """
    Smoke test for model provider compatibility through OpenAI-compatible endpoint.

    This test MUST pass before dependency versions are locked.
    """
    provider, api_key, model_id, base_url = _get_model_config()

    if not api_key:
        pytest.skip(f"API key not configured for provider '{provider}'")

    if not base_url:
        pytest.skip(f"MODEL_BASE_URL not configured for provider '{provider}'")

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)

    # Test 1: Explicit model selection
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "user",
                    "content": "Respond with exactly: 'Model selection works'",
                }
            ],
            temperature=0.0,
            max_tokens=1024,
        )

        assert response.choices[0].message.content is not None
        assert "Model selection works" in response.choices[0].message.content
        print(f"✓ Test 1: Model selection works ({provider}/{model_id})")

    except Exception as e:
        pytest.fail(f"Model selection test failed ({provider}/{model_id}): {e}")

    # Test 2: Structured output parsing
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "user",
                    "content": 'Return a JSON object with exactly this structure: {"status": "ok", "value": 42}',
                }
            ],
            temperature=0.0,
            max_tokens=1024,
        )

        content = response.choices[0].message.content
        assert content is not None

        # Parse as JSON - strip markdown code fences if present
        json_str = content.strip()
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        parsed = json.loads(json_str)
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
            model=model_id,
            messages=[
                {
                    "role": "user",
                    "content": "Call the test_function with name='Agent Forge'",
                }
            ],
            tools=tools,
            temperature=0.0,
            max_tokens=1024,
        )

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
        tool_result = {"greeting": "Hello, Agent Forge!"}

        response = client.chat.completions.create(
            model=model_id,
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
            max_tokens=1024,
        )

        content = response.choices[0].message.content
        assert content is not None
        assert "Agent Forge" in content or "Hello" in content
        print("✓ Test 4: Multi-turn tool result works")

    except Exception as e:
        pytest.fail(f"Multi-turn tool result test failed: {e}")

    # Test 5: Sanitized error handling
    try:
        with pytest.raises(Exception) as exc_info:
            client.chat.completions.create(
                model=model_id, messages=[], temperature=0.0, max_tokens=100
            )

        # Verify API key is NOT in error message
        if api_key and len(api_key) > 8:
            key_fragment = api_key[4:12]
            assert key_fragment not in str(exc_info.value), "API key leaked in error message"

        print("✓ Test 5: Sanitized error handling works")

    except AssertionError:
        raise
    except Exception as e:
        pytest.fail(f"Error handling test failed: {e}")

    print(f"\n✅ Model provider smoke test: PASS ({provider}/{model_id})")
    print("All smoke tests passed. Safe to lock dependency versions.")


if __name__ == "__main__":
    test_gemini_smoke()
