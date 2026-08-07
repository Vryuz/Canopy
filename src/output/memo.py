"""Render attestations for a terminal or a file. Citations are never optional."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.models import Severity, SiteScreen, VerdictKind, VerificationMemo

VERDICT_STYLE = {
    VerdictKind.VERIFIED: ("green", "VERIFIED"),
    VerdictKind.DISPUTED: ("red", "DISPUTED"),
    VerdictKind.FLAGGED: ("yellow", "FLAGGED"),
    VerdictKind.INCONCLUSIVE: ("dim", "INCONCLUSIVE"),
}

SEVERITY_STYLE = {
    Severity.CRITICAL: "bold red",
    Severity.MAJOR: "red",
    Severity.MINOR: "yellow",
}


def render_memo(memo: VerificationMemo, console: Console | None = None) -> None:
    console = console or Console()

    style, label = VERDICT_STYLE[memo.verdict.kind]
    header = Text.assemble(
        (f" {label} ", f"bold white on {style}" if style != "dim" else "bold"),
        ("  ", ""),
        (memo.verdict.reasoning, ""),
    )
    console.print(
        Panel(
            header,
            title="[bold]Verification Memo[/bold]",
            subtitle=f"confidence: {memo.verdict.confidence.value}",
            border_style=style,
        )
    )

    console.print(f'\n[bold]Claim:[/bold] "{memo.claim.text}"')
    location = memo.location.resolved_address or str(memo.location)
    console.print(f"[bold]Location:[/bold] {location}  [dim]({memo.location})[/dim]")
    if not memo.location.parcel_grade:
        console.print("[yellow]  ! coordinate interpolated from street, not rooftop-matched[/yellow]")

    if memo.discrepancies:
        console.print("\n[bold]Discrepancies[/bold]")
        for d in memo.discrepancies:
            badge = Text(f" {d.severity.value.upper()} ", style=f"bold white on {SEVERITY_STYLE[d.severity].split()[-1]}")
            console.print(Text.assemble(badge, ("  ", ""), (d.field, "bold")))
            console.print(f"    claimed: [dim]{d.claimed}[/dim]   observed: [bold]{d.observed}[/bold]")
            console.print(f"    {d.explanation}")
            console.print()

    if memo.signals:
        console.print("\n[bold]Corroborating signals[/bold]")
        for s in memo.signals:
            console.print(f"  • [bold]{s.label}[/bold] — {s.detail}")
            console.print(f"    [dim]{s.source} · fetched {s.fetched_at:%Y-%m-%d}[/dim]")

    _render_evidence(memo.evidence, console)
    _render_gaps(memo.data_gaps, console)
    _render_sources(memo.sources(), console)
    console.print(f"\n[dim]Generated {memo.generated_at:%Y-%m-%d %H:%M UTC}[/dim]")


def render_screen(screen: SiteScreen, console: Console | None = None) -> None:
    console = console or Console()

    style, label = VERDICT_STYLE[screen.verdict.kind]
    console.print(
        Panel(
            Text.assemble(
                (f" {label} ", f"bold white on {style}" if style != "dim" else "bold"),
                ("  ", ""),
                (screen.verdict.reasoning, ""),
            ),
            title="[bold]Data Center Site Screen[/bold]",
            subtitle=f"confidence: {screen.verdict.confidence.value}",
            border_style=style,
        )
    )

    location = screen.location.resolved_address or str(screen.location)
    console.print(f"\n[bold]Site:[/bold] {location}  [dim]({screen.location})[/dim]")

    if screen.scores:
        console.print("\n[bold]Scored dimensions[/bold]")
        table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
        table.add_column("Dimension", width=22)
        table.add_column("Score", width=8, justify="right")
        table.add_column("Rationale")
        for s in screen.scores:
            colour = "green" if s.score >= 0.7 else "yellow" if s.score >= 0.4 else "red"
            table.add_row(s.dimension, Text(f"{s.score:.2f}", style=colour), s.rationale)
        console.print(table)

    if screen.signals:
        console.print("\n[bold]Regulatory & opposition signals[/bold]")
        for s in screen.signals:
            marker = "[red]![/red]" if s.weight is Severity.CRITICAL else "•"
            console.print(f"  {marker} [bold]{s.label}[/bold] — {s.detail}")
            console.print(f"    [dim]{s.source} · fetched {s.fetched_at:%Y-%m-%d}[/dim]")

    if screen.path_to_yes:
        console.print("\n[bold cyan]Path to yes[/bold cyan] [dim](what would unblock this site)[/dim]")
        console.print(f"  {screen.path_to_yes.summary}")
        for lever in sorted(screen.path_to_yes.levers, key=lambda l: l.strength, reverse=True):
            colour = "green" if lever.strength >= 0.7 else "yellow" if lever.strength >= 0.4 else "dim"
            console.print(
                Text.assemble(
                    ("  → ", ""),
                    (f"{lever.name} ", "bold"),
                    (f"[{lever.strength:.2f}] ", colour),
                    (lever.headline, ""),
                )
            )

    _render_evidence(screen.evidence, console)
    _render_gaps(screen.data_gaps, console)
    _render_sources(screen.sources(), console)
    console.print(f"\n[dim]Generated {screen.generated_at:%Y-%m-%d %H:%M UTC}[/dim]")


def _render_evidence(evidence, console: Console) -> None:
    if not evidence:
        return
    console.print("\n[bold]Evidence[/bold]")
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Field", no_wrap=True)
    table.add_column("Value", no_wrap=True)
    table.add_column("Source", no_wrap=True)
    table.add_column("Fetched", no_wrap=True)
    table.add_column("Conf", no_wrap=True)
    for e in evidence:
        table.add_row(
            e.field,
            e.display(),
            e.source,
            f"{e.fetched_at:%Y-%m-%d}",
            e.confidence.value,
        )
    console.print(table)


def _render_gaps(gaps, console: Console) -> None:
    if not gaps:
        return
    console.print("\n[bold yellow]Declared data gaps[/bold yellow] [dim](requested, not returned)[/dim]")
    for g in gaps:
        retry = " [dim](retryable)[/dim]" if g.retryable else ""
        console.print(f"  · {g.field}: {g.reason}{retry}")


def _render_sources(sources, console: Console) -> None:
    if not sources:
        return
    console.print(f"\n[dim]Sources: {', '.join(sources)}[/dim]")


def memo_to_markdown(memo: VerificationMemo) -> str:
    lines = [
        "# Verification Memo",
        "",
        f"**Verdict:** {memo.verdict.kind.value.upper()} "
        f"(confidence: {memo.verdict.confidence.value})",
        "",
        memo.verdict.reasoning,
        "",
        f'**Claim:** "{memo.claim.text}"',
        f"**Location:** {memo.location.resolved_address or memo.location} "
        f"({memo.location})",
        "",
    ]

    if memo.discrepancies:
        lines += ["## Discrepancies", "", "| Severity | Field | Claimed | Observed | Finding |",
                  "|---|---|---|---|---|"]
        lines += [
            f"| {d.severity.value.upper()} | {d.field} | {d.claimed} | {d.observed} | {d.explanation} |"
            for d in memo.discrepancies
        ]
        lines.append("")

    if memo.signals:
        lines += ["## Corroborating signals", ""]
        lines += [
            f"- **{s.label}** — {s.detail}  \n  _{s.source}, fetched {s.fetched_at:%Y-%m-%d}_"
            for s in memo.signals
        ]
        lines.append("")

    if memo.evidence:
        lines += ["## Evidence", "", "| Field | Value | Source | Fetched | Confidence |",
                  "|---|---|---|---|---|"]
        lines += [
            f"| {e.field} | {e.display()} | "
            f"{f'[{e.source}]({e.source_url})' if e.source_url else e.source} | "
            f"{e.fetched_at:%Y-%m-%d} | {e.confidence.value} |"
            for e in memo.evidence
        ]
        lines.append("")

    if memo.data_gaps:
        lines += ["## Declared data gaps", ""]
        lines += [f"- `{g.field}`: {g.reason}" for g in memo.data_gaps]
        lines.append("")

    lines.append(f"_Generated {memo.generated_at:%Y-%m-%d %H:%M UTC}_")
    return "\n".join(lines)
