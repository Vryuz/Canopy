# Canopy — Internal Reference & Build Log

> Internal working doc. Not the README (that's the outward pitch). This is the "what we
> actually did, why, what broke, and where we go next" record. Written to be picked up
> cold after a break.

Last updated: 2026-08-10 (session 5 — resume-scan UI, map tour, attestation share; §17). 59 tests.

> **Session 2 additions** (see §11 at the bottom): the national scan, the community-benefit
> "path to yes" layer, and the content-hashed attestation artifact. The §1–§10 material below
> is the original build; §11 is what changed. Test count: **38** (was 33).

---

## 0. One-paragraph summary

We built an **agent that verifies claims about US locations against cited federal ground
truth, and reports where the sources disagree.** It fuses Mireye (per-coordinate physical
facts, every value carrying its own source + timestamp + confidence) with independent
sources Mireye doesn't have — OpenFEMA (flood disaster + claims history), Moratorium Nation
(local data-center bans), and OSM protected areas. Three verticals ride one domain-free
engine: **flood-disclosure verification** (buyer: mortgage lenders / title / insurers),
**data-center site screening** (buyer: developer site-selection teams), and **carbon-credit
verification** (buyer: credit buyers / verification bodies). On top of the verticals sit a
national scan (1,154 US data-center campuses ranked by stranded viability, with a `/map`
view), shareable self-verifying attestations (`/a/{id}`), and a portfolio batch tab. It is
the Mireye challenge entry (also submitted to Untrivial's Orchestra hackathon), and it
doubles as a working prototype of Canopy's Verification Engine. Live against the real API,
**55 tests passing**.

---

## 1. The problem we set out to solve

### 1.1 The challenge (Mireye's brief)
Mireye is a YC S26 startup. It sells **one API + MCP server** returning cited geospatial
facts for any US coordinate — 304 fields across 7 layers (terrain, land cover, built
environment, utilities, parcels, climate, hazards), sourced only from federal databases
(USGS, FEMA, NOAA, EPA, EIA, NREL, USFWS, etc.). Every field comes back with `source`,
`source_url`, `fetched_at`, and a `confidence` bucket.

Their challenge has one hard rule and four judging lines:
- **Hard rule:** build an *agent* — something that reasons, decides, and acts on
  physical-world data. Not a website with a map on it.
- **Judging:** (1) What did you combine Mireye with? (2) Is it a real problem — does
  someone lose money/time/health today? (3) Who writes the cheque? "Developers might like
  this" is not a buyer. (4) It has to be an agent.

They explicitly said the example ideas on their brief (eagle-strike screening, foundation
forensics, etc.) are for ideation — *do not build those.*

### 1.2 The three candidate pitches we started from
From prior research the user had three:
1. **Data-center / interconnection triage agent** — strong commercially, but Mireye already
   demoed site screening themselves, so pure screening is derivative.
2. **Property-underwriting verification agent** (insurers/lenders) — the verification /
   attestation angle; strongest fit with the user's Canopy work.
3. **"What's blocking this project" agent** (environmental/regulatory blockers) — broad,
   harder to scope for a weekend.

### 1.3 What we chose and why
We did **not** pick one pitch. We extracted the **common primitive** — *verification* — and
built it once, then expressed it as two verticals (a third, carbon, was added later — §13):
- **Flood verification** (pitch 2, cleanest public data via OpenFEMA)
- **Data-center screening** (pitch 1 + 3, but reframed: not "is this site physically good?"
  — Mireye already answers that — but "is this site physically good *and will it actually
  get permitted?*")

The decisive insight: Mireye tells you what's *true at a coordinate*. The harder, unowned
question is whether what someone *told you* about the place holds up, and what the record
says that the coordinate alone doesn't. That reframing is the whole product, and it's the
exact primitive Canopy needs (`observation → estimate → evidence → attestation`).

---

## 2. Why this is the right build (strategic reasoning)

### 2.1 Against Mireye's rubric

| Judging line | Our answer |
|---|---|
| Combined with what? | OpenFEMA (disaster declarations + NFIP claims) and Moratorium Nation (505 geocoded data-center moratoria) |
| Real problem? | Post-close flood surprises cost billions; a 60 MW data-center loses ~$14.2M/month of delay |
| Who writes the cheque? | Flood: mortgage lenders, title cos, insurers. DC: developer site-selection teams |
| Is it an agent? | Reasons (diffs sources, weighs contradictions by severity), decides (VERIFIED/DISPUTED/FLAGGED + calibrated confidence), acts (produces the cited attestation) |

### 2.2 The Canopy carryover (why this isn't a throwaway detour)
The user's rule for doing Mireye at all: it's worth a weekend **only if the build also
produces a reusable Canopy piece.** It does. `agent.py` holds *zero domain knowledge* — a
vertical supplies three things (which fields to pull, how to read a claim, what counts as a
contradiction) and the loop turns that into a cited attestation. That loop + the
`Evidence`/`Discrepancy`/`Verdict` models **are** the Canopy Verification Engine, now with a
working reference implementation behind them. Different geography (US vs India), identical
primitive.

Canopy's own Decision Log already flags data-center environmental externalities as
"architecturally closer to Mireye's world than to Canopy's" — so this build is the literal
bridge the strategy doc anticipated. See §9 for the India extension the user asked about.

---

## 3. What Mireye actually is (as we learned it from the live API)

Endpoints we use / know:
- `POST /v1/geocode` — address → coordinate. Returns `lat`, `lng`, `accuracy` (0–1),
  `accuracy_type` (e.g. `nearest_rooftop_match`), `normalized_address`, `provider`,
  `source`. **1 credit.**
- `POST /v1/fetch` — the workhorse. Pass `fields: [...]` or `preset: "..."`. Returns
  `fields: { name: { value, unit, source, source_url, confidence, fetched_at,
  dataset_vintage, notes, status } }` plus a top-level `partial_failures[]`. **1 credit per
  field per location.**
- `POST /v1/ask` — natural-language question → cited answer (planner + synthesizer LLM
  pipeline). **10 credits.** We don't use it in the hot path (deterministic fetch is
  cheaper and faster) but the client supports it.
- `POST /v1/lookup` — address → canonical parcel + jurisdiction. **300 credits.** Supported
  in client, not used yet (expensive; only needed if we want parcel geometry/owner).
- `GET /v1/meta/fields` — public field catalog. This is how we discovered real field names.

Coverage bounds: **US only**, lat ∈ [18, 72], lng ∈ [-180, -65]. This is the single most
important constraint for the India question (§9): **Mireye cannot answer about India.**

Presets that matter to us: `flood_risk` (13 fields), `data_center_siting` (96 fields — the
doc says 90, live returns 96), `natural_hazard`, `utilities`, `grid_interconnect`.

Pricing: free tier 5,000 credits/mo; Growth $99/mo = 120,000 credits (code GROWTH = free
month). A full DC screen = 96 credits (~9¢). A flood check = ~10 credits.

---

## 4. Architecture — how the whole thing fits together

```
                          ┌─────────────────────────────────────────┐
   CLI  ──┐               │              agent.py                     │
   API  ──┼──►  input ──► │  VerificationAgent.verify(...)            │
   Web  ──┘               │   1. RESOLVE  geocode addr → coordinate   │
                          │   2. GATHER   Mireye fetch (fields/preset)│
                          │              + vertical.gather_external() │
                          │   3. COMPARE  vertical.compare(claim, ev) │
                          │   4. DECIDE   _decide(discrepancies, ...)  │
                          │   5. RENDER   VerificationMemo             │
                          └─────────────────────────────────────────┘
                                   │              │              │
                          ┌────────┘        ┌─────┘         ┌────┘
                          ▼                 ▼               ▼
                   clients/mireye.py  clients/openfema.py  clients/moratoria.py
                   (fetch/geocode,    (disaster decls,     (505 geocoded bans,
                    provenance wrap)   NFIP claims)         haversine proximity)

   Verticals (domain plug-ins, the only place domain logic lives):
     verticals/flood.py       parse_claim / gather_external / compare
     verticals/datacenter.py  score_terrain/power/hazard/externalities/regulatory → screen_site
```

**The key design property:** the engine is domain-free. Adding a third vertical (e.g. wildfire
underwriting, or the India DC screen) means writing one file that satisfies the `Vertical`
protocol. Nothing in `agent.py` changes.

### 4.1 File-by-file (current state, ~2000 LOC total)

> **This table is the original-build snapshot (sessions 1–2).** It has grown since — a
> carbon vertical, the national scan/map, attestations, and a portfolio tab — so counts
> below are historical. See §11–§16 for what each later session added; current test count is
> **55**.

| File | LOC | What it does |
|---|---|---|
| `src/models.py` | 177 | Pydantic models: `Confidence`, `Coordinate`, `Evidence` (with `as_meters()`, `display()`, `vintage`), `DataGap`, `Discrepancy`, `Severity`, `Signal`, `Verdict`/`VerdictKind`, `VerificationMemo`, `SiteScore`, `SiteScreen`, `Claim` |
| `src/agent.py` | 150 | `Vertical` protocol, `VerificationAgent`, `_decide()` (verdict + coverage-capped confidence) |
| `src/clients/mireye.py` | 239 | Live + offline-fixture client. `_to_evidence()` splits values from gaps, preserves provenance |
| `src/clients/openfema.py` | 161 | Disaster declarations + NFIP claims summary by county FIPS. No auth |
| `src/clients/moratoria.py` | 178 | Downloads Moratorium Nation tarball, `find_nearby()` haversine search |
| `src/verticals/flood.py` | 311 | Claim parsing, FEMA zone comparison, unit-safe BFE check, county FIPS derivation |
| `src/verticals/datacenter.py` | 399 | Five scoring dims + `screen_site()` |
| `src/output/memo.py` | 200 | Rich terminal + markdown renderers |
| `src/cli.py` | 91 | `flood` and `dc` commands |
| `api/server.py` | 95 | FastAPI: `/verify/flood`, `/screen/datacenter`, serves web demo |
| `web/index.html` + `style.css` | — | Two-tab single-page demo, clickable citations |
| `tests/test_agent.py` | — | 33 tests |

### 4.2 Core data model (the reusable Canopy primitive)

```
Evidence      = one cited fact (value, unit, source, source_url, fetched_at,
                confidence, note, vintage). as_meters() normalizes length units.
Discrepancy   = where a claim ≠ observed evidence (claimed, observed, severity,
                explanation, evidence[]). Severity ∈ {CRITICAL, MAJOR, MINOR}.
Signal        = corroborating context that isn't a direct contradiction
                (e.g. "24 flood declarations in this county"), weighted.
DataGap       = a requested field that didn't resolve (field, reason, source,
                retryable). Declared, never hidden.
Verdict       = {VERIFIED | DISPUTED | FLAGGED | INCONCLUSIVE} + confidence + reasoning.
VerificationMemo / SiteScreen = the full cited output object.
```

---

## 5. Build sequence — what we did, step by step

The plan file (`~/.claude/plans/abundant-whistling-scott.md`) has the original two-day
plan. Actual sequence:

1. **Research pass.** Read all three Mireye blog posts (cold-chain meat plants, solar
   carports, data-center siting), the templates page, docs, pricing, compare, homepage.
   Learned the recipe Mireye rewards: *public address list + Mireye enrichment + one
   non-obvious second source → ranked, cited, actionable output.*
2. **External-source research** (via subagent): confirmed OpenFEMA is free/no-auth with
   OData query syntax, and that Moratorium Nation (GitHub `mjbommar/moratorium-data-2026`)
   is the best structured moratorium source — 533 rows, geocoded, CC-BY-4.0.
3. **Scaffolding + models** — pydantic models first, everything else depends on them.
4. **Mireye client** with offline fixture mode, so the whole thing was testable before we
   had a token.
5. **OpenFEMA client** — testable live immediately (no auth).
6. **Agent core + flood vertical + memo renderer + CLI.**
7. **Moratoria client + data-center vertical.**
8. **FastAPI server + web demo** (two tabs, live-verified in-browser).
9. **Tests + README.**
10. **Token arrived → swapped to live API → found and fixed 4 real bugs** (see §6). This
    was the highest-value phase: fixtures encode your *assumptions*, live data encodes
    *reality*, and the gap between them is exactly where the bugs live.

---

## 6. What broke against the live API, and how we fixed it

This section is the important one. Everything passed on fixtures; then the real token
exposed four genuine bugs. All fixed, all now covered by regression tests.

### BUG 1 — Unit mismatch (metres vs feet). **Severity: critical.**
- **Symptom:** the flood vertical's "is the ground below the base flood elevation?" check
  subtracted `elevation` (metres) from `fema_base_flood_elevation` (feet) directly.
- **Why it's dangerous:** on Galveston, ground = 2.5 m, BFE = 11 ft (= 3.35 m). Real deficit
  = **0.85 m**. Raw subtraction reports `11 - 2.5 = 8.5 m`. That's a confident, correctly-
  cited, *completely fabricated* finding — the exact failure mode a verification tool exists
  to prevent.
- **Fix:** added `Evidence.as_meters()` which reads the `unit` field and converts feet→m
  before any comparison. `flood.py` `_elevation_check` now uses it.
- **Test:** `test_ground_below_bfe_is_flagged` (asserts 0.85, not 8.5) +
  `test_bfe_in_feet_above_ground_produces_no_finding`.

### BUG 2 — `fema_flood_zone` isn't in the `flood_risk` preset. **Severity: high.**
- **Symptom:** the whole flood check keys on the FEMA zone, but requesting the `flood_risk`
  preset doesn't return `fema_flood_zone` — it lives in `data_center_siting`, and
  `fema_base_flood_elevation` is in *no* preset at all.
- **Fix:** the flood vertical now names its fields **explicitly** (`FLOOD_FIELDS` list)
  instead of expanding a preset. The `Vertical` protocol now accepts `preset` *or* `fields`.
- **Lesson:** presets are convenience bundles, not guarantees of field membership. Always
  check the catalog.

### BUG 3 — Duplicate data gaps. **Severity: medium (cosmetic but sloppy).**
- **Symptom:** a field that times out shows up twice — once as a null-valued field wrapper
  (`status: error`) and again in `partial_failures[]`. The memo listed it twice.
- **Fix:** `_to_evidence()` now merges gaps by field name, keeping the `retryable` flag and
  the more useful reason string.
- **Test:** `test_failed_field_reported_twice_yields_one_gap`.

### BUG 4 — No `county_fips` field for OpenFEMA. **Severity: high (blocking the fusion).**
- **Symptom:** OpenFEMA filters flood claims/declarations by 5-digit county FIPS. Mireye has
  no `county_fips` field.
- **Fix:** derive it from the first 5 digits of `tract_geoid` (the 11-digit census tract
  GEOID is `SS CCC TTTTTT`). Added `political_county` too for the human-readable label.
- **Verified:** Galveston `tract_geoid = 48167724400` → FIPS `48167` → correct county.

### Plus: schema adaptations (not bugs, but reality ≠ my fixtures)
- Geocode response uses `accuracy_type` + `normalized_address`, and `parcel_grade` is
  derived from whether `accuracy_type` contains "rooftop" (street interpolation can be
  hundreds of metres off in rural areas — the memo says so when it wasn't rooftop-matched).
- Field wrappers carry `status: ok | absent | error`. `absent` = "we looked, nothing here";
  `error` = "we couldn't look". Both become gaps, but only `error`/`unavailable` are
  retryable. The `notes` field is preferred over a generic reason string.
- The live catalog is **richer than assumed** — 96 DC fields, including
  `in_air_quality_nonattainment`, `surface_water_supply_use_index_huc12`,
  `housing_units_within_1km`, `interconnection_queue_active_capacity_county_mw`. This let us
  add a whole scoring dimension (see §7).

---

## 7. The data-center scoring model (current)

`screen_site()` produces five scored dimensions (0–1) plus a verdict. Thresholds are
**screening heuristics, not engineering criteria** — they decide what to look at next, not
what to build.

| Dimension | Fields used | Logic |
|---|---|---|
| **Power proximity** | `nearest_substation_distance_m`, `nearest_substation_max_voltage_kv`, `transmission_lines_within_radius_count`, `interconnection_queue_active_capacity_county_mw` | Band substation distance; HV (≥230 kV) scores full; line count for redundancy; a crowded county queue (>5 GW) discounts the score (competing for upgrade capacity) |
| **Terrain** | `slope_degrees` | ≤3° ideal, ≥10° near-zero. Missing = 0.5 (neutral, not penalized) |
| **Hazard & wetlands** | `within_floodplain_polygon`, `fema_flood_zone`, `intersects_wetland` | SFHA −0.6, wetland −0.3 (triggers USACE §404) |
| **Externalities** | `surface_water_supply_use_index_huc12`, `in_air_quality_nonattainment` (+pollutants), `housing_units_within_1km` | The layer opposition actually organizes on: water stress, air permitting difficulty, noise-sensitive receptors |
| **Permitting risk** | Moratorium Nation proximity | The layer **Mireye doesn't have.** Nearest active moratorium drives severity; ≤25 km = critical |

Verdict logic (`_verdict` in datacenter.py, `_decide` in agent.py):
- Regulatory ≤0.25 → **DISPUTED** (physically fine but a permitting minefield)
- Regulatory ≤0.6 or physical mean <0.5 → **FLAGGED**
- else → **VERIFIED**
- Confidence is **capped by field coverage** — an answer built on 30% of requested evidence
  can never be reported high-confidence.

### Live results (real API, 2026-08-07)

| Market | Verdict | Power | Terrain | Hazard | Externalities | Permitting |
|---|---|---|---|---|---|---|
| Ashburn, VA | DISPUTED | 1.00 | 1.00 | 1.00 | 0.43 | 0.20 |
| Columbus, OH | DISPUTED | 0.82 | 1.00 | 1.00 | 0.67 | 0.05 |
| Phoenix, AZ | VERIFIED | 0.75 | 1.00 | 1.00 | 0.40 | 1.00 |
| Council Bluffs, IA | FLAGGED | 0.82 | 1.00 | 1.00 | 0.66 | 0.60 |

**The headline finding:** Ashburn — Mireye's *own* example coordinate, the data-center
capital of the world — is flawless on every engineering axis and contested on the two that
never appear on a site plan (ozone nonattainment + 3,253 homes within 1 km + 5 county
moratoria within 80 km). And Columbus — which Mireye's own blog recommends as the Tier-2
escape from congested Tier-1 markets — scores the *worst* permitting risk of the four
(0.05). The escape hatch is more restricted than what it's escaping. No amount of physical
site data surfaces that; only the fusion does.

---

## 8. Current state / how to run

- **Tests:** `MIREYE_OFFLINE=1 python -m pytest tests/ -q` → 33 passing.
- **CLI flood:** `python -m src.cli flood "1719 Broadway Ave J, Galveston, TX" --claim "not in a flood zone"`
- **CLI DC:** `python -m src.cli dc "39.0438,-77.4874"`
- **Server:** `python -m uvicorn api.server:app --port 8000` → http://localhost:8000
- **Token:** in `.env` (gitignored, confirmed absent from all tracked source). `MIREYE_OFFLINE=0` for live.
- **Offline mode:** works with no token via recorded fixtures in `tests/fixtures/mireye/`.

### Known housekeeping items
- **The git repo is rooted at `C:\Users\varun`, not the project folder.** `git status` shows
  the whole home directory. Run `git init` inside `Desktop/Mireye` before pushing anything.
- Screenshot of the web UI couldn't be captured (Browser pane not displayed) — verified at
  DOM level instead. If you want a screenshot for the submission, display the pane and retry.

### Cheap next wins (not yet done)
- `/v1/proximity` for *drive-time* to nearest substation instead of straight-line haversine.
- A `/v1/field-requests` submission for a "nearest enacted moratorium" field — puts our
  fusion insight into Mireye's own catalog, and the field-request flow is judging-visible
  proof we found a real gap.

---

## 9. The India question (you asked — here's the real analysis)

You raised: Microsoft's biggest data centre in Hyderabad, Google's in Vizag (Visakhapatnam),
and whether we should have India-focused data with checks on power, water, sound, and
environmental protection.

### 9.1 The hard constraint first
**Mireye is US-only** (lat ∈ [18, 72], lng ∈ [-180, -65] — that's North America). It
physically cannot answer about Hyderabad or Vizag. So for the **Mireye challenge itself,
India is out** — an India entry can't use their API, which is the whole point of the
challenge. Keep the submission US. Don't dilute it.

### 9.2 But India data-center screening is a genuinely strong *separate* thesis
And it's not a tangent — it's the **exact bridge to Canopy** the strategy doc already
flagged. The verification-engine pattern we just built transfers directly; **only the data
sources change.** This is the highest-value thing this weekend produced, strategically.

The India data-center boom is real and the environmental stakes are higher than the US:
- **Microsoft** — large campus in Hyderabad (Telangana).
- **Google** — its first India data centre in Vizag, Andhra Pradesh (~$2B announced).
- **AWS** — ~$12.7B committed to India by 2030.
- Plus Reliance (Jamnagar, aiming gigawatt-scale), Adani (AdaniConneX), CtrlS, Yotta.

India's externalities are *worse* than the US on exactly the axes we already score:
- **Power:** the grid is coal-heavy; a hyperscale load in a coal region has a far bigger
  carbon and grid-stability footprint than the same load in Iowa. Renewable-firming is
  harder.
- **Water:** Hyderabad and Chennai have had acute water crises. Evaporative cooling in a
  water-stressed basin is a direct community conflict. This is *the* flashpoint, same as the
  US but sharper — and it's exactly Canopy's InSAR-groundwater wedge (§Wedge 2 in the Canopy
  doc). The water-stress-per-site field is the shared capability.
- **Sound/noise:** generator and chiller noise near dense residential — India's setback and
  zoning enforcement is weaker, so the conflict surfaces *after* build, not before.
- **Land / heat island / e-waste:** urban heat concentration, land-use change, and
  end-of-life hardware disposal are all under-instrumented.

### 9.3 What the India version would fuse (since Mireye can't play)
This is the interesting part — the same five-dimension scorecard, different sources:

| Dimension | US source (what we use now) | India equivalent |
|---|---|---|
| Power | Mireye (EIA/HIFLD grid) | CEA grid data, state DISCOM load, coal vs RE mix (CEA/POSOCO) |
| Water | Mireye `surface_water_supply_use_index_huc12` | **CGWB** groundwater assessment (over-exploited blocks), IMD rainfall, basin stress — *this is Canopy's home turf* |
| Terrain/hazard | Mireye (USGS/FEMA) | Bhuvan / ISRO DEM, CWC flood, BIS seismic zones |
| Air | Mireye (EPA nonattainment) | **CPCB** national air quality, non-attainment cities list (131 cities) |
| Permitting/regulatory | Moratorium Nation | State Pollution Control Board consent-to-establish/operate, EIA notification 2006 clearances, coastal CRZ, forest clearance (FSI) |
| Receptors (noise) | Mireye `housing_units_within_1km` | Census India population grid, built-up from Bhuvan/WorldPop |

Almost all of these are public (CGWB, CPCB, IMD, Bhuvan, Census). None is packaged as a
per-coordinate API — which is *precisely the gap*, and precisely why the Canopy "cited,
timestamped, per-coordinate attestation" primitive is the moat. India has the data siloed
across a dozen government portals in PDFs and dashboards; nobody has fused it into a
go/no-go site screen with provenance.

### 9.4 My honest recommendation on India
1. **For the Mireye submission: stay US.** India can't use their API; mixing it in weakens
   the entry. Ship the US version.
2. **Log India DC environmental screening as a first-class Canopy-adjacent thread** (it's
   already half-logged in the Canopy Decision Log). The verification engine we built is the
   reusable core; the India version is "same engine, Indian data sources." That's a real
   product, a real buyer (Indian hyperscaler siting teams, and the state pollution boards
   themselves), and it uses the InSAR-groundwater capability Canopy is already betting on.
3. **The "protect the environment" framing is genuinely differentiating in India** — not as
   charity, but because *community water conflict is the thing that delays/kills Indian data
   centres*, the same way moratoria do in the US. A screen that says "this Vizag parcel sits
   on an over-exploited CGWB block and 4,000 people live within 1 km" is worth money to the
   developer (avoid the delay) *and* aligns with the community-trust thesis Canopy runs on.
   Same insight as the US Ashburn finding, sharper stakes.

**Bottom line:** don't put India in the Mireye entry. Do treat the India DC environmental
screen as the concrete first application of the Canopy Verification Engine, because that's
what it is — and it's the answer to "how does this weekend move the company forward."

---

## 10. Glossary of the non-obvious bits

- **BFE** — Base Flood Elevation. The height floodwater is expected to reach in a 1%-annual
  (100-year) flood. FEMA reports it in **feet**. Ground elevation is in metres. See BUG 1.
- **SFHA** — Special Flood Hazard Area. FEMA zones starting A or V. Triggers mandatory flood
  insurance on a federally-backed mortgage.
- **Tract GEOID** — 11-digit census identifier, `SS CCC TTTTTT` (state, county, tract).
  First 5 digits = county FIPS. Our OpenFEMA join key. See BUG 4.
- **Moratorium Nation** — GitHub dataset of US local moratoria (data centers, crypto, solar,
  etc.), geocoded, CC-BY-4.0, ~quarterly refresh. 505 of the rows are data-center related.
- **Interconnection queue** — the backlog of projects waiting for grid-connection studies. A
  county already carrying a big queue is competing for the same upgrade capacity.
- **HUC12** — a 12-digit hydrologic unit code; a small watershed. The water-stress index is
  computed per HUC12.
- **Coverage-capped confidence** — our rule that the verdict's confidence can't exceed what
  the evidence coverage supports. 30% of fields returned → LOW confidence, always.

---

## 11. Session 2 — scan, community-benefit, attestation (2026-08-08)

User picked all three proposed directions. Built B → C → A.

### 11.1 New files
| File | LOC | What it does |
|---|---|---|
| `src/output/attestation.py` | ~180 | `Attestation` model + `attest_memo`/`attest_screen`; canonical-JSON sha256 content hash; markdown + JSON renderers. Tamper-evident. |
| `src/clients/osm.py` | ~130 | OpenStreetMap Overpass client for US data centers. UA header + 3 mirror fallbacks; disk cache. |
| `src/scan.py` | ~180 | National scan: batch-screen, rank by stranded viability, emit finding + per-site attestations. |

### 11.2 New models (`models.py`)
- `Lever` — one community-benefit lever (name, strength 0–1, headline, detail, evidence).
- `PathToYes` — summary + list of levers, with `top_lever`.
- `SiteScreen` gained `path_to_yes`, `name`, and the metrics `physical_mean` and
  `stranded_viability` (physical mean − permitting score — the scan's ranking key).

### 11.3 Community-benefit layer (`datacenter.py`)
- `DC_FIELDS` — explicit ~27-field list replacing the 96-field preset (gets `iso_rto` from
  `grid_interconnect`; ~27 credits/site for the scan).
- `compute_path_to_yes(evidence, scores)` — three levers:
  - **Grid flexibility (VPP):** weighted by ISO/RTO market quality (`VPP_MARKET_ISOS`), boosted
    by a crowded county queue and a carbon-heavy grid.
  - **District heat (liquid cooling):** rises with cold climate + housing density + urban
    proximity.
  - **Water offset:** strength rises with basin stress (high-leverage where it's the flashpoint).
- Only computed for actionable (DISPUTED/FLAGGED) verdicts.

### 11.4 Attestation (`output/attestation.py`)
- `attest_screen` / `attest_memo` → `Attestation{content_hash, body, ...}`.
- `verify_integrity()` re-hashes the canonical body; any change breaks it (tested).
- `generated_at` excluded from the hash (wall-clock noise); `issued_at` records mint time.
- PKI signing deferred; `signature`/`signed_by` reserved so it slots in later.

### 11.5 National scan (`scan.py` + `osm.py`)
- `fetch_us_data_centers()` — **1,824 live** US data centers from OSM, cached to
  `data/us_data_centers.json`.
- `run_scan(limit, concurrency, attestation_dir)` — bounded-concurrency batch screen; each
  actionable site emits a content-hashed attestation.
- `render_finding(result, top_n)` — publishable markdown: verdict counts, top-N stranded
  table (with strongest path-to-yes per site), method, honest boundaries.
- CLI: `python -m src.cli scan --limit N --top K` → writes `findings/finding.md`,
  `findings/scan.json`, `findings/attestations/*.{json,md}`.
- CLI: `python -m src.cli dc <loc> --attest out.json` writes a single site's attestation.

### 11.6 Live results (20-site scan, 2026-08-08)
- 1,824 DCs found; 20 screened, 0 failed; 5 DISPUTED, 5 FLAGGED, 10 VERIFIED.
- Top stranded: Google Fiber (0.76), Rack59 (0.72), CoreSite DC1 (0.72) — physically strong,
  permitting ~0.05.
- The "strongest path to yes" column varied by site (VPP / water / heat) — proof the
  community-benefit layer discriminates, not just labels.
- 10/10 attestations verified; tampering a verdict flipped integrity to False.

### 11.7 Bugs fixed this session
- **UTF-8 stdout** — Windows cp1252 console crashed on `→`; forced UTF-8 in CLI.
- **Fixture collision** — both verticals fetch by explicit fields now, colliding on the
  generic `v1_fetch.json`; fixtures re-keyed by rounded coordinate.
- **Water lever inverted** — strength now rises with basin stress (was backwards).

### 11.8 Still open
- OSM tags include university server rooms + a sliver of southern Canada; a production finding
  would filter to named commercial operators.
- Full 1,824-site scan not run (would cost ~1,824 × 27 ≈ 49k credits — inside the Growth
  plan's 120k/mo, but run deliberately, not by reflex).
- PKI signing of attestations (structure reserved, not implemented).

---

## 12. Third vertical — carbon-credit verification (2026-08-08)

Data-center thread closed; brought in a Canopy-thesis wedge that fits the engine.

- **New file:** `src/verticals/carbon.py` (~260 LOC) — `CarbonVertical` implementing the
  `Vertical` protocol.
- **What it checks:** a stated carbon-project claim (reforestation / avoided-deforestation /
  soil-carbon / grassland) against Mireye vegetation ground truth — `lcms_class`,
  `tree_canopy_pct`, `ndvi_current`, **`ndvi_change_5y`**, `cdl_class`, `intersects_wetland`.
- **The crux is additionality.** `ndvi_change_5y` carries it: a reforestation claim over
  mature canopy with no 5-year gain → "the forest appears to predate the project" (the exact
  rice-credit failure). Bare ground → "project may not exist." Avoided-deforestation over
  intact forest → VERIFIED.
- **Wired everywhere:** CLI `carbon` command (+ `--attest`), API `POST /verify/carbon`, web
  third tab. Carbon returns a `VerificationMemo` (same shape as flood), so all three reuse the
  existing renderer; the web form handler was refactored into a shared `wireMemoForm()`.
- **Fixture:** `tests/fixtures/mireye/v1_fetch_47.80_-123.50.json` (Olympic old-growth: 76%
  canopy, "Trees", −0.038 NDVI/5y).
- **Canopy tie:** this is Wedge 1 ("sell attestations TO carbon developers, don't compete"),
  dry-run on US data. Fusion upgrade logged, not built: a Global Forest Watch / registry
  second source.
- **Tests:** 50 total (was 38) — claim parsing, the three verdict paths, wetland flag, offline
  integration.

---

## 13. Carbon fusion — the real second source (2026-08-08)

The carbon vertical was Mireye-only, which failed Mireye's #1 judging line ("what did you
combine us with?"). Fixed by adding an independent second source.

- **Second source: OSM protected-area status** via Overpass `is_in` (keyless). USGS PAD-US
  is the authoritative US source but its ArcGIS endpoints were 502-ing; OSM is stable and
  well-populated for the parks/reserves/wilderness that drive additionality. Cited as OSM.
- **New:** `clients/osm.py` → `protected_areas_at(lat, lng)` + `ProtectedArea` model
  (name, designation, IUCN `protect_class`, `is_strict`).
- **The additionality test:** an avoided-deforestation credit on land *already inside a
  strictly protected area* (national park / IUCN I–IV) fails additionality — the forest was
  protected by law regardless. Live: Olympic point → "already inside Olympic National Park…
  you cannot be paid to prevent a loss that law already prevents." Verdict draws on **6
  sources** (5 Mireye federal + OSM).
- **Architecture change:** `Vertical.gather_external` now takes the `claim` and returns
  `(signals, gaps, discrepancies)` — an independent source contradicting the claim is a
  first-class discrepancy, not just context. Agent merges external discrepancies with
  `compare()`'s. Flood updated to the new signature (returns no external discrepancies).
- **Testable + graceful:** `CarbonVertical(protected_areas_fn=…)` is injectable, so tests
  never hit the network; a live lookup failure is declared as a retryable data gap, not
  swallowed. Tests: 52 total (was 50), incl. the fusion path and the graceful-degradation path.
- **GFW note:** Global Forest Watch tree-cover-loss (actual deforestation pixels) needs a free
  API key (403 keyless); logged as the optional keyed upgrade, not built.

---

## 14. Canopy brand: generated artwork, logo, plates (2026-08-08/09)

Rebranded the demo from "Verification Agent" to **Canopy**, with all imagery generated
rather than sourced (the Dribbble references are other people's artwork).

### 14.1 `scripts/make_art.py`
One reproducible script produces every asset. A real halftone screen — one dot per cell,
radius tracking local darkness, supersampled then downscaled — is applied over procedural
fields. Output: `web/img/*.png` + `logo.svg`.

### 14.2 The plates had to become real structures
The first set halftoned raw noise fields and looked, correctly, like random noise. Each
was rebuilt as an actual structure, then screened:

| Plate | Method |
|---|---|
| Terrain | Contour **lines**: elevation crossings divided by local gradient so line width stays even; every 5th is a heavier index line |
| Canopy cover | Individual crowns drawn as circles, clustered by a density field so stands and clearings emerge |
| Watershed | Priority-flood pit filling → steepest-descent routing → flow accumulation → threshold on catchment size |
| Parcels | Recursive BSP subdivision with off-centre splits, varied lot tones |

Screen also went finer for the plates (`cell=3, scale=5`): at `cell=5` the dot lattice
swallowed contour lines and channel threads, which is *why* the first set read as noise.

### 14.3 The watershed took four passes — worth recording
1. Thresholded ridged noise → blobs, no connectivity.
2. Flow accumulation on a gently tilted surface → scattered fragments (flow dies in local pits).
3. Steep regional tilt to escape the pits → parallel vertical streaks, since every cell then
   drains straight down and nothing converges.
4. **Priority-flood pit filling + noise-dominant surface** → genuine dendritic network.
   Threshold also moved from 0.33 to 0.56 of the log range: at 0.33 a cell needs only ~38
   upstream cells to qualify, so nearly every cell did and the frame filled with texture.

### 14.4 Hero plate
A forested horizon built like a screen print: flat tonal ridges painted front-over-back with
mist pooling under each crest. Two earlier failures are documented in §13 of this file
(gradient-instead-of-landscape, and the inverted `freq` parameter).

### 14.5 Logo — four attempts, all association failures
Rendered at 160/64/28/16px and inverted each time; the small sizes are where marks break.
1. Three overlapping crowns → **cloud**. Also a silent bug: `fill-rule="evenodd"` resolves
   within a single path, never across sibling `<circle>` elements, so the intended
   negative-space knockout never happened and it rendered as a solid blob.
2. Nested arcs + dot → **upside-down wifi**.
3. Concentric contour rings → topographic at 160px, **eye** at 16px.
4. **Two angular ridge lines** → terrain. Shipped. Smooth parallel curves read as the water
   glyph, so angular peaks and two lines (not three) were both necessary.

### 14.6 Plate hover interaction
Pointer-driven parallax: `scale(1.09)` plus up to 9px of translation opposite the cursor,
110ms while tracking, 620ms eased return on leave. Transform only (compositor-friendly);
disabled under `prefers-reduced-motion`; rect cached on `pointerenter` to avoid layout
thrash from read/write interleaving.

### 14.7 Bugs fixed
- **`.plate` had zero width.** `<figure>` carries a UA default margin of `1em 40px`; 80px per
  column collapsed the grid tracks. Symptom was subtle — the parallax silently did nothing,
  because a zero-size rect makes the offsets NaN and `translate(NaNpx)` is dropped by the CSS
  parser with no error. Fixed with `margin: 0`, plus a guard in the handler.
- **`index.html` served from cache** during development — spent a cycle debugging markup that
  was no longer on disk. Added `Cache-Control: no-store` to the index route.
- **Hero CTA clipped** at short viewports (`overflow: hidden` + inline-block baseline + no
  bottom padding).

---

## 15. Campus dedupe + shareable attestation surface (2026-08-09)

Two product-hardening pieces after the full scan landed.

### 15.1 Campus rollup (`src/scan.py`)
1,814 OSM buildings → **1,154 campuses**. Operator normalization (`_ALIASES` +
first-token) then within-operator greedy spatial clustering at 4 km. Unnamed OSM features
stay singletons labelled "Unnamed data center". Campus-level verdicts: 500 disputed (43%),
541 verified, 113 flagged — the honest headline (building counts triple-count campuses;
135 "Amazon Web Services" rows were one operator). `finding.md` now ranks campuses with
building counts; `campuses.json` added. Regenerated from the existing `scan.json` — no
re-billing.

### 15.2 Shareable attestation surface
The difference between a demo and a product: a verdict you can send someone.
- `src/output/store.py` — save/load attestations to `data/attestations/{id}.json`; id = first
  12 hex of the content hash. Path-traversal guarded (`isalnum`). Thin interface so Postgres/S3
  is a one-file swap.
- `src/output/attestation_page.py` — renders a standalone Canopy-styled page.
- API: `/verify/*` and `/screen/*` now persist + return `attestation_id`; `GET /a/{id}` (HTML)
  and `GET /a/{id}.json` (raw) added. `attestation_id` added to `VerificationMemo`/`SiteScreen`,
  **excluded from the hash** (it's derived *from* the hash — can't be an input to it).
- Web UI shows a "Attestation /a/{id} → · raw JSON" link under every result.

### 15.3 The self-verify bug worth remembering
First cut re-canonicalised the body in JS and sha256'd it — it falsely reported **TAMPERED**
on an untouched record. Two cross-language divergences from Python's `json.dumps`:
1. **Non-ASCII escaping** — Python (`ensure_ascii=True`) emits `\u2014` for the em-dashes all
   over our reasoning text; JS `JSON.stringify` keeps them raw.
2. **Float formatting** — Python renders `1.0`, JS renders `1`.
Fix: embed the *exact* canonical string the server hashed and sha256 **that** in the browser —
identical bytes can't drift, yet a real body edit still breaks the match (stored hash no longer
matches the string). Both branches verified live (✓ Intact and ✗ Tampered). Tests: 55 (was 52).

---

## 16. Portfolio batch verification + demo runbook + Orchestra note (2026-08-10)

Autonomous session — kicked off after the map polish, before the submission deadline.

### 16.1 Portfolio (batch) verification
A fourth tab on the demo: paste `vertical | location | claim` lines, and Canopy fans them
out through the existing `/verify/*` and `/screen/*` endpoints with bounded client-side
parallelism (default 4 workers). Results stream into a live table with progress meter, per-
row verdict badges, tinted rows by verdict, and an attestation link on every completed row.

Deliberately client-side: the existing endpoints already do everything a batch call would,
and adding a new server endpoint would just duplicate that logic (plus add its own tests,
its own error handling, its own timeouts). One pool of workers reading `/verify/*` in the
browser is smaller, safer, and equally observable. Verified live end-to-end (3-row batch,
Ashburn/Denver/Galveston, cached-warm — all three rows landed with attestation links).

### 16.2 Demo runbook (`docs/DEMO_RUNBOOK.md`)
Scripted four-beat live demo (macro map → live vertical → attestation tamper → batch
portfolio), ~2 minutes total. Includes the two-command cache warm-up, per-beat talking
points, and a contingency table for common failure modes.

### 16.3 Orchestra fit note (`docs/ORCHESTRA_SUBMISSION.md`)
Written after research on Untrivial's Agent Orchestrator hackathon (Aug 12–13). AO is a
desktop app supervising parallel coding agents via git worktrees — a *dev workspace*, not a
protocol to integrate against. Orchestra's judging is "ship something real, no theme, no
limits," so Canopy submits as-is; the note explains the fit (three verticals as parallel-
agent work, `src/scan.py`'s checkpoint/resume as a literal instance of nick_realm's
"stateful continuity for stateless MCP" thesis) and is honest that the project pre-dates
the hackathon announcement.

Test count: **55** (unchanged; the batch tab is pure JS orchestration over the tested
endpoints, so no new tests are meaningful).

---

## 17. Resume-scan UI, map tour, attestation share (2026-08-10, session 5)

The three features originally scoped for an AO parallel-agent pass (see
`AO_SESSION_PROMPTS.md`). AO was skipped; built directly on `main` instead.

### 17.1 Resumable-state demo (`/scan/resume-ui`) — commit `795c0e0`
Makes the scan's checkpoint/resume mechanism clickable. New endpoints in `api/server.py`:
`GET /scan/state` (reads a demo checkpoint, returns completed/remaining/total), `POST
/scan/resume-demo` (genuinely calls `run_scan(limit=completed+5, concurrency=2,
checkpoint=demo-checkpoint.jsonl)` — real screening, appends the next 5), `POST
/scan/reset-demo`, and the page route. The **+5 batch is server-fixed and hard-capped** so
nothing the client sends can trigger a full paid scan, and it never touches the real
`findings/checkpoint.jsonl`. Verified live: reset→0, resume→5 real sites, second resume→5
*different* sites (genuine continuity, not re-screening). This is the project's most direct
expression of the Orchestra "stateful continuity for stateless MCP" thesis.

### 17.2 Guided story tour on `/map` — commit `4a9c0da`
Four numbered narrator pins (Ashburn/Columbus/Phoenix/Council Bluffs, same coords as the DC
demo examples) with a panel telling each market's story from the finding. Start button +
Prev/Next + keys 1–4 + arrows + Esc. Focusing a stop dims the campus dots, colours the number
by verdict, and pulses a ring (reduced-motion aware). Base map unchanged until you start.
Pure client-side, no backend route.

### 17.3 Shareable attestation links — commit `77d5d54`
OG + Twitter Card meta on the attestation page (title = kind + verdict, description = verdict
reasoning), so a pasted `/a/{id}` previews richly. Copy-link button (clipboard + confirmation)
and a verdict-aware Share-on-X intent (tweet text server-computed, page URL assembled in the
browser). `page_meta()` / `_tweet_text()` live in `attestation_page.py` and degrade gracefully
when a verdict has no reasoning. 4 new tests.

Test count: **59** (was 55).
