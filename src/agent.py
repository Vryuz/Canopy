"""The verification loop: resolve -> gather -> compare -> reason -> decide -> attest.

This is the reusable core. A vertical supplies the domain knowledge (which fields to
pull, how to read a claim, what counts as a contradiction); the loop below is what
turns that into a cited attestation and never varies.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from src.clients.mireye import MireyeClient
from src.models import (
    Claim,
    Confidence,
    Coordinate,
    DataGap,
    Discrepancy,
    Evidence,
    Severity,
    Signal,
    Verdict,
    VerdictKind,
    VerificationMemo,
)


class Vertical(Protocol):
    """Domain plug-in for the verification loop.

    A vertical names either a preset or an explicit field list — presets are
    convenient, but they don't always contain the fields a given check turns on.
    """

    preset: str | None
    fields: list[str] | None

    def parse_claim(self, text: str) -> Claim: ...

    async def gather_external(
        self, location: Coordinate, evidence: list[Evidence]
    ) -> tuple[list[Signal], list[DataGap]]: ...

    def compare(
        self, claim: Claim, evidence: list[Evidence]
    ) -> list[Discrepancy]: ...


# Any field the agent could not read is a hole in the attestation, so the verdict's
# confidence is capped by how much of the requested evidence actually arrived.
COVERAGE_FLOOR_HIGH = 0.8
COVERAGE_FLOOR_MEDIUM = 0.5


def _decide(
    discrepancies: list[Discrepancy],
    signals: list[Signal],
    coverage: float,
) -> Verdict:
    critical = [d for d in discrepancies if d.severity is Severity.CRITICAL]
    major = [d for d in discrepancies if d.severity is Severity.MAJOR]
    minor = [d for d in discrepancies if d.severity is Severity.MINOR]
    heavy_signals = [s for s in signals if s.weight in (Severity.CRITICAL, Severity.MAJOR)]

    if coverage >= COVERAGE_FLOOR_HIGH:
        confidence = Confidence.HIGH
    elif coverage >= COVERAGE_FLOOR_MEDIUM:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW

    if critical:
        kind = VerdictKind.DISPUTED
        reasoning = (
            f"{len(critical)} critical contradiction(s) between the claim and federal "
            f"ground truth: {'; '.join(d.explanation for d in critical)}"
        )
    elif major:
        kind = VerdictKind.DISPUTED
        reasoning = (
            f"{len(major)} material discrepancy(ies) found: "
            f"{'; '.join(d.explanation for d in major)}"
        )
    elif minor or heavy_signals:
        kind = VerdictKind.FLAGGED
        parts = [d.explanation for d in minor] + [s.detail for s in heavy_signals]
        reasoning = f"Claim is not contradicted, but context warrants review: {'; '.join(parts)}"
    elif confidence is Confidence.LOW:
        kind = VerdictKind.INCONCLUSIVE
        reasoning = (
            "Too little of the requested evidence resolved to support or contradict "
            "the claim. See declared data gaps."
        )
    else:
        kind = VerdictKind.VERIFIED
        reasoning = "Every checked field agrees with the claim, and no adverse signals were found."

    if kind is not VerdictKind.INCONCLUSIVE and confidence is Confidence.LOW:
        reasoning += " Confidence is low because a substantial share of requested fields did not resolve."

    return Verdict(kind=kind, confidence=confidence, reasoning=reasoning)


class VerificationAgent:
    def __init__(self, mireye: MireyeClient, vertical: Vertical):
        self.mireye = mireye
        self.vertical = vertical

    async def verify(self, *, address: str | None = None,
                     coordinate: Coordinate | None = None,
                     claim_text: str) -> VerificationMemo:
        if coordinate is None:
            if not address:
                raise ValueError("Provide either an address or a coordinate.")
            coordinate = await self.mireye.geocode(address)

        claim = self.vertical.parse_claim(claim_text)

        evidence, gaps = await self.mireye.fetch(
            coordinate.lat,
            coordinate.lng,
            preset=getattr(self.vertical, "preset", None),
            fields=getattr(self.vertical, "fields", None),
        )

        signals, external_gaps = await self.vertical.gather_external(coordinate, evidence)
        gaps = [*gaps, *external_gaps]

        discrepancies = self.vertical.compare(claim, evidence)

        requested = len(evidence) + len(gaps)
        coverage = len(evidence) / requested if requested else 0.0
        verdict = _decide(discrepancies, signals, coverage)

        if not coordinate.parcel_grade:
            verdict.reasoning += (
                " Note: this location was interpolated from the street address rather than "
                "matched to a rooftop, so parcel-specific conclusions should be confirmed."
            )

        return VerificationMemo(
            claim=claim,
            location=coordinate,
            verdict=verdict,
            evidence=evidence,
            discrepancies=discrepancies,
            signals=signals,
            data_gaps=gaps,
        )
