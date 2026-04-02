from __future__ import annotations

from tools.web_policy import validate_url_basic


def web_search(
    query: str,
    max_results: int = 5,
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
    safe_mode: bool = True,
):
    try:
        cleaned_query = query.strip()
        if not cleaned_query:
            return {
                "status": "error",
                "error": "Query cannot be empty",
                "query": query,
            }

        DDGS = None
        try:
            from ddgs import DDGS as DDGSClient

            DDGS = DDGSClient
        except Exception:
            try:
                from duckduckgo_search import DDGS as DDGSClient

                DDGS = DDGSClient
            except Exception:
                return {
                    "status": "error",
                    "error": "Neither ddgs nor duckduckgo-search is installed",
                    "query": cleaned_query,
                }

        safesearch = "strict" if safe_mode else "off"
        raw_results = []

        with DDGS() as ddgs:
            for row in ddgs.text(cleaned_query, safesearch=safesearch, max_results=max_results * 3):
                raw_results.append(row)

        filtered = []
        blocked_count = 0

        for row in raw_results:
            url = (row.get("href") or "").strip()
            if not url:
                blocked_count += 1
                continue

            ok, _, _ = validate_url_basic(
                url=url,
                allowed_domains=allowed_domains,
                blocked_domains=blocked_domains,
            )
            if not ok:
                blocked_count += 1
                continue

            filtered.append(
                {
                    "title": (row.get("title") or "").strip() or url,
                    "url": url,
                    "snippet": (row.get("body") or "").strip() or None,
                    "source": "duckduckgo",
                    "rank": len(filtered) + 1,
                }
            )

            if len(filtered) >= max_results:
                break

        return {
            "status": "ok",
            "query": cleaned_query,
            "results": filtered,
            "blocked_count": blocked_count,
            "error": None,
        }
    except Exception as e:
        return {
            "status": "error",
            "query": query,
            "results": [],
            "blocked_count": 0,
            "error": str(e),
        }
