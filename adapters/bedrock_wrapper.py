"""
Amazon Bedrock model wrapper for Agent Forge.

Uses the Bedrock Converse API for chat completions and function calling.
Supports Claude, Llama, Mistral, and other Bedrock-hosted models.
"""

import json
import os
from typing import Any

import boto3


class BedrockModelWrapper:
    """
    Wrapper for Amazon Bedrock's Converse API.

    Provides the same interface as ModelWrapper but uses native Bedrock
    auth (SigV4 via boto3) and supports forced tool calling.
    """

    def __init__(
        self,
        model_id: str,
        region_name: str,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ):
        if not model_id:
            raise ValueError("BEDROCK_MODEL_ID is required")

        self.model_id = model_id
        self.provider = "bedrock"

        session_kwargs: dict[str, str] = {"region_name": region_name}
        if aws_access_key_id and aws_secret_access_key:
            session_kwargs["aws_access_key_id"] = aws_access_key_id
            session_kwargs["aws_secret_access_key"] = aws_secret_access_key

        session = boto3.Session(**session_kwargs)
        self._client = session.client("bedrock-runtime")

        self._verify_model_availability()

    def _verify_model_availability(self) -> None:
        try:
            response = self._client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": "test"}]}],
                inferenceConfig={"maxTokens": 5, "temperature": 0.0},
            )
            if not response.get("output", {}).get("message"):
                raise ConnectionError(
                    f"Bedrock model {self.model_id} returned empty response"
                )
        except self._client.exceptions.ValidationException as e:
            raise ConnectionError(f"Bedrock model {self.model_id} not available: {e}") from e
        except Exception as e:
            if "ValidationException" in str(type(e).__name__) or "AccessDeniedException" in str(e):
                raise ConnectionError(f"Bedrock model {self.model_id} access denied: {e}") from e
            raise ConnectionError(
                f"Failed to verify Bedrock model {self.model_id}: {e}"
            ) from e

    @property
    def client(self) -> Any:
        return self._client

    def get_model_id(self) -> str:
        return self.model_id

    def get_provider(self) -> str:
        return self.provider

    def create_completion(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        converse_messages, system_prompts = self._convert_messages(messages)

        converse_kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": converse_messages,
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        }

        if system_prompts:
            converse_kwargs["system"] = system_prompts

        if tools:
            converse_kwargs["toolConfig"] = self._build_tool_config(tools, tool_choice)

        response = self._client.converse(**converse_kwargs)
        return self._to_openai_format(response)

    def create_completion_with_retry(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        max_retries: int = 2,
        **kwargs: Any,
    ) -> Any:
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return self.create_completion(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    **kwargs,
                )
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    import time
                    time.sleep(2**attempt)
                    continue
        raise Exception(f"Failed after {max_retries + 1} attempts: {last_error}") from last_error

    def _convert_messages(
        self, messages: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """Convert OpenAI-format messages to Bedrock Converse format."""
        converse_messages: list[dict[str, Any]] = []
        system_prompts: list[dict[str, str]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_prompts.append({"text": content})
            elif role == "user":
                converse_messages.append({
                    "role": "user",
                    "content": [{"text": content}],
                })
            elif role == "assistant":
                converse_messages.append({
                    "role": "assistant",
                    "content": [{"text": content}],
                })

        if not converse_messages:
            converse_messages.append({
                "role": "user",
                "content": [{"text": "Hello"}],
            })

        return converse_messages, system_prompts

    def _build_tool_config(
        self,
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Convert OpenAI tool format to Bedrock toolConfig."""
        bedrock_tools: list[dict[str, Any]] = []

        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                bedrock_tools.append({
                    "toolSpec": {
                        "name": func["name"],
                        "description": func.get("description", ""),
                        "inputSchema": {
                            "json": func.get("parameters", {"type": "object", "properties": {}})
                        },
                    }
                })

        config: dict[str, Any] = {"tools": bedrock_tools}

        if tool_choice:
            func_name = tool_choice.get("function", {}).get("name")
            if func_name:
                config["toolChoice"] = {"tool": {"name": func_name}}
            else:
                config["toolChoice"] = {"any": {}}
        else:
            config["toolChoice"] = {"auto": {}}

        return config

    def _to_openai_format(self, response: dict[str, Any]) -> Any:
        """Convert Bedrock Converse response to OpenAI-compatible format."""
        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])

        text_content = ""
        tool_calls: list[Any] = []

        for block in content_blocks:
            if "text" in block:
                text_content += block["text"]
            elif "toolUse" in block:
                tool_use = block["toolUse"]
                tool_calls.append(
                    _ToolCall(
                        id=tool_use.get("toolUseId", ""),
                        function=_Function(
                            name=tool_use["name"],
                            arguments=json.dumps(tool_use.get("input", {})),
                        ),
                        type="function",
                    )
                )

        stop_reason = response.get("stopReason", "end_turn")
        finish_reason = "tool_calls" if tool_calls else "stop"

        return _CompletionResponse(
            choices=[
                _Choice(
                    message=_Message(
                        content=text_content or None,
                        tool_calls=tool_calls if tool_calls else None,
                        role="assistant",
                    ),
                    finish_reason=finish_reason,
                )
            ]
        )


class _Function:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, id: str, function: _Function, type: str):
        self.id = id
        self.function = function
        self.type = type


class _Message:
    def __init__(self, content: str | None, tool_calls: list[_ToolCall] | None, role: str):
        self.content = content
        self.tool_calls = tool_calls
        self.role = role


class _Choice:
    def __init__(self, message: _Message, finish_reason: str):
        self.message = message
        self.finish_reason = finish_reason


class _CompletionResponse:
    def __init__(self, choices: list[_Choice]):
        self.choices = choices


def initialize_bedrock_model() -> BedrockModelWrapper:
    """
    Initialize a Bedrock model wrapper from environment variables.

    Required env vars:
        BEDROCK_MODEL_ID: Model ID (e.g., us.anthropic.claude-sonnet-4-20250514)
        AWS_REGION: AWS region (e.g., us-east-1)

    Optional env vars (falls back to AWS credential chain):
        AWS_ACCESS_KEY_ID: AWS access key
        AWS_SECRET_ACCESS_KEY: AWS secret key
    """
    model_id = os.getenv("BEDROCK_MODEL_ID", "")
    region = os.getenv("AWS_REGION", "us-east-1")
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    if not model_id:
        raise ValueError(
            "BEDROCK_MODEL_ID is required. Set it to a Bedrock model ID "
            "(e.g., us.anthropic.claude-sonnet-4-20250514)"
        )

    return BedrockModelWrapper(
        model_id=model_id,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
