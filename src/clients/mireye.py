"""Mireye Earth API client. Preserves per-field provenance on every value."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.models import Confidence, Coordinate, DataGap, Evidence

BASE_URL = "https://api.mireye.com"
FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "mireye"

# Timeouts follow Mireye's documented bounds: /v1/ask is bounded at 110s server-side,
# and a client timeout below that aborts requests that are still billing.
ASK_TIMEOUT = 120.0
FETCH_TIMEOUT = 90.0


class MireyeError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False, code: str | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


def _parse_ts(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _parse_confidence(raw: Any) -> Confidence:
    try:
        return Confidence(str(raw).lower())
    except ValueError:
        return Confidence.MEDIUM


class MireyeClient:
    """Wraps the Mireye REST API.

    Offline mode replays recorded fixtures so the agent is testable without a token.
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        offline: bool | None = None,
        base_url: str = BASE_URL,
    ):
        self.token = token or os.getenv("MIREYE_API_TOKEN") or ""
        env_offline = os.getenv("MIREYE_OFFLINE", "0") == "1"
        self.offline = env_offline if offline is None else offline
        if not self.token and not self.offline:
            self.offline = True
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------ transport

    async def _post(self, path: str, payload: dict, timeout: float) -> dict:
        if self.offline:
            return self._fixture(path, payload)

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}{path}", json=payload, headers=headers
            )
            if response.status_code >= 400:
                detail: Any = {}
                try:
                    detail = response.json().get("detail", {})
                except Exception:
                    detail = {}
                if isinstance(detail, dict):
                    raise MireyeError(
                        detail.get("message", response.text[:300]),
                        retryable=bool(detail.get("retryable")),
                        code=detail.get("error"),
                    )
                raise MireyeError(response.text[:300])
            return response.json()

    def _fixture(self, path: str, payload: dict) -> dict:
        name = path.strip("/").replace("/", "_")
        lat, lng = payload.get("lat"), payload.get("lng")
        preset = payload.get("preset")
        # Two verticals now both fetch by explicit field list (no preset), so the fixture
        # is keyed by coordinate first — otherwise a flood fetch and a DC fetch collide on
        # the same generic filename.
        candidates: list[str] = []
        if lat is not None and lng is not None:
            candidates.append(f"{name}_{lat:.2f}_{lng:.2f}.json")
        if preset:
            candidates.append(f"{name}_{preset}.json")
        candidates.append(f"{name}.json")

        for candidate in candidates:
            fixture = FIXTURE_DIR / candidate
            if fixture.exists():
                return json.loads(fixture.read_text(encoding="utf-8"))
        raise MireyeError(
            f"No fixture for {path} (looked for {candidates} in {FIXTURE_DIR}). "
            "Set MIREYE_API_TOKEN to run live."
        )

    # ------------------------------------------------------------------ endpoints

    async def geocode(self, address: str) -> Coordinate:
        data = await self._post("/v1/geocode", {"address": address}, timeout=30.0)
        accuracy_type = data.get("accuracy_type") or data.get("match_type") or ""
        return Coordinate(
            lat=data["lat"],
            lng=data["lng"],
            resolved_address=(
                data.get("normalized_address") or data.get("resolved_address") or address
            ),
            accuracy=accuracy_type or None,
            # Only a rooftop-grade match can carry a parcel-specific conclusion;
            # street interpolation can land hundreds of metres off in rural areas.
            parcel_grade="rooftop" in accuracy_type.lower(),
        )

    async def fetch(
        self,
        lat: float,
        lng: float,
        *,
        preset: str | None = None,
        fields: list[str] | None = None,
    ) -> tuple[list[Evidence], list[DataGap]]:
        payload: dict[str, Any] = {"lat": lat, "lng": lng}
        if preset:
            payload["preset"] = preset
        if fields:
            payload["fields"] = fields

        data = await self._post("/v1/fetch", payload, timeout=FETCH_TIMEOUT)
        return self._to_evidence(data)

    @staticmethod
    def _to_evidence(data: dict) -> tuple[list[Evidence], list[DataGap]]:
        evidence: list[Evidence] = []
        gaps: list[DataGap] = []

        for field, wrapper in (data.get("fields") or {}).items():
            if not isinstance(wrapper, dict):
                # Bare scalar with no provenance block — keep it, mark it unsourced.
                evidence.append(
                    Evidence(
                        field=field,
                        value=wrapper,
                        source="mireye",
                        fetched_at=datetime.now(timezone.utc),
                        confidence=Confidence.LOW,
                        note="value returned without a provenance block",
                    )
                )
                continue

            value = wrapper.get("value")
            status = str(wrapper.get("status") or "").lower()

            # The API distinguishes "we looked and there is nothing here" (absent)
            # from "we could not look" (error). Both are gaps, but the notes field
            # carries the reason a human needs, so prefer it over a generic string.
            if value is None or status in {"absent", "error", "unavailable"}:
                gaps.append(
                    DataGap(
                        field=field,
                        reason=(
                            wrapper.get("notes")
                            or wrapper.get("reason")
                            or f"source returned no value (status: {status or 'null'})"
                        ),
                        source=wrapper.get("source"),
                        retryable=status in {"error", "unavailable"},
                    )
                )
                continue

            evidence.append(
                Evidence(
                    field=field,
                    value=value,
                    source=wrapper.get("source", "mireye"),
                    source_url=wrapper.get("source_url"),
                    fetched_at=_parse_ts(wrapper.get("fetched_at")),
                    confidence=_parse_confidence(wrapper.get("confidence")),
                    unit=wrapper.get("unit"),
                    note=wrapper.get("notes"),
                    vintage=wrapper.get("dataset_vintage"),
                )
            )

        # A failed field is reported twice — once as a null-valued field wrapper and
        # again in partial_failures. The second copy carries the retryable flag, so
        # it upgrades the first rather than appending beside it.
        def _merge(gap: DataGap) -> None:
            for existing in gaps:
                if existing.field == gap.field:
                    existing.retryable = existing.retryable or gap.retryable
                    if gap.reason and gap.reason not in existing.reason:
                        existing.reason = gap.reason
                    existing.source = existing.source or gap.source
                    return
            gaps.append(gap)

        for failure in data.get("partial_failures") or []:
            _merge(
                DataGap(
                    field=failure.get("field", "unknown"),
                    reason=failure.get("error") or failure.get("message") or "fetch failed",
                    source=failure.get("source"),
                    retryable=bool(failure.get("retryable")),
                )
            )

        for gap in data.get("data_gaps") or []:
            _merge(
                DataGap(field=gap.get("field", "unknown"), reason=gap.get("reason", "no value"))
            )

        return evidence, gaps

    async def ask(self, lat: float, lng: float, question: str) -> dict:
        return await self._post(
            "/v1/ask", {"lat": lat, "lng": lng, "question": question}, timeout=ASK_TIMEOUT
        )

    async def lookup(self, address: str) -> dict:
        """Canonical parcel + jurisdiction. Costs 300 credits — call sparingly."""
        return await self._post("/v1/lookup", {"address": address}, timeout=60.0)
