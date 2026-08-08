# National Scan — Run Log

A running record of the national data-center scan (`python -m src.cli scan`), so a full
run and its findings can be referenced back later. Companion to `INTERNAL_REFERENCE.md`.

---

## What the scan does

1. Pull every OSM-tagged US data center (`clients/osm.py`, cached to
   `data/us_data_centers.json`) — **1,824 sites**.
2. Screen each on the ~27 curated `DC_FIELDS` via Mireye, plus nearby active moratoria
   (Mireye + Moratorium Nation fusion).
3. Rank by **stranded viability** = physical mean − permitting score (high = an excellent
   site being held back by permitting risk).
4. Emit `findings/finding.md` (publishable), `findings/scan.json` (raw), and a content-hashed
   attestation per actionable site under `findings/attestations/`.

## Reliability features (added before the full run)

- **Checkpointing:** every successful row is appended to `findings/checkpoint.jsonl` as it
  finishes. `--resume` (default on) skips sites already in the checkpoint, so an interruption
  costs nothing to recover. Failures are *not* checkpointed, so they're retried on resume.
- **Progress logging:** processes sites as-completed (not one final gather), logging count /
  failures / rate / ETA every 25 sites.
- **Isolation:** a single site's failure (timeout, bad geometry, Mireye error) is caught and
  counted, never aborts the run.

---

## Run 1 — full national scan (2026-08-09)

- **Command:** `python -m src.cli scan --concurrency 6 --top 40 --out findings`
- **Scope:** all 1,824 OSM-mapped US data centers.
- **Live token:** yes (`MIREYE_OFFLINE=0`).
- **Observed rate:** ~90 sites/min at concurrency 6.
- **Cost estimate:** ~1,814 × ~27 credits ≈ **49k credits** (inside Growth's 120k/mo).
- **Status:** COMPLETE.

### Results

- **1,824** found · **1,814** screened · **10** failed (transient errors, isolated).
- Verdict split:
  - **866 DISPUTED (48%)** — physically viable, inside an active moratorium's blast radius.
  - **736 VERIFIED (41%)** — clear a first-pass screen.
  - **212 FLAGGED (12%)** — a named risk to resolve early.
- **2,156 attestations** written (one per actionable site; disputed + flagged).

**Headline:** nearly half of America's mapped data centers sit on physically excellent land
that is now inside the reach of an enacted local moratorium. The top of the stranded list is
not fringe — it's Google, AWS, QTS, Flexential, Digital Realty, Switch, T5.

Top stranded sites (physical ≈ 1.00, permitting 0.05, stranded ≈ 0.95):

| Site | Physical | Permitting | Stranded |
|---|---|---|---|
| LexisNexis Springfield | 1.00 | 0.05 | 0.95 |
| Google Lockbourne, OH | 1.00 | 0.05 | 0.95 |
| Nautilus Cryptomine | 1.00 | 0.05 | 0.95 |
| Amazon AWS PHL | 0.99 | 0.05 | 0.94 |
| QTS / Flexential Raleigh | 0.99 | 0.05 | 0.94 |

Artifacts: `findings/finding.md` (top-40 table + method) and `findings/scan.json` (all 1,814
rows) are committed. The 2,156 per-site attestations stay local (regenerable, too many to track).

### Known caveats
- **Duplicate names** in the top list (multiple "Google", "QTS", "Amazon Web Services") are
  distinct OSM-tagged buildings on the same campus. A production finding would dedupe by
  proximity/operator; honest to leave as "OSM-mapped" for now.
- Permitting 0.05 recurs at the top because the metric floors there once ≥1 active moratorium
  sits inside the default 80 km radius — so the ranking above ~0.90 is driven by physical
  quality. That's intended (stranded viability = physical − permitting), but worth stating.
- Every top site's strongest path-to-yes is **grid flexibility (VPP)** — expected, since most
  cluster in PJM/MISO metros with real capacity markets.
