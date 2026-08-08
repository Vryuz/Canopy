"""On-disk response cache — one mechanism serving three needs.

- **Credits:** a coordinate screened once never bills again. Real users re-run the same
  portfolio constantly; the demo re-runs the same handful of coordinates dozens of times.
- **Demo safety:** pre-warm the exact demo coordinates (`scripts/warm_demo.py`), set
  `CANOPY_CACHE_ONLY=1`, and the whole flow serves from disk — instant, network-independent,
  impossible to 504 on stage.
- **Freshness (product):** entries carry a fetched timestamp and a TTL, so re-screening on a
  schedule (moratoria shift quarterly, FEMA maps update) has a natural home.

Modes, via env:
  CANOPY_CACHE=1        enable read+write caching (default off, so nothing changes silently)
  CANOPY_CACHE_ONLY=1   serve only from cache; a miss raises instead of hitting the network
                        (implies caching enabled — the demo-replay mode)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "responses"
DEFAULT_TTL = 30 * 24 * 3600  # 30 days — geospatial ground truth moves slowly


class CacheMiss(RuntimeError):
    """Raised in cache-only mode when a key isn't present — the demo wasn't warmed."""


def enabled() -> bool:
    return os.getenv("CANOPY_CACHE") == "1" or cache_only()


def cache_only() -> bool:
    return os.getenv("CANOPY_CACHE_ONLY") == "1"


def key(namespace: str, payload: Any) -> str:
    """Stable key from a namespace + any JSON-able payload (params/body/coords)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(f"{namespace}|{blob}".encode("utf-8")).hexdigest()[:24]
    return f"{namespace}_{digest}"


def get(k: str, ttl: float = DEFAULT_TTL) -> Any | None:
    """Return the cached value, or None on miss/expiry. In cache-only mode a miss raises,
    because silently falling through to the network is exactly what the demo must not do."""
    path = CACHE_DIR / f"{k}.json"
    if path.exists():
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - rec["cached_at"] <= ttl:
                return rec["value"]
        except (json.JSONDecodeError, KeyError):
            pass
    if cache_only():
        raise CacheMiss(
            f"cache-only mode: no warmed entry for {k}. Run scripts/warm_demo.py first."
        )
    return None


def put(k: str, value: Any) -> None:
    if not enabled():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{k}.json").write_text(
        json.dumps({"cached_at": time.time(), "value": value}), encoding="utf-8"
    )
