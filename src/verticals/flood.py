"""Flood-zone claim verification.

Buyer: mortgage lenders, title companies, insurance agents. A seller disclosure or
policy record says one thing; FEMA's map and the county's claims history say another.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from src.clients.openfema import OpenFemaClient
from src.models import (
    Claim,
    Coordinate,
    DataGap,
    Discrepancy,
    Evidence,
    Severity,
    Signal,
)

# FEMA Special Flood Hazard Areas — the zones that trigger mandatory flood insurance
# on a federally backed mortgage. V/VE additionally carry wave action.
SFHA_ZONES = {"A", "AE", "AH", "AO", "AR", "A99", "V", "VE"}
HIGH_RISK_COASTAL = {"V", "VE"}
MINIMAL_RISK_ZONES = {"X", "C", "B"}

FLOOD_ZONE_FIELDS = ("fema_flood_zone", "flood_zone", "fema_zone")
BFE_FIELDS = ("fema_base_flood_elevation", "base_flood_elevation", "bfe")

# The flood_risk preset omits the two fields this check turns on — fema_flood_zone
# sits in data_center_siting and fema_base_flood_elevation in no preset at all — so
# the vertical names its fields explicitly rather than expanding a preset.
FLOOD_FIELDS = [
    "fema_flood_zone",
    "fema_base_flood_elevation",
    "within_floodplain_polygon",
    "elevation",
    "coast_distance_m",
    "intersects_wetland",
    "nearest_waterbody_name",
    "surface_water_permanence_pct",
    # OpenFEMA filters by county FIPS. There is no county_fips field, but the
    # 11-digit census tract GEOID carries it in its first five characters.
    "tract_geoid",
    "political_county",
]
ZONE_PATTERN = re.compile(r"\bzone\s+([A-Z]{1,2}\d{0,2})\b", re.IGNORECASE)

NEGATION_MARKERS = (
    "not in",
    "no flood",
    "outside",
    "not located in",
    "not a flood",
    "isn't in",
    "is not",
    "free of",
)


class FloodVertical:
    """Reads a plain-English flood claim and checks it against FEMA ground truth."""

    preset = None
    fields = FLOOD_FIELDS

    def __init__(self, fema: OpenFemaClient | None = None):
        self.fema = fema or OpenFemaClient()

    # ------------------------------------------------------------------- claim

    def parse_claim(self, text: str) -> Claim:
        """Extract the assertion. Two shapes: a named zone, or a denial of flood risk."""
        lowered = text.lower()

        match = ZONE_PATTERN.search(text)
        if match:
            zone = match.group(1).upper()
            return Claim(
                text=text,
                subject="fema_flood_zone",
                asserted_value=zone,
            )

        if any(marker in lowered for marker in NEGATION_MARKERS):
            return Claim(
                text=text,
                subject="fema_flood_zone",
                asserted_value="NOT_IN_SFHA",
            )

        # An unparsed claim still gets screened; it just has nothing to contradict.
        return Claim(text=text, subject="fema_flood_zone", asserted_value=None)

    # ---------------------------------------------------------------- external

    async def gather_external(
        self, claim: Claim, location: Coordinate, evidence: list[Evidence]
    ) -> tuple[list[Signal], list[DataGap], list[Discrepancy]]:
        county_fips = _county_fips(evidence)
        if not county_fips:
            return [], [
                DataGap(
                    field="openfema_context",
                    reason="county FIPS not resolved, so FEMA history could not be queried",
                    source="OPENFEMA",
                )
            ], []

        signals: list[Signal] = []
        gaps: list[DataGap] = []

        declarations = await self.fema.get_declarations(county_fips)
        flood_events = [d for d in declarations if d.is_flood_related]
        if flood_events:
            recent = sorted(
                flood_events,
                key=lambda d: d.declaration_date or _EPOCH,
                reverse=True,
            )[:3]
            detail = ", ".join(
                f"{d.title.title()} ({d.declaration_date.year})" if d.declaration_date else d.title.title()
                for d in recent
            )
            signals.append(
                Signal(
                    label="Federal flood disaster declarations",
                    detail=f"{len(flood_events)} flood-related declarations in this county. Most recent: {detail}",
                    source="OPENFEMA_DisasterDeclarationsSummaries",
                    source_url="https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries",
                    fetched_at=_now(),
                    weight=Severity.MAJOR if len(flood_events) >= 3 else Severity.MINOR,
                )
            )

        claims = await self.fema.get_claims_summary(county_fips)
        if not claims.available:
            gaps.append(
                DataGap(
                    field="nfip_claims",
                    reason=claims.note or "NFIP claims dataset unavailable",
                    source="OPENFEMA_FimaNfipClaims",
                    retryable=True,
                )
            )
        elif claims.claim_count:
            span = (
                f"{claims.earliest_year}–{claims.latest_year}"
                if claims.earliest_year
                else "unknown period"
            )
            zone_note = ""
            if claims.zones_on_claims:
                top = ", ".join(f"{z} ({n})" for z, n in claims.zones_on_claims.items())
                zone_note = f" Claims came from zones: {top}."
            prefix = "At least " if claims.truncated else ""
            cap_note = f" {claims.note}" if claims.truncated and claims.note else ""
            signals.append(
                Signal(
                    label="NFIP paid flood claims (county)",
                    detail=(
                        f"{prefix}{claims.claim_count:,} paid claims totalling "
                        f"${claims.total_paid:,.0f} over {span}.{zone_note}{cap_note}"
                    ),
                    source="OPENFEMA_FimaNfipClaims",
                    source_url="https://www.fema.gov/api/open/v2/FimaNfipClaims",
                    fetched_at=claims.fetched_at,
                    weight=Severity.MAJOR if claims.claim_count >= 500 else Severity.MINOR,
                )
            )

        return signals, gaps, []

    # ----------------------------------------------------------------- compare

    def compare(self, claim: Claim, evidence: list[Evidence]) -> list[Discrepancy]:
        zone_evidence = _find_evidence(evidence, FLOOD_ZONE_FIELDS)
        if zone_evidence is None or claim.asserted_value is None:
            return []

        observed = str(zone_evidence.value).upper().strip()
        in_sfha = observed in SFHA_ZONES
        discrepancies: list[Discrepancy] = []

        if claim.asserted_value == "NOT_IN_SFHA":
            if in_sfha:
                coastal = observed in HIGH_RISK_COASTAL
                discrepancies.append(
                    Discrepancy(
                        field="fema_flood_zone",
                        claimed="not in a flood zone",
                        observed=observed,
                        severity=Severity.CRITICAL,
                        explanation=(
                            f"FEMA maps this location as Zone {observed}, a Special Flood "
                            f"Hazard Area{' with wave action' if coastal else ''}. "
                            "Flood insurance is mandatory on a federally backed mortgage here."
                        ),
                        evidence=[zone_evidence],
                    )
                )
        elif claim.asserted_value != observed:
            claimed_in_sfha = claim.asserted_value in SFHA_ZONES
            # Understating risk is a different problem from overstating it.
            severity = (
                Severity.CRITICAL
                if in_sfha and not claimed_in_sfha
                else Severity.MAJOR
                if in_sfha != claimed_in_sfha
                else Severity.MINOR
            )
            discrepancies.append(
                Discrepancy(
                    field="fema_flood_zone",
                    claimed=claim.asserted_value,
                    observed=observed,
                    severity=severity,
                    explanation=(
                        f"Claim states Zone {claim.asserted_value}; FEMA maps Zone {observed}."
                        + (
                            " The claimed zone understates the mapped flood risk."
                            if in_sfha and not claimed_in_sfha
                            else ""
                        )
                    ),
                    evidence=[zone_evidence],
                )
            )

        discrepancies.extend(self._elevation_check(evidence, zone_evidence, in_sfha))
        return discrepancies

    @staticmethod
    def _elevation_check(
        evidence: list[Evidence], zone_evidence: Evidence, in_sfha: bool
    ) -> list[Discrepancy]:
        """Ground below the base flood elevation is the concrete form of the risk."""
        if not in_sfha:
            return []

        bfe = _find_evidence(evidence, BFE_FIELDS)
        ground = _find_evidence(evidence, ("elevation",))
        if not bfe or not ground:
            return []

        # Mireye reports elevation in metres and FEMA BFE in feet. Normalise both
        # before subtracting — a raw comparison would read 4.6 ft as 4.6 m and
        # invent a 3 m deficit that isn't there.
        bfe_m, ground_m = bfe.as_meters(), ground.as_meters()
        if bfe_m is None or ground_m is None:
            return []

        deficit = bfe_m - ground_m
        if deficit <= 0:
            return []

        return [
            Discrepancy(
                field="elevation",
                claimed="—",
                observed=f"{ground.display()} ground vs {bfe.display()} BFE",
                severity=Severity.MAJOR,
                explanation=(
                    f"Ground elevation sits {deficit:.2f} m below the base flood elevation "
                    f"for Zone {zone_evidence.value}."
                ),
                evidence=[ground, bfe],
            )
        ]


# --------------------------------------------------------------------- helpers

_EPOCH = datetime(1900, 1, 1, tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _find_evidence(evidence: list[Evidence], names: tuple[str, ...]) -> Evidence | None:
    for name in names:
        for item in evidence:
            if item.field == name:
                return item
    return None


def _find_value(evidence: list[Evidence], names: tuple[str, ...]):
    found = _find_evidence(evidence, names)
    return found.value if found else None


def _county_fips(evidence: list[Evidence]) -> str | None:
    """Derive the 5-digit county FIPS OpenFEMA filters on.

    Preferred source is the census tract GEOID (SSCCCTTTTTT); an explicit county
    FIPS field is accepted if one ever appears in the catalog.
    """
    explicit = _find_value(evidence, ("county_fips", "fips_county"))
    if explicit:
        return str(explicit).zfill(5)

    tract = _find_value(evidence, ("tract_geoid",))
    if tract:
        digits = "".join(ch for ch in str(tract) if ch.isdigit())
        if len(digits) >= 5:
            return digits[:5]
    return None
