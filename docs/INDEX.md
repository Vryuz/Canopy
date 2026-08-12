# docs/ — what's here and how to read it

If you're picking this up months later, read in this order.

| # | Doc | What it is | Read it when |
|---|---|---|---|
| 1 | [`../README.md`](../README.md) | The **outward pitch** — what the agent does, the three verticals, how to run it, the honest boundaries. | You want the 5-minute "what is this" or you're preparing a submission. |
| 2 | [`INTERNAL_REFERENCE.md`](INTERNAL_REFERENCE.md) | The **build log** — problem, architecture, file-by-file, every real bug the live API exposed (fix + test each), and each session's additions (§11–§16). | You're getting back into the *code*, debugging, or extending a vertical. |
| 3 | [`SCAN_RUNLOG.md`](SCAN_RUNLOG.md) | The **national-scan results** — 1,814 buildings → 1,154 campuses, 500 disputed, plus method and honest caveats. | You want the headline finding or the numbers behind `/map`. |
| 4 | [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) | The **live-demo script** — four beats (~2 min), the cache warm-up, per-beat talk track, contingency table. | You're about to present. |
| 5 | [`ORCHESTRA_SUBMISSION.md`](ORCHESTRA_SUBMISSION.md) | The **AO Orchestra fit brief** — why this dual-submits, and what's honest about it. | You're deciding whether/how to enter Orchestra. |
| 6 | [`AO_SESSION_PROMPTS.md`](AO_SESSION_PROMPTS.md) | **Paste-ready briefs** for three parallel AO sessions (resume-scan UI, map tour, attestation share). | You're building the AO-evidence feature pass. |

**Local-only strategy docs (deliberately not committed):** `DECISION_LOG.md` (every decision
+ why, including rejects) and `COMPANY_THESIS.md` (the 10-year view). These hold candid
strategy and competitor analysis and live only on the author's machine — they're in
`.gitignore` on purpose. If you're the author reading this locally, they're right next to
this file.

## The 30-second version

It's an **agent**: give it a location + a claim, and it checks the claim against Mireye's
cited facts *plus* an independent second source, weighs the contradictions, decides a verdict
with calibrated confidence, and emits a cited, tamper-evident **attestation**. Not a map, not
a dashboard — a decision with evidence.

Three verticals on one domain-free engine:

- **Flood-disclosure verification** — Mireye + OpenFEMA. *Buyer: lenders / title / insurers.*
- **Data-center siting** — Mireye + Moratorium Nation. *Buyer: developer siting teams.*
- **Carbon-credit verification** — Mireye + OSM protected areas. *Buyer: credit buyers / VVBs.*

On top of the verticals: a **national scan** (`/map` — 1,154 campuses, 43% stranded), a
**portfolio** batch tab (a whole book, screened in parallel), and **shareable attestations**
(`/a/{id}`, self-verifying in the browser).

- **Near-term:** the Mireye challenge entry (+ Untrivial's Orchestra hackathon) and a
  reusable verification engine.
- **The engine** (`observation → estimate → evidence → attestation`) is the piece Canopy also
  needs — hardening it here on US data is the fastest path.
- **The 10-year read:** the same engine becomes the neutral trust/settlement layer for the
  data-center↔community↔grid interface (screen where → structure the benefit → verify delivery
  → orchestrate the flexible resources). Distinct company from Canopy; shared primitive.

## Cross-project links

- **Canopy** (separate company) — environmental state infrastructure for the Indian landscape.
  Its master doc parked data-center externalities as "not Canopy, pick up separately"; this
  project is that parked thread. Shared: the Verification Engine; one shared capability
  (water-basin stress per site, from Canopy's InSAR-groundwater wedge).
