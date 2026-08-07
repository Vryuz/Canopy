"""FastAPI wrapper. Serves the demo page and exposes the agent as two endpoints."""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.agent import VerificationAgent
from src.clients.mireye import MireyeClient, MireyeError
from src.models import Coordinate, SiteScreen, VerificationMemo
from src.verticals.datacenter import screen_site
from src.verticals.flood import FloodVertical

load_dotenv()

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
COORD_PATTERN = re.compile(r"^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$")

app = FastAPI(
    title="Verification Agent",
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


@app.post("/verify/flood", response_model=VerificationMemo)
async def verify_flood(request: FloodRequest) -> VerificationMemo:
    coordinate = _as_coordinate(request.location)
    agent = VerificationAgent(_client(), FloodVertical())
    try:
        return await agent.verify(
            address=None if coordinate else request.location,
            coordinate=coordinate,
            claim_text=request.claim,
        )
    except MireyeError as exc:
        raise HTTPException(status_code=502, detail=f"Mireye: {exc}") from exc


@app.post("/screen/datacenter", response_model=SiteScreen)
async def screen_datacenter(request: ScreenRequest) -> SiteScreen:
    client = _client()
    coordinate = _as_coordinate(request.location)
    try:
        if coordinate is None:
            coordinate = await client.geocode(request.location)
        return await screen_site(client, coordinate, radius_km=request.radius_km)
    except MireyeError as exc:
        raise HTTPException(status_code=502, detail=f"Mireye: {exc}") from exc


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
