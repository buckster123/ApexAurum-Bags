"""
Pricing Service - LLM cost calculation for billing.

Provides accurate cost calculation per provider/model based on token usage.
Prices are per 1 million tokens (as Anthropic and others advertise).
"""

from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# PRICING TABLE - Per 1M tokens (as of January 2026)
# ═══════════════════════════════════════════════════════════════════════════════

PRICING: Dict[str, Dict[str, Dict[str, float]]] = {
    # Anthropic Claude models
    "anthropic": {
        "claude-opus-4-5-20251101": {
            "input": 15.00,   # $15 per 1M input tokens
            "output": 75.00,  # $75 per 1M output tokens
        },
        "claude-sonnet-4-5-20250929": {
            "input": 3.00,    # $3 per 1M input tokens
            "output": 15.00,  # $15 per 1M output tokens
        },
        "claude-haiku-4-5-20251001": {
            "input": 0.25,    # $0.25 per 1M input tokens
            "output": 1.25,   # $1.25 per 1M output tokens
        },
        # Legacy models (still might be used)
        "claude-3-opus-20240229": {
            "input": 15.00,
            "output": 75.00,
        },
        "claude-3-5-sonnet-20241022": {
            "input": 3.00,
            "output": 15.00,
        },
        "claude-3-haiku-20240307": {
            "input": 0.25,
            "output": 1.25,
        },
    },

    # Groq (LPU inference - very cheap)
    "groq": {
        "llama-3.3-70b-versatile": {
            "input": 0.59,
            "output": 0.79,
        },
        "llama-3.1-70b-versatile": {
            "input": 0.59,
            "output": 0.79,
        },
        "llama3-8b-8192": {
            "input": 0.05,
            "output": 0.08,
        },
        "mixtral-8x7b-32768": {
            "input": 0.24,
            "output": 0.24,
        },
        "gemma2-9b-it": {
            "input": 0.20,
            "output": 0.20,
        },
    },

    # DeepSeek (very affordable)
    "deepseek": {
        "deepseek-chat": {
            "input": 0.14,
            "output": 0.28,
        },
        "deepseek-reasoner": {
            "input": 0.55,
            "output": 2.19,
        },
    },

    # Together AI
    "together": {
        "meta-llama/Llama-3.3-70B-Instruct-Turbo": {
            "input": 0.88,
            "output": 0.88,
        },
        "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo": {
            "input": 0.88,
            "output": 0.88,
        },
        "mistralai/Mixtral-8x7B-Instruct-v0.1": {
            "input": 0.60,
            "output": 0.60,
        },
        "Qwen/Qwen2.5-72B-Instruct-Turbo": {
            "input": 1.20,
            "output": 1.20,
        },
    },

    # Qwen (Alibaba Cloud)
    "qwen": {
        "qwen-turbo": {
            "input": 0.14,
            "output": 0.28,
        },
        "qwen-plus": {
            "input": 0.57,
            "output": 1.14,
        },
        "qwen-max": {
            "input": 2.80,
            "output": 11.20,
        },
    },

    # OpenAI (for reference, not currently used)
    "openai": {
        "gpt-4o": {
            "input": 2.50,
            "output": 10.00,
        },
        "gpt-4o-mini": {
            "input": 0.15,
            "output": 0.60,
        },
        "gpt-4-turbo": {
            "input": 10.00,
            "output": 30.00,
        },
    },
}

# Default pricing for unknown models (use conservative Sonnet-tier pricing)
DEFAULT_PRICING = {
    "input": 3.00,
    "output": 15.00,
}


def get_model_pricing(provider: str, model: str) -> Dict[str, float]:
    """
    Get pricing for a specific provider/model combination.

    Returns input/output prices per 1M tokens.
    Falls back to DEFAULT_PRICING if model not found.
    """
    provider_prices = PRICING.get(provider, {})
    model_prices = provider_prices.get(model)

    if model_prices:
        return model_prices

    # Try partial model name match (for versioned models)
    for known_model, prices in provider_prices.items():
        if known_model in model or model in known_model:
            return prices

    logger.warning(f"Unknown model {provider}/{model}, using default pricing")
    return DEFAULT_PRICING


def calculate_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """
    Calculate cost in USD for a request.

    Args:
        provider: LLM provider (anthropic, groq, deepseek, etc.)
        model: Model ID
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens

    Returns:
        Cost in USD (float, e.g., 0.0045 for $0.0045)
    """
    prices = get_model_pricing(provider, model)

    input_cost = (input_tokens / 1_000_000) * prices["input"]
    output_cost = (output_tokens / 1_000_000) * prices["output"]

    return input_cost + output_cost


def calculate_cost_cents(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> int:
    """
    Calculate cost in cents for a request (for credit deduction).

    Args:
        provider: LLM provider
        model: Model ID
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens

    Returns:
        Cost in cents (integer, rounded up)
    """
    cost_usd = calculate_cost(provider, model, input_tokens, output_tokens)

    # Convert to cents and round up (always charge at least 1 cent)
    cost_cents = int(cost_usd * 100)

    # Minimum 1 cent if any tokens were used
    if cost_cents == 0 and (input_tokens > 0 or output_tokens > 0):
        cost_cents = 1

    return cost_cents


def estimate_cost(
    provider: str,
    model: str,
    message_length: int,
    estimated_response_multiplier: float = 1.5,
) -> float:
    """
    Estimate cost before sending a request.

    Uses a rough estimate of tokens based on message length.
    Average: ~4 characters per token for English text.

    Args:
        provider: LLM provider
        model: Model ID
        message_length: Character length of user message
        estimated_response_multiplier: Expected response length relative to input

    Returns:
        Estimated cost in USD
    """
    # Rough token estimate (4 chars per token)
    estimated_input_tokens = message_length // 4 + 100  # Add some for system prompt
    estimated_output_tokens = int(estimated_input_tokens * estimated_response_multiplier)

    return calculate_cost(provider, model, estimated_input_tokens, estimated_output_tokens)


def get_tier_for_model(model: str) -> str:
    """
    Determine the minimum tier required for a model.

    Returns: 'free_trial', 'seeker', or 'adept'
    """
    # Opus models require adept tier (limited) or higher
    if "opus" in model.lower():
        return "adept"

    # Sonnet models require seeker tier
    if "sonnet" in model.lower():
        return "seeker"

    # Haiku available on free trial
    return "free_trial"


def format_cost_display(cost_usd: float) -> str:
    """
    Format cost for display to users.

    Shows appropriate precision based on cost magnitude.
    """
    if cost_usd < 0.01:
        return f"${cost_usd:.4f}"
    elif cost_usd < 1.00:
        return f"${cost_usd:.3f}"
    else:
        return f"${cost_usd:.2f}"
