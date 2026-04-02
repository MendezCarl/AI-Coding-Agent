from __future__ import annotations


def should_use_research(hits: list[dict], min_hits: int = 1, max_distance: float = 1.2) -> bool:
    if len(hits) < min_hits:
        return True

    best = min((hit.get("distance", 9999.0) for hit in hits), default=9999.0)
    return best > max_distance
