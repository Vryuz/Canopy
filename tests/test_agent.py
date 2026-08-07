"""Tests for the verification loop and the two verticals."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.agent import _decide
from src.clients.mireye import MireyeClient
from src.clients.moratoria import Moratorium, haversine_km
from src.models import (
    Confidence,
    Coordinate,
    Discrepancy,
    Evidence,
    Severity,
    Signal,
    VerdictKind,
)
from src.verticals.datacenter import score_hazard, score_power, score_regulatory, score_terrain
from src.verticals.flood import FloodVertical


def _evidence(field: str, value, source: str = "TEST", unit: str | None = None) -> Evidence:
    return Evidence(
        field=field,
        value=value,
        source=source,
        unit=unit,
        fetched_at=datetime.now(timezone.utc),
    )


def _moratorium(distance_hint: float, status: str = "active", **kwargs) -> Moratorium:
    return Moratorium(
        moratorium_id=kwargs.get("id", "m1"),
        state=kwargs.get("state", "MD"),
        jurisdiction=kwargs.get("jurisdiction", "Test County"),
        jurisdiction_type="County",
        enacted_status=status,
        date_enacted="2026-01-01",
        duration="12 months",
        sectors=["data_center"],
        lat=0.0,
        lng=0.0,
        distance_km=distance_hint,
    )


# ------------------------------------------------------------------- claim parsing


@pytest.mark.parametrize(
    "text,expected",
    [
        ("not in a flood zone", "NOT_IN_SFHA"),
        ("Seller states the property is not located in a flood zone", "NOT_IN_SFHA"),
        ("the listing says Zone X", "X"),
        ("policy lists this as Zone AE", "AE"),
        ("property is free of flood risk", "NOT_IN_SFHA"),
    ],
)
def test_parses_flood_claims(text, expected):
    assert FloodVertical().parse_claim(text).asserted_value == expected


def test_unparseable_claim_has_no_assertion():
    assert FloodVertical().parse_claim("looks nice").asserted_value is None


# ----------------------------------------------------------------------- comparison


def test_denial_of_flood_risk_in_sfha_is_critical():
    vertical = FloodVertical()
    claim = vertical.parse_claim("not in a flood zone")
    found = vertical.compare(claim, [_evidence("fema_flood_zone", "AE")])

    assert len(found) == 1
    assert found[0].severity is Severity.CRITICAL
    assert "AE" in found[0].explanation


def test_denial_outside_sfha_produces_no_discrepancy():
    vertical = FloodVertical()
    claim = vertical.parse_claim("not in a flood zone")
    assert vertical.compare(claim, [_evidence("fema_flood_zone", "X")]) == []


def test_understating_zone_is_more_severe_than_overstating():
    vertical = FloodVertical()

    understated = vertical.compare(
        vertical.parse_claim("Zone X"), [_evidence("fema_flood_zone", "AE")]
    )
    overstated = vertical.compare(
        vertical.parse_claim("Zone AE"), [_evidence("fema_flood_zone", "X")]
    )

    assert understated[0].severity is Severity.CRITICAL
    assert overstated[0].severity is Severity.MAJOR


def test_ground_below_bfe_is_flagged():
    vertical = FloodVertical()
    found = vertical.compare(
        vertical.parse_claim("Zone AE"),
        [
            _evidence("fema_flood_zone", "AE"),
            _evidence("fema_base_flood_elevation", 11.0, unit="feet"),
            _evidence("elevation", 2.5, unit="meters"),
        ],
    )
    elevation = [d for d in found if d.field == "elevation"]
    assert len(elevation) == 1
    # 11 ft = 3.35 m against 2.5 m of ground is a 0.85 m deficit. Subtracting the
    # raw numbers would claim 8.5 m and turn a real finding into a fabricated one.
    assert "0.85" in elevation[0].explanation


def test_bfe_in_feet_above_ground_produces_no_finding():
    """3 ft of BFE is below 2.5 m of ground; only a unit-blind check would flag it."""
    vertical = FloodVertical()
    found = vertical.compare(
        vertical.parse_claim("Zone AE"),
        [
            _evidence("fema_flood_zone", "AE"),
            _evidence("fema_base_flood_elevation", 3.0, unit="feet"),
            _evidence("elevation", 2.5, unit="meters"),
        ],
    )
    assert not [d for d in found if d.field == "elevation"]


def test_no_elevation_discrepancy_outside_sfha():
    vertical = FloodVertical()
    found = vertical.compare(
        vertical.parse_claim("Zone X"),
        [
            _evidence("fema_flood_zone", "X"),
            _evidence("fema_base_flood_elevation", 15.0, unit="feet"),
            _evidence("elevation", 2.0, unit="meters"),
        ],
    )
    assert not [d for d in found if d.field == "elevation"]


# -------------------------------------------------------------------------- verdict


def test_critical_discrepancy_disputes():
    verdict = _decide(
        [
            Discrepancy(
                field="f",
                claimed="a",
                observed="b",
                severity=Severity.CRITICAL,
                explanation="mismatch",
            )
        ],
        [],
        coverage=1.0,
    )
    assert verdict.kind is VerdictKind.DISPUTED
    assert verdict.confidence is Confidence.HIGH


def test_clean_check_verifies():
    verdict = _decide([], [], coverage=1.0)
    assert verdict.kind is VerdictKind.VERIFIED


def test_heavy_signal_alone_flags():
    signal = Signal(
        label="history",
        detail="many claims",
        source="OPENFEMA",
        fetched_at=datetime.now(timezone.utc),
        weight=Severity.MAJOR,
    )
    assert _decide([], [signal], coverage=1.0).kind is VerdictKind.FLAGGED


def test_thin_coverage_is_inconclusive_not_verified():
    verdict = _decide([], [], coverage=0.2)
    assert verdict.kind is VerdictKind.INCONCLUSIVE
    assert verdict.confidence is Confidence.LOW


def test_coverage_caps_confidence_even_with_findings():
    verdict = _decide(
        [
            Discrepancy(
                field="f",
                claimed="a",
                observed="b",
                severity=Severity.CRITICAL,
                explanation="mismatch",
            )
        ],
        [],
        coverage=0.3,
    )
    assert verdict.kind is VerdictKind.DISPUTED
    assert verdict.confidence is Confidence.LOW


# ------------------------------------------------------------------ provenance wrap


def test_fetch_splits_values_from_gaps():
    evidence, gaps = MireyeClient._to_evidence(
        {
            "fields": {
                "good": {
                    "value": 1.0,
                    "source": "USGS",
                    "source_url": "https://usgs.gov",
                    "fetched_at": "2026-08-06T00:00:00+00:00",
                    "confidence": "high",
                    "status": "ok",
                    "dataset_vintage": "3DEP",
                },
                "empty": {
                    "value": None,
                    "status": "absent",
                    "notes": "no BFE on this polygon",
                    "source": "FEMA_NFHL",
                },
            },
            "partial_failures": [
                {"field": "slow", "error": "timeout", "source": "PJM", "retryable": True}
            ],
        }
    )

    assert [e.field for e in evidence] == ["good"]
    assert evidence[0].confidence is Confidence.HIGH
    assert evidence[0].source_url == "https://usgs.gov"
    assert evidence[0].vintage == "3DEP"

    gap_fields = {g.field for g in gaps}
    assert gap_fields == {"empty", "slow"}
    # The API's own note is more useful than a generic "no value".
    assert "BFE" in next(g for g in gaps if g.field == "empty").reason
    assert next(g for g in gaps if g.field == "slow").retryable


def test_failed_field_reported_twice_yields_one_gap():
    """A timeout appears both as a null field and in partial_failures."""
    _, gaps = MireyeClient._to_evidence(
        {
            "fields": {"waterbody": {"value": None, "status": "error", "source": "NHD"}},
            "partial_failures": [
                {"field": "waterbody", "error": "TimeoutError", "retryable": True}
            ],
        }
    )
    assert len(gaps) == 1
    assert gaps[0].retryable


def test_rooftop_match_is_parcel_grade_but_interpolation_is_not():
    from src.models import Coordinate

    def grade(accuracy_type: str) -> bool:
        return Coordinate(
            lat=1.0, lng=1.0, parcel_grade="rooftop" in accuracy_type.lower()
        ).parcel_grade

    assert grade("nearest_rooftop_match")
    assert grade("rooftop")
    assert not grade("street_center")
    assert not grade("place")


def test_value_without_provenance_is_kept_but_marked_low():
    evidence, _ = MireyeClient._to_evidence({"fields": {"bare": 42}})
    assert evidence[0].confidence is Confidence.LOW
    assert evidence[0].note


# ------------------------------------------------------------------- datacenter


def test_haversine_matches_known_distance():
    # Washington DC to Baltimore is ~56 km.
    assert 50 < haversine_km(38.9072, -77.0369, 39.2904, -76.6122) < 62


def test_flat_site_scores_well_and_steep_site_does_not():
    flat = score_terrain([_evidence("slope_degrees", 1.5)])
    steep = score_terrain([_evidence("slope_degrees", 14.0)])
    assert flat.score == 1.0
    assert steep.score == 0.0


def test_missing_slope_is_neutral_not_zero():
    assert score_terrain([]).score == 0.5


def test_close_high_voltage_scores_better_than_remote():
    close = score_power(
        [
            _evidence("nearest_substation_distance_m", 1270),
            _evidence("nearest_substation_max_voltage_kv", 345),
            _evidence("transmission_lines_within_radius_count", 5),
        ]
    )
    remote = score_power(
        [
            _evidence("nearest_substation_distance_m", 30000),
            _evidence("nearest_substation_max_voltage_kv", 69),
            _evidence("transmission_lines_within_radius_count", 0),
        ]
    )
    assert close.score > 0.9
    assert remote.score < 0.3


def test_crowded_interconnection_queue_discounts_power_score():
    base = [
        _evidence("nearest_substation_distance_m", 1270),
        _evidence("nearest_substation_max_voltage_kv", 345),
        _evidence("transmission_lines_within_radius_count", 5),
    ]
    quiet = score_power(base + [_evidence("interconnection_queue_active_capacity_county_mw", 200)])
    crowded = score_power(
        base + [_evidence("interconnection_queue_active_capacity_county_mw", 9000)]
    )
    assert crowded.score < quiet.score


def test_floodplain_and_wetland_reduce_hazard_score():
    clean = score_hazard([_evidence("fema_flood_zone", "X")])
    flooded = score_hazard(
        [
            _evidence("fema_flood_zone", "AE"),
            _evidence("within_floodplain_polygon", True),
            _evidence("intersects_wetland", True),
        ]
    )
    assert clean.score == 1.0
    assert flooded.score == pytest.approx(0.1)


def test_nonattainment_and_neighbours_lower_externalities():
    from src.verticals.datacenter import score_externalities

    quiet = score_externalities(
        [
            _evidence("surface_water_supply_use_index_huc12", 0.1),
            _evidence("in_air_quality_nonattainment", False),
            _evidence("housing_units_within_1km", 20),
        ]
    )
    contested = score_externalities(
        [
            _evidence("surface_water_supply_use_index_huc12", 0.9),
            _evidence("in_air_quality_nonattainment", True),
            _evidence("housing_units_within_1km", 3253),
        ]
    )
    assert quiet.score > 0.9
    assert contested.score < 0.3


def test_adjacent_moratorium_tanks_permitting_score():
    near, _ = score_regulatory([_moratorium(12.0)], 80.0)
    far, _ = score_regulatory([_moratorium(70.0)], 80.0)
    none, signals = score_regulatory([], 80.0)

    assert near.score < far.score < none.score
    assert none.score == 1.0
    assert signals == []


def test_expired_moratorium_is_not_treated_as_blocking():
    score, signals = score_regulatory([_moratorium(10.0, status="expired")], 80.0)
    assert score.score == 1.0
    assert signals == []


def test_nearest_moratorium_drives_severity():
    _, signals = score_regulatory([_moratorium(10.0)], 80.0)
    assert signals[0].weight is Severity.CRITICAL


# -------------------------------------------------------------------- integration


# ----------------------------------------------------------------------- carbon


def _carbon():
    from src.verticals.carbon import CarbonVertical

    return CarbonVertical()


@pytest.mark.parametrize(
    "text,expected",
    [
        ("reforestation project since 2021", "reforestation"),
        ("new trees planted for carbon", "reforestation"),
        ("avoided deforestation, protecting intact forest", "avoided_deforestation"),
        ("REDD+ forest protection", "avoided_deforestation"),
        ("regenerative agriculture soil carbon", "soil_carbon"),
        ("avoided grassland conversion", "grassland"),
    ],
)
def test_carbon_claim_parsing(text, expected):
    assert _carbon().parse_claim(text).asserted_value == expected


def test_reforestation_over_bare_ground_is_critical():
    v = _carbon()
    found = v.compare(
        v.parse_claim("reforestation project since 2021"),
        [_evidence("tree_canopy_pct", 0.0, unit="percent"), _evidence("lcms_class", "Barren or Impervious")],
    )
    assert len(found) == 1
    assert found[0].severity is Severity.CRITICAL
    assert "not detectable" in found[0].explanation or "not exist" in found[0].explanation


def test_reforestation_over_mature_forest_flags_additionality():
    """The failure mode that sank the rice credits: claiming new trees where the forest
    already existed and isn't growing."""
    v = _carbon()
    found = v.compare(
        v.parse_claim("reforestation, new trees planted"),
        [
            _evidence("tree_canopy_pct", 76.0, unit="percent"),
            _evidence("lcms_class", "Trees"),
            _evidence("ndvi_change_5y", -0.04),
        ],
    )
    additionality = [d for d in found if d.field == "ndvi_change_5y"]
    assert len(additionality) == 1
    assert "predate" in additionality[0].explanation


def test_avoided_deforestation_over_intact_forest_verifies():
    v = _carbon()
    found = v.compare(
        v.parse_claim("avoided deforestation, protecting intact forest"),
        [
            _evidence("tree_canopy_pct", 76.0, unit="percent"),
            _evidence("lcms_class", "Trees"),
            _evidence("ndvi_change_5y", -0.03),
        ],
    )
    # A mild NDVI dip above the loss threshold shouldn't manufacture a discrepancy.
    assert found == []


def test_avoided_deforestation_over_bare_ground_flags_inflated_baseline():
    v = _carbon()
    found = v.compare(
        v.parse_claim("REDD+ forest protection"),
        [_evidence("tree_canopy_pct", 3.0, unit="percent"), _evidence("lcms_class", "Grass/Forb/Herb")],
    )
    assert found[0].severity is Severity.CRITICAL
    assert "baseline" in found[0].explanation


def test_reforestation_on_wetland_is_flagged():
    v = _carbon()
    found = v.compare(
        v.parse_claim("reforestation project"),
        [
            _evidence("tree_canopy_pct", 30.0, unit="percent"),
            _evidence("lcms_class", "Trees"),
            _evidence("ndvi_change_5y", 0.1),
            _evidence("intersects_wetland", True),
        ],
    )
    wetland = [d for d in found if d.field == "intersects_wetland"]
    assert len(wetland) == 1
    assert wetland[0].severity is Severity.MINOR


@pytest.mark.asyncio
async def test_offline_carbon_disputes_additionality_at_olympic_forest():
    from src.agent import VerificationAgent

    agent = VerificationAgent(MireyeClient(offline=True), _carbon())
    memo = await agent.verify(
        coordinate=Coordinate(lat=47.8, lng=-123.5),
        claim_text="reforestation project, new trees planted since 2021",
    )
    assert memo.verdict.kind is VerdictKind.DISPUTED
    assert any(d.field == "ndvi_change_5y" for d in memo.discrepancies)
    assert all(e.source for e in memo.evidence)


@pytest.mark.asyncio
async def test_offline_flood_run_disputes_galveston():
    from src.agent import VerificationAgent

    agent = VerificationAgent(MireyeClient(offline=True), FloodVertical())
    memo = await agent.verify(
        address="2201 Seawall Blvd, Galveston, TX",
        claim_text="not in a flood zone",
    )

    assert memo.verdict.kind is VerdictKind.DISPUTED
    assert any(d.severity is Severity.CRITICAL for d in memo.discrepancies)
    # Every fact in the memo must carry a source.
    assert all(e.source for e in memo.evidence)
    assert "FEMA_NFHL" in memo.sources()


def test_path_to_yes_names_vpp_market_and_ranks_levers():
    from src.verticals.datacenter import compute_path_to_yes

    p2y = compute_path_to_yes(
        [
            _evidence("iso_rto", "PJM"),
            _evidence("interconnection_queue_active_capacity_county_mw", 715),
            _evidence("surface_water_supply_use_index_huc12", 0.17),
            _evidence("mean_annual_dry_bulb_temperature_degc", 12.0),
            _evidence("housing_units_within_1km", 3253),
        ],
        [],
    )
    names = {l.name for l in p2y.levers}
    assert names == {"Grid flexibility (VPP)", "District heat (liquid cooling)", "Water offset"}
    # PJM is a top-tier capacity market, so the VPP lever should lead here.
    assert p2y.top_lever.name == "Grid flexibility (VPP)"
    assert "PJM" in p2y.top_lever.detail


def test_water_lever_leverage_rises_with_basin_stress():
    from src.verticals.datacenter import compute_path_to_yes

    def water_strength(index: float) -> float:
        p2y = compute_path_to_yes([_evidence("surface_water_supply_use_index_huc12", index)], [])
        return next(l for l in p2y.levers if l.name == "Water offset").strength

    # A stressed basin makes a water offset high-leverage; a wet one makes it cheap goodwill.
    assert water_strength(0.9) > water_strength(0.2)


def test_attestation_is_tamper_evident():
    from datetime import datetime, timezone

    from src.models import Coordinate, Verdict, VerdictKind, VerificationMemo, Claim
    from src.output.attestation import attest_memo

    memo = VerificationMemo(
        claim=Claim(text="not in a flood zone", subject="fema_flood_zone"),
        location=Coordinate(lat=29.3, lng=-94.8),
        verdict=Verdict(
            kind=VerdictKind.DISPUTED, confidence=Confidence.HIGH, reasoning="Zone AE"
        ),
        evidence=[_evidence("fema_flood_zone", "AE", source="FEMA_NFHL")],
    )
    att = attest_memo(memo)
    assert att.verify_integrity()

    # Any change to the body must break the hash.
    att.body["verdict"]["kind"] = "verified"
    assert not att.verify_integrity()


def test_attestation_hash_is_stable_across_runs():
    from src.models import Coordinate, Verdict, VerdictKind, VerificationMemo, Claim
    from src.output.attestation import attest_memo

    def build() -> str:
        memo = VerificationMemo(
            claim=Claim(text="x", subject="fema_flood_zone"),
            location=Coordinate(lat=1.0, lng=2.0),
            verdict=Verdict(kind=VerdictKind.VERIFIED, confidence=Confidence.HIGH, reasoning="ok"),
        )
        return attest_memo(memo).content_hash

    # generated_at is excluded from the body, so identical verifications hash identically.
    assert build() == build()


def test_stranded_viability_metric():
    from src.models import SiteScore, SiteScreen, Coordinate, Verdict, VerdictKind

    screen = SiteScreen(
        location=Coordinate(lat=1.0, lng=1.0),
        scores=[
            SiteScore(dimension="Power proximity", score=1.0, rationale=""),
            SiteScore(dimension="Terrain", score=1.0, rationale=""),
            SiteScore(dimension="Permitting risk", score=0.2, rationale=""),
        ],
        verdict=Verdict(kind=VerdictKind.DISPUTED, confidence=Confidence.HIGH, reasoning=""),
    )
    assert screen.physical_mean == pytest.approx(1.0)
    assert screen.stranded_viability == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_offline_dc_screen_flags_ashburn():
    from src.verticals.datacenter import screen_site

    screen = await screen_site(
        MireyeClient(offline=True), Coordinate(lat=39.0438, lng=-77.4874)
    )

    by_name = {s.dimension: s for s in screen.scores}

    # The finding the whole tool exists for: Ashburn is buildable on every
    # engineering axis and contested on the two that don't appear on a site plan.
    assert by_name["Power proximity"].score >= 0.9
    assert by_name["Terrain"].score >= 0.9
    assert by_name["Hazard & wetlands"].score >= 0.9
    assert by_name["Externalities"].score < 0.6
    assert by_name["Permitting risk"].score < 0.5
    assert screen.verdict.kind is VerdictKind.DISPUTED

    # Nothing is silently dropped: the fixture's failed field is a declared gap.
    assert screen.data_gaps
    assert all(e.source for e in screen.evidence)
