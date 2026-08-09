"""Core verification primitives: observation -> evidence -> discrepancy -> attestation."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Severity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class VerdictKind(str, Enum):
    VERIFIED = "verified"
    DISPUTED = "disputed"
    FLAGGED = "flagged"
    INCONCLUSIVE = "inconclusive"


class Coordinate(BaseModel):
    lat: float
    lng: float
    resolved_address: str | None = None
    accuracy: str | None = None
    # False when the point came from street interpolation rather than a rooftop match.
    parcel_grade: bool = True

    def __str__(self) -> str:
        return f"{self.lat:.5f}, {self.lng:.5f}"


class Evidence(BaseModel):
    """A single cited fact. Provenance travels with the value, never beside it."""

    field: str
    value: Any
    source: str
    source_url: str | None = None
    fetched_at: datetime
    confidence: Confidence = Confidence.MEDIUM
    unit: str | None = None
    note: str | None = None
    vintage: str | None = None

    def display(self) -> str:
        if self.value is None:
            return "—"
        if isinstance(self.value, float):
            rendered = f"{self.value:,.2f}".rstrip("0").rstrip(".")
        else:
            rendered = str(self.value)
        return f"{rendered} {self.unit}" if self.unit else rendered

    def as_meters(self) -> float | None:
        """Normalise a length to metres. Mireye reports elevation in metres but
        FEMA base flood elevation in feet — comparing them raw is a real error."""
        try:
            magnitude = float(self.value)
        except (TypeError, ValueError):
            return None
        unit = (self.unit or "").lower()
        if unit in {"feet", "foot", "ft"}:
            return magnitude * 0.3048
        return magnitude


class DataGap(BaseModel):
    """A field we asked for and did not get. Declared, never silently dropped."""

    field: str
    reason: str
    source: str | None = None
    retryable: bool = False


class Claim(BaseModel):
    """What someone asserts about a location, before anyone checks."""

    text: str
    subject: str
    asserted_value: Any = None
    claimed_by: str | None = None


class Discrepancy(BaseModel):
    """Where the claim and the ground truth disagree."""

    field: str
    claimed: Any
    observed: Any
    severity: Severity
    explanation: str
    evidence: list[Evidence] = Field(default_factory=list)


class Signal(BaseModel):
    """A corroborating or contradicting fact that is not a direct claim comparison.

    Flood history, nearby moratoria, disaster declarations — context that shapes
    the verdict without being a field-level contradiction.
    """

    label: str
    detail: str
    source: str
    source_url: str | None = None
    fetched_at: datetime
    weight: Severity = Severity.MINOR


class Verdict(BaseModel):
    kind: VerdictKind
    confidence: Confidence
    reasoning: str

    @property
    def is_actionable(self) -> bool:
        return self.kind in (VerdictKind.DISPUTED, VerdictKind.FLAGGED)


class VerificationMemo(BaseModel):
    """The attestation. Every value in it carries its source and timestamp."""

    claim: Claim
    location: Coordinate
    verdict: Verdict
    evidence: list[Evidence] = Field(default_factory=list)
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)
    data_gaps: list[DataGap] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Set once the memo is persisted; the shareable /a/{id} address. Excluded from the
    # attestation hash so attaching it can't change the content it commits to.
    attestation_id: str | None = None

    def sources(self) -> list[str]:
        seen: list[str] = []
        for item in (*self.evidence, *self.signals):
            if item.source not in seen:
                seen.append(item.source)
        return seen


class SiteScore(BaseModel):
    """One scored dimension of a site screen (physical or regulatory)."""

    dimension: str
    score: float
    rationale: str
    evidence: list[Evidence] = Field(default_factory=list)


class Lever(BaseModel):
    """One community-benefit lever that could move a contested site toward a yes.

    Wave 3 of the thesis: a data center doesn't just take power/water/land — it can
    bring flexible capacity, waste heat, and water offsets. Each lever is a benefit
    the site could deliver, with a rough, honestly-hedged sizing.
    """

    name: str  # "Grid flexibility (VPP)", "District heat", "Water offset"
    strength: float  # 0-1: how well the site fits this lever
    headline: str  # one line a developer could put in a permit application
    detail: str
    evidence: list[Evidence] = Field(default_factory=list)


class PathToYes(BaseModel):
    """The reframe from go/no-go to negotiation: given a contested site, what
    community-benefit package would plausibly unblock it."""

    summary: str
    levers: list[Lever] = Field(default_factory=list)

    @property
    def top_lever(self) -> Lever | None:
        return max(self.levers, key=lambda l: l.strength) if self.levers else None


class SiteScreen(BaseModel):
    """Data-center screening output. Same provenance discipline as VerificationMemo."""

    location: Coordinate
    scores: list[SiteScore] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    data_gaps: list[DataGap] = Field(default_factory=list)
    verdict: Verdict
    path_to_yes: PathToYes | None = None
    name: str | None = None  # site label, when screened from a named list
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attestation_id: str | None = None  # shareable /a/{id}; excluded from the hash

    def sources(self) -> list[str]:
        seen: list[str] = []
        for item in (*self.evidence, *self.signals):
            if item.source not in seen:
                seen.append(item.source)
        return seen

    def score_for(self, dimension: str) -> float | None:
        for s in self.scores:
            if s.dimension == dimension:
                return s.score
        return None

    @property
    def physical_mean(self) -> float:
        physical = [s.score for s in self.scores if s.dimension != "Permitting risk"]
        return sum(physical) / len(physical) if physical else 0.0

    @property
    def stranded_viability(self) -> float:
        """The headline metric of the national scan: how much good physical site is
        being blocked by permitting risk. High physical + low permitting = high strand."""
        permitting = self.score_for("Permitting risk")
        if permitting is None:
            return 0.0
        return max(0.0, self.physical_mean - permitting)
