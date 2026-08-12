# Canopy for The Orchestra hackathon

Notes on why Canopy fits Untrivial's Orchestra (Aug 12–13). Not a pitch deck — a short brief
so we can decide fast whether it's worth submitting the same project twice.

## Orchestra's ask

> *"A fully online hackathon for the @aoagents community. Build anything you want. No theme.
> No limits. Just use AO as your coding workspace and ship something real."* — @Maaztwts

Two things that matter for judging:

1. **Ship something real.** No theme, no limits — the bar is "would a human use this in the
   real world," not "did you use their framework."
2. **Built using AO.** Agent Orchestrator is a desktop app that supervises multiple coding
   agents (Claude Code, Cursor, Aider, Codex, …) working in parallel on the same repo via
   git worktrees. It's a *dev workspace*, not a protocol you integrate against.

The nick_realm subthread hints at the deeper AO thesis: **stateful continuity for stateless
MCP** — an execution's workspace, artifacts, tool handles, mutations, failures, and
checkpoints, as a first-class object you can hand off. "Save games, but for agents."

## Why Canopy is the right submission

**It ships something real.**
Three verticals (flood, carbon, data center), 1,814-site national scan, shareable
self-verifying attestations, a lender/VVB/developer batch surface, real cited federal
sources on every claim. A named buyer per vertical. Real problem, real cheque-writer.

**It was structurally built like an AO project would be.**
Three independent verticals sitting on one domain-free engine — each vertical is a single
file (`src/verticals/*.py`), each landed in a separate commit with its own tests, each is
exactly the shape of work a parallel-agent workspace produces. If we'd developed this in AO
proper, the three verticals would have been three concurrent agent sessions.

**Its national scan is a working demonstration of AO's own thesis.**
`src/scan.py` implements exactly the "save-games for agents" pattern nick_realm's tweet
describes:

- The scan is a long execution over 1,824 sites.
- Every completed row is appended to `findings/checkpoint.jsonl` as it lands.
- Kill it at row 1,500 and `--resume` picks up at 1,501, with **zero re-billed credits**.
- Different agent, different model, different day — the checkpoint is the state handle;
  any resumer can continue. That's "MCP stays stateless, the execution doesn't."

That's not a coincidence — it's what a real long-running agentic workflow needs.

## What to point to during judging

| Judge asks | We show |
|---|---|
| "What did you ship?" | `/map` — 500 disputed campuses out of 1,154 |
| "Who'd use it?" | `/` — three verticals, each with a named buyer + a live verdict |
| "Is it trustworthy?" | `/a/{id}` — tamper it live; the page catches it |
| "Would a real user run this at scale?" | `/`, **Portfolio** tab — batch verification over a portfolio, streaming |
| "Where's the parallel-agent story?" | The three verticals, all independent, all on one engine (`src/agent.py`). And the scan checkpointing. |
| "Show me the stateful-continuity thesis" | `/scan/resume-ui` — kill the scan, click Resume, watch the checkpoint grow five real sites at a time. |

## The stateful-continuity feature (built)

The one thing that makes the "save-games for agents" thesis literal is now built:
**`/scan/resume-ui`**. It runs `run_scan(...)` against a throwaway demo checkpoint five real
sites at a time, so an audience can watch the state handle grow — the same mechanism that lets
the real 1,824-site scan survive an interruption and resume with zero re-billed work. This is
the closest thing in the project to AO's own pitch, and it's clickable.

Two supporting features shipped alongside it: a guided **story tour** on `/map` (the finding,
narrated) and **shareable attestation links** with OG previews + Copy/Share (the trust surface
made portable).

## Honest notes — READ THIS

- **We did not use AO as our workspace.** The plan to build the final feature pass inside AO
  (three parallel sessions — see `AO_SESSION_PROMPTS.md`) was **dropped**; these features were
  built directly on `main` in a normal Claude Code session. So we have **no AO-provenance
  evidence** — no dashboard screenshots, no worktree-per-session history.
- Orchestra's bar is explicitly *"use AO as your coding workspace."* Without AO provenance, a
  submission can only compete on the **shipped artifact**, not on "we used AO." Judges who
  weight AO usage will (correctly) mark us down; judges who weight "ship something real" will
  find a strong entry.
- We started building before Orchestra was announced, and the git history shows that.

## Submit / skip decision

**This is now the user's call, and it's a real trade-off, not a free win.** Submitting is
still zero marginal cost and the artifact is strong — but be clear-eyed that the "built in AO"
story is gone. Options:

1. **Submit the artifact honestly** — lead with the shipped product and the `/scan/resume-ui`
   stateful-continuity demo, and state plainly that AO wasn't the workspace. Competes on
   substance; loses any AO-provenance points.
2. **Skip Orchestra** — if the judging is heavily AO-usage-weighted, the honest artifact-only
   entry may not place, and the effort is better spent on the Mireye submission.
3. **Actually use AO for something** — even a small real change built in one AO session would
   restore *some* provenance. `AO_SESSION_PROMPTS.md` still has three ready briefs; any one of
   them could be rebuilt/extended in AO if you change your mind.

**Recommendation:** option 1 if entering at all — submit honestly, don't fake AO usage.
