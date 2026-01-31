"""
Multi-Provider LLM Service - The Many Flames of the Athanor

Supports multiple LLM providers through a unified interface.
Hidden in dev/adept mode for nerds and tinkerers.

Providers:
- Anthropic (Claude) - Native SDK
- DeepSeek - OpenAI-compatible
- Groq - OpenAI-compatible (fastest)
- Together AI - OpenAI-compatible (200+ models)
- Qwen - OpenAI-compatible
- Moonshot (Kimi) - OpenAI-compatible

All OpenAI-compatible providers use the same SDK with different base URLs.
"""

import json
import logging
import os
from typing import AsyncGenerator, Optional

import anthropic
from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


# =============================================================================
# PROVIDER REGISTRY
# =============================================================================

PROVIDERS = {
    "anthropic": {
        "name": "Anthropic",
        "base_url": None,  # Uses native SDK
        "key_env": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-5-20250929",
        "supports_tools": True,
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "supports_tools": True,  # deepseek-chat only, not reasoner
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
        "supports_tools": True,
    },
    "together": {
        "name": "Together AI",
        "base_url": "https://api.together.xyz/v1",
        "key_env": "TOGETHER_API_KEY",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "supports_tools": True,
    },
    "qwen": {
        "name": "Qwen",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "key_env": "DASHSCOPE_API_KEY",
        "default_model": "qwen-plus",
        "supports_tools": True,
    },
    "moonshot": {
        "name": "Moonshot",
        "base_url": "https://api.moonshot.ai/v1",
        "key_env": "MOONSHOT_API_KEY",
        "default_model": "kimi-k2.5",
        "supports_tools": True,
    },
}


# =============================================================================
# MODEL REGISTRY PER PROVIDER
# =============================================================================

PROVIDER_MODELS = {
    "anthropic": {
        "claude-opus-4-5-20251101": {
            "name": "Opus 4.5",
            "tier": "opus",
            "max_tokens": 16384,
            "context_window": 200000,
            "description": "Most powerful model - deep reasoning, complex analysis",
        },
        "claude-sonnet-4-5-20250929": {
            "name": "Sonnet 4.5",
            "tier": "sonnet",
            "max_tokens": 16384,
            "context_window": 200000,
            "description": "Excellent balance - fast and highly capable",
        },
        "claude-haiku-4-5-20251001": {
            "name": "Haiku 4.5",
            "tier": "haiku",
            "max_tokens": 8192,
            "context_window": 200000,
            "description": "Fastest 4.5 model - quick responses, efficient",
        },
    },
    "deepseek": {
        "deepseek-chat": {
            "name": "DeepSeek V3",
            "tier": "standard",
            "max_tokens": 8192,
            "context_window": 128000,
            "description": "671B MoE flagship - strong general-purpose model",
        },
        "deepseek-reasoner": {
            "name": "DeepSeek R1",
            "tier": "reasoning",
            "max_tokens": 8192,
            "context_window": 128000,
            "description": "Chain-of-thought reasoning model (no tool support)",
            "supports_tools": False,
        },
    },
    "groq": {
        "llama-3.3-70b-versatile": {
            "name": "Llama 3.3 70B",
            "tier": "large",
            "max_tokens": 8192,
            "context_window": 128000,
            "description": "Fast versatile workhorse - great all-rounder on Groq",
        },
        "llama-3.1-8b-instant": {
            "name": "Llama 3.1 8B",
            "tier": "small",
            "max_tokens": 8192,
            "context_window": 128000,
            "description": "Ultra-fast small model - 560 tokens/sec on Groq",
        },
        "deepseek-r1-distill-llama-70b": {
            "name": "DeepSeek R1 Distill 70B",
            "tier": "reasoning",
            "max_tokens": 8192,
            "context_window": 128000,
            "description": "Reasoning distilled into Llama 70B - fast on Groq",
        },
        "qwen-qwq-32b": {
            "name": "Qwen QwQ 32B",
            "tier": "reasoning",
            "max_tokens": 8192,
            "context_window": 128000,
            "description": "Reasoning model with excellent tool use",
        },
    },
    "together": {
        "meta-llama/Llama-3.3-70B-Instruct-Turbo": {
            "name": "Llama 3.3 70B Turbo",
            "tier": "large",
            "max_tokens": 8192,
            "context_window": 128000,
            "description": "Fast Llama flagship - turbo inference on Together",
        },
        "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo": {
            "name": "Llama 3.1 405B Turbo",
            "tier": "large",
            "max_tokens": 8192,
            "context_window": 128000,
            "description": "Largest open-source model - 405B parameters",
        },
        "deepseek-ai/DeepSeek-V3.1": {
            "name": "DeepSeek V3.1",
            "tier": "standard",
            "max_tokens": 8192,
            "context_window": 128000,
            "description": "Top open-source base model - rivals frontier models",
        },
        "deepseek-ai/DeepSeek-R1": {
            "name": "DeepSeek R1",
            "tier": "reasoning",
            "max_tokens": 8192,
            "context_window": 128000,
            "description": "671B MoE reasoning - chain-of-thought on Together",
        },
    },
    "qwen": {
        "qwen3-max": {
            "name": "Qwen3 Max",
            "tier": "large",
            "max_tokens": 8192,
            "context_window": 262000,
            "description": "Latest Qwen flagship - 262K context window",
        },
        "qwen-plus": {
            "name": "Qwen Plus",
            "tier": "standard",
            "max_tokens": 8192,
            "context_window": 128000,
            "description": "Balanced performance and cost",
        },
        "qwen-turbo": {
            "name": "Qwen Turbo",
            "tier": "fast",
            "max_tokens": 8192,
            "context_window": 128000,
            "description": "Fastest Qwen option - low latency",
        },
        "qwq-plus": {
            "name": "QwQ Plus",
            "tier": "reasoning",
            "max_tokens": 8192,
            "context_window": 128000,
            "description": "Reasoning-focused model with chain-of-thought",
        },
    },
    "moonshot": {
        "kimi-k2.5": {
            "name": "Kimi K2.5",
            "tier": "reasoning",
            "max_tokens": 16384,
            "context_window": 256000,
            "description": "1T MoE flagship - deep reasoning with chain-of-thought (256K ctx)",
        },
        "kimi-k2.5-instant": {
            "name": "Kimi K2.5 Instant",
            "tier": "standard",
            "max_tokens": 8192,
            "context_window": 256000,
            "description": "1T MoE flagship - fast responses, no reasoning overhead (256K ctx)",
            "api_model_id": "kimi-k2.5",
            "extra_body": {"thinking": {"type": "disabled"}},
        },
    },
}


# =============================================================================
# TOOL FORMAT CONVERSION
# =============================================================================

def convert_tools_to_openai(anthropic_tools: list[dict]) -> list[dict]:
    """
    Convert Anthropic tool schema to OpenAI function calling format.

    Anthropic format:
    {
        "name": "get_weather",
        "description": "Get weather for a location",
        "input_schema": { ... }
    }

    OpenAI format:
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": { ... }
        }
    }
    """
    if not anthropic_tools:
        return []

    openai_tools = []
    for tool in anthropic_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            }
        })
    return openai_tools


def convert_tool_calls_from_openai(openai_tool_calls: list) -> list[dict]:
    """
    Convert OpenAI tool_calls to Anthropic tool_use format.

    OpenAI format (in message.tool_calls):
    {
        "id": "call_abc123",
        "type": "function",
        "function": {
            "name": "get_weather",
            "arguments": '{"location": "Paris"}'
        }
    }

    Anthropic format (content block):
    {
        "type": "tool_use",
        "id": "call_abc123",
        "name": "get_weather",
        "input": {"location": "Paris"}
    }
    """
    if not openai_tool_calls:
        return []

    tool_uses = []
    for tc in openai_tool_calls:
        try:
            arguments = json.loads(tc.function.arguments) if tc.function.arguments else {}
        except json.JSONDecodeError:
            arguments = {}

        tool_uses.append({
            "type": "tool_use",
            "id": tc.id,
            "name": tc.function.name,
            "input": arguments,
        })
    return tool_uses


def convert_messages_for_openai(messages: list[dict], system: Optional[str] = None) -> list[dict]:
    """
    Convert Anthropic-style messages to OpenAI format.

    Main differences:
    - OpenAI has system as a message, Anthropic has it separate
    - OpenAI uses 'tool_calls' and 'tool' role, Anthropic uses content blocks
    """
    openai_messages = []

    # Add system message if provided
    if system:
        openai_messages.append({"role": "system", "content": system})

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Handle Anthropic's content block format
        if isinstance(content, list):
            # Check for tool_use or tool_result blocks
            text_parts = []
            tool_calls = []
            tool_results = []

            image_blocks = []

            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "image":
                        # Convert Anthropic image format to OpenAI vision format
                        source = block.get("source", {})
                        if source.get("type") == "base64":
                            media_type = source.get("media_type", "image/png")
                            data = source.get("data", "")
                            image_blocks.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{media_type};base64,{data}"}
                            })
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block.get("id"),
                            "type": "function",
                            "function": {
                                "name": block.get("name"),
                                "arguments": json.dumps(block.get("input", {})),
                            }
                        })
                    elif block.get("type") == "tool_result":
                        tool_results.append({
                            "tool_call_id": block.get("tool_use_id"),
                            "content": str(block.get("content", "")),
                        })
                else:
                    text_parts.append(str(block))

            # Build appropriate message(s)
            if tool_results:
                # Tool results become separate messages with role "tool"
                for tr in tool_results:
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_call_id"],
                        "content": tr["content"],
                    })
            elif tool_calls:
                # Assistant message with tool calls
                msg_dict = {"role": "assistant"}
                if text_parts:
                    msg_dict["content"] = "\n".join(text_parts)
                msg_dict["tool_calls"] = tool_calls
                openai_messages.append(msg_dict)
            elif image_blocks:
                # Vision message: mix of text and images as content array
                vision_content = []
                for img in image_blocks:
                    vision_content.append(img)
                if text_parts:
                    vision_content.append({"type": "text", "text": "\n".join(text_parts)})
                openai_messages.append({
                    "role": role,
                    "content": vision_content,
                })
            else:
                # Regular text message
                openai_messages.append({
                    "role": role,
                    "content": "\n".join(text_parts) if text_parts else "",
                })
        else:
            # Simple string content
            openai_messages.append({
                "role": role,
                "content": content,
            })

    return openai_messages


# =============================================================================
# MULTI-PROVIDER LLM SERVICE
# =============================================================================

class MultiProviderLLM:
    """
    Unified interface for multiple LLM providers.

    Uses Anthropic SDK for Claude, OpenAI SDK for others.
    """

    def __init__(self, provider: str = "anthropic", api_key: Optional[str] = None):
        """
        Initialize the multi-provider LLM service.

        Args:
            provider: Provider ID (anthropic, deepseek, groq, together, qwen)
            api_key: Optional API key override
        """
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}")

        self.provider = provider
        self.config = PROVIDERS[provider]
        self.api_key = api_key or os.getenv(self.config["key_env"])

        if not self.api_key:
            raise ValueError(f"No API key for provider: {provider}")

        # Initialize appropriate client
        if provider == "anthropic":
            self.anthropic_client = anthropic.AsyncAnthropic(api_key=self.api_key)
            self.openai_client = None
        else:
            self.anthropic_client = None
            self.openai_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.config["base_url"],
            )

    def get_model_max_tokens(self, model: str) -> int:
        """Get max tokens for a model."""
        models = PROVIDER_MODELS.get(self.provider, {})
        model_info = models.get(model, {})
        return model_info.get("max_tokens", 8192)

    def model_supports_tools(self, model: str) -> bool:
        """Check if a model supports tool calling."""
        if not self.config.get("supports_tools", True):
            return False
        models = PROVIDER_MODELS.get(self.provider, {})
        model_info = models.get(model, {})
        return model_info.get("supports_tools", True)

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        system: Optional[str] = None,
        max_tokens: int = 8192,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        """
        Send a chat message and get a response.

        Returns unified format regardless of provider.
        """
        model = model or self.config["default_model"]
        model_limit = self.get_model_max_tokens(model)
        effective_max_tokens = min(max_tokens, model_limit)

        # Filter out tools if model doesn't support them
        if tools and not self.model_supports_tools(model):
            logger.warning(f"Model {model} doesn't support tools, ignoring")
            tools = None

        if self.provider == "anthropic":
            return await self._chat_anthropic(messages, model, system, effective_max_tokens, tools)
        else:
            return await self._chat_openai(messages, model, system, effective_max_tokens, tools)

    async def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        system: Optional[str] = None,
        max_tokens: int = 8192,
        tools: Optional[list[dict]] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Stream a chat response.

        Yields unified event format regardless of provider.
        """
        model = model or self.config["default_model"]
        model_limit = self.get_model_max_tokens(model)
        effective_max_tokens = min(max_tokens, model_limit)

        if tools and not self.model_supports_tools(model):
            logger.warning(f"Model {model} doesn't support tools, ignoring")
            tools = None

        if self.provider == "anthropic":
            async for event in self._stream_anthropic(messages, model, system, effective_max_tokens, tools):
                yield event
        else:
            async for event in self._stream_openai(messages, model, system, effective_max_tokens, tools):
                yield event

    # -------------------------------------------------------------------------
    # ANTHROPIC IMPLEMENTATION
    # -------------------------------------------------------------------------

    async def _chat_anthropic(
        self,
        messages: list[dict],
        model: str,
        system: Optional[str],
        max_tokens: int,
        tools: Optional[list[dict]],
    ) -> dict:
        """Chat using Anthropic API."""
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        try:
            response = await self.anthropic_client.messages.create(**kwargs)

            content_blocks = []
            for block in response.content:
                if block.type == "text":
                    content_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    content_blocks.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            return {
                "id": response.id,
                "role": response.role,
                "content": content_blocks,
                "model": response.model,
                "stop_reason": response.stop_reason,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                "provider": "anthropic",
            }
        except anthropic.AuthenticationError:
            raise ValueError("Invalid Anthropic API key")
        except anthropic.RateLimitError:
            raise ValueError("Anthropic rate limit exceeded")

    async def _stream_anthropic(
        self,
        messages: list[dict],
        model: str,
        system: Optional[str],
        max_tokens: int,
        tools: Optional[list[dict]],
    ) -> AsyncGenerator[dict, None]:
        """Stream using Anthropic API."""
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        current_tool = None
        tool_input_json = ""
        usage_info = {"input_tokens": 0, "output_tokens": 0}

        try:
            async with self.anthropic_client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            yield {"type": "token", "content": event.delta.text}
                        elif hasattr(event.delta, "partial_json"):
                            tool_input_json += event.delta.partial_json
                    elif event.type == "message_start":
                        yield {"type": "start", "model": event.message.model, "provider": "anthropic"}
                        # Capture input tokens from message_start
                        if hasattr(event.message, "usage") and event.message.usage:
                            usage_info["input_tokens"] = event.message.usage.input_tokens
                    elif event.type == "message_delta":
                        # Capture output tokens from message_delta (sent near end of stream)
                        if hasattr(event, "usage") and event.usage:
                            usage_info["output_tokens"] = event.usage.output_tokens
                    elif event.type == "message_stop":
                        # Yield usage info before end event
                        yield {"type": "usage", "usage": usage_info}
                        yield {"type": "end"}
                    elif event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            current_tool = {
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                            }
                            tool_input_json = ""
                            yield {
                                "type": "tool_start",
                                "tool_name": event.content_block.name,
                                "tool_id": event.content_block.id,
                            }
                    elif event.type == "content_block_stop":
                        if current_tool:
                            try:
                                tool_input = json.loads(tool_input_json) if tool_input_json else {}
                            except json.JSONDecodeError:
                                tool_input = {}
                            yield {
                                "type": "tool_use",
                                "id": current_tool["id"],
                                "name": current_tool["name"],
                                "input": tool_input,
                            }
                            current_tool = None
                            tool_input_json = ""
        except anthropic.AuthenticationError:
            yield {"type": "error", "error": "api_key_invalid", "message": "Invalid Anthropic API key"}
        except anthropic.RateLimitError:
            yield {"type": "error", "error": "rate_limit", "message": "Rate limit exceeded"}
        except Exception as e:
            logger.error(f"Anthropic stream error: {e}")
            yield {"type": "error", "error": "api_error", "message": str(e)}

    # -------------------------------------------------------------------------
    # OPENAI-COMPATIBLE IMPLEMENTATION
    # -------------------------------------------------------------------------

    async def _chat_openai(
        self,
        messages: list[dict],
        model: str,
        system: Optional[str],
        max_tokens: int,
        tools: Optional[list[dict]],
    ) -> dict:
        """Chat using OpenAI-compatible API."""
        openai_messages = convert_messages_for_openai(messages, system)
        openai_tools = convert_tools_to_openai(tools) if tools else None

        # Resolve model alias and extra params (e.g. kimi-k2.5-instant → kimi-k2.5 + thinking disabled)
        model_config = PROVIDER_MODELS.get(self.provider, {}).get(model, {})
        actual_model = model_config.get("api_model_id", model)

        kwargs = {
            "model": actual_model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
        }

        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        if model_config.get("extra_body"):
            kwargs["extra_body"] = model_config["extra_body"]

        try:
            response = await self.openai_client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            # Build unified content blocks
            content_blocks = []

            if choice.message.content:
                content_blocks.append({"type": "text", "text": choice.message.content})

            if choice.message.tool_calls:
                for tc in convert_tool_calls_from_openai(choice.message.tool_calls):
                    content_blocks.append(tc)

            # Map finish_reason to stop_reason
            stop_reason_map = {
                "stop": "end_turn",
                "tool_calls": "tool_use",
                "length": "max_tokens",
            }

            return {
                "id": response.id,
                "role": "assistant",
                "content": content_blocks,
                "model": response.model,
                "stop_reason": stop_reason_map.get(choice.finish_reason, choice.finish_reason),
                "usage": {
                    "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "output_tokens": response.usage.completion_tokens if response.usage else 0,
                },
                "provider": self.provider,
            }
        except Exception as e:
            logger.error(f"OpenAI-compatible API error ({self.provider}): {e}")
            raise ValueError(f"{self.provider} API error: {str(e)}")

    async def _stream_openai(
        self,
        messages: list[dict],
        model: str,
        system: Optional[str],
        max_tokens: int,
        tools: Optional[list[dict]],
    ) -> AsyncGenerator[dict, None]:
        """Stream using OpenAI-compatible API."""
        openai_messages = convert_messages_for_openai(messages, system)
        openai_tools = convert_tools_to_openai(tools) if tools else None

        # Resolve model alias and extra params (e.g. kimi-k2.5-instant → kimi-k2.5 + thinking disabled)
        model_config = PROVIDER_MODELS.get(self.provider, {}).get(model, {})
        actual_model = model_config.get("api_model_id", model)

        kwargs = {
            "model": actual_model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        if model_config.get("extra_body"):
            kwargs["extra_body"] = model_config["extra_body"]

        # Track tool calls being built
        tool_calls_in_progress = {}
        started = False

        try:
            stream = await self.openai_client.chat.completions.create(**kwargs)

            async for chunk in stream:
                if not started:
                    yield {"type": "start", "model": model, "provider": self.provider}
                    started = True

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Handle text content
                if delta.content:
                    yield {"type": "token", "content": delta.content}

                # Handle tool calls
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index

                        if idx not in tool_calls_in_progress:
                            # New tool call starting
                            tool_calls_in_progress[idx] = {
                                "id": tc_delta.id or f"call_{idx}",
                                "name": tc_delta.function.name if tc_delta.function else "",
                                "arguments": "",
                            }
                            if tc_delta.function and tc_delta.function.name:
                                yield {
                                    "type": "tool_start",
                                    "tool_name": tc_delta.function.name,
                                    "tool_id": tool_calls_in_progress[idx]["id"],
                                }

                        # Accumulate arguments
                        if tc_delta.function and tc_delta.function.arguments:
                            tool_calls_in_progress[idx]["arguments"] += tc_delta.function.arguments

                # Check for finish
                if chunk.choices[0].finish_reason:
                    # Emit any completed tool calls
                    for tc in tool_calls_in_progress.values():
                        try:
                            tool_input = json.loads(tc["arguments"]) if tc["arguments"] else {}
                        except json.JSONDecodeError:
                            tool_input = {}
                        yield {
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tool_input,
                        }

                    yield {"type": "end"}
        except Exception as e:
            logger.error(f"OpenAI-compatible stream error ({self.provider}): {e}")
            yield {"type": "error", "error": "api_error", "message": str(e)}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_available_providers() -> list[dict]:
    """
    Get list of available providers with their status.

    Returns providers that have API keys configured.
    """
    providers = []
    for provider_id, config in PROVIDERS.items():
        api_key = os.getenv(config["key_env"])
        providers.append({
            "id": provider_id,
            "name": config["name"],
            "available": bool(api_key),
            "default_model": config["default_model"],
        })
    return providers


def get_provider_models(provider: str) -> list[dict]:
    """Get models for a specific provider."""
    if provider not in PROVIDER_MODELS:
        return []

    models = []
    for model_id, info in PROVIDER_MODELS[provider].items():
        models.append({
            "id": model_id,
            "name": info["name"],
            "tier": info["tier"],
            "max_tokens": info.get("max_tokens", 8192),
            "description": info.get("description", f"{info['name']} - {info['tier']} tier"),
            "context_window": info.get("context_window", 128000),
        })
    return models


def get_default_model(provider: str) -> str:
    """Get default model for a provider."""
    if provider in PROVIDERS:
        return PROVIDERS[provider]["default_model"]
    return "claude-sonnet-4-5-20250929"


def create_llm_service(
    provider: str = "anthropic",
    api_key: Optional[str] = None
) -> MultiProviderLLM:
    """
    Factory function to create a MultiProviderLLM instance.

    Args:
        provider: Provider ID
        api_key: Optional API key override

    Returns:
        Configured MultiProviderLLM instance
    """
    return MultiProviderLLM(provider=provider, api_key=api_key)
