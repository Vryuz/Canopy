"""FastAPI wrapper. Serves the demo page and exposes the agent as two endpoints."""

from __future__ import annotations

import json
import os
import re
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
    att = store.load(att_id)
    if att is None:
        raise HTTPException(status_code=404, detail="attestation not found")
    return HTMLResponse(_PAGE_SHELL.format(body=render_page(att, att_id)))


# The attestation page reuses the demo's stylesheet; this shell wraps the rendered body
# with the same <head> the index uses so the Canopy styling applies.
_PAGE_SHELL = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Canopy Attestation</title>
<link rel="icon" href="/static/img/logo.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/style.css?v=16">
</head><body>{body}</body></html>"""


FINDINGS_DIR = Path(__file__).resolve().parents[1] / "findings"


@app.get("/scan/campuses")
def scan_campuses() -> JSONResponse:
    """The national scan rolled up to campuses — the data behind the /map view."""
    path = FINDINGS_DIR / "campuses.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no scan yet — run `python -m src.cli scan`")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


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
