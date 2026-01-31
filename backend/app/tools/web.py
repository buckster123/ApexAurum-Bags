"""
Tier 2: Web Tools - The Reaching Hands

Fetch content and search the web. Pure HTTP - no API keys needed.
"Extend into the web and bring back knowledge"
"""

import logging
import re
from typing import Optional
from urllib.parse import quote_plus

import httpx

from . import registry
from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory


logger = logging.getLogger(__name__)

# Shared HTTP client settings
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_LENGTH = 50000
USER_AGENT = "Mozilla/5.0 (compatible; ApexAurum/1.0; +https://apexaurum.cloud)"


# =============================================================================
# WEB FETCH
# =============================================================================

class WebFetchTool(BaseTool):
    """Fetch content from any URL."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="web_fetch",
            description="""Fetch content from a URL. Returns page content, status code, and metadata.

Use for:
- Reading web pages and articles
- Fetching API responses (JSON, XML)
- Checking if URLs are accessible
- Getting raw HTML for analysis

Note: Content is truncated at 50KB by default. HTML is returned as-is.""",
            category=ToolCategory.WEB,
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch (http:// or https://)",
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "HEAD"],
                        "description": "HTTP method (default: GET)",
                        "default": "GET",
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional custom headers as key-value pairs",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Request timeout in seconds (default: 30, max: 60)",
                        "default": 30,
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Max response length in characters (default: 50000)",
                        "default": 50000,
                    },
                },
                "required": ["url"],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        url = params.get("url", "")
        method = params.get("method", "GET").upper()
        custom_headers = params.get("headers", {})
        timeout = min(params.get("timeout", DEFAULT_TIMEOUT), 60)  # Cap at 60s
        max_length = min(params.get("max_length", DEFAULT_MAX_LENGTH), 100000)  # Cap at 100KB

        # Validate URL
        if not url:
            return ToolResult(success=False, error="URL is required")

        # Add protocol if missing
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Build headers
        headers = {"User-Agent": USER_AGENT}
        if custom_headers:
            headers.update(custom_headers)

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                max_redirects=5,
            ) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                )

                # Get content
                content = response.text
                original_length = len(content)
                truncated = False

                if len(content) > max_length:
                    content = content[:max_length]
                    truncated = True

                # Extract title if HTML
                title = None
                content_type = response.headers.get("content-type", "")
                if "text/html" in content_type:
                    title_match = re.search(
                        r"<title[^>]*>([^<]+)</title>",
                        content,
                        re.IGNORECASE,
                    )
                    if title_match:
                        title = title_match.group(1).strip()

                return ToolResult(
                    success=True,
                    result={
                        "url": str(response.url),
                        "status_code": response.status_code,
                        "title": title,
                        "content_type": content_type,
                        "content_length": original_length,
                        "truncated": truncated,
                        "content": content,
                    },
                )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Request timed out after {timeout}s",
            )
        except httpx.ConnectError as e:
            return ToolResult(
                success=False,
                error=f"Connection failed: {str(e)}",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"HTTP error {e.response.status_code}: {str(e)}",
            )
        except Exception as e:
            logger.exception(f"Web fetch error for {url}")
            return ToolResult(
                success=False,
                error=f"Fetch failed: {str(e)}",
            )


# =============================================================================
# WEB SEARCH
# =============================================================================

class WebSearchTool(BaseTool):
    """Search the web using DuckDuckGo Instant Answers."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="web_search",
            description="""Search the web using DuckDuckGo Instant Answers API.

Returns instant answers, definitions, and related topics. Good for:
- Quick facts and definitions
- Finding relevant topics and links
- General knowledge queries
- Wikipedia-style information

Note: This uses DuckDuckGo's free API (no API key needed).
For full web page content, use web_fetch on specific URLs.""",
            category=ToolCategory.WEB,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Max number of results to return (default: 5, max: 10)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        query = params.get("query", "")
        num_results = min(params.get("num_results", 5), 10)

        if not query:
            return ToolResult(success=False, error="Search query is required")

        try:
            # DuckDuckGo Instant Answer API
            url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": USER_AGENT},
                )
                response.raise_for_status()
                data = response.json()

            results = []

            # Abstract (main answer - usually from Wikipedia)
            if data.get("Abstract"):
                results.append({
                    "type": "answer",
                    "title": data.get("Heading", "Answer"),
                    "text": data["Abstract"],
                    "url": data.get("AbstractURL", ""),
                    "source": data.get("AbstractSource", ""),
                })

            # Infobox (structured data)
            if data.get("Infobox") and data["Infobox"].get("content"):
                infobox_items = []
                for item in data["Infobox"]["content"][:5]:
                    if item.get("label") and item.get("value"):
                        infobox_items.append(f"{item['label']}: {item['value']}")
                if infobox_items:
                    results.append({
                        "type": "infobox",
                        "title": "Quick Facts",
                        "text": "\n".join(infobox_items),
                        "url": "",
                        "source": "DuckDuckGo",
                    })

            # Related topics
            for topic in data.get("RelatedTopics", []):
                if len(results) >= num_results:
                    break

                if isinstance(topic, dict):
                    if "Text" in topic:
                        results.append({
                            "type": "related",
                            "title": topic.get("Text", "")[:100],
                            "text": topic.get("Text", ""),
                            "url": topic.get("FirstURL", ""),
                            "source": "",
                        })
                    elif "Topics" in topic:
                        # Nested category
                        for subtopic in topic["Topics"][:2]:
                            if len(results) >= num_results:
                                break
                            if "Text" in subtopic:
                                results.append({
                                    "type": "related",
                                    "title": subtopic.get("Text", "")[:100],
                                    "text": subtopic.get("Text", ""),
                                    "url": subtopic.get("FirstURL", ""),
                                    "source": "",
                                })

            # Definition
            if data.get("Definition") and len(results) < num_results:
                results.append({
                    "type": "definition",
                    "title": "Definition",
                    "text": data["Definition"],
                    "url": data.get("DefinitionURL", ""),
                    "source": data.get("DefinitionSource", ""),
                })

            # Answer (for calculations, conversions, etc.)
            if data.get("Answer") and len(results) < num_results:
                results.append({
                    "type": "instant",
                    "title": "Instant Answer",
                    "text": data["Answer"],
                    "url": "",
                    "source": "DuckDuckGo",
                })

            return ToolResult(
                success=True,
                result={
                    "query": query,
                    "result_count": len(results),
                    "answer_type": data.get("Type", "unknown"),
                    "results": results[:num_results],
                },
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error="Search request timed out",
            )
        except Exception as e:
            logger.exception(f"Web search error for '{query}'")
            return ToolResult(
                success=False,
                error=f"Search failed: {str(e)}",
            )


# =============================================================================
# REGISTER TOOLS
# =============================================================================

registry.register(WebFetchTool())
registry.register(WebSearchTool())
