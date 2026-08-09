"""National data-center scan — the Mireye recipe applied to their own industry.

Take every OSM-mapped US data center, screen each one, and rank by *stranded viability*:
physically excellent sites being held back by permitting/opposition risk. The output is a
finding, not a lookup — "the N US data centers where site quality and permitting risk most
diverge" — and the moratorium-vs-viability gap it surfaces is the market map for the whole
Wave-3 thesis.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
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


class Campus(BaseModel):
    """One data-center campus, rolled up from the OSM buildings that make it up."""

    name: str
    operator: str
    lat: float
    lng: float
    verdict: str
    physical_mean: float
    permitting: float | None
    stranded_viability: float
    top_lever: str | None = None
    nearest_moratorium: str | None = None
    building_count: int = 1


# Brand canonicalisation. OSM tags the same operator a dozen ways ("Amazon Web Services",
# "Amazon AWS PHL", "AWS"); a finding that lists them separately looks unserious.
_ALIASES: dict[str, str] = {
    "amazon": "Amazon", "aws": "Amazon",
    "google": "Google", "microsoft": "Microsoft", "azure": "Microsoft",
    "meta": "Meta", "facebook": "Meta",
    "qts": "QTS", "digital realty": "Digital Realty", "stack": "STACK Infrastructure",
    "equinix": "Equinix", "flexential": "Flexential", "switch": "Switch",
    "coresite": "CoreSite", "cyxtera": "Cyxtera", "ntt": "NTT", "lumen": "Lumen",
    "centurylink": "Lumen", "verizon": "Verizon", "apple": "Apple", "compass": "Compass",
    "tierpoint": "TierPoint", "vantage": "Vantage", "iron mountain": "Iron Mountain",
    "nautilus": "Nautilus", "blockfusion": "Blockfusion", "centersquare": "Centersquare",
    "lexisnex": "LexisNexis", "quantum loophole": "Quantum Loophole", "edgeconnex": "EdgeConneX",
    "aligned": "Aligned", "databank": "DataBank", "sabey": "Sabey", "t5 ": "T5",
}

_CAMPUS_RADIUS_KM = 4.0  # same operator within this of another building = one campus


def _operator_key(name: str) -> str | None:
    """Canonical operator, or None for an unnamed OSM feature (kept as its own singleton)."""
    if not name or name.startswith(("way/", "node/", "relation/")):
        return None
    low = name.lower()
    for sub, canon in _ALIASES.items():
        if sub in low:
            return canon
    token = re.split(r"[\s,\-/]+", name.strip())[0]
    return token[:24] or None


def dedupe_campuses(rows: list[ScanRow], radius_km: float = _CAMPUS_RADIUS_KM) -> list[Campus]:
    """Roll buildings up to campuses: group by operator, then greedily merge same-operator
    buildings within `radius_km`. Unnamed features stay as singletons. The representative
    keeps the cluster's worst-case (max stranded) row and its most specific name."""
    from src.clients.moratoria import haversine_km

    by_op: dict[str | None, list[ScanRow]] = {}
    for r in rows:
        by_op.setdefault(_operator_key(r.name), []).append(r)

    campuses: list[Campus] = []
    for op, members in by_op.items():
        if op is None:
            campuses.extend(_campus_from([r], None) for r in members)  # unnamed → singletons
            continue
        remaining = sorted(members, key=lambda r: r.stranded_viability, reverse=True)
        while remaining:
            seed = remaining.pop(0)
            cluster = [seed]
            rest: list[ScanRow] = []
            for r in remaining:
                if haversine_km(seed.lat, seed.lng, r.lat, r.lng) <= radius_km:
                    cluster.append(r)
                else:
                    rest.append(r)
            remaining = rest
            campuses.append(_campus_from(cluster, op))

    return sorted(campuses, key=lambda c: c.stranded_viability, reverse=True)


def _campus_from(cluster: list[ScanRow], operator: str | None) -> Campus:
    rep = max(cluster, key=lambda r: r.stranded_viability)  # worst-case representative
    # Most specific label: the longest real name; a bare OSM id reads as "Unnamed".
    named = [r.name for r in cluster if not r.name.startswith(("way/", "node/", "relation/"))]
    label = max(named, key=len) if named else "Unnamed data center"
    return Campus(
        name=label,
        operator=operator or "—",
        lat=rep.lat,
        lng=rep.lng,
        verdict=rep.verdict,
        physical_mean=rep.physical_mean,
        permitting=rep.permitting,
        stranded_viability=rep.stranded_viability,
        top_lever=rep.top_lever,
        nearest_moratorium=rep.nearest_moratorium,
        building_count=len(cluster),
    )


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
) -> tuple[DataCenter, SiteScreen | None]:
    async with sem:
        try:
            screen = await screen_site(
                mireye,
                Coordinate(lat=dc.lat, lng=dc.lng),
                moratoria=moratoria,
                name=dc.name or dc.osm_id,
            )
            return dc, screen
        except Exception:
            # A single site's failure (Mireye error, timeout, bad geometry) must never
            # abort a 1,800-site run — record it as a failure and carry on.
            return dc, None


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


def _load_checkpoint(path: Path) -> dict[str, ScanRow]:
    """Rows already screened in a prior (possibly interrupted) run, keyed by osm id.

    A long national scan is credit-metered and network-bound; resuming means an
    interruption at site 1,500 costs nothing to recover instead of re-billing 1,500 sites.
    """
    if not path.exists():
        return {}
    done: dict[str, ScanRow] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            done[rec["osm_id"]] = ScanRow(**rec["row"])
        except (json.JSONDecodeError, KeyError):
            continue  # tolerate a torn final line from a hard kill
    return done


def _log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


async def run_scan(
    *,
    limit: int | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    mireye: MireyeClient | None = None,
    attestation_dir: Path | None = None,
    checkpoint: Path | None = None,
    progress_every: int = 25,
) -> ScanResult:
    """Screen (a slice of) every OSM-mapped US data center and rank by stranded viability.

    Processes sites as they complete (not one big gather at the end) so progress is
    visible and every finished row is appended to `checkpoint` immediately — the run is
    both observable and resumable.
    """
    mireye = mireye or MireyeClient()
    moratoria = MoratoriaClient()
    moratoria.load()  # warm the cache once, not per-site

    centers = fetch_us_data_centers()
    if limit:
        centers = centers[:limit]

    done = _load_checkpoint(checkpoint) if checkpoint else {}
    rows: dict[str, ScanRow] = dict(done)
    pending = [dc for dc in centers if dc.osm_id not in done]
    failed = 0

    if done:
        _log(f"Resuming: {len(done)} already screened, {len(pending)} remaining.")
    _log(f"Screening {len(pending)} of {len(centers)} sites at concurrency {concurrency}…")

    if checkpoint is not None:
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
    ckpt = checkpoint.open("a", encoding="utf-8") if checkpoint else None
    started = time.monotonic()
    completed = 0
    try:
        sem = asyncio.Semaphore(concurrency)
        tasks = [asyncio.create_task(_screen_one(mireye, moratoria, dc, sem)) for dc in pending]
        for coro in asyncio.as_completed(tasks):
            dc, screen = await coro
            completed += 1
            if screen is None:
                failed += 1
            else:
                row = _to_row(screen)
                rows[dc.osm_id] = row
                if ckpt is not None:
                    ckpt.write(json.dumps({"osm_id": dc.osm_id, "row": row.model_dump()}) + "\n")
                    ckpt.flush()
                if attestation_dir is not None and screen.verdict.is_actionable:
                    _write_attestation(screen, attestation_dir)
            if completed % progress_every == 0 or completed == len(pending):
                rate = completed / max(time.monotonic() - started, 1e-6) * 60
                eta = (len(pending) - completed) / max(rate / 60, 1e-6)
                _log(f"  {completed}/{len(pending)} done · {failed} failed · "
                     f"{rate:.0f}/min · ETA {eta/60:.1f} min")
    finally:
        if ckpt is not None:
            ckpt.close()

    return ScanResult(
        generated_at=datetime.now(timezone.utc),
        total_found=len(centers),
        screened=len(rows),
        failed=failed,
        rows=list(rows.values()),
    )


def _write_attestation(screen: SiteScreen, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    att = attest_screen(screen)
    stem = att.content_hash[:12]
    (out_dir / f"{stem}.json").write_text(to_json(att), encoding="utf-8")
    (out_dir / f"{stem}.md").write_text(render_markdown(att), encoding="utf-8")


def render_finding(result: ScanResult, campuses: list[Campus], top_n: int = 25) -> str:
    """A publishable markdown finding — the blog-post-shaped output Mireye rewards.

    Counts are campus-level (OSM buildings rolled up), so "866 disputed" means 866 distinct
    sites, not 866 tagged rooftops."""
    ranked = sorted(campuses, key=lambda c: c.stranded_viability, reverse=True)[:top_n]
    disputed = [c for c in campuses if c.verdict == "disputed"]
    flagged = [c for c in campuses if c.verdict == "flagged"]
    verified = [c for c in campuses if c.verdict == "verified"]

    lines = [
        "# The US data centers most stranded by permitting risk",
        "",
        f"_Screened {result.screened} of {result.total_found} OSM-mapped US data-center "
        f"buildings on {result.generated_at:%Y-%m-%d}, rolled up to **{len(campuses)} campuses**. "
        "Physical viability from Mireye; permitting risk from the Moratorium Nation inventory. "
        "Every value cited; method reproducible._",
        "",
        "## What we found",
        "",
        f"- **{len(disputed)}** campuses are DISPUTED — physically viable but sitting inside the "
        "blast radius of an active moratorium.",
        f"- **{len(flagged)}** are FLAGGED — a named risk to resolve early.",
        f"- **{len(verified)}** clear a first-pass screen clean.",
        "",
        "**Stranded viability** is the headline metric: physical site quality minus permitting "
        "risk. A high score means an excellent site the market is being forced to walk away from "
        "— exactly the parcels where a community-benefit package (grid flexibility, waste-heat "
        "reuse, water offsets) would unlock the most value.",
        "",
        f"## Top {len(ranked)} most-stranded campuses",
        "",
        "| # | Campus | Operator | Bldgs | Verdict | Physical | Permitting | Stranded | Path to yes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(ranked, 1):
        perm = f"{c.permitting:.2f}" if c.permitting is not None else "—"
        lines.append(
            f"| {i} | {c.name} | {c.operator} | {c.building_count} | {c.verdict.upper()} | "
            f"{c.physical_mean:.2f} | {perm} | **{c.stranded_viability:.2f}** | {c.top_lever or '—'} |"
        )
    lines += [
        "",
        "## Method",
        "",
        f"1. Pull all US data centers tagged in OpenStreetMap ({result.total_found} buildings).",
        f"2. Screen each on {len(DC_FIELDS)} cited Mireye fields (terrain, power, hazard, "
        "externalities) plus nearby active moratoria.",
        "3. Roll buildings up to campuses (operator + spatial clustering).",
        "4. Rank by stranded viability = physical mean − permitting score.",
        "5. Every screened site emits a content-hashed attestation; nothing is asserted "
        "without a citation and a re-checkable source.",
        "",
        "_Not construction advice. Proximity is not deliverability; a screen tells you where "
        "to look, not what you'll find on the ground. Campus rollup is operator + 4 km "
        "clustering; a bare-branded cluster in one metro may span more than one physical site._",
    ]
    return "\n".join(lines)
