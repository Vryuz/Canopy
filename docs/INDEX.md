# docs/ — what's here and how to read it

If you're picking this up months later, read in this order.

| # | Doc | What it is | Read it when |
|---|---|---|---|
| 1 | [`../README.md`](../README.md) | The **outward pitch** — what the tool does, the verticals, how to run it, the honest boundaries. | You want the 5-minute "what is this" or you're preparing the Mireye submission. |
| 2 | [`INTERNAL_REFERENCE.md`](INTERNAL_REFERENCE.md) | The **build log** — problem, architecture, file-by-file, and the real bugs the live API exposed (with fix + test each). | You're getting back into the *code*, or debugging, or extending a vertical. |

**Local-only strategy docs (deliberately not committed):** `DECISION_LOG.md` (every decision
+ why, including rejects) and `COMPANY_THESIS.md` (the 10-year view). These hold candid
strategy and competitor analysis and live only on the author's machine — they're in
`.gitignore` on purpose. If you're the author reading this locally, they're right next to
this file.

## The 30-second version

We built a **verification agent**: give it a location + a claim, it checks the claim against
Mireye's cited facts *plus* external sources (OpenFEMA, Moratorium Nation), and reports where
they disagree. Two verticals — **flood-disclosure verification** and **data-center permitting
screening** — on one domain-free engine.

- **Near-term:** the Mireye challenge entry + a reusable verification engine.
- **The engine** (`observation → estimate → evidence → attestation`) is the piece Canopy also
  needs — building it here on US data is the fastest way to harden it.
- **The 10-year read:** the same engine becomes the neutral trust/settlement layer for the
  data-center↔community↔grid interface (screen where → structure the benefit → verify delivery
  → orchestrate the flexible resources). Distinct company from Canopy; shared primitive.

## Cross-project links

- **Canopy** (separate company) — environmental state infrastructure for the Indian landscape.
  Its master doc parked data-center externalities as "not Canopy, pick up separately"; this
  project is that parked thread. Shared: the Verification Engine; one shared capability
  (water-basin stress per site, from Canopy's InSAR-groundwater wedge).
