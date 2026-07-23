"""Unit tests for the Amazon Bedrock model wrapper."""

import json
from unittest.mock import MagicMock, patch

import pytest

from adapters.bedrock_wrapper import BedrockModelWrapper, initialize_bedrock_model


class TestBedrockModelWrapperInit:
    @patch("adapters.bedrock_wrapper.boto3.Session")
    def test_init_raises_on_empty_model_id(self, mock_session: MagicMock) -> None:
        with pytest.raises(ValueError, match="BEDROCK_MODEL_ID is required"):
            BedrockModelWrapper(model_id="", region_name="us-east-1")

    @patch("adapters.bedrock_wrapper.boto3.Session")
    def test_init_sets_provider_to_bedrock(self, mock_session: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        }
        mock_session.return_value.client.return_value = mock_client

        wrapper = BedrockModelWrapper(
            model_id="us.anthropic.claude-sonnet-4-20250514",
            region_name="us-east-1",
        )
        assert wrapper.provider == "bedrock"
        assert wrapper.get_provider() == "bedrock"
        assert wrapper.get_model_id() == "us.anthropic.claude-sonnet-4-20250514"

    @patch("adapters.bedrock_wrapper.boto3.Session")
    def test_init_passes_credentials_to_session(self, mock_session: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        }
        mock_session.return_value.client.return_value = mock_client

        BedrockModelWrapper(
            model_id="test-model",
            region_name="eu-west-1",
            aws_access_key_id="AKIATEST",
            aws_secret_access_key="secret123",
        )

        mock_session.assert_called_once_with(
            region_name="eu-west-1",
            aws_access_key_id="AKIATEST",
            aws_secret_access_key="secret123",
        )


class TestConvertMessages:
    @patch("adapters.bedrock_wrapper.boto3.Session")
    def test_converts_system_messages_to_system_prompts(self, mock_session: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        }
        mock_session.return_value.client.return_value = mock_client

        wrapper = BedrockModelWrapper(model_id="test", region_name="us-east-1")
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        converse_msgs, system_prompts = wrapper._convert_messages(messages)

        assert system_prompts == [{"text": "You are helpful."}]
        assert len(converse_msgs) == 1
        assert converse_msgs[0]["role"] == "user"

    @patch("adapters.bedrock_wrapper.boto3.Session")
    def test_converts_user_and_assistant_messages(self, mock_session: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        }
        mock_session.return_value.client.return_value = mock_client

        wrapper = BedrockModelWrapper(model_id="test", region_name="us-east-1")
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Bye"},
        ]
        converse_msgs, system_prompts = wrapper._convert_messages(messages)

        assert system_prompts == []
        assert len(converse_msgs) == 3
        assert converse_msgs[0]["content"] == [{"text": "Hi"}]
        assert converse_msgs[1]["role"] == "assistant"

    @patch("adapters.bedrock_wrapper.boto3.Session")
    def test_adds_fallback_when_no_messages(self, mock_session: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        }
        mock_session.return_value.client.return_value = mock_client

        wrapper = BedrockModelWrapper(model_id="test", region_name="us-east-1")
        converse_msgs, _ = wrapper._convert_messages([])

        assert len(converse_msgs) == 1
        assert converse_msgs[0]["content"] == [{"text": "Hello"}]


class TestBuildToolConfig:
    @patch("adapters.bedrock_wrapper.boto3.Session")
    def test_converts_openai_tool_format(self, mock_session: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        }
        mock_session.return_value.client.return_value = mock_client

        wrapper = BedrockModelWrapper(model_id="test", region_name="us-east-1")
        tools = [{
            "type": "function",
            "function": {
                "name": "update_intake",
                "description": "Extract fields",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            },
        }]

        config = wrapper._build_tool_config(tools)
        assert len(config["tools"]) == 1
        assert config["tools"][0]["toolSpec"]["name"] == "update_intake"
        assert config["toolChoice"] == {"auto": {}}

    @patch("adapters.bedrock_wrapper.boto3.Session")
    def test_forced_tool_choice_by_name(self, mock_session: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        }
        mock_session.return_value.client.return_value = mock_client

        wrapper = BedrockModelWrapper(model_id="test", region_name="us-east-1")
        tools = [{
            "type": "function",
            "function": {"name": "my_func", "description": "desc", "parameters": {}},
        }]
        tool_choice = {"type": "function", "function": {"name": "my_func"}}

        config = wrapper._build_tool_config(tools, tool_choice)
        assert config["toolChoice"] == {"tool": {"name": "my_func"}}

    @patch("adapters.bedrock_wrapper.boto3.Session")
    def test_any_tool_choice(self, mock_session: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        }
        mock_session.return_value.client.return_value = mock_client

        wrapper = BedrockModelWrapper(model_id="test", region_name="us-east-1")
        tools = [{
            "type": "function",
            "function": {"name": "fn", "description": "d", "parameters": {}},
        }]
        tool_choice = {"type": "any"}

        config = wrapper._build_tool_config(tools, tool_choice)
        assert config["toolChoice"] == {"any": {}}


class TestToOpenAIFormat:
    @patch("adapters.bedrock_wrapper.boto3.Session")
    def test_text_response(self, mock_session: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        }
        mock_session.return_value.client.return_value = mock_client

        wrapper = BedrockModelWrapper(model_id="test", region_name="us-east-1")

        response = {
            "output": {"message": {"content": [{"text": "Hello there!"}]}},
            "stopReason": "end_turn",
        }

        result = wrapper._to_openai_format(response)
        assert result.choices[0].message.content == "Hello there!"
        assert result.choices[0].message.tool_calls is None
        assert result.choices[0].finish_reason == "stop"

    @patch("adapters.bedrock_wrapper.boto3.Session")
    def test_tool_call_response(self, mock_session: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        }
        mock_session.return_value.client.return_value = mock_client

        wrapper = BedrockModelWrapper(model_id="test", region_name="us-east-1")

        response = {
            "output": {
                "message": {
                    "content": [{
                        "toolUse": {
                            "toolUseId": "call_123",
                            "name": "update_intake",
                            "input": {"business_name": "Test Co", "org_id": "test_co"},
                        }
                    }]
                }
            },
            "stopReason": "tool_use",
        }

        result = wrapper._to_openai_format(response)
        assert result.choices[0].finish_reason == "tool_calls"
        assert len(result.choices[0].message.tool_calls) == 1

        tool_call = result.choices[0].message.tool_calls[0]
        assert tool_call.function.name == "update_intake"
        args = json.loads(tool_call.function.arguments)
        assert args["business_name"] == "Test Co"
        assert args["org_id"] == "test_co"


class TestCreateCompletion:
    @patch("adapters.bedrock_wrapper.boto3.Session")
    def test_passes_tools_and_tool_choice(self, mock_session: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "result"}]}},
            "stopReason": "end_turn",
        }
        mock_session.return_value.client.return_value = mock_client

        wrapper = BedrockModelWrapper(model_id="test-model", region_name="us-east-1")

        tools = [{
            "type": "function",
            "function": {
                "name": "update_intake",
                "description": "Extract",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        tool_choice = {"type": "function", "function": {"name": "update_intake"}}

        wrapper.create_completion(
            messages=[{"role": "user", "content": "Hello"}],
            tools=tools,
            tool_choice=tool_choice,
        )

        call_kwargs = mock_client.converse.call_args[1]
        assert "toolConfig" in call_kwargs
        assert call_kwargs["toolConfig"]["toolChoice"] == {"tool": {"name": "update_intake"}}


class TestInitializeBedrockModel:
    @patch.dict("os.environ", {
        "BEDROCK_MODEL_ID": "us.anthropic.claude-sonnet-4-20250514",
        "AWS_REGION": "us-west-2",
        "AWS_ACCESS_KEY_ID": "AKIATEST",
        "AWS_SECRET_ACCESS_KEY": "secret",
    })
    @patch("adapters.bedrock_wrapper.boto3.Session")
    def test_initializes_from_env(self, mock_session: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        }
        mock_session.return_value.client.return_value = mock_client

        wrapper = initialize_bedrock_model()
        assert wrapper.model_id == "us.anthropic.claude-sonnet-4-20250514"
        mock_session.assert_called_once_with(
            region_name="us-west-2",
            aws_access_key_id="AKIATEST",
            aws_secret_access_key="secret",
        )

    @patch.dict("os.environ", {"BEDROCK_MODEL_ID": ""}, clear=False)
    def test_raises_when_no_model_id(self) -> None:
        with pytest.raises(ValueError, match="BEDROCK_MODEL_ID is required"):
            initialize_bedrock_model()
