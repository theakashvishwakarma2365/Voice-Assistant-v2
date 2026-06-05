"""
Web Search Service using ddgs (DuckDuckGo).
Uses the `ddgs` library (successor to duckduckgo_search) with an httpx fallback.
"""
import asyncio
import re
from app.core.logger import logger


class SearchService:
    def __init__(self):
        pass

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Search the web using DuckDuckGo via the ddgs library.
        Returns a list of dicts: [{'title': ..., 'href': ..., 'body': ...}]
        """
        if not query:
            return []

        logger.info(f"Web search: '{query}'")

        # Try ddgs library first (runs sync in thread to avoid blocking event loop)
        try:
            def _sync_search():
                from ddgs import DDGS
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=max_results))

            results = await asyncio.to_thread(_sync_search)
            formatted = [
                {
                    "title": r.get("title", ""),
                    "href":  r.get("href", ""),
                    "body":  r.get("body", ""),
                }
                for r in results
                if r.get("title") or r.get("body")
            ]
            logger.info(f"ddgs returned {len(formatted)} results for '{query}'")
            if formatted:
                return formatted
        except Exception as e:
            logger.warning(f"ddgs failed ({e}), falling back to HTML scraper…")

        # Fallback: scrape html.duckduckgo.com
        return await self._fallback_search(query, max_results)

    async def _fallback_search(self, query: str, max_results: int = 5) -> list[dict]:
        """Fallback: direct HTTP scrape of html.duckduckgo.com."""
        try:
            import httpx
            from urllib.parse import quote_plus
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            }
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(url, headers=headers, timeout=12.0)

            if resp.status_code != 200:
                logger.warning(f"Fallback search HTTP {resp.status_code}")
                return []

            html = resp.text
            clean = re.compile(r"<[^>]+>")
            matches = re.findall(
                r'<a\s+class="result__a"\s+href="([^"]+)">([^<]+)</a>'
                r'.*?<a\s+class="result__snippet"[^>]*>(.*?)</a>',
                html, re.DOTALL
            )
            results = []
            for href, title, snippet in matches[:max_results]:
                results.append({
                    "title": clean.sub("", title).strip(),
                    "href":  href.strip(),
                    "body":  clean.sub("", snippet).strip(),
                })

            logger.info(f"Fallback returned {len(results)} results for '{query}'")
            return results

        except Exception as e:
            logger.error(f"Fallback search error: {e}")
            return []


# Singleton
search_service = SearchService()
