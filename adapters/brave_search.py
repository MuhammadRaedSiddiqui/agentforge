"""
Web search adapter for Agent Forge.

Uses DuckDuckGo HTML search (no API key required) as a read-only fallback
for the information agent when internal knowledge doesn't have an answer.
"""

import requests

from adapters.base import AdapterReceipt
from shared.errors import (
    PermanentError,
    TransientError,
    ValidationError,
)


class BraveSearchAdapter:
    """
    Web search adapter using DuckDuckGo (no API key required).

    Maintains the BraveSearchAdapter class name for backward compatibility.

    All operations:
    - Timeout: 10s connect, 30s read
    - Retry: max 2 for transient failures
    - Read-only: no side effects
    """

    def __init__(self) -> None:
        """Initialize DuckDuckGo search adapter."""
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "AgentForge/1.0 (troubleshooting fallback)"})

    def web_search(
        self,
        query: str,
        count: int = 10,
        country: str = "US",
        search_lang: str = "en",
        safesearch: str = "moderate",
    ) -> AdapterReceipt:
        """
        Search the web using DuckDuckGo.

        Args:
            query: Search query (1-400 characters)
            count: Number of results (1-20, default 10)
            country: Country code (2 letters, default US)
            search_lang: Search language (default en)
            safesearch: Safe search level (off, moderate, strict; default moderate)

        Returns:
            AdapterReceipt with sanitized search results
        """
        self._validate_query(query)
        self._validate_count(count)

        safesearch_map = {"off": "-2", "moderate": "-1", "strict": "1"}
        kp_value = safesearch_map.get(safesearch, "-1")

        # DuckDuckGo HTML lite endpoint
        url = "https://lite.duckduckgo.com/lite/"
        params = {
            "q": query,
            "kl": f"{country.lower()}-{search_lang}",
            "kp": kp_value,
        }

        try:
            response = self.session.get(url, params=params, timeout=(10, 30))

            if response.status_code >= 500:
                raise TransientError(f"HTTP {response.status_code}: Server error")
            elif response.status_code >= 400:
                raise PermanentError(f"HTTP {response.status_code}: Client error")

            results = self._parse_html_results(response.text, count)

            return AdapterReceipt(
                platform="web_search",
                operation="web_search",
                remote_id=None,
                status="success",
                response_data={"query": query, "results": results},
                idempotency_key=None,
                can_retry=True,
            )

        except requests.Timeout as e:
            raise TransientError(f"Request timeout: {e}") from e
        except requests.ConnectionError as e:
            raise TransientError(f"Connection error: {e}") from e
        except (TransientError, PermanentError):
            raise
        except requests.RequestException as e:
            raise PermanentError(f"Request failed: {e}") from e

    def _parse_html_results(self, html: str, max_results: int) -> list[dict[str, str]]:
        """Parse DuckDuckGo lite HTML into structured results."""
        import re
        from urllib.parse import parse_qs, unquote, urlparse

        results: list[dict[str, str]] = []

        # DDG lite uses redirect links: //duckduckgo.com/l/?uddg=<encoded_url>
        link_pattern = re.compile(r'<a\s+rel="nofollow"\s+href="([^"]+)"[^>]*>([^<]+)</a>')

        # Find snippet rows (text after the link in a <td class="result-snippet">)
        snippet_pattern = re.compile(r'class="result-snippet"[^>]*>(.*?)</td>', re.DOTALL)

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (raw_url, title) in enumerate(links):
            # Extract actual URL from DDG redirect
            actual_url = raw_url
            if "uddg=" in raw_url:
                parsed = urlparse(raw_url if raw_url.startswith("http") else f"https:{raw_url}")
                qs = parse_qs(parsed.query)
                if "uddg" in qs:
                    actual_url = unquote(qs["uddg"][0])

            # Clean title
            title = (
                title.strip()
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&#x27;", "'")
            )

            # Get snippet if available
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
                snippet = (
                    snippet.replace("&amp;", "&")
                    .replace("&lt;", "<")
                    .replace("&gt;", ">")
                    .replace("&#x27;", "'")
                )

            if title and actual_url and not actual_url.startswith("//duckduckgo"):
                results.append({"title": title, "url": actual_url, "description": snippet})

            if len(results) >= max_results:
                break

        return results

    def _validate_query(self, query: str) -> None:
        """Validate search query."""
        if not query:
            raise ValidationError(
                "Search query cannot be empty",
                field="query",
                context={"operation": "web_search"},
            )

        if len(query) > 400:
            raise ValidationError(
                "Search query must be between 1 and 400 characters",
                field="query",
                context={"operation": "web_search", "length": len(query)},
            )

    def _validate_count(self, count: int) -> None:
        """Validate result count."""
        if not (1 <= count <= 20):
            raise ValidationError(
                "Result count must be between 1 and 20",
                field="count",
                context={"operation": "web_search", "provided": count},
            )
