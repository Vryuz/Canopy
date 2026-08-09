"""CLI for the verification agent."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.text import Text

from src.agent import VerificationAgent
from src.clients.mireye import MireyeClient, MireyeError
from src.models import Coordinate
from src.output.memo import memo_to_markdown, render_memo, render_screen
from src.verticals.flood import FloodVertical

# The Windows legacy console defaults to cp1252, which can't encode the citation glyphs
# (arrows, bullets) this tool prints. Force UTF-8 so provenance renders, not crashes.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

load_dotenv()
# Evidence tables carry long field and source names; a narrow terminal would
# truncate exactly the provenance this tool exists to show.
console = Console(width=max(Console().width, 100))

COORD_PATTERN = re.compile(r"^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$")


def _as_coordinate(value: str) -> Coordinate | None:
    match = COORD_PATTERN.match(value)
    if not match:
        return None
    return Coordinate(lat=float(match.group(1)), lng=float(match.group(2)))


@click.group()
def cli() -> None:
    """Verify claims about physical locations against cited federal ground truth."""


@cli.command()
@click.argument("location")
@click.option("--claim", required=True, help='The assertion to check, e.g. "not in a flood zone".')
@click.option("--offline", is_flag=True, help="Use recorded fixtures instead of the live API.")
@click.option("--markdown", type=click.Path(path_type=Path), help="Also write the memo to a file.")
def flood(location: str, claim: str, offline: bool, markdown: Path | None) -> None:
    """Verify a flood-risk claim for an address or "lat,lng"."""
    coordinate = _as_coordinate(location)
    agent = VerificationAgent(
        MireyeClient(offline=True if offline else None), FloodVertical()
    )

    try:
        memo = asyncio.run(
            agent.verify(
                address=None if coordinate else location,
                coordinate=coordinate,
                claim_text=claim,
            )
        )
    except MireyeError as exc:
        raise click.ClickException(f"Mireye: {exc}") from exc

    render_memo(memo, console)

    if markdown:
        markdown.write_text(memo_to_markdown(memo), encoding="utf-8")
        console.print(f"\n[green]Memo written to {markdown}[/green]")


@cli.command()
@click.argument("location")
@click.option("--claim", required=True, help='The project claim, e.g. "reforestation project since 2021".')
@click.option("--offline", is_flag=True, help="Use recorded fixtures instead of the live API.")
@click.option("--attest", type=click.Path(path_type=Path), help="Write a content-hashed attestation JSON.")
def carbon(location: str, claim: str, offline: bool, attest: Path | None) -> None:
    """Verify a carbon-project claim against vegetation ground truth."""
    from src.verticals.carbon import CarbonVertical

    coordinate = _as_coordinate(location)
    agent = VerificationAgent(
        MireyeClient(offline=True if offline else None), CarbonVertical()
    )
    try:
        memo = asyncio.run(
            agent.verify(
                address=None if coordinate else location,
                coordinate=coordinate,
                claim_text=claim,
            )
        )
    except MireyeError as exc:
        raise click.ClickException(f"Mireye: {exc}") from exc

    render_memo(memo, console)

    if attest:
        from src.output.attestation import attest_memo, to_json

        att = attest_memo(memo)
        attest.write_text(to_json(att), encoding="utf-8")
        console.print(
            f"\n[green]Attestation written to {attest}[/green] "
            f"[dim](sha256 {att.content_hash[:16]}…)[/dim]"
        )


@cli.command(name="dc")
@click.argument("location")
@click.option("--radius", default=80.0, show_default=True, help="Moratorium search radius in km.")
@click.option("--offline", is_flag=True, help="Use recorded fixtures instead of the live API.")
@click.option("--attest", type=click.Path(path_type=Path), help="Write a content-hashed attestation JSON.")
def datacenter(location: str, radius: float, offline: bool, attest: Path | None) -> None:
    """Screen a data-center site for physical viability and permitting risk."""
    from src.verticals.datacenter import screen_site

    coordinate = _as_coordinate(location)
    client = MireyeClient(offline=True if offline else None)

    try:
        if coordinate is None:
            coordinate = asyncio.run(client.geocode(location))
        screen = asyncio.run(screen_site(client, coordinate, radius_km=radius))
    except MireyeError as exc:
        raise click.ClickException(f"Mireye: {exc}") from exc

    render_screen(screen, console)

    if attest:
        from src.output.attestation import attest_screen, to_json

        att = attest_screen(screen)
        attest.write_text(to_json(att), encoding="utf-8")
        console.print(
            f"\n[green]Attestation written to {attest}[/green] "
            f"[dim](sha256 {att.content_hash[:16]}…)[/dim]"
        )


@cli.command()
@click.option("--limit", type=int, help="Screen only the first N data centers (saves credits).")
@click.option("--concurrency", default=6, show_default=True, help="Parallel screens.")
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("findings"),
    show_default=True,
    help="Directory for the finding + per-site attestations.",
)
@click.option("--top", default=25, show_default=True, help="How many sites to rank in the finding.")
@click.option("--resume/--no-resume", default=True, show_default=True,
              help="Resume from the checkpoint if one exists.")
def scan(limit: int | None, concurrency: int, out: Path, top: int, resume: bool) -> None:
    """Screen every OSM-mapped US data center and rank by stranded viability."""
    from src.scan import render_finding, run_scan

    out.mkdir(parents=True, exist_ok=True)
    checkpoint = out / "checkpoint.jsonl"
    if not resume and checkpoint.exists():
        checkpoint.unlink()

    console.print("[dim]Fetching US data centers from OpenStreetMap…[/dim]")
    try:
        result = asyncio.run(
            run_scan(
                limit=limit,
                concurrency=concurrency,
                attestation_dir=out / "attestations",
                checkpoint=checkpoint,
            )
        )
    except MireyeError as exc:
        raise click.ClickException(f"Mireye: {exc}") from exc

    console.print(
        f"[green]Screened {result.screened}/{result.total_found}[/green] "
        f"({result.failed} failed)."
    )

    from src.scan import dedupe_campuses

    campuses = dedupe_campuses(result.rows)
    finding = render_finding(result, campuses, top_n=top)
    (out / "finding.md").write_text(finding, encoding="utf-8")
    (out / "scan.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    (out / "campuses.json").write_text(
        json.dumps([c.model_dump() for c in campuses], indent=2), encoding="utf-8"
    )

    console.print(
        f"[dim]{result.screened} buildings rolled up to {len(campuses)} campuses.[/dim]"
    )
    console.print(f"\n[bold]Top {min(top, len(campuses))} most-stranded campuses[/bold]")
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("#", width=3, justify="right")
    table.add_column("Campus")
    table.add_column("Op", width=14)
    table.add_column("Bldgs", width=5, justify="right")
    table.add_column("Verdict", width=10)
    table.add_column("Stranded", width=8, justify="right")
    for i, c in enumerate(campuses[:top], 1):
        colour = "red" if c.verdict == "disputed" else "yellow" if c.verdict == "flagged" else "green"
        table.add_row(
            str(i), (c.name or "")[:34], (c.operator or "")[:14], str(c.building_count),
            Text(c.verdict.upper(), style=colour), Text(f"{c.stranded_viability:.2f}", style="bold"),
        )
    console.print(table)
    console.print(f"\n[green]Finding written to {out / 'finding.md'}[/green]")


if __name__ == "__main__":
    cli()
