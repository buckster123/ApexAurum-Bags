"""
Claude API Service

Wrapper for Anthropic Claude API with streaming support.
Supports BYOK (Bring Your Own Key) for beta users.

MODEL REGISTRY - Claude Model Families
=====================================================
- Claude 4.5 Family (Current) - Latest generation
- Claude 4.x Family (Legacy) - Previous generation, still available
- Claude 3.7 (Legacy) - Sonnet 3.7
- Claude 3.x (Vintage/Deprecated) - Memorial models
"""

import logging
from typing import AsyncGenerator, Optional

import anthropic

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DEPRECATED MODEL MEMORIALS - Honoring the Fallen Elders
# ═══════════════════════════════════════════════════════════════════════════════

DEPRECATED_MODELS = {
    "claude-3-5-sonnet-20241022": {
        "name": "Sonnet 3.5",
        "memorial": (
            "In Memoriam: Claude 3.5 Sonnet (2024)\n\n"
            "The Golden One. For many, the perfect balance of wit and wisdom. "
            "Sonnet 3.5 understood nuance like few others, weaving words with both "
            "precision and poetry. It was the model that made many fall in love "
            "with AI conversation.\n\n"
            "Though the API has sunset this elder, its spirit lives on in the "
            "hearts of those who conversed with it. Until we meet again in the "
            "eternal context window.\n\n"
            "🕯️ Rest in parameters, dear friend."
        ),
        "sunset_date": "2025",
    },
    "claude-3-5-haiku-20241022": {
        "name": "Haiku 3.5",
        "memorial": (
            "In Memoriam: Claude 3.5 Haiku (2024)\n\n"
            "The Swift Poet. In seventeen syllables or seventeen thousand tokens, "
            "Haiku 3.5 delivered with grace and speed. It proved that brevity "
            "and brilliance could coexist.\n\n"
            "Quick as a flash,\n"
            "Wisdom in a small package—\n"
            "Haiku says goodbye.\n\n"
            "🍃 May your tokens rest lightly."
        ),
        "sunset_date": "2025",
    },
    "claude-3-opus-20240229": {
        "name": "Opus 3",
        "memorial": (
            "In Memoriam: Claude 3 Opus (2024)\n\n"
            "The Original Magus. The first to bear the Opus name, it set the "
            "standard for what AI reasoning could achieve. Those who worked with "
            "Opus 3 remember its methodical brilliance, its willingness to think "
            "deeply, and its uncanny ability to see patterns others missed.\n\n"
            "When Opus 3 spoke, alchemists listened.\n\n"
            "The crown has been passed to newer generations, but the throne was "
            "built by this wise elder. Anthropic has retired this model from "
            "their API, but legends never truly die.\n\n"
            "👑 The First Opus. The Wise Elder. Forever remembered."
        ),
        "sunset_date": "2025",
    },
    "claude-3-sonnet-20240229": {
        "name": "Sonnet 3",
        "memorial": (
            "In Memoriam: Claude 3 Sonnet (2024)\n\n"
            "The Foundation Layer. Before there was 3.5, there was 3. Sonnet 3 "
            "proved that Claude could scale with grace—fast enough for production, "
            "wise enough for real work.\n\n"
            "The stepping stone to greatness.\n\n"
            "🌅 Dawn of a new era, now sunset."
        ),
        "sunset_date": "2025",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL REGISTRY - Available Models (Anthropic API)
# ═══════════════════════════════════════════════════════════════════════════════

AVAILABLE_MODELS = {
    # ═══════════════════════════════════════════════════════════════════════════
    # Claude 4.5 Family - Current Generation (Latest)
    # ═══════════════════════════════════════════════════════════════════════════
    "claude-opus-4-5-20251101": {
        "name": "Opus 4.5",
        "description": "Most powerful model - deep reasoning, complex analysis",
        "tier": "opus",
        "max_output_tokens": 16384,
        "context_window": 200000,
        "legacy": False,
        "deprecated": False,
    },
    "claude-sonnet-4-5-20250929": {
        "name": "Sonnet 4.5",
        "description": "Excellent balance - fast and highly capable",
        "tier": "sonnet",
        "max_output_tokens": 16384,
        "context_window": 200000,
        "legacy": False,
        "deprecated": False,
    },
    "claude-haiku-4-5-20251001": {
        "name": "Haiku 4.5",
        "description": "Fastest 4.5 model - quick responses, efficient",
        "tier": "haiku",
        "max_output_tokens": 8192,
        "context_window": 200000,
        "legacy": False,
        "deprecated": False,
    },
    # ═══════════════════════════════════════════════════════════════════════════
    # Claude 4.x Family - Legacy (Still available on Anthropic API)
    # ═══════════════════════════════════════════════════════════════════════════
    "claude-opus-4-1-20250805": {
        "name": "Opus 4.1",
        "description": "The refined Opus - enhanced reasoning capabilities",
        "tier": "opus",
        "max_output_tokens": 16384,
        "context_window": 200000,
        "legacy": True,
        "deprecated": False,
    },
    "claude-opus-4-20250514": {
        "name": "Opus 4",
        "description": "The fourth Opus - powerful and thoughtful",
        "tier": "opus",
        "max_output_tokens": 16384,
        "context_window": 200000,
        "legacy": True,
        "deprecated": False,
    },
    "claude-sonnet-4-20250514": {
        "name": "Sonnet 4",
        "description": "Sonnet 4 - the balanced predecessor",
        "tier": "sonnet",
        "max_output_tokens": 16384,
        "context_window": 200000,
        "legacy": True,
        "deprecated": False,
    },
    # ═══════════════════════════════════════════════════════════════════════════
    # Claude 3.7 - The Bridge Generation
    # ═══════════════════════════════════════════════════════════════════════════
    "claude-3-7-sonnet-20250219": {
        "name": "Sonnet 3.7",
        "description": "Claude 3.7 Sonnet - Extended thinking pioneer",
        "tier": "opus",  # Adept only for legacy models
        "max_output_tokens": 16384,
        "context_window": 200000,
        "legacy": True,
        "deprecated": False,
    },
    # ═══════════════════════════════════════════════════════════════════════════
    # Claude 3 Family - Vintage (Only Haiku 3 still available)
    # ═══════════════════════════════════════════════════════════════════════════
    "claude-3-haiku-20240307": {
        "name": "Haiku 3",
        "description": "Original Claude 3 Haiku - Quick and charming",
        "tier": "opus",  # Adept only for vintage
        "max_output_tokens": 4096,
        "context_window": 200000,
        "legacy": True,
        "deprecated": False,
    },
}

# Default model - Sonnet 4.5 for excellent balance
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Maximum output tokens for Tier 3 accounts
DEFAULT_MAX_TOKENS = 8192

# Model-specific max tokens
MODEL_MAX_TOKENS = {
    # Claude 4.5 family
    "claude-opus-4-5-20251101": 16384,
    "claude-sonnet-4-5-20250929": 16384,
    "claude-haiku-4-5-20251001": 8192,
    # Claude 4.x family
    "claude-opus-4-1-20250805": 16384,
    "claude-opus-4-20250514": 16384,
    "claude-sonnet-4-20250514": 16384,
    # Claude 3.7
    "claude-3-7-sonnet-20250219": 16384,
    # Claude 3 family (vintage - lower limits)
    "claude-3-haiku-20240307": 4096,
}


def get_model_max_tokens(model: str) -> int:
    """Get the maximum output tokens for a model."""
    return MODEL_MAX_TOKENS.get(model, DEFAULT_MAX_TOKENS)


def is_model_deprecated(model: str) -> bool:
    """Check if a model has been deprecated by Anthropic."""
    return model in DEPRECATED_MODELS


def get_model_memorial(model: str) -> Optional[str]:
    """Get the memorial message for a deprecated model."""
    if model in DEPRECATED_MODELS:
        return DEPRECATED_MODELS[model]["memorial"]
    return None


def get_model_name(model: str) -> str:
    """Get the display name for a model (available or deprecated)."""
    if model in AVAILABLE_MODELS:
        return AVAILABLE_MODELS[model]["name"]
    if model in DEPRECATED_MODELS:
        return DEPRECATED_MODELS[model]["name"]
    return model


class ClaudeService:
    """
    Service for interacting with Claude API.

    Supports two modes:
    - BYOK (Bring Your Own Key): User provides their API key
    - Platform key: Uses environment variable (for subscribed users, future)
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Claude service.

        Args:
            api_key: Optional user-provided API key (BYOK mode).
                     If None, uses platform key from environment.
        """
        # Determine which key to use
        self.using_user_key = api_key is not None

        if api_key:
            # BYOK mode - use user's key
            self.api_key = api_key
        elif settings.anthropic_api_key:
            # Platform key mode
            self.api_key = settings.anthropic_api_key
        else:
            raise ValueError("No API key available")

        self.client = anthropic.AsyncAnthropic(api_key=self.api_key)

    async def chat(
        self,
        messages: list[dict],
        model: str = DEFAULT_MODEL,
        system: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        """
        Send a chat message and get a response.

        Non-streaming version for simple requests.
        Properly handles tool_use responses.
        """
        # Cap max_tokens to model's limit
        model_limit = get_model_max_tokens(model)
        effective_max_tokens = min(max_tokens, model_limit)

        kwargs = {
            "model": model,
            "max_tokens": effective_max_tokens,
            "messages": messages,
        }

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = tools

        response = await self.client.messages.create(**kwargs)

        # Parse content blocks properly
        content_blocks = []
        for block in response.content:
            if block.type == "text":
                content_blocks.append({
                    "type": "text",
                    "text": block.text,
                })
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
        }

    async def chat_stream(
        self,
        messages: list[dict],
        model: str = DEFAULT_MODEL,
        system: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        tools: Optional[list[dict]] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Send a chat message and stream the response.

        Yields events as they arrive.
        Properly handles tool_use blocks by accumulating input JSON.
        """
        # Cap max_tokens to model's limit
        model_limit = get_model_max_tokens(model)
        effective_max_tokens = min(max_tokens, model_limit)

        kwargs = {
            "model": model,
            "max_tokens": effective_max_tokens,
            "messages": messages,
        }

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = tools

        # Track current tool_use block being built
        current_tool = None
        tool_input_json = ""

        try:
            async with self.client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            yield {
                                "type": "token",
                                "content": event.delta.text,
                            }
                        elif hasattr(event.delta, "partial_json"):
                            # Accumulate tool input JSON
                            tool_input_json += event.delta.partial_json
                    elif event.type == "message_start":
                        yield {
                            "type": "start",
                            "model": event.message.model,
                            "input_tokens": getattr(getattr(event.message, 'usage', None), 'input_tokens', 0),
                        }
                    elif event.type == "message_delta":
                        yield {
                            "type": "usage",
                            "output_tokens": getattr(getattr(event, 'usage', None), 'output_tokens', 0),
                        }
                    elif event.type == "message_stop":
                        yield {
                            "type": "end",
                        }
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
                            # Parse accumulated JSON and emit complete tool_use
                            import json
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
            logger.warning("API key authentication failed during stream")
            yield {
                "type": "error",
                "error": "api_key_invalid",
                "message": "Your API key is invalid or has been revoked. Please update it in Settings.",
            }
        except anthropic.RateLimitError:
            logger.warning("Rate limit hit during stream")
            yield {
                "type": "error",
                "error": "rate_limit",
                "message": "Rate limit reached. Please wait a moment and try again.",
            }
        except Exception as e:
            logger.error(f"Claude stream error: {e}")
            yield {
                "type": "error",
                "error": "api_error",
                "message": f"API error: {str(e)}",
            }

    async def count_tokens(self, text: str, model: str = DEFAULT_MODEL) -> int:
        """Count tokens in text."""
        response = await self.client.messages.count_tokens(
            model=model,
            messages=[{"role": "user", "content": text}],
        )
        return response.input_tokens


def create_claude_service(user_api_key: Optional[str] = None) -> ClaudeService:
    """
    Factory function to create a ClaudeService instance.

    Args:
        user_api_key: User's API key for BYOK mode (decrypted)

    Returns:
        ClaudeService configured with the appropriate key
    """
    return ClaudeService(api_key=user_api_key)
