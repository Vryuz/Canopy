"""OpenFEMA client. No auth required — https://www.fema.gov/about/openfema/api"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel

BASE_URL = "https://www.fema.gov/api/open/v2"
CLAIMS_URL = f"{BASE_URL}/FimaNfipClaims"
DECLARATIONS_URL = f"{BASE_URL}/DisasterDeclarationsSummaries"

FLOOD_INCIDENT_TYPES = {"Flood", "Hurricane", "Severe Storm", "Coastal Storm", "Tsunami"}


class Declaration(BaseModel):
    disaster_number: int
    declaration_date: datetime | None
    incident_type: str
    title: str

    @property
    def is_flood_related(self) -> bool:
        return self.incident_type in FLOOD_INCIDENT_TYPES


class ClaimsSummary(BaseModel):
    county_fips: str
    claim_count: int
    total_paid: float
    earliest_year: int | None
    latest_year: int | None
    zones_on_claims: dict[str, int]
    available: bool = True
    truncated: bool = False
    note: str | None = None
    fetched_at: datetime


class OpenFemaError(RuntimeError):
    pass


def _parse_date(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


class OpenFemaClient:
    """Queries FEMA's public disaster and NFIP datasets by county FIPS."""

    def __init__(self, *, timeout: float = 45.0):
        self.timeout = timeout

    async def _get(self, url: str, params: dict[str, Any]) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            if response.status_code >= 400:
                raise OpenFemaError(f"{response.status_code}: {response.text[:200]}")
            body = response.json()
            if "error" in body:
                raise OpenFemaError(str(body["error"])[:300])
            return body

    async def get_declarations(
        self, county_fips: str, *, limit: int = 200
    ) -> list[Declaration]:
        """County FIPS is 5 digits: 2-digit state + 3-digit county."""
        state_code, county_code = county_fips[:2], county_fips[2:]
        params = {
            "$filter": f"fipsStateCode eq '{state_code}' and fipsCountyCode eq '{county_code}'",
            "$select": "disasterNumber,declarationDate,incidentType,declarationTitle",
            "$top": limit,
        }
        body = await self._get(DECLARATIONS_URL, params)

        seen: set[int] = set()
        declarations: list[Declaration] = []
        for row in body.get("DisasterDeclarationsSummaries", []):
            number = row.get("disasterNumber")
            if number in seen:
                continue
            seen.add(number)
            declarations.append(
                Declaration(
                    disaster_number=number,
                    declaration_date=_parse_date(row.get("declarationDate")),
                    incident_type=row.get("incidentType") or "Unknown",
                    title=row.get("declarationTitle") or "",
                )
            )
        return declarations

    async def get_claims_summary(
        self, county_fips: str, *, limit: int = 10000
    ) -> ClaimsSummary:
        """Aggregate NFIP claims for a county.

        The dataset has been suspended before; a failure returns an unavailable
        summary rather than raising, so the memo can declare the gap honestly.
        """
        now = datetime.now(timezone.utc)
        params = {
            "$filter": f"countyCode eq '{county_fips}'",
            "$select": "yearOfLoss,amountPaidOnBuildingClaim,amountPaidOnContentsClaim,ratedFloodZone",
            "$top": limit,
        }

        try:
            body = await self._get(CLAIMS_URL, params)
        except (OpenFemaError, httpx.HTTPError) as exc:
            return ClaimsSummary(
                county_fips=county_fips,
                claim_count=0,
                total_paid=0.0,
                earliest_year=None,
                latest_year=None,
                zones_on_claims={},
                available=False,
                note=f"NFIP claims unavailable: {exc}",
                fetched_at=now,
            )

        rows = body.get("FimaNfipClaims", [])
        years = [r["yearOfLoss"] for r in rows if r.get("yearOfLoss")]
        total = sum(
            float(r.get("amountPaidOnBuildingClaim") or 0)
            + float(r.get("amountPaidOnContentsClaim") or 0)
            for r in rows
        )
        zones = Counter(r["ratedFloodZone"] for r in rows if r.get("ratedFloodZone"))

        # OpenFEMA caps a page at 10k rows. Saying "10,000 claims" when the real
        # number is higher would be exactly the kind of unsourced figure this
        # tool exists to catch.
        truncated = len(rows) >= limit
        note = (
            f"Counts are a floor: the query returned the {limit:,}-row API page cap, "
            "so the county's true totals are higher."
            if truncated
            else None
        )

        return ClaimsSummary(
            county_fips=county_fips,
            claim_count=len(rows),
            total_paid=total,
            earliest_year=min(years) if years else None,
            latest_year=max(years) if years else None,
            zones_on_claims=dict(zones.most_common(6)),
            truncated=truncated,
            note=note,
            fetched_at=now,
        )
