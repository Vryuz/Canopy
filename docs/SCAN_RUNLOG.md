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
- **Observed rate:** ~87 sites/min at concurrency 6 → ETA ~21 min.
- **Cost estimate:** ~1,824 × ~27 credits ≈ **49k credits** (inside Growth's 120k/mo).
- **Status:** RUNNING (checkpoint growing; monitor armed for `finding.md`).

_Results table + headline findings to be filled in on completion._

<!-- RESULTS PLACEHOLDER — updated once the run finishes -->
