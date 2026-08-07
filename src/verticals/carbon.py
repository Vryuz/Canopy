"""Carbon-project claim verification.

A carbon credit *is* a claim — "this land was reforested / this forest is being
protected / this cropland switched to regenerative practice" — and the whole market runs
on whether that claim is defensible. Verra invalidated 37 rice-methane projects (4.5M
credits, ~99.9% of all rice credits ever issued) over integrity; buyers are terrified of
holding junk. This checks a stated project claim against federal vegetation ground truth
and flags the two things that sink credits: the project isn't real, or its additionality
doesn't hold.

Buyer: credit buyers, corporate net-zero desks, and the verification bodies (VVBs) who
must not certify a credit that later gets clawed back. This is Canopy Wedge 1 — sell the
attestation *to* the developers, don't become one.

Mireye supplies the ground truth; the claim is the external assertion being tested. A
Global Forest Watch / registry second source is the fusion upgrade (see module notes).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from src.clients.osm import ProtectedArea, protected_areas_at
from src.models import (
    Claim,
    Coordinate,
    DataGap,
    Discrepancy,
    Evidence,
    Severity,
    Signal,
)

OSM_SOURCE = "OSM_OVERPASS"
OSM_SOURCE_URL = "https://www.openstreetmap.org"

# Second source: a function (lat, lng) -> protected areas. Injectable so tests don't hit
# the network and the live default can degrade gracefully.
ProtectedAreasFn = Callable[[float, float], list[ProtectedArea]]

# Explicit field list: the vegetation signals span wildfire_underwrite + land_cover presets,
# so no single preset carries them all.
CARBON_FIELDS = [
    "lcms_class",
    "land_use_class",
    "cdl_class",
    "tree_canopy_pct",
    "ndvi_current",
    "ndvi_change_5y",
    "intersects_wetland",
]

# Project archetypes. The claim text is matched to one; each implies a different expected
# ground truth.
REFORESTATION = "reforestation"        # newly established trees — expect canopy + greening
AVOIDED_DEFORESTATION = "avoided_deforestation"  # REDD+ — expect intact existing forest
SOIL_CARBON = "soil_carbon"            # regenerative ag — expect cropland
GRASSLAND = "grassland"                # avoided grassland conversion — expect grassland

# Thresholds — screening heuristics, not certification criteria.
CANOPY_FOREST_PCT = 40.0   # at/above this, the parcel reads as forest
CANOPY_SPARSE_PCT = 10.0   # below this, essentially no tree cover
NDVI_GAIN = 0.05           # a real greening trend over 5 years
NDVI_LOSS = -0.05          # a real decline — reversal / disturbance risk

_CLAIM_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (REFORESTATION, ("reforest", "afforest", "tree planting", "tree-planting", "plant",
                     "restoration", "revegetat")),
    (AVOIDED_DEFORESTATION, ("avoided deforestation", "redd", "forest protection",
                             "protect", "avoided conversion", "conserv", "intact forest")),
    (SOIL_CARBON, ("soil carbon", "regenerative", "no-till", "cover crop", "cropland",
                   "agricultur")),
    (GRASSLAND, ("grassland", "rangeland", "avoided grassland", "prairie")),
]

_FOREST_LCMS = ("tree", "forest")
_CROP_LCMS = ("crop", "agric")
_GRASS_LCMS = ("grass", "herb", "shrub")


class CarbonVertical:
    """Reads a carbon-project claim and checks it against two independent sources:
    Mireye vegetation ground truth, and OSM protected-area status (the additionality
    crux — land already legally protected would have been conserved regardless)."""

    preset = None
    fields = CARBON_FIELDS

    def __init__(self, protected_areas_fn: ProtectedAreasFn | None = None):
        self._protected_areas = protected_areas_fn or protected_areas_at

    # ------------------------------------------------------------------- claim

    def parse_claim(self, text: str) -> Claim:
        lowered = text.lower()
        for project_type, keywords in _CLAIM_KEYWORDS:
            if any(k in lowered for k in keywords):
                return Claim(text=text, subject="carbon_project", asserted_value=project_type)
        # An unrecognised claim is still screened; it just has no expected land cover to test.
        return Claim(text=text, subject="carbon_project", asserted_value=None)

    # ---------------------------------------------------------------- external

    async def gather_external(
        self, claim: Claim, location: Coordinate, evidence: list[Evidence]
    ) -> tuple[list[Signal], list[DataGap], list[Discrepancy]]:
        """Second source: OSM protected-area status. The core additionality test for an
        avoided-deforestation credit is whether the land was already legally protected —
        if so, the "avoided" deforestation would not have happened, and the credit is not
        additional. Also surfaces the NDVI trajectory as a cited signal."""
        signals: list[Signal] = []
        gaps: list[DataGap] = []
        discrepancies: list[Discrepancy] = []
        now = datetime.now(timezone.utc)

        # -- NDVI trajectory signal (from Mireye evidence) --
        trend = _get(evidence, "ndvi_change_5y")
        if trend is not None:
            try:
                delta = float(trend.value)
                direction = "greening" if delta >= NDVI_GAIN else "declining" if delta <= NDVI_LOSS else "flat"
                signals.append(
                    Signal(
                        label="5-year vegetation trajectory (additionality signal)",
                        detail=(
                            f"NDVI change over 5 years is {delta:+.2f} ({direction}). "
                            + {
                                "greening": "consistent with vegetation being added.",
                                "declining": "a red flag for loss or reversal on a credited parcel.",
                                "flat": "no measurable change — additionality is hard to defend.",
                            }[direction]
                        ),
                        source=trend.source,
                        source_url=trend.source_url,
                        fetched_at=trend.fetched_at,
                        weight=Severity.MAJOR if delta <= NDVI_LOSS else Severity.MINOR,
                    )
                )
            except (TypeError, ValueError):
                pass

        # -- Protected-area fusion (second source) --
        try:
            areas = self._protected_areas(location.lat, location.lng)
        except Exception as exc:
            gaps.append(
                DataGap(
                    field="protected_areas",
                    reason=f"protected-area lookup unavailable: {exc}",
                    source=OSM_SOURCE,
                    retryable=True,
                )
            )
            return signals, gaps, discrepancies

        if not areas:
            return signals, gaps, discrepancies

        names = "; ".join(
            f"{a.name} ({a.iucn_level or a.designation.replace('_', ' ')})" for a in areas
        )
        signals.append(
            Signal(
                label="Protected-area status (independent source)",
                detail=f"Parcel lies within: {names}.",
                source=OSM_SOURCE,
                source_url=OSM_SOURCE_URL,
                fetched_at=now,
                weight=Severity.MINOR,
            )
        )

        strict = [a for a in areas if a.is_strict]
        if claim.asserted_value == AVOIDED_DEFORESTATION and strict:
            top = strict[0]
            discrepancies.append(
                Discrepancy(
                    field="protected_areas",
                    claimed="avoided deforestation is additional",
                    observed=f"already within {top.name} ({top.iucn_level or top.designation})",
                    severity=Severity.CRITICAL,
                    explanation=(
                        f"The parcel is already inside {top.name}, a strictly protected area. "
                        "Land under existing legal protection would have been conserved without "
                        "the project, so an avoided-deforestation credit here fails additionality — "
                        "you cannot be paid to prevent a loss that law already prevents."
                    ),
                )
            )

        return signals, gaps, discrepancies

    # ----------------------------------------------------------------- compare

    def compare(self, claim: Claim, evidence: list[Evidence]) -> list[Discrepancy]:
        if claim.asserted_value is None:
            return []

        canopy = _num(evidence, "tree_canopy_pct")
        ndvi_change = _num(evidence, "ndvi_change_5y")
        lcms = _str(evidence, "lcms_class")
        canopy_ev = [e for e in (_get(evidence, "tree_canopy_pct"), _get(evidence, "lcms_class")) if e]
        ndvi_ev = [e for e in (_get(evidence, "ndvi_change_5y"),) if e]

        handler = {
            REFORESTATION: self._check_reforestation,
            AVOIDED_DEFORESTATION: self._check_avoided_deforestation,
            SOIL_CARBON: self._check_soil_carbon,
            GRASSLAND: self._check_grassland,
        }[claim.asserted_value]

        found = handler(canopy, ndvi_change, lcms, canopy_ev, ndvi_ev)
        found.extend(self._wetland_flag(claim, evidence))
        return found

    # -- per-archetype checks ------------------------------------------------

    def _check_reforestation(self, canopy, ndvi_change, lcms, canopy_ev, ndvi_ev):
        found: list[Discrepancy] = []
        # 1. Is there anything actually growing? A reforestation credit over bare ground
        #    with no canopy is the classic "the project isn't real" failure.
        if canopy is not None and canopy < CANOPY_SPARSE_PCT and not _is(lcms, _FOREST_LCMS):
            found.append(
                Discrepancy(
                    field="tree_canopy_pct",
                    claimed="reforestation established",
                    observed=f"{canopy:.0f}% canopy" + (f", land cover '{lcms}'" if lcms else ""),
                    severity=Severity.CRITICAL,
                    explanation=(
                        "Claim asserts reforestation, but tree canopy is effectively absent. "
                        "The credited trees are not detectable in federal land-cover data — "
                        "the project may not exist on the ground."
                    ),
                    evidence=canopy_ev,
                )
            )
        # 2. Additionality: canopy present but no greening → the forest likely predates the
        #    project, so the credit isn't additional.
        elif ndvi_change is not None and ndvi_change < NDVI_GAIN and canopy and canopy >= CANOPY_FOREST_PCT:
            severity = Severity.CRITICAL if ndvi_change <= NDVI_LOSS else Severity.MAJOR
            found.append(
                Discrepancy(
                    field="ndvi_change_5y",
                    claimed="new vegetation added",
                    observed=f"NDVI change {ndvi_change:+.2f} over 5y with {canopy:.0f}% existing canopy",
                    severity=severity,
                    explanation=(
                        "Canopy is already mature and the 5-year trend shows no gain"
                        + (" (in fact a decline)" if ndvi_change <= NDVI_LOSS else "")
                        + ". A reforestation credit here is hard to defend as additional — the "
                        "forest appears to predate the project."
                    ),
                    evidence=ndvi_ev,
                )
            )
        return found

    def _check_avoided_deforestation(self, canopy, ndvi_change, lcms, canopy_ev, ndvi_ev):
        found: list[Discrepancy] = []
        # There must be forest to protect. A REDD+ credit over sparse cover means an
        # inflated baseline — protecting a forest that isn't there.
        if canopy is not None and canopy < CANOPY_SPARSE_PCT and not _is(lcms, _FOREST_LCMS):
            found.append(
                Discrepancy(
                    field="tree_canopy_pct",
                    claimed="protecting existing forest",
                    observed=f"{canopy:.0f}% canopy" + (f", land cover '{lcms}'" if lcms else ""),
                    severity=Severity.CRITICAL,
                    explanation=(
                        "Claim protects standing forest, but canopy is effectively absent. "
                        "There is little forest to avoid deforesting — a hallmark of an "
                        "inflated REDD+ baseline."
                    ),
                    evidence=canopy_ev,
                )
            )
        elif ndvi_change is not None and ndvi_change <= NDVI_LOSS:
            found.append(
                Discrepancy(
                    field="ndvi_change_5y",
                    claimed="forest kept intact",
                    observed=f"NDVI change {ndvi_change:+.2f} over 5y",
                    severity=Severity.MAJOR,
                    explanation=(
                        "The protected parcel shows a measurable vegetation decline — possible "
                        "loss or leakage inside a credit that claims the forest stayed intact."
                    ),
                    evidence=ndvi_ev,
                )
            )
        return found

    def _check_soil_carbon(self, canopy, ndvi_change, lcms, canopy_ev, ndvi_ev):
        # Regenerative-ag / soil-carbon credits should sit on cropland.
        if lcms and not _is(lcms, _CROP_LCMS) and canopy is not None and canopy >= CANOPY_FOREST_PCT:
            return [
                Discrepancy(
                    field="lcms_class",
                    claimed="cropland under regenerative practice",
                    observed=f"land cover '{lcms}', {canopy:.0f}% canopy",
                    severity=Severity.MAJOR,
                    explanation=(
                        "A soil-carbon / regenerative-agriculture claim expects cropland, but the "
                        "parcel reads as forest. The stated practice can't be occurring here."
                    ),
                    evidence=canopy_ev,
                )
            ]
        return []

    def _check_grassland(self, canopy, ndvi_change, lcms, canopy_ev, ndvi_ev):
        if lcms and not _is(lcms, _GRASS_LCMS) and canopy is not None and canopy >= CANOPY_FOREST_PCT:
            return [
                Discrepancy(
                    field="lcms_class",
                    claimed="grassland / rangeland",
                    observed=f"land cover '{lcms}', {canopy:.0f}% canopy",
                    severity=Severity.MAJOR,
                    explanation=(
                        "An avoided-grassland-conversion claim expects grassland, but the parcel "
                        "reads as forest. The baseline land cover doesn't match the claim."
                    ),
                    evidence=canopy_ev,
                )
            ]
        return []

    def _wetland_flag(self, claim: Claim, evidence: list[Evidence]) -> list[Discrepancy]:
        # Afforesting a wetland drains carbon-rich soil and is an ecological/permitting red flag.
        if claim.asserted_value != REFORESTATION:
            return []
        wetland = _get(evidence, "intersects_wetland")
        if wetland is None or not bool(wetland.value):
            return []
        return [
            Discrepancy(
                field="intersects_wetland",
                claimed="reforestation site",
                observed="intersects a mapped wetland",
                severity=Severity.MINOR,
                explanation=(
                    "The reforestation parcel intersects a wetland. Afforesting wetlands can "
                    "release more soil carbon than the trees capture, and triggers USACE §404 "
                    "review — a flag for both integrity and permitting."
                ),
                evidence=[wetland],
            )
        ]


# --------------------------------------------------------------------- helpers


def _get(evidence: list[Evidence], name: str) -> Evidence | None:
    for item in evidence:
        if item.field == name:
            return item
    return None


def _num(evidence: list[Evidence], name: str) -> float | None:
    found = _get(evidence, name)
    if found is None:
        return None
    try:
        return float(found.value)
    except (TypeError, ValueError):
        return None


def _str(evidence: list[Evidence], name: str) -> str | None:
    found = _get(evidence, name)
    return str(found.value) if found is not None and found.value is not None else None


def _is(lcms: str | None, needles: tuple[str, ...]) -> bool:
    return bool(lcms) and any(n in lcms.lower() for n in needles)
