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

## Honest notes

- We started building before Orchestra was announced, and the git history shows that. So
  we're submitting the *artifact*, not claiming AO was the workspace we used.
- No changes needed to submit — the project stands on its own for both Mireye and Orchestra.
- If the hackathon judges care specifically about AO-as-workspace-provenance, we won't win.
  If they judge on the shipped artifact, we're competitive.

## Submit / skip decision

**Recommendation: submit.** Zero marginal cost, and the artifact is legitimately strong
against Orchestra's stated criteria. Include this file (or a shorter version) in the
submission notes so we're transparent about the timeline.

## What to build next only if we commit

If we do commit to Orchestra as a first-class target, one thing would materially strengthen
the submission: **wire up a live "resume this scan" demo** — a UI that shows an interrupted
scan, lets the audience click resume, and continues from the checkpoint. That's a 2–3 hour
build (`findings/checkpoint.jsonl` is already the data source) and it makes the "save-games
for agents" story literal instead of narrative.
