"""Data-center site screening: physical viability from Mireye, permitting risk from
local moratoria.

Buyer: site-selection teams at land developers. A 60 MW facility loses roughly
$14.2M per month of delay, and the moratorium that kills a site is usually passed
by a county nobody screened for.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.clients.mireye import MireyeClient
from src.clients.moratoria import MoratoriaClient, Moratorium
from src.models import (
    Confidence,
    Coordinate,
    DataGap,
    Evidence,
    Lever,
    PathToYes,
    Severity,
    Signal,
    SiteScore,
    SiteScreen,
    Verdict,
    VerdictKind,
)

# A curated field list, not the 96-field preset. Every field here maps to a score or a
# community-benefit lever, and the slim set keeps a national batch scan affordable
# (~27 credits/site vs 96). iso_rto lives in grid_interconnect, not data_center_siting,
# so an explicit list is the only way to get it alongside the siting fields.
DC_FIELDS = [
    # terrain
    "slope_degrees",
    "elevation",
    # power proximity
    "nearest_substation_distance_m",
    "nearest_substation_max_voltage_kv",
    "nearest_substation_status",
    "transmission_lines_within_radius_count",
    "interconnection_queue_active_capacity_county_mw",
    "grid_price_usd_per_mwh",
    # hazard
    "within_floodplain_polygon",
    "fema_flood_zone",
    "intersects_wetland",
    "drought_category",
    # externalities
    "surface_water_supply_use_index_huc12",
    "in_air_quality_nonattainment",
    "air_quality_nonattainment_pollutants",
    "housing_units_within_1km",
    "public_water_system_population_served",
    # path-to-yes: grid flexibility / VPP
    "iso_rto",
    "egrid_co2_output_rate_kg_per_mwh",
    # path-to-yes: district heat
    "mean_annual_dry_bulb_temperature_degc",
    "days_above_32c_annual_count",
    "housing_units_density_per_km2",
    "nearest_urban_area_distance_m",
    # path-to-yes: water offset
    "huc12_thermoelectric_consumptive_use_m3_per_day",
    "nearest_groundwater_well_depth_to_water_m",
]

PRESET = "data_center_siting"

# Thresholds are screening heuristics, not engineering criteria — they decide what
# to look at next, not what to build.
SLOPE_IDEAL_DEG = 3.0
SLOPE_MAX_DEG = 10.0
TRANSMISSION_NEAR_M = 1_500
TRANSMISSION_FAR_M = 10_000
SUBSTATION_NEAR_M = 5_000
SUBSTATION_FAR_M = 20_000
HV_THRESHOLD_KV = 230

SFHA_PREFIXES = ("A", "V")


def _get(evidence: list[Evidence], *names: str) -> Evidence | None:
    for name in names:
        for item in evidence:
            if item.field == name:
                return item
    return None


def _num(evidence: list[Evidence], *names: str) -> float | None:
    found = _get(evidence, *names)
    if found is None:
        return None
    try:
        return float(found.value)
    except (TypeError, ValueError):
        return None


def _band(value: float, good: float, bad: float) -> float:
    """Linear score in [0,1]; 1.0 at or below `good`, 0.0 at or above `bad`."""
    if value <= good:
        return 1.0
    if value >= bad:
        return 0.0
    return 1.0 - (value - good) / (bad - good)


def score_terrain(evidence: list[Evidence]) -> SiteScore:
    slope = _num(evidence, "slope_degrees", "slope")
    used = [e for e in (_get(evidence, "slope_degrees", "slope"), _get(evidence, "elevation")) if e]

    if slope is None:
        return SiteScore(
            dimension="Terrain",
            score=0.5,
            rationale="Slope did not resolve; terrain buildability unscored.",
            evidence=used,
        )

    score = _band(slope, SLOPE_IDEAL_DEG, SLOPE_MAX_DEG)
    if slope <= SLOPE_IDEAL_DEG:
        rationale = f"{slope:.1f}° slope — flat enough for slab-on-grade with minimal earthwork."
    elif slope <= SLOPE_MAX_DEG:
        rationale = f"{slope:.1f}° slope — buildable, but grading cost rises with pad size."
    else:
        rationale = f"{slope:.1f}° slope — steep; earthwork likely dominates site prep cost."

    return SiteScore(dimension="Terrain", score=score, rationale=rationale, evidence=used)


def score_power(evidence: list[Evidence]) -> SiteScore:
    """Power is the binding constraint. Proximity is a weak proxy for deliverability,
    so the queue depth — when the catalog has it — carries more weight than distance."""
    sub_m = _num(evidence, "nearest_substation_distance_m")
    kv = _num(evidence, "nearest_substation_max_voltage_kv")
    line_count = _num(evidence, "transmission_lines_within_radius_count")
    queue_mw = _num(evidence, "interconnection_queue_active_capacity_county_mw")

    used = [
        e
        for e in (
            _get(evidence, "nearest_substation_distance_m"),
            _get(evidence, "nearest_substation_max_voltage_kv"),
            _get(evidence, "nearest_substation_status"),
            _get(evidence, "transmission_lines_within_radius_count"),
            _get(evidence, "interconnection_queue_active_capacity_county_mw"),
            _get(evidence, "grid_price_usd_per_mwh"),
        )
        if e
    ]

    parts: list[float] = []
    notes: list[str] = []

    if sub_m is not None:
        parts.append(_band(sub_m, SUBSTATION_NEAR_M, SUBSTATION_FAR_M))
        notes.append(f"substation {sub_m:,.0f} m")
    if kv is not None:
        parts.append(1.0 if kv >= HV_THRESHOLD_KV else 0.45)
        notes.append(f"{kv:.0f} kV")
    if line_count is not None:
        # Redundancy matters: one line is a single point of failure.
        parts.append(1.0 if line_count >= 2 else 0.6 if line_count == 1 else 0.2)
        notes.append(f"{line_count:.0f} transmission line(s) in radius")

    if not parts:
        return SiteScore(
            dimension="Power proximity",
            score=0.5,
            rationale="No grid fields resolved; power proximity unscored.",
            evidence=used,
        )

    score = sum(parts) / len(parts)

    if queue_mw is not None:
        # A county already carrying a large active queue is competing for the same
        # upgrade capacity this project would need.
        notes.append(f"{queue_mw:,.0f} MW active in the county queue")
        if queue_mw > 5_000:
            score *= 0.75
        elif queue_mw > 1_000:
            score *= 0.9

    rationale = (
        f"{', '.join(notes)}. Proximity and queue volume only — actual deliverability "
        "depends on a study this screen does not run."
    )
    return SiteScore(
        dimension="Power proximity", score=min(1.0, score), rationale=rationale, evidence=used
    )


def score_hazard(evidence: list[Evidence]) -> SiteScore:
    zone_ev = _get(evidence, "fema_flood_zone", "flood_zone")
    floodplain_ev = _get(evidence, "within_floodplain_polygon")
    wetland_ev = _get(evidence, "intersects_wetland", "wetland_intersect")
    drought_ev = _get(evidence, "drought_category")
    used = [e for e in (zone_ev, floodplain_ev, wetland_ev, drought_ev) if e]

    score = 1.0
    notes: list[str] = []

    if floodplain_ev is not None and bool(floodplain_ev.value):
        score -= 0.6
        zone = str(zone_ev.value).upper().strip() if zone_ev else "unmapped"
        notes.append(f"inside a FEMA Special Flood Hazard Area (Zone {zone})")
    elif zone_ev is not None:
        zone = str(zone_ev.value).upper().strip()
        if zone.startswith(SFHA_PREFIXES) and zone != "AREA NOT INCLUDED":
            score -= 0.6
            notes.append(f"Zone {zone} is a Special Flood Hazard Area")
        else:
            notes.append(f"Zone {zone}, outside the mapped floodplain")

    if wetland_ev is not None and bool(wetland_ev.value):
        score -= 0.3
        notes.append("wetland intersect triggers USACE Section 404 permitting")

    return SiteScore(
        dimension="Hazard & wetlands",
        score=max(0.0, score),
        rationale="; ".join(notes) or "No hazard fields resolved.",
        evidence=used,
    )


def score_externalities(evidence: list[Evidence]) -> SiteScore:
    """Water, air, and neighbours — the three things that turn a physically fine
    site into a contested one. This is the layer the opposition actually organises on."""
    water_ev = _get(evidence, "surface_water_supply_use_index_huc12")
    air_ev = _get(evidence, "in_air_quality_nonattainment")
    housing_ev = _get(evidence, "housing_units_within_1km")
    used = [
        e
        for e in (
            water_ev,
            air_ev,
            housing_ev,
            _get(evidence, "air_quality_nonattainment_pollutants"),
            _get(evidence, "public_water_system_population_served"),
        )
        if e
    ]

    parts: list[float] = []
    notes: list[str] = []

    water = _num(evidence, "surface_water_supply_use_index_huc12")
    if water is not None:
        # The index rises with the share of available supply already withdrawn.
        parts.append(_band(water, 0.2, 0.8))
        notes.append(f"basin water-use index {water:.2f}")

    if air_ev is not None:
        nonattainment = bool(air_ev.value)
        parts.append(0.3 if nonattainment else 1.0)
        pollutants = _get(evidence, "air_quality_nonattainment_pollutants")
        if nonattainment:
            detail = f" ({pollutants.value})" if pollutants else ""
            notes.append(f"air-quality nonattainment area{detail} — genset permitting is harder")
        else:
            notes.append("in attainment for criteria pollutants")

    housing = _num(evidence, "housing_units_within_1km")
    if housing is not None:
        # Noise complaints need complainants; housing within 1 km is the proxy.
        parts.append(_band(housing, 50, 2_000))
        notes.append(f"{housing:,.0f} housing units within 1 km")

    if not parts:
        return SiteScore(
            dimension="Externalities",
            score=0.5,
            rationale="No water, air, or receptor fields resolved.",
            evidence=used,
        )

    return SiteScore(
        dimension="Externalities",
        score=sum(parts) / len(parts),
        rationale="; ".join(notes),
        evidence=used,
    )


def score_regulatory(nearby: list[Moratorium], radius_km: float) -> tuple[SiteScore, list[Signal]]:
    """The layer Mireye does not have: who nearby has already said no."""
    now = datetime.now(timezone.utc)
    blocking = [m for m in nearby if m.is_blocking]
    signals: list[Signal] = []

    for m in blocking[:5]:
        weight = (
            Severity.CRITICAL
            if m.distance_km <= 25
            else Severity.MAJOR
            if m.distance_km <= 60
            else Severity.MINOR
        )
        window = f", enacted {m.date_enacted}" if m.date_enacted else ""
        signals.append(
            Signal(
                label=f"{m.jurisdiction}, {m.state} ({m.jurisdiction_type})",
                detail=(
                    f"{m.enacted_status.title()} data-center moratorium "
                    f"{m.distance_km:.0f} km away{window}"
                    + (f". Term: {m.duration}" if m.duration else "")
                ),
                source="MORATORIUM_NATION_2026",
                source_url="https://github.com/mjbommar/moratorium-data-2026",
                fetched_at=now,
                weight=weight,
            )
        )

    if not blocking:
        return (
            SiteScore(
                dimension="Permitting risk",
                score=1.0,
                rationale=f"No active data-center moratoria within {radius_km:.0f} km.",
            ),
            signals,
        )

    nearest = blocking[0]
    # A neighbouring jurisdiction that has already banned data centers is the
    # strongest available leading indicator that this one will be asked to.
    if nearest.distance_km <= 25:
        score, verdict_note = 0.15, "immediately adjacent"
    elif nearest.distance_km <= 60:
        score, verdict_note = 0.4, "in the same metro"
    else:
        score, verdict_note = 0.65, "in the wider region"

    score = max(0.05, score - 0.05 * (len(blocking) - 1))

    return (
        SiteScore(
            dimension="Permitting risk",
            score=score,
            rationale=(
                f"{len(blocking)} active moratori{'um' if len(blocking) == 1 else 'a'} "
                f"within {radius_km:.0f} km; nearest is {nearest.jurisdiction}, "
                f"{nearest.state} at {nearest.distance_km:.0f} km ({verdict_note})."
            ),
        ),
        signals,
    )


def _verdict(scores: list[SiteScore], coverage: float) -> Verdict:
    regulatory = next((s for s in scores if s.dimension == "Permitting risk"), None)
    physical = [s for s in scores if s.dimension != "Permitting risk"]
    physical_mean = sum(s.score for s in physical) / len(physical) if physical else 0.5

    confidence = (
        Confidence.HIGH if coverage >= 0.8
        else Confidence.MEDIUM if coverage >= 0.5
        else Confidence.LOW
    )

    reg_score = regulatory.score if regulatory else 1.0

    if reg_score <= 0.25:
        return Verdict(
            kind=VerdictKind.DISPUTED,
            confidence=confidence,
            reasoning=(
                f"Physical viability scores {physical_mean:.2f}, but permitting risk is "
                f"severe: {regulatory.rationale if regulatory else ''} "
                "Treat this site as high-risk before spending diligence dollars."
            ),
        )
    if reg_score <= 0.6 or physical_mean < 0.5:
        return Verdict(
            kind=VerdictKind.FLAGGED,
            confidence=confidence,
            reasoning=(
                f"Physical viability {physical_mean:.2f}, permitting risk {reg_score:.2f}. "
                "Site is worth pursuing but carries a named risk to resolve early."
            ),
        )
    return Verdict(
        kind=VerdictKind.VERIFIED,
        confidence=confidence,
        reasoning=(
            f"Physical viability {physical_mean:.2f} with no active moratoria nearby. "
            "Clears first-pass screening; confirm interconnection queue position next."
        ),
    )


# ISOs/RTOs with real capacity or demand-response markets a data-center-funded VPP can
# actually be paid through. Non-market West/Southeast utilities are vertically integrated
# with far fewer mechanisms — flexibility there is harder to monetize.
VPP_MARKET_ISOS = {
    "PJM": 1.0,
    "CAISO": 1.0,
    "ISONE": 0.95,
    "ISO-NE": 0.95,
    "NYISO": 0.9,
    "MISO": 0.85,
    "SPP": 0.75,
    "ERCOT": 0.85,  # energy-only, but strong ADER/DR growth
}

# District-heat capture from liquid cooling only pencils where it's cold enough to want
# heat and dense enough to deliver it economically.
HEAT_COLD_CLIMATE_DEGC = 12.0  # mean annual dry-bulb below this → real heating season


def _iso_label(evidence: list[Evidence]) -> tuple[str | None, float]:
    iso_ev = _get(evidence, "iso_rto")
    if iso_ev is None or not iso_ev.value:
        return None, 0.6  # unknown market — assume a middling opportunity
    key = str(iso_ev.value).upper().replace("_", "").replace(" ", "")
    for name, weight in VPP_MARKET_ISOS.items():
        if name.replace("-", "") == key or name == str(iso_ev.value).upper():
            return str(iso_ev.value), weight
    return str(iso_ev.value), 0.5


def compute_path_to_yes(evidence: list[Evidence], scores: list[SiteScore]) -> PathToYes:
    """Reframe a contested site from go/no-go to negotiation: what community-benefit
    package would plausibly move it toward a yes. Three levers, honestly hedged."""
    levers: list[Lever] = []

    # --- Lever 1: grid flexibility / VPP funding ---
    iso_name, iso_weight = _iso_label(evidence)
    queue_mw = _num(evidence, "interconnection_queue_active_capacity_county_mw")
    co2 = _num(evidence, "egrid_co2_output_rate_kg_per_mwh")
    flex_ev = [
        e for e in (
            _get(evidence, "iso_rto"),
            _get(evidence, "interconnection_queue_active_capacity_county_mw"),
            _get(evidence, "egrid_co2_output_rate_kg_per_mwh"),
        ) if e
    ]
    # A crowded queue *raises* the value of funding flexibility — the site can't just
    # take grid capacity, so buying down community flexibility is the faster path.
    queue_boost = 0.15 if (queue_mw or 0) > 1_000 else 0.0
    flex_strength = min(1.0, iso_weight + queue_boost)
    where = f"in {iso_name}" if iso_name else "in this region"
    dirty = co2 is not None and co2 > 350
    levers.append(
        Lever(
            name="Grid flexibility (VPP)",
            strength=flex_strength,
            headline=(
                f"Fund distributed flexible capacity {where} instead of waiting on the queue"
                + (" — and cut load on a carbon-heavy grid" if dirty else "")
            ),
            detail=(
                f"{iso_name or 'The local market'} "
                + ("has a capacity/DR market a data-center-funded VPP can be paid through. "
                   if iso_weight >= 0.75 else
                   "has limited market mechanisms for paid flexibility; structure carefully. ")
                + (f"The county already carries {queue_mw:,.0f} MW of active queue, so new "
                   "generation is slow — funded flexibility (batteries, demand response) is "
                   "the faster route to firm power and a community benefit at once."
                   if queue_mw else
                   "Funded flexibility doubles as bill relief and grid resilience for residents.")
            ),
            evidence=flex_ev,
        )
    )

    # --- Lever 2: district heat from liquid cooling ---
    temp = _num(evidence, "mean_annual_dry_bulb_temperature_degc")
    housing = _num(evidence, "housing_units_within_1km")
    urban_m = _num(evidence, "nearest_urban_area_distance_m")
    heat_ev = [
        e for e in (
            _get(evidence, "mean_annual_dry_bulb_temperature_degc"),
            _get(evidence, "housing_units_within_1km"),
            _get(evidence, "nearest_urban_area_distance_m"),
        ) if e
    ]
    heat_strength = 0.0
    if temp is not None:
        # Colder = stronger heating case; scale 0 at 18°C to 1 at 4°C.
        heat_strength = _band(temp, HEAT_COLD_CLIMATE_DEGC, 18.0) * 0.5 + 0.5 * _band(temp, 4.0, 12.0)
    if housing is not None and housing > 500:
        heat_strength = min(1.0, heat_strength + 0.2)
    if urban_m is not None and urban_m < 3_000:
        heat_strength = min(1.0, heat_strength + 0.1)
    if temp is None:
        heat_strength = 0.3
    heat_fit = (
        "strong" if heat_strength >= 0.7 else "plausible" if heat_strength >= 0.4 else "weak"
    )
    levers.append(
        Lever(
            name="District heat (liquid cooling)",
            strength=round(heat_strength, 2),
            headline=(
                "Switch to liquid cooling and pipe waste heat to nearby homes/facilities"
                if heat_strength >= 0.4 else
                "Waste-heat reuse is a weak fit here (warm climate or sparse demand)"
            ),
            detail=(
                f"District-heat fit is {heat_fit}: "
                + (f"mean annual temperature {temp:.1f}°C" if temp is not None else "climate unknown")
                + (f", {housing:,.0f} homes within 1 km" if housing is not None else "")
                + (f", nearest urban area {urban_m:,.0f} m away." if urban_m is not None else ".")
                + " Liquid cooling also sharply cuts the water draw that drives opposition."
            ),
            evidence=heat_ev,
        )
    )

    # --- Lever 3: water offset ---
    water = _num(evidence, "surface_water_supply_use_index_huc12")
    thermo = _num(evidence, "huc12_thermoelectric_consumptive_use_m3_per_day")
    water_ev = [
        e for e in (
            _get(evidence, "surface_water_supply_use_index_huc12"),
            _get(evidence, "huc12_thermoelectric_consumptive_use_m3_per_day"),
            _get(evidence, "nearest_groundwater_well_depth_to_water_m"),
        ) if e
    ]
    # Strength = leverage as a path-to-yes, which *rises* with basin stress: in a stressed
    # basin the offset addresses the actual flashpoint; in a wet basin it's cheap goodwill
    # that buys little. (Not to be confused with cost, which moves the opposite way.)
    if water is not None:
        water_strength = min(1.0, 0.3 + water)
        stress = "high" if water > 0.6 else "moderate" if water > 0.3 else "low"
        headline = (
            f"Commit a water offset in a {stress}-stress basin — the flashpoint that kills siting"
            if water > 0.3 else
            "Commit a water offset (basin is not stressed, so this is cheap goodwill)"
        )
        detail = (
            f"Basin water-use index {water:.2f} ({stress} stress). "
            "Pair a metered offset commitment with low-/no-water cooling; this is the "
            "single most opposition-relevant benefit in water-short regions."
        )
    else:
        water_strength = 0.4
        headline = "Offer a water-offset commitment (basin stress not resolved here)"
        detail = "Water-stress index did not resolve; treat a metered offset as table stakes."
    levers.append(
        Lever(
            name="Water offset",
            strength=round(water_strength, 2),
            headline=headline,
            detail=detail,
            evidence=water_ev,
        )
    )

    top = max(levers, key=lambda l: l.strength)
    summary = (
        f"This site is contested, not dead. The strongest lever toward a yes is "
        f"'{top.name.lower()}' — {top.headline.lower()}. A structured community-benefit "
        "package built on the levers below is the fastest path from a no to a permitted site."
    )
    return PathToYes(summary=summary, levers=levers)


async def screen_site(
    mireye: MireyeClient,
    coordinate: Coordinate,
    *,
    radius_km: float = 80.0,
    moratoria: MoratoriaClient | None = None,
    name: str | None = None,
) -> SiteScreen:
    evidence, gaps = await mireye.fetch(coordinate.lat, coordinate.lng, fields=DC_FIELDS)

    client = moratoria or MoratoriaClient()
    try:
        nearby = client.find_nearby(coordinate.lat, coordinate.lng, radius_km=radius_km)
    except Exception as exc:  # network or cache failure — declare it, don't hide it
        nearby = []
        gaps.append(
            DataGap(
                field="moratoria",
                reason=f"moratorium inventory unavailable: {exc}",
                source="MORATORIUM_NATION_2026",
                retryable=True,
            )
        )

    regulatory_score, signals = score_regulatory(nearby, radius_km)
    scores = [
        score_power(evidence),
        score_terrain(evidence),
        score_hazard(evidence),
        score_externalities(evidence),
        regulatory_score,
    ]

    requested = len(evidence) + len(gaps)
    coverage = len(evidence) / requested if requested else 0.0
    verdict = _verdict(scores, coverage)

    # The path-to-yes only makes sense for a site that has a "no" to overcome. A clean
    # VERIFIED site doesn't need a benefit package to get built.
    path_to_yes = (
        compute_path_to_yes(evidence, scores) if verdict.is_actionable else None
    )

    return SiteScreen(
        location=coordinate,
        name=name,
        scores=scores,
        signals=signals,
        evidence=evidence,
        data_gaps=gaps,
        verdict=verdict,
        path_to_yes=path_to_yes,
    )
