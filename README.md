# Verification Agent

**An agent that checks claims about physical locations against cited federal ground truth — and reports where the sources disagree.**

Mireye tells you what is true at a coordinate. This agent asks a harder question: *is what someone told you about this place actually true, and what does the record say that the coordinate alone does not?*

Built for the Mireye challenge. Mireye supplies the site facts; FEMA's claims history, a national moratorium inventory, and satellite vegetation trends supply the context those facts can't carry.

One domain-free engine, three verticals: **flood disclosure**, **data-center siting**, and **carbon-credit claims**. Each supplies which fields to pull, how to read a claim, and what counts as a contradiction — the engine turns that into a cited, tamper-evident attestation.

---

## What it does

### 1. Flood claim verification
**Who loses money today:** mortgage lenders, title companies, and insurance agents who close on a property whose flood disclosure was wrong. The correction arrives as a denied claim or an uninsurable asset.

Give it an address and a claim. It pulls FEMA's mapped flood zone, base flood elevation, and ground elevation from Mireye, then pulls the county's disaster-declaration and NFIP paid-claims history from OpenFEMA — and tells you whether the claim survives.

```
DISPUTED   confidence: high

Claim: "seller states the property is not in a flood zone"
Location: 1721 Broadway St J, Galveston, TX 77550   (29.30134, -94.78574)

CRITICAL  fema_flood_zone
  claimed: not in a flood zone   observed: AE
  FEMA maps this location as Zone AE, a Special Flood Hazard Area.
  Flood insurance is mandatory on a federally backed mortgage here.

MAJOR  elevation
  observed: 2.5 meters ground vs 11 feet BFE
  Ground elevation sits 0.85 m below the base flood elevation for Zone AE.

Corroborating signals
  • 24 flood-related federal disaster declarations in this county.
    Most recent: Hurricane Beryl (2024), Hurricane Laura (2020)
  • At least 10,000 paid NFIP claims totalling $408,740,612 over 1978–2025.
    Claims came from zones: AE (2207), X (1508), C (1117)…
```

That elevation line is the reason units are carried through the whole pipeline rather than stripped at the edge. Mireye reports ground elevation in **metres** and FEMA's base flood elevation in **feet**; subtracting them raw would report an 8.5 m deficit instead of the real 0.85 m — a fabricated finding, stated confidently, with correct citations underneath it.

### 2. Data-center site screening
**Who loses money today:** site-selection teams at land developers. A 60 MW facility loses roughly **$14.2M per month** of delay, and the moratorium that kills a site is usually passed by a county nobody screened.

Mireye scores physical viability — slope, flood zone, transmission distance, substation proximity, voltage class. Then the agent checks 505 geocoded local data-center moratoria for what's been enacted nearby.

Four real markets, screened live:

| Market | Verdict | Power | Terrain | Hazard | Externalities | Permitting |
|---|---|---|---|---|---|---|
| Ashburn, VA | `DISPUTED` | 1.00 | 1.00 | 1.00 | **0.43** | **0.20** |
| Columbus, OH | `DISPUTED` | 0.82 | 1.00 | 1.00 | 0.67 | **0.05** |
| Phoenix, AZ | `VERIFIED` | 0.75 | 1.00 | 1.00 | **0.40** | 1.00 |
| Council Bluffs, IA | `FLAGGED` | 0.82 | 1.00 | 1.00 | 0.66 | 0.60 |

Ashburn — Mireye's own example coordinate, and the data-center capital of the world — is **flawless on every engineering axis and contested on both axes that never appear on a site plan**: an ozone nonattainment area (which makes backup-generator permitting materially harder) with 3,253 housing units inside 1 km, and five active county moratoria within 80 km. That gap is the product.

It gets sharper. Mireye's own siting post recommends pivoting from congested Tier-1 markets to Tier-2 ones like Columbus. Columbus scores **0.05 on permitting risk — the worst of the four**, with 9 active moratoria within 80 km. The recommended escape hatch is more heavily restricted than the market it's an escape from, and no amount of physical site data surfaces that.

Phoenix inverts it: zero moratoria and a clean `VERIFIED`, but the lowest externalities score in the set — the risk there is water and heat, not politics.

---

## What it combines

Every vertical fuses Mireye with at least one independent second source — that combination
*is* the product.

| Source | What it contributes | Used by | Auth |
|---|---|---|---|
| **Mireye Earth** | Per-coordinate physical facts with per-field provenance | all | Bearer token |
| **OpenFEMA** | County disaster declarations + NFIP paid claims | flood | None |
| **Moratorium Nation** | 505 geocoded data-center moratoria (CC-BY-4.0) | data center | None |
| **OSM / Overpass** | 1,824 US data-center locations; protected-area status (parks/reserves/wilderness) | data center, carbon | None |

---

### 3. National scan — the recipe, aimed at their own industry

Mireye's blog is "we screened all 7,185 meat plants in an afternoon." So we pointed the DC
screen at **every data center in America** — 1,824 of them, pulled free from OpenStreetMap —
and ranked by **stranded viability**: physically excellent sites being held back by
permitting risk. High score = an excellent site the market is forced to walk away from, which
is exactly where a community-benefit package unlocks the most value. The moratorium-vs-
viability gap map *is* the market map.

```bash
python -m src.cli scan --limit 50 --top 25
```

Writes a publishable `findings/finding.md`, the raw `scan.json`, and a content-hashed
attestation per site. Every site screened emits a tamper-evident artifact — re-hash the
canonical body and any alteration is caught.

### The "path to yes" — from go/no-go to negotiation

A contested site isn't dead; it's a negotiation. For every DISPUTED or FLAGGED site the screen
computes the **community-benefit package that would unblock it**, from fields it already
fetched:

- **Grid flexibility (VPP)** — weighted by whether the site's ISO/RTO (PJM, CAISO, ERCOT…) has
  a market a data-center-funded VPP can be paid through, and by how crowded the county queue is.
- **District heat** — liquid cooling turns waste heat into a deliverable benefit where the
  climate is cold and housing is dense enough to pipe it.
- **Water offset** — highest-leverage exactly where the basin is stressed (the flashpoint that
  kills siting).

Ashburn, DISPUTED, returns: *"strongest lever — grid flexibility: fund distributed capacity in
PJM instead of waiting on the queue."* The reframe: data centers as verifiable good neighbors,
not just consumers.

### 3. Carbon-credit claim verification

**Who loses money today:** credit buyers and the verification bodies (VVBs) who certify them.
A carbon credit *is* a claim — "this land was reforested" — and the market is drowning in an
integrity crisis (Verra invalidated 37 rice-methane projects, 4.5M credits, ~99.9% of all rice
credits ever issued). A buyer holding junk credits eats the clawback.

Give it a parcel and a project claim. It checks the claim against federal vegetation ground
truth (land cover, tree canopy, and the **5-year NDVI trend** — the additionality signal) and
flags the two things that sink credits: the project isn't real, or its additionality doesn't
hold.

```bash
python -m src.cli carbon "47.8,-123.5" --claim "reforestation project, new trees planted since 2021"
```

```
DISPUTED   confidence: high

MAJOR  ndvi_change_5y
  claimed: new vegetation added   observed: NDVI change -0.04 over 5y with 76% existing canopy
  Canopy is already mature and the 5-year trend shows no gain. A reforestation credit here
  is hard to defend as additional — the forest appears to predate the project.
```

That's the exact failure mode that sank the rice credits, caught from a coordinate.

**The fusion:** Mireye's vegetation truth is combined with a second, independent source —
**OSM protected-area status** — to test the hardest additionality question of all. An
avoided-deforestation claim over the same Olympic forest returns DISPUTED, because the parcel
sits *inside Olympic National Park and a designated Wilderness*: the land was legally protected
regardless, so you cannot be paid to prevent a loss that law already prevents. Neither source
alone catches this; the combination does. This is Canopy's Wedge 1 (sell the attestation *to*
developers, don't become one), dry-run on US data.

## Why it's an agent, not a dashboard

It **reasons** — diffs a claim against multiple independent sources and weighs contradictions by severity, distinguishing a claim that *understates* risk from one that overstates it.

It **decides** — emits `VERIFIED` / `DISPUTED` / `FLAGGED` / `INCONCLUSIVE` with a calibrated confidence, not a pile of fields for a human to interpret.

It **acts** — produces an attestation: a cited, timestamped artifact that survives a dispute.

And it declares what it doesn't know. Every requested field that failed to resolve appears as a **data gap** in the output, and confidence is capped by coverage — an answer built on 30% of the requested evidence can never be reported as high-confidence. When OpenFEMA returns its 10,000-row page cap, the memo says "at least 10,000 claims" rather than passing a truncated count off as a total.

---

## Quickstart

```bash
pip install -e .
cp .env.example .env    # add your MIREYE_API_TOKEN
```

Without a token it runs on recorded fixtures — every command below works offline with `--offline`.

**CLI**

```bash
python -m src.cli flood "2201 Seawall Blvd, Galveston, TX" --claim "not in a flood zone"
```

```bash
python -m src.cli dc "39.0438, -77.4874"
```

**Web demo**

```bash
python -m uvicorn api.server:app --port 8000
```

Then open http://localhost:8000 — two tabs, one per vertical, with clickable source citations on every value.

**API**

```bash
curl -X POST localhost:8000/verify/flood -H 'content-type: application/json' \
  -d '{"location":"2201 Seawall Blvd, Galveston, TX","claim":"not in a flood zone"}'
```

**Tests**

```bash
python -m pytest tests/ -q
```

---

## Structure

```
src/
├── agent.py              # the verification loop — resolve → gather → compare → decide → attest
├── models.py             # Evidence, Discrepancy, Verdict, VerificationMemo
├── clients/
│   ├── mireye.py         # Mireye API, provenance preserved per field
│   ├── openfema.py       # disaster declarations + NFIP claims
│   └── moratoria.py      # moratorium inventory + haversine proximity
├── verticals/
│   ├── flood.py          # claim parsing, zone comparison, BFE check
│   └── datacenter.py     # physical scoring + permitting risk
└── output/memo.py        # terminal and markdown renderers
```

`agent.py` holds no domain knowledge. A vertical supplies three things — which fields to pull, how to read a claim, what counts as a contradiction — and the loop turns that into a cited attestation. Adding a third vertical means writing one file.

---

## Honest boundaries

- **Proximity is not deliverability.** Distance to a transmission line says nothing about interconnection-queue position or available headroom. This screen ranks candidates; it does not promise power.
- **Moratoria are a leading indicator, not a prediction.** A neighbouring county's ban is the best available signal that this one will be asked for the same, but it is a signal, not a forecast.
- **FEMA zones flip at building scale.** Twenty metres of geocode error can change the answer, which is why the agent surfaces whether a coordinate was rooftop-matched or interpolated from a street centerline, and says so in the memo when it wasn't.
- **County-level flood history is context, not a property-level claim.** NFIP claim counts are aggregated by county; they describe the neighbourhood, not the parcel.
- **The moratorium inventory refreshes quarterly.** It carries its own verification tags, and some rows are flagged by their maintainers as needing confirmation.
- **Scores are screening heuristics, not engineering criteria.** The thresholds decide what to look at next; they do not size a pad, a genset, or a water permit.

## Cost

A full `data_center_siting` screen bills 96 credits (~9¢); a flood verification bills 10. The free tier's 5,000 monthly credits covers roughly 50 site screens or 500 flood checks. OpenFEMA and the moratorium inventory are free and unmetered.

---

## Data sources

- [Mireye Earth](https://docs.mireye.ai) — 317 fields, federal sources, per-field citations
- [OpenFEMA](https://www.fema.gov/about/openfema/api) — public, no auth
- [Moratorium Nation](https://github.com/mjbommar/moratorium-data-2026) — CC-BY-4.0
