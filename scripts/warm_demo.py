"""Pre-warm the response cache for the live demo.

Runs exactly the requests the demo UI will make — the three canned examples per vertical —
with caching on, so on stage they serve from disk: instant, zero credits, and immune to a
slow Overpass or a suspended OpenFEMA endpoint.

Usage:
    python scripts/warm_demo.py            # populate .cache/ from live sources
    # then run the server in replay mode:
    CANOPY_CACHE_ONLY=1 python -m uvicorn api.server:app --port 8000

In cache-only mode every demo query is served from the warmed cache; a miss raises loudly
(so you find out before the audience does), and nothing touches the network.
"""

from __future__ import annotations

import asyncio
import os

# Enable read+write caching for this process before any client is imported.
os.environ["CANOPY_CACHE"] = "1"
os.environ.pop("CANOPY_CACHE_ONLY", None)  # warming must be allowed to hit the network

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src.agent import VerificationAgent  # noqa: E402
from src.clients.mireye import MireyeClient  # noqa: E402
from src.models import Coordinate  # noqa: E402
from src.verticals.carbon import CarbonVertical  # noqa: E402
from src.verticals.datacenter import screen_site  # noqa: E402
from src.verticals.flood import FloodVertical  # noqa: E402

# Must mirror the examples in web/index.html exactly, or the demo will still cache-miss.
FLOOD = [
    ("1719 Broadway Ave J, Galveston, TX", "seller states the property is not in a flood zone"),
    ("350 5th Ave, New York, NY", "Zone X"),
    ("1600 Sherman St, Denver, CO", "not in a flood zone"),
]
CARBON = [
    ("33.4484, -112.074", "reforestation project established since 2021"),
    ("47.8, -123.5", "reforestation project, new trees planted since 2021"),
    ("47.8, -123.5", "avoided deforestation, protecting intact forest"),
]
DC = ["39.0438, -77.4874", "39.9612, -82.9988", "33.4484, -112.074", "41.2619, -95.8608"]


def _coord(text: str) -> Coordinate | None:
    parts = text.split(",")
    if len(parts) == 2:
        try:
            return Coordinate(lat=float(parts[0]), lng=float(parts[1]))
        except ValueError:
            return None
    return None


async def main() -> None:
    client = MireyeClient()
    if client.offline:
        raise SystemExit("No MIREYE_API_TOKEN — warming needs live sources.")

    print("Warming flood examples…")
    for location, claim in FLOOD:
        agent = VerificationAgent(MireyeClient(), FloodVertical())
        c = _coord(location)
        memo = await agent.verify(address=None if c else location, coordinate=c, claim_text=claim)
        print(f"  flood   {location:38} → {memo.verdict.kind.value}")

    print("Warming carbon examples…")
    for location, claim in CARBON:
        agent = VerificationAgent(MireyeClient(), CarbonVertical())
        c = _coord(location)
        memo = await agent.verify(address=None if c else location, coordinate=c, claim_text=claim)
        print(f"  carbon  {location:38} → {memo.verdict.kind.value}")

    print("Warming data-center examples…")
    for location in DC:
        c = _coord(location) or await MireyeClient().geocode(location)
        screen = await screen_site(MireyeClient(), c)
        print(f"  dc      {location:38} → {screen.verdict.kind.value}")

    print("\nDone. Launch the demo with CANOPY_CACHE_ONLY=1 to serve entirely from cache.")


if __name__ == "__main__":
    asyncio.run(main())
