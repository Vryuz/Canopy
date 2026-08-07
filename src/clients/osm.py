"""OpenStreetMap Overpass client — a free, public list of US data centers.

The Mireye recipe every blog post follows: take a public address/location list, enrich
it, find the tail. OSM tags data centers (`telecom=data_center`, and the older
`building=data_center` / `power=plant + plant:source=...`), which gives real coordinates
for a national scan without paying for a proprietary list.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pydantic import BaseModel

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CACHE_PATH = DATA_DIR / "us_data_centers.json"

# overpass-api.de rejects requests without a real User-Agent (406). Mirrors are tried in
# order — the main instance rate-limits aggressively, so a fallback keeps a scan moving.
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
USER_AGENT = "verification-agent/0.1 (data-center permitting research; contact: local)"

# CONUS bounding box (south, west, north, east). Excludes AK/HI to stay inside the federal
# hazard grids the screen relies on anyway.
CONUS_BBOX = (24.0, -125.0, 49.5, -66.0)

SOURCE_NAME = "OSM_OVERPASS"
SOURCE_URL = "https://www.openstreetmap.org"


class DataCenter(BaseModel):
    osm_id: str
    name: str | None
    lat: float
    lng: float
    operator: str | None = None


def _query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    b = f"{s},{w},{n},{e}"
    # Match the common data-center tags across nodes, ways, and relations.
    return f"""[out:json][timeout:90];
(
  nwr[telecom=data_center]({b});
  nwr[building=data_center]({b});
  nwr[man_made=data_center]({b});
);
out center tags;"""


def _parse(elements: list[dict]) -> list[DataCenter]:
    seen: set[str] = set()
    out: list[DataCenter] = []
    for el in elements:
        centre = el if "lat" in el else el.get("center", {})
        lat, lng = centre.get("lat"), centre.get("lon")
        if lat is None or lng is None:
            continue
        osm_id = f"{el.get('type')}/{el.get('id')}"
        if osm_id in seen:
            continue
        seen.add(osm_id)
        tags = el.get("tags") or {}
        out.append(
            DataCenter(
                osm_id=osm_id,
                name=tags.get("name"),
                lat=float(lat),
                lng=float(lng),
                operator=tags.get("operator"),
            )
        )
    return out


def fetch_us_data_centers(
    *, bbox: tuple[float, float, float, float] = CONUS_BBOX, use_cache: bool = True
) -> list[DataCenter]:
    """Return all OSM-tagged US data centers, cached to disk after the first pull."""
    if use_cache and CACHE_PATH.exists():
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return [DataCenter(**row) for row in raw["data_centers"]]

    query = _query(bbox)
    last_error: Exception | None = None
    for endpoint in ENDPOINTS:
        try:
            response = httpx.post(
                endpoint,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=120.0,
            )
            response.raise_for_status()
            centers = _parse(response.json().get("elements", []))
            if centers:
                _write_cache(centers, endpoint)
                return centers
        except Exception as exc:  # try the next mirror
            last_error = exc
            continue

    raise RuntimeError(f"all Overpass endpoints failed; last error: {last_error}")


def _write_cache(centers: list[DataCenter], endpoint: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "endpoint": endpoint,
                "count": len(centers),
                "data_centers": [c.model_dump() for c in centers],
            },
            indent=1,
        ),
        encoding="utf-8",
    )
