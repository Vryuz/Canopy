"""National data-center scan — the Mireye recipe applied to their own industry.

Take every OSM-mapped US data center, screen each one, and rank by *stranded viability*:
physically excellent sites being held back by permitting/opposition risk. The output is a
finding, not a lookup — "the N US data centers where site quality and permitting risk most
diverge" — and the moratorium-vs-viability gap it surfaces is the market map for the whole
Wave-3 thesis.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from src.clients.mireye import MireyeClient, MireyeError
from src.clients.moratoria import MoratoriaClient
from src.clients.osm import DataCenter, fetch_us_data_centers
from src.models import Coordinate, SiteScreen
from src.output.attestation import attest_screen, render_markdown, to_json
from src.verticals.datacenter import DC_FIELDS, screen_site

# Screening is credit-metered (~len(DC_FIELDS) credits/site). A bounded concurrency keeps
# us polite to the API and predictable on spend.
DEFAULT_CONCURRENCY = 6


class ScanRow(BaseModel):
    name: str
    lat: float
    lng: float
    verdict: str
    physical_mean: float
    permitting: float | None
    stranded_viability: float
    top_lever: str | None = None
    nearest_moratorium: str | None = None


class ScanResult(BaseModel):
    generated_at: datetime
    total_found: int
    screened: int
    failed: int
    rows: list[ScanRow]

    def ranked(self, by: str = "stranded_viability") -> list[ScanRow]:
        return sorted(self.rows, key=lambda r: getattr(r, by), reverse=True)


async def _screen_one(
    mireye: MireyeClient,
    moratoria: MoratoriaClient,
    dc: DataCenter,
    sem: asyncio.Semaphore,
) -> SiteScreen | None:
    async with sem:
        try:
            return await screen_site(
                mireye,
                Coordinate(lat=dc.lat, lng=dc.lng),
                moratoria=moratoria,
                name=dc.name or dc.osm_id,
            )
        except MireyeError:
            return None


def _to_row(screen: SiteScreen) -> ScanRow:
    permitting = screen.score_for("Permitting risk")
    nearest = next(
        (s.label for s in screen.signals if "moratorium" in s.detail.lower()), None
    )
    top = screen.path_to_yes.top_lever if screen.path_to_yes else None
    return ScanRow(
        name=screen.name or str(screen.location),
        lat=screen.location.lat,
        lng=screen.location.lng,
        verdict=screen.verdict.kind.value,
        physical_mean=round(screen.physical_mean, 3),
        permitting=round(permitting, 3) if permitting is not None else None,
        stranded_viability=round(screen.stranded_viability, 3),
        top_lever=top.name if top else None,
        nearest_moratorium=nearest,
    )


async def run_scan(
    *,
    limit: int | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    mireye: MireyeClient | None = None,
    attestation_dir: Path | None = None,
) -> ScanResult:
    """Screen (a slice of) every OSM-mapped US data center and rank by stranded viability."""
    mireye = mireye or MireyeClient()
    moratoria = MoratoriaClient()
    moratoria.load()  # warm the cache once, not per-site

    centers = fetch_us_data_centers()
    if limit:
        centers = centers[:limit]

    sem = asyncio.Semaphore(concurrency)
    screens = await asyncio.gather(
        *(_screen_one(mireye, moratoria, dc, sem) for dc in centers)
    )

    rows: list[ScanRow] = []
    for screen in screens:
        if screen is None:
            continue
        rows.append(_to_row(screen))
        if attestation_dir is not None and screen.verdict.is_actionable:
            _write_attestation(screen, attestation_dir)

    return ScanResult(
        generated_at=datetime.now(timezone.utc),
        total_found=len(centers),
        screened=len(rows),
        failed=sum(1 for s in screens if s is None),
        rows=rows,
    )


def _write_attestation(screen: SiteScreen, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    att = attest_screen(screen)
    stem = att.content_hash[:12]
    (out_dir / f"{stem}.json").write_text(to_json(att), encoding="utf-8")
    (out_dir / f"{stem}.md").write_text(render_markdown(att), encoding="utf-8")


def render_finding(result: ScanResult, top_n: int = 25) -> str:
    """A publishable markdown finding — the blog-post-shaped output Mireye rewards."""
    ranked = result.ranked()[:top_n]
    disputed = [r for r in result.rows if r.verdict == "disputed"]
    flagged = [r for r in result.rows if r.verdict == "flagged"]
    verified = [r for r in result.rows if r.verdict == "verified"]

    lines = [
        "# The US data centers most stranded by permitting risk",
        "",
        f"_Screened {result.screened} of {result.total_found} OSM-mapped US data centers on "
        f"{result.generated_at:%Y-%m-%d}. Physical viability from Mireye; permitting risk from "
        "the Moratorium Nation inventory. Every value cited; method reproducible._",
        "",
        "## What we found",
        "",
        f"- **{len(disputed)}** sites are DISPUTED — physically viable but sitting inside the "
        "blast radius of an active moratorium.",
        f"- **{len(flagged)}** are FLAGGED — a named risk to resolve early.",
        f"- **{len(verified)}** clear a first-pass screen clean.",
        "",
        "**Stranded viability** is the headline metric: physical site quality minus permitting "
        "risk. A high score means an excellent site the market is being forced to walk away from "
        "— exactly the parcels where a community-benefit package (grid flexibility, waste-heat "
        "reuse, water offsets) would unlock the most value.",
        "",
        f"## Top {len(ranked)} most-stranded sites",
        "",
        "| # | Site | Verdict | Physical | Permitting | Stranded | Strongest path to yes |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(ranked, 1):
        perm = f"{r.permitting:.2f}" if r.permitting is not None else "—"
        lines.append(
            f"| {i} | {r.name} | {r.verdict.upper()} | {r.physical_mean:.2f} | {perm} | "
            f"**{r.stranded_viability:.2f}** | {r.top_lever or '—'} |"
        )
    lines += [
        "",
        "## Method",
        "",
        f"1. Pull all US data centers tagged in OpenStreetMap ({result.total_found} found).",
        f"2. Screen each on {len(DC_FIELDS)} cited Mireye fields (terrain, power, hazard, "
        "externalities) plus nearby active moratoria.",
        "3. Rank by stranded viability = physical mean − permitting score.",
        "4. Every screened site emits a content-hashed attestation; nothing is asserted "
        "without a citation and a re-checkable source.",
        "",
        "_Not construction advice. Proximity is not deliverability; a screen tells you where "
        "to look, not what you'll find on the ground._",
    ]
    return "\n".join(lines)
