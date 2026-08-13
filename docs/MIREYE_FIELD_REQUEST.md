# Field request to Mireye — `nearest_enacted_moratorium`

A drafted field request, ready to send through Mireye's feedback / field-request channel.
Writing it is the point: building on Mireye hard enough to find the one field that would have
saved us an entire external integration is the strongest evidence of real product use.

## The gap we hit

Building the data-center siting vertical, Mireye answered every *physical* question cleanly —
slope, flood zone, substation distance, voltage class, interconnection queue. But the question
that actually kills data-center projects today is **regulatory, not physical**: is there an
enacted local moratorium near this site?

Mireye has no field for it. We had to fuse an external, community-maintained dataset
(Moratorium Nation — 505 geocoded local bans) to answer it. That fusion became the sharpest
finding in our whole submission (43% of US data-center campuses are "stranded" — physically
viable, permitting-blocked). It would be materially stronger as a first-class Mireye field
with Mireye's provenance guarantees behind it.

## Proposed field

Matching Mireye's own field schema (`value`, `unit`, `source`, `source_url`, `confidence`,
`fetched_at`, `dataset_vintage`):

```
name:            nearest_enacted_moratorium_km
type:            float
unit:            kilometers
description:     Distance to the nearest enacted local moratorium, ban, or restrictive
                 ordinance affecting data-center / large-load development.
presets:         data_center_siting, grid_interconnect
source:          (curated legislative tracker — see note)
confidence:      medium   # ordinances are noisy; vintage matters a lot here

companion fields (same query, so they return together):
  nearest_enacted_moratorium_name       string   e.g. "Loudoun County BOS 2024-11 moratorium"
  nearest_enacted_moratorium_status     string    enacted | pending | expired | extended
  nearest_enacted_moratorium_jurisdiction  string   the county/municipality
  active_moratoria_within_80km_count    int
```

## Why it fits Mireye specifically

- It's **federal/public-record adjacent** — county board minutes, municipal ordinances, state
  bills — which matches Mireye's cited-source ethos, just at the local-government layer instead
  of the USGS/FEMA/NOAA layer.
- It slots into an existing preset (`data_center_siting`) that already answers the physical
  half of the siting question. This closes the loop: Mireye could answer "is this site good
  **and** will it get permitted?" in one call.
- It carries real freshness risk (ordinances change quarterly), which is exactly the kind of
  thing Mireye's `dataset_vintage` + `confidence` model is built to express honestly.

## What it would change for us

Our data-center vertical would drop its Moratorium Nation dependency and read this field
directly — same finding, one fewer source to maintain, and Mireye's provenance on the
regulatory signal instead of a community CSV. The national scan (`src/scan.py`) would get it
for free on every site.

---

*Adjacent smaller asks we noticed while building (lower priority):*

- `fema_flood_zone` lives in the `data_center_siting` preset but not `flood_risk`, and
  `fema_base_flood_elevation` is in no preset at all — so a flood check has to name fields
  explicitly. Adding both to `flood_risk` would make the obvious preset the correct one.
- A boolean `intersects_protected_area` (PAD-US / IUCN) would let a carbon-additionality check
  avoid an OSM Overpass round-trip.
