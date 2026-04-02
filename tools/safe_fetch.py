from __future__ import annotations

from datetime import datetime, UTC
import re

import httpx
from bs4 import BeautifulSoup

from tools.web_policy import validate_url_for_fetch

ALLOWED_CONTENT_TYPES = {
    "text/html",
    "text/plain",
    "application/json",
    "application/xml",
    "text/xml",
}


def _normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    compact = "\n".join(line for line in lines if line)
    compact = re.sub(r"\n{3,}", "\n\n", compact)
    return compact.strip()


def _extract_text_from_html(html: str) -> tuple[str | None, str]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "iframe", "object", "form", "svg", "canvas"]):
        tag.decompose()

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    text = soup.get_text("\n")
    return title, _normalize_text(text)


def safe_fetch(
    url: str,
    max_chars: int = 12000,
    timeout_seconds: int = 10,
    max_size_bytes: int = 1_000_000,
    output_format: str = "markdown",
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
):
    try:
        ok, error, _ = validate_url_for_fetch(
            url=url,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
        )
        if not ok:
            return {
                "status": "error",
                "url": url,
                "error": error,
            }

        timeout = httpx.Timeout(timeout_seconds)
        headers = {
            "User-Agent": "ai-agent-safe-fetch/0.1",
            "Accept": "text/html,text/plain,application/json,application/xml,text/xml;q=0.9,*/*;q=0.1",
        }

        with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()

                content_type_header = (response.headers.get("content-type") or "").lower()
                content_type = content_type_header.split(";")[0].strip()

                if content_type and content_type not in ALLOWED_CONTENT_TYPES:
                    return {
                        "status": "error",
                        "url": url,
                        "error": f"Blocked content type: {content_type}",
                    }

                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > max_size_bytes:
                        return {
                            "status": "error",
                            "url": url,
                            "error": f"Response too large ({len(raw)} bytes)",
                        }

        if output_format not in {"markdown", "text"}:
            return {
                "status": "error",
                "url": url,
                "error": f"Unsupported output_format: {output_format}",
            }

        decoded = bytes(raw).decode("utf-8", errors="replace")

        title = None
        if output_format == "text":
            content = _normalize_text(decoded)
        elif content_type == "text/html" or "<html" in decoded.lower():
            title, content = _extract_text_from_html(decoded)
        else:
            content = _normalize_text(decoded)

        if len(content) > max_chars:
            content = content[:max_chars]

        return {
            "status": "ok",
            "url": url,
            "title": title,
            "content": content,
            "content_type": content_type or None,
            "char_count": len(content),
            "citation": {
                "url": url,
                "title": title,
                "fetched_at": datetime.now(UTC).isoformat(),
            },
            "error": None,
        }
    except httpx.HTTPError as e:
        return {
            "status": "error",
            "url": url,
            "error": f"Fetch failed: {e}",
        }
    except Exception as e:
        return {
            "status": "error",
            "url": url,
            "error": str(e),
        }
