"""Moratorium Nation data — local moratoria on data centers, crypto, and storage.

Source: https://github.com/mjbommar/moratorium-data-2026 (CC-BY-4.0)
533 records, 505 of them data-center related, every one carrying a coordinate.
"""

from __future__ import annotations

import csv
import io
import json
import math
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pydantic import BaseModel

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
INVENTORY_PATH = DATA_DIR / "moratoria.csv"
LEGISLATION_PATH = DATA_DIR / "state_legislation.csv"

# raw.githubusercontent.com is blocked on some networks; codeload serves the same
# content as a repo tarball and is reachable where raw is not.
ARCHIVE_URL = (
    "https://codeload.github.com/mjbommar/moratorium-data-2026/tar.gz/refs/heads/main"
)
ARCHIVE_MEMBERS = {
    "moratorium-data-2026-main/data/moratorium_inventory.csv": INVENTORY_PATH,
    "moratorium-data-2026-main/data/state_legislation.csv": LEGISLATION_PATH,
}

SOURCE_NAME = "MORATORIUM_NATION_2026"
SOURCE_URL = "https://github.com/mjbommar/moratorium-data-2026"

# A moratorium that has expired or been rescinded is history, not a live constraint.
BLOCKING_STATUSES = {"active", "extended", "pending"}

EARTH_RADIUS_KM = 6371.0


class Moratorium(BaseModel):
    moratorium_id: str
    state: str
    jurisdiction: str
    jurisdiction_type: str
    enacted_status: str
    date_enacted: str | None
    duration: str | None
    sectors: list[str]
    lat: float
    lng: float
    distance_km: float = 0.0
    summary: str | None = None

    @property
    def is_blocking(self) -> bool:
        return self.enacted_status.lower() in BLOCKING_STATUSES


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _parse_sectors(raw: str) -> list[str]:
    """The sectors column is JSON-ish but inconsistently spaced across rows."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(s).strip() for s in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return [s.strip(' "[]') for s in raw.split(",") if s.strip(' "[]')]


def ensure_data(force: bool = False) -> Path:
    """Download the inventory if it isn't cached yet."""
    if INVENTORY_PATH.exists() and not force:
        return INVENTORY_PATH

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    response = httpx.get(ARCHIVE_URL, timeout=180.0, follow_redirects=True)
    response.raise_for_status()

    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
        for member, destination in ARCHIVE_MEMBERS.items():
            try:
                payload = archive.extractfile(member)
            except KeyError:
                continue
            if payload is not None:
                destination.write_bytes(payload.read())

    return INVENTORY_PATH


class MoratoriaClient:
    def __init__(self, path: Path | None = None):
        self.path = path or INVENTORY_PATH
        self._rows: list[Moratorium] | None = None

    def load(self) -> list[Moratorium]:
        if self._rows is not None:
            return self._rows

        if not self.path.exists():
            ensure_data()

        rows: list[Moratorium] = []
        with self.path.open(encoding="utf-8", newline="") as handle:
            for raw in csv.DictReader(handle):
                lat, lng = raw.get("latitude"), raw.get("longitude")
                if not lat or not lng:
                    continue
                try:
                    lat_f, lng_f = float(lat), float(lng)
                except ValueError:
                    continue

                rows.append(
                    Moratorium(
                        moratorium_id=raw.get("moratorium_id") or "",
                        state=raw.get("state_abbrev") or raw.get("state") or "",
                        jurisdiction=raw.get("jurisdiction") or "",
                        jurisdiction_type=raw.get("jurisdiction_type") or "",
                        enacted_status=(raw.get("enacted_status") or "unknown").lower(),
                        date_enacted=raw.get("date_enacted_iso") or None,
                        duration=raw.get("duration") or None,
                        sectors=_parse_sectors(raw.get("sectors") or ""),
                        lat=lat_f,
                        lng=lng_f,
                        summary=(raw.get("current_status") or None),
                    )
                )

        self._rows = rows
        return rows

    def find_nearby(
        self,
        lat: float,
        lng: float,
        *,
        radius_km: float = 80.0,
        sector: str = "data_center",
        blocking_only: bool = False,
    ) -> list[Moratorium]:
        matches: list[Moratorium] = []
        for row in self.load():
            if sector and sector not in row.sectors:
                continue
            if blocking_only and not row.is_blocking:
                continue
            distance = haversine_km(lat, lng, row.lat, row.lng)
            if distance <= radius_km:
                matches.append(row.model_copy(update={"distance_km": round(distance, 1)}))

        return sorted(matches, key=lambda m: m.distance_km)

    def state_summary(self, state_abbrev: str, sector: str = "data_center") -> dict:
        """How restrictive the whole state is, as context around a single site."""
        rows = [
            r
            for r in self.load()
            if r.state.upper() == state_abbrev.upper() and sector in r.sectors
        ]
        return {
            "total": len(rows),
            "blocking": sum(1 for r in rows if r.is_blocking),
            "fetched_at": datetime.now(timezone.utc),
        }
