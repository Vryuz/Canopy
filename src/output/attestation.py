"""Attestation artifact — the evidentiary form of a verification.

The whole paid-verification thesis (and Canopy's) rests on producing an artifact that
is *defensible when disputed*: reproducible, timestamped, and tamper-evident. This turns
a VerificationMemo or SiteScreen into exactly that — a canonical JSON body with a content
hash over it, so any party can independently re-hash and confirm nothing was altered.

Content-addressing (sha256 over canonical JSON) is the honest, dependency-free integrity
guarantee. It is deliberately structured so a PKI signature (ed25519 over the same digest)
can slot in later without changing the artifact shape — see `signature` / `signed_by`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from src.models import SiteScreen, VerificationMemo

ATTESTATION_VERSION = "0.1.0"
ISSUER = "verification-agent"


class Attestation(BaseModel):
    """A tamper-evident wrapper around a verification result."""

    version: str = ATTESTATION_VERSION
    issuer: str = ISSUER
    kind: str  # "flood_verification" | "datacenter_screen"
    subject: str  # human label: the address or coordinate
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: str  # sha256 hex over the canonical body
    body: dict[str, Any]
    # Reserved for later PKI signing over content_hash. Content-addressing stands alone
    # until then; these being None is honest, not a gap.
    signature: str | None = None
    signed_by: str | None = None

    def verify_integrity(self) -> bool:
        """Re-hash the body and confirm it matches — the check a disputing party runs."""
        return _hash_body(self.body) == self.content_hash


def _canonical(body: dict[str, Any]) -> str:
    """Deterministic JSON: sorted keys, no whitespace jitter, ISO datetimes. Two runs
    over identical evidence must produce byte-identical output, or the hash is useless."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.astimezone(timezone.utc).isoformat()
    raise TypeError(f"not JSON-serialisable: {type(obj)}")


def _hash_body(body: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _issued_body(model: BaseModel) -> dict[str, Any]:
    # generated_at is excluded from the hashed body: it's wall-clock noise that would make
    # two otherwise-identical verifications hash differently. The attestation's own
    # issued_at records when the artifact was minted.
    return model.model_dump(mode="json", exclude={"generated_at"})


def attest_memo(memo: VerificationMemo) -> Attestation:
    body = _issued_body(memo)
    return Attestation(
        kind="flood_verification",
        subject=memo.location.resolved_address or str(memo.location),
        content_hash=_hash_body(body),
        body=body,
    )


def attest_screen(screen: SiteScreen) -> Attestation:
    body = _issued_body(screen)
    return Attestation(
        kind="datacenter_screen",
        subject=screen.name or screen.location.resolved_address or str(screen.location),
        content_hash=_hash_body(body),
        body=body,
    )


def render_markdown(att: Attestation) -> str:
    """A human-readable evidentiary memo carrying the same facts as the JSON, so the
    artifact is legible without a parser while staying verifiable with one."""
    lines: list[str] = []
    title = "Flood Verification" if att.kind == "flood_verification" else "Data-Center Site Screen"
    lines.append(f"# Attestation — {title}")
    lines.append("")
    lines.append(f"**Subject:** {att.subject}  ")
    lines.append(f"**Issued:** {att.issued_at.isoformat()}  ")
    lines.append(f"**Issuer:** {att.issuer} · v{att.version}  ")
    lines.append(f"**Content hash (sha256):** `{att.content_hash}`  ")
    lines.append("")
    lines.append("> Re-hash the canonical body below to confirm this attestation is intact.")
    lines.append("")

    verdict = att.body.get("verdict", {})
    lines.append(f"## Verdict: {str(verdict.get('kind', '')).upper()} "
                 f"(confidence: {verdict.get('confidence', '')})")
    lines.append("")
    lines.append(verdict.get("reasoning", ""))
    lines.append("")

    discrepancies = att.body.get("discrepancies") or []
    if discrepancies:
        lines.append("## Discrepancies")
        for d in discrepancies:
            lines.append(f"- **{str(d.get('severity','')).upper()}** `{d.get('field')}` — "
                         f"claimed {d.get('claimed')!r}, observed {d.get('observed')!r}. "
                         f"{d.get('explanation','')}")
        lines.append("")

    scores = att.body.get("scores") or []
    if scores:
        lines.append("## Scored dimensions")
        for s in scores:
            lines.append(f"- **{s.get('dimension')}**: {s.get('score'):.2f} — {s.get('rationale','')}")
        lines.append("")

    p2y = att.body.get("path_to_yes")
    if p2y:
        lines.append("## Path to yes")
        lines.append(p2y.get("summary", ""))
        for lever in p2y.get("levers", []):
            lines.append(f"- **{lever.get('name')}** ({lever.get('strength'):.2f}): "
                         f"{lever.get('headline','')}")
        lines.append("")

    signals = att.body.get("signals") or []
    if signals:
        lines.append("## Corroborating signals")
        for sig in signals:
            lines.append(f"- **{sig.get('label')}** — {sig.get('detail','')} "
                         f"({sig.get('source')})")
        lines.append("")

    evidence = att.body.get("evidence") or []
    if evidence:
        lines.append("## Evidence")
        lines.append("| Field | Value | Source | Fetched | Confidence |")
        lines.append("|---|---|---|---|---|")
        for e in evidence:
            val = e.get("value")
            unit = e.get("unit")
            val_str = f"{val} {unit}" if unit else str(val)
            fetched = str(e.get("fetched_at", ""))[:10]
            url = e.get("source_url")
            src = f"[{e.get('source')}]({url})" if url else e.get("source")
            lines.append(f"| `{e.get('field')}` | {val_str} | {src} | {fetched} | {e.get('confidence')} |")
        lines.append("")

    gaps = att.body.get("data_gaps") or []
    if gaps:
        lines.append("## Declared data gaps")
        for g in gaps:
            retry = " _(retryable)_" if g.get("retryable") else ""
            lines.append(f"- `{g.get('field')}`: {g.get('reason')}{retry}")
        lines.append("")

    return "\n".join(lines)


def to_json(att: Attestation) -> str:
    """The full artifact, pretty-printed, for writing to disk or an API response."""
    return att.model_dump_json(indent=2)
