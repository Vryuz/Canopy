# Canopy — Mireye challenge submission

The one-page answer to Mireye's rubric. Everything below is live in this repo; run it with
the two commands in `DEMO_RUNBOOK.md`.

## What it is, in one line

**An agent that checks claims about US locations against cited federal ground truth, and
reports where the sources disagree — as a tamper-evident attestation.**

Give it a location and a claim. It reasons over Mireye's facts plus an independent second
source, decides a verdict with calibrated confidence, and produces a cited artifact that
survives a dispute. Three verticals ride one domain-free engine.

## It is an agent, not a website (the hard rule, first)

Mireye's rule: *build something that reasons, decides, and acts — not a website with a map on
it.* The web pages are windows onto the agent; the agent is `src/agent.py`, and it:

- **Reasons** — diffs a claim against multiple independent sources and weighs contradictions
  by severity, distinguishing a claim that *understates* risk (critical) from one that
  overstates it (major). `_decide()` in `src/agent.py`.
- **Decides** — emits `VERIFIED` / `DISPUTED` / `FLAGGED` / `INCONCLUSIVE` with a confidence
  that is **capped by evidence coverage** — a verdict built on 30% of the requested fields
  can never be reported as high-confidence.
- **Acts** — mints a content-hashed attestation: a cited, timestamped artifact that a
  counterparty can re-verify without trusting us (`/a/{id}` recomputes the hash in-browser).
- **Declares what it doesn't know** — every field that failed to resolve appears as a data
  gap; when OpenFEMA hits its 10,000-row cap the memo says "at least 10,000," never a
  truncated total dressed up as complete.

The map, the portfolio tab, and the resumable-scan page are the *same agent* run at scale, on
a book, and over a long execution — not separate dashboards.

## The four judging lines

### 1 · What did you combine Mireye with?

Three independent fusions, one per vertical — the combination *is* the product; neither source
alone catches what the pair does:

| Vertical | Mireye + | Catches |
|---|---|---|
| Flood | **OpenFEMA** (disaster declarations + NFIP paid claims) | A "not in a flood zone" disclosure that FEMA maps as Zone AE, backed by the county's real claims history |
| Data center | **Moratorium Nation** (505 geocoded local bans) | A physically flawless site sitting inside an enacted moratorium's blast radius |
| Carbon | **OSM protected areas** | A "protecting intact forest" credit on land already inside a national park — non-additional by law |

### 2 · Is it a real problem — does someone lose money today?

- **Flood:** a wrong flood disclosure surfaces as a denied claim or an uninsurable asset after
  close. Billions in NFIP payouts; our Galveston example alone sits in a county with **$408M**
  of paid claims.
- **Data center:** a 60 MW facility loses roughly **$14.2M per month** of permitting delay, and
  the moratorium that kills a site is usually passed by a county nobody screened.
- **Carbon:** Verra invalidated **4.5M rice-methane credits** (~99.9% of all ever issued) over
  integrity — a buyer holding junk credits eats the clawback.

### 3 · Who writes the cheque?

Named, not "developers might like this":

- **Flood** → mortgage lenders, title companies, insurance underwriters.
- **Data center** → land-developer site-selection teams.
- **Carbon** → credit buyers and the verification bodies (VVBs) who must not certify a credit
  that later gets clawed back.

### 4 · Is it an agent?

Answered first, above. Short version: reasons → decides → acts → attests, and declares its
own gaps.

## Beyond the rubric — the proof it scales

Mireye's own blog is "we screened all 7,185 meat plants in an afternoon." We pointed the same
agent at **every US data center** — 1,824 buildings → 1,154 campuses — and found **500 (43%)
disputed**: physically excellent sites now stranded by permitting risk, led by Google, AWS,
QTS, Flexential. That's `/map`, and the run is checkpointed so it survives interruption
(`/scan/resume-ui` makes that resumability clickable).

## The Canopy carryover (why we cared enough to build it well)

The engine — `observation → estimate → evidence → attestation`, domain-free — is the exact
primitive Canopy needs for environmental MRV. Building it here on Mireye's US data is the
fastest way to harden it. Different geography, identical loop.

## How to run it

Local, ~2 minutes: see [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md). CLI works offline with recorded
fixtures (`--offline`); the API + web demo need a `MIREYE_API_TOKEN`. 59 tests, all green.

## Honest boundaries

- **US only** — Mireye's coverage bounds. An India version needs different sources (documented
  in `INTERNAL_REFERENCE.md` §9); the engine transfers, the data doesn't.
- **A screen, not a survey.** Proximity is not deliverability; confidence is capped by
  coverage; every gap is declared. The agent's honesty about what it *can't* see is a feature,
  not a limitation we're hiding.
