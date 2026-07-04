"""07. Flight Planning — terrain-aware 경로 생성 (stub DEM).

지형 표고(DEM) stub = 0m (flat terrain). 실제 DEM 연동은 후순위.
clearance_m = alt_m (stub DEM=0 기준).

generate_route(flight_action, altitude_delta_m, replan_scope, cycle_context)
  → list[dict]  # [{lat, lon, alt_m, clearance_m}, ...]

replan_scope 별 동작:
  NONE  → []  (MAINTAIN — 재계획 없음)
  LOCAL → corridor waypoints + delta 적용 (RTL은 역순 + base 추가)
  FULL  → corridor waypoints + delta 적용 (full 경로 재생성)
"""

from __future__ import annotations

from ..shared.constants import ROUTE_MIN_CLEARANCE_M


def generate_route(
    flight_action: str,
    altitude_delta_m: int,
    replan_scope: str,
    cycle_context: dict,
) -> list[dict]:
    """terrain-aware 경로 생성.

    cycle_context 키:
      corridor_waypoints: list[dict] — 코리더 waypoints ({lat, lon, alt_m, ...})
      corridor_bases: dict — 복귀 기지 ({emergency: {lat, lon, alt_m}, ...})
    """
    waypoints: list[dict] = cycle_context.get("corridor_waypoints") or []
    if not waypoints or replan_scope == "NONE":
        return []

    if flight_action == "RTL":
        return _rtl_route(waypoints, cycle_context.get("corridor_bases") or {})

    return _apply_delta(waypoints, altitude_delta_m)


def _apply_delta(waypoints: list[dict], delta_m: int) -> list[dict]:
    """모든 waypoint 에 고도 delta 적용 + 최소 clearance clamp."""
    route = []
    for wp in waypoints:
        raw_alt = float(wp.get("alt_m", ROUTE_MIN_CLEARANCE_M)) + delta_m
        alt = max(ROUTE_MIN_CLEARANCE_M, raw_alt)
        route.append({
            "lat": float(wp["lat"]),
            "lon": float(wp["lon"]),
            "alt_m": alt,
            "clearance_m": alt,  # stub DEM=0 → clearance = alt
        })
    return route


def _rtl_route(waypoints: list[dict], bases: dict) -> list[dict]:
    """RTL: corridor 역순 + emergency base 를 최종 목적지로 추가."""
    reversed_wps = list(reversed(waypoints))
    route = _apply_delta(reversed_wps, 0)

    base = bases.get("emergency")
    if base:
        base_alt = max(ROUTE_MIN_CLEARANCE_M, float(base.get("alt_m", ROUTE_MIN_CLEARANCE_M)))
        route.append({
            "lat": float(base["lat"]),
            "lon": float(base["lon"]),
            "alt_m": base_alt,
            "clearance_m": base_alt,
        })
    return route
