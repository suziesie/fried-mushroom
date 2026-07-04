"""07 route.py — terrain-aware 경로 생성 단위 테스트 (issue #102).

수용 기준:
- 07 출력에 terrain-aware 경로(좌표+고도 배열) 포함
- 지형에 대해 최소 안전 clearance 보장
- 물리적 상승/하강률 내
"""

import pytest

from onboard.layer_07_planning.route import generate_route
from onboard.shared.constants import ROUTE_MAX_CLIMB_RATE_M_PER_WP, ROUTE_MIN_CLEARANCE_M

_WPS = [
    {"id": "wp1", "lat": 37.50, "lon": 127.00, "alt_m": 120},
    {"id": "wp2", "lat": 37.51, "lon": 127.01, "alt_m": 120},
    {"id": "wp3", "lat": 37.52, "lon": 127.02, "alt_m": 120},
]

_BASES = {
    "emergency": {"id": "base_emergency", "lat": 37.49, "lon": 127.00, "alt_m": 50},
    "alternate": {"id": "base_alternate", "lat": 37.48, "lon": 127.005, "alt_m": 50},
}

_CTX = {"corridor_waypoints": _WPS, "corridor_bases": _BASES}


# ---------------------------------------------------------------------------
# 기본 계약
# ---------------------------------------------------------------------------


def test_maintain_returns_empty_route():
    route = generate_route("MAINTAIN", 0, "NONE", _CTX)
    assert route == [], "MAINTAIN(replan_scope=NONE) 는 빈 경로를 반환해야 함"


def test_no_corridor_returns_empty_route():
    route = generate_route("ALTITUDE_CHANGE", 15, "LOCAL", {})
    assert route == [], "corridor_waypoints 없으면 빈 경로를 반환해야 함"


def test_route_waypoints_have_required_fields():
    route = generate_route("ALTITUDE_CHANGE", 15, "LOCAL", _CTX)
    assert route, "ALTITUDE_CHANGE 는 비어 있지 않은 경로를 반환해야 함"
    for wp in route:
        assert "lat" in wp, "lat 필드 누락"
        assert "lon" in wp, "lon 필드 누락"
        assert "alt_m" in wp, "alt_m 필드 누락"
        assert "clearance_m" in wp, "clearance_m 필드 누락"


def test_route_is_json_serializable():
    import json
    route = generate_route("ALTITUDE_CHANGE", 15, "LOCAL", _CTX)
    assert json.dumps(route)  # 직렬화 가능해야 함


# ---------------------------------------------------------------------------
# 고도 delta 적용
# ---------------------------------------------------------------------------


def test_altitude_change_applies_delta_to_all_waypoints():
    route = generate_route("ALTITUDE_CHANGE", 15, "LOCAL", _CTX)
    assert len(route) == len(_WPS), "waypoint 수 일치해야 함"
    for i, wp in enumerate(route):
        expected_alt = _WPS[i]["alt_m"] + 15
        assert wp["alt_m"] == pytest.approx(expected_alt), (
            f"wp[{i}] alt_m={wp['alt_m']} — 예상 {expected_alt}"
        )


def test_posture_elevate_applies_larger_delta():
    from onboard.shared.constants import POSTURE_ELEVATE_ALTITUDE_M

    route = generate_route("POSTURE_ELEVATE", POSTURE_ELEVATE_ALTITUDE_M, "LOCAL", _CTX)
    assert len(route) == len(_WPS)
    for i, wp in enumerate(route):
        assert wp["alt_m"] == pytest.approx(_WPS[i]["alt_m"] + POSTURE_ELEVATE_ALTITUDE_M)


def test_full_replan_applies_delta():
    route = generate_route("ALTITUDE_CHANGE_REROUTE", 50, "FULL", _CTX)
    assert route, "ALTITUDE_CHANGE_REROUTE 는 비어 있지 않은 경로를 반환해야 함"
    for i, wp in enumerate(route):
        assert wp["alt_m"] == pytest.approx(_WPS[i]["alt_m"] + 50)


# ---------------------------------------------------------------------------
# 최소 clearance
# ---------------------------------------------------------------------------


def test_min_clearance_enforced_when_alt_too_low():
    """현재 고도 + delta < ROUTE_MIN_CLEARANCE_M 이면 ROUTE_MIN_CLEARANCE_M 로 clamp."""
    low_wps = [{"id": "wp1", "lat": 37.50, "lon": 127.00, "alt_m": 30}]
    ctx = {"corridor_waypoints": low_wps}
    route = generate_route("ALTITUDE_CHANGE", -20, "LOCAL", ctx)
    assert route[0]["alt_m"] >= ROUTE_MIN_CLEARANCE_M, (
        f"alt_m={route[0]['alt_m']} < ROUTE_MIN_CLEARANCE_M={ROUTE_MIN_CLEARANCE_M}"
    )


def test_all_waypoints_meet_min_clearance():
    route = generate_route("ALTITUDE_CHANGE", 15, "LOCAL", _CTX)
    for wp in route:
        assert wp["alt_m"] >= ROUTE_MIN_CLEARANCE_M, (
            f"alt_m={wp['alt_m']} < 최소 clearance={ROUTE_MIN_CLEARANCE_M}"
        )


def test_clearance_field_reflects_dem_stub():
    """stub DEM = 0m → clearance_m = alt_m 과 동일."""
    route = generate_route("ALTITUDE_CHANGE", 15, "LOCAL", _CTX)
    for wp in route:
        assert wp["clearance_m"] == pytest.approx(wp["alt_m"]), (
            "stub DEM 0m 기준으로 clearance_m == alt_m 이어야 함"
        )


# ---------------------------------------------------------------------------
# 물리적 상승/하강률
# ---------------------------------------------------------------------------


def test_consecutive_altitude_diff_within_max_rate_uniform_delta():
    """동일 delta 적용 시 연속 waypoint 간 고도 차이가 0 → 상승률 제한 내."""
    route = generate_route("ALTITUDE_CHANGE", 15, "LOCAL", _CTX)
    for i in range(len(route) - 1):
        diff = abs(route[i + 1]["alt_m"] - route[i]["alt_m"])
        assert diff <= ROUTE_MAX_CLIMB_RATE_M_PER_WP, (
            f"연속 고도 차이 {diff}m > 제한 {ROUTE_MAX_CLIMB_RATE_M_PER_WP}m"
        )


# ---------------------------------------------------------------------------
# RTL
# ---------------------------------------------------------------------------


def test_rtl_reverses_waypoints():
    """RTL 은 corridor 역순으로 경로를 생성한다."""
    route = generate_route("RTL", 0, "LOCAL", _CTX)
    assert route, "RTL 은 비어 있지 않은 경로를 반환해야 함"
    # 역순: 마지막 corridor wp 가 첫 번째 route wp
    assert route[0]["lat"] == pytest.approx(_WPS[-1]["lat"])
    assert route[0]["lon"] == pytest.approx(_WPS[-1]["lon"])


def test_rtl_route_ends_near_emergency_base():
    """RTL 경로의 마지막 waypoint 는 emergency base 위치에 가깝다."""
    route = generate_route("RTL", 0, "LOCAL", _CTX)
    base = _BASES["emergency"]
    last = route[-1]
    assert last["lat"] == pytest.approx(base["lat"])
    assert last["lon"] == pytest.approx(base["lon"])


def test_rtl_all_waypoints_meet_min_clearance():
    """RTL 경로의 모든 waypoint 도 최소 clearance 를 보장한다."""
    route = generate_route("RTL", 0, "LOCAL", _CTX)
    for wp in route:
        assert wp["alt_m"] >= ROUTE_MIN_CLEARANCE_M
