"""FastAPI wrapper. Serves the demo page and exposes the agent as two endpoints."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.agent import VerificationAgent
from src.clients.mireye import MireyeClient, MireyeError
from src.models import Coordinate, SiteScreen, VerificationMemo
from src.output import store
from src.output.attestation import Attestation, attest_memo, attest_screen
from src.output.attestation_page import render_page
from src.verticals.datacenter import screen_site
from src.verticals.flood import FloodVertical

load_dotenv()

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
COORD_PATTERN = re.compile(r"^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$")

app = FastAPI(
    title="Canopy",
    description="Checks claims about US locations against cited federal ground truth.",
    version="0.1.0",
)


class FloodRequest(BaseModel):
    location: str = Field(..., description='Address or "lat,lng".')
    claim: str = Field(..., description='e.g. "not in a flood zone" or "Zone X".')


class ScreenRequest(BaseModel):
    location: str = Field(..., description='Address or "lat,lng".')
    radius_km: float = Field(80.0, ge=1, le=500)


def _as_coordinate(value: str) -> Coordinate | None:
    match = COORD_PATTERN.match(value)
    if not match:
        return None
    return Coordinate(lat=float(match.group(1)), lng=float(match.group(2)))


def _client() -> MireyeClient:
    return MireyeClient()


@app.get("/healthz")
def healthz() -> dict:
    client = _client()
    return {
        "ok": True,
        "mireye_mode": "offline-fixtures" if client.offline else "live",
    }


def _persist(memo_or_screen, att: Attestation):
    """Save the attestation and stamp its shareable id back onto the result."""
    att_id = store.save(att)
    memo_or_screen.attestation_id = att_id
    return memo_or_screen


@app.post("/verify/flood", response_model=VerificationMemo)
async def verify_flood(request: FloodRequest) -> VerificationMemo:
    coordinate = _as_coordinate(request.location)
    agent = VerificationAgent(_client(), FloodVertical())
    try:
        memo = await agent.verify(
            address=None if coordinate else request.location,
            coordinate=coordinate,
            claim_text=request.claim,
        )
    except MireyeError as exc:
        raise HTTPException(status_code=502, detail=f"Mireye: {exc}") from exc
    return _persist(memo, attest_memo(memo))


@app.post("/verify/carbon", response_model=VerificationMemo)
async def verify_carbon(request: FloodRequest) -> VerificationMemo:
    from src.verticals.carbon import CarbonVertical

    coordinate = _as_coordinate(request.location)
    agent = VerificationAgent(_client(), CarbonVertical())
    try:
        memo = await agent.verify(
            address=None if coordinate else request.location,
            coordinate=coordinate,
            claim_text=request.claim,
        )
    except MireyeError as exc:
        raise HTTPException(status_code=502, detail=f"Mireye: {exc}") from exc
    return _persist(memo, attest_memo(memo))


@app.post("/screen/datacenter", response_model=SiteScreen)
async def screen_datacenter(request: ScreenRequest) -> SiteScreen:
    client = _client()
    coordinate = _as_coordinate(request.location)
    try:
        if coordinate is None:
            coordinate = await client.geocode(request.location)
        screen = await screen_site(client, coordinate, radius_km=request.radius_km)
    except MireyeError as exc:
        raise HTTPException(status_code=502, detail=f"Mireye: {exc}") from exc
    return _persist(screen, attest_screen(screen))


@app.get("/a/{att_id}.json")
def attestation_json(att_id: str) -> JSONResponse:
    """The raw attestation, for programmatic re-verification."""
    att = store.load(att_id)
    if att is None:
        raise HTTPException(status_code=404, detail="attestation not found")
    return JSONResponse(att.model_dump(mode="json"))


@app.get("/a/{att_id}", response_class=HTMLResponse)
def attestation_html(att_id: str) -> HTMLResponse:
    """A shareable, self-verifying attestation page."""
    from html import escape

    from src.output.attestation_page import page_meta

    att = store.load(att_id)
    if att is None:
        raise HTTPException(status_code=404, detail="attestation not found")
    title, description = page_meta(att)
    return HTMLResponse(_PAGE_SHELL.format(
        body=render_page(att, att_id),
        title=escape(title, quote=True),
        description=escape(description, quote=True),
    ))


# The attestation page reuses the demo's stylesheet; this shell wraps the rendered body
# with the same <head> the index uses so the Canopy styling applies. The OG/Twitter tags
# give a shared /a/{id} link a rich preview in Slack, iMessage, and X.
_PAGE_SHELL = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<link rel="icon" href="/static/img/logo.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/style.css?v=17">
</head><body>{body}</body></html>"""


FINDINGS_DIR = Path(__file__).resolve().parents[1] / "findings"


@app.get("/scan/campuses")
def scan_campuses() -> JSONResponse:
    """The national scan rolled up to campuses — the data behind the /map view."""
    path = FINDINGS_DIR / "campuses.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no scan yet — run `python -m src.cli scan`")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


# --- resume-scan demo ---------------------------------------------------------
# The national scan checkpoints every completed site to a JSONL file, so a killed run
# resumes with zero re-billed work. That's the most interesting thing the scan does and it's
# normally invisible. These endpoints make it clickable: a *separate* demo checkpoint that
# genuinely runs `run_scan(...)` five sites at a time, so you watch the same state handle
# grow. The +5 cap is server-fixed and load-bearing — nothing the client sends can widen it,
# so this can never kick off a full paid scan.

DEMO_CHECKPOINT = FINDINGS_DIR / "demo-checkpoint.jsonl"
RESUME_BATCH = 5


def _scan_total() -> int:
    from src.clients.osm import fetch_us_data_centers

    return len(fetch_us_data_centers())


@app.get("/scan/state")
def scan_state() -> JSONResponse:
    from src.scan import _load_checkpoint

    done = _load_checkpoint(DEMO_CHECKPOINT)
    total = _scan_total()
    mtime = DEMO_CHECKPOINT.stat().st_mtime if DEMO_CHECKPOINT.exists() else None
    return JSONResponse({
        "total_target": total,
        "completed": len(done),
        "remaining": max(0, total - len(done)),
        "batch": RESUME_BATCH,
        "last_updated": (
            datetime.fromtimestamp(mtime, timezone.utc).isoformat() if mtime else None
        ),
    })


@app.post("/scan/resume-demo")
async def scan_resume_demo() -> JSONResponse:
    from src.scan import _load_checkpoint, run_scan

    before = set(_load_checkpoint(DEMO_CHECKPOINT).keys())
    completed = len(before)
    total = _scan_total()
    if completed >= total:
        return JSONResponse({"added": [], "completed": completed, "remaining": 0, "done": True})

    # Hard cap: resume at most RESUME_BATCH sites past whatever is already checkpointed.
    limit = min(completed + RESUME_BATCH, total)
    try:
        await run_scan(limit=limit, concurrency=2, checkpoint=DEMO_CHECKPOINT, attestation_dir=None)
    except MireyeError as exc:
        raise HTTPException(status_code=502, detail=f"Mireye: {exc}") from exc

    after = _load_checkpoint(DEMO_CHECKPOINT)
    added = [after[k].model_dump() for k in after if k not in before]
    return JSONResponse({
        "added": added,
        "completed": len(after),
        "remaining": max(0, total - len(after)),
        "done": len(after) >= total,
    })


@app.post("/scan/reset-demo")
def scan_reset_demo() -> JSONResponse:
    """Wipe the demo checkpoint so the resume demo can start over. Never touches the real
    `findings/checkpoint.jsonl`."""
    if DEMO_CHECKPOINT.exists():
        DEMO_CHECKPOINT.unlink()
    return JSONResponse({"ok": True})


@app.get("/scan/resume-ui", response_class=HTMLResponse)
def scan_resume_ui() -> HTMLResponse:
    return HTMLResponse(
        (WEB_DIR / "scan-resume.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


@app.get("/map", response_class=HTMLResponse)
def national_map() -> HTMLResponse:
    return HTMLResponse(
        (WEB_DIR / "map.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


@app.get("/")
def index() -> FileResponse:
    # The demo page is edited constantly; without this the browser serves a stale
    # copy and you end up debugging markup that is no longer on disk.
    return FileResponse(
        WEB_DIR / "index.html",
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
