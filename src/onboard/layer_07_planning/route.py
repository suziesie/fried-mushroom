"""07. Flight Planning — terrain-aware 경로 생성 (stub DEM).

지형 표고(DEM) stub = 0m (flat terrain). 실제 DEM 연동은 후순위.
clearance_m = alt_m (stub DEM=0 기준).

generate_route(flight_action, altitude_delta_m, replan_scope, cycle_context)
  → list[dict]  # [{lat, lon, alt_m, clearance_m}, ...]

replan_scope 별 동작:
  NONE  → []  (MAINTAIN — 재계획 없음)
  LOCAL → corridor waypoints + delta 적용 (RTL은 역순 + base 추가)
  FULL  → corridor waypoints + delta 적용 (full 경로 재생성)

물리적 상승/하강률:
  연속 waypoint 간 고도차가 ROUTE_MAX_CLIMB_RATE_M_PER_WP 를 초과하면
  두 점 사이에 중간 waypoint 를 보간해 제약을 강제한다.
"""

from __future__ import annotations

import math

from ..shared.constants import ROUTE_MAX_CLIMB_RATE_M_PER_WP, ROUTE_MIN_CLEARANCE_M


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
    """고도 delta 적용 + 연속 고도차 상한(ROUTE_MAX_CLIMB_RATE_M_PER_WP) 강제.

    초과 시 두 corridor waypoint 사이에 위경도를 선형 보간한 중간 waypoint 삽입.
    모든 waypoint 는 ROUTE_MIN_CLEARANCE_M 이상으로 clamp.
    """
    if not waypoints:
        return []

    # 목표 고도 산출 (min clearance clamp 포함)
    targets: list[tuple[float, float, float]] = [
        (
            float(wp["lat"]),
            float(wp["lon"]),
            max(ROUTE_MIN_CLEARANCE_M, float(wp.get("alt_m", ROUTE_MIN_CLEARANCE_M)) + delta_m),
        )
        for wp in waypoints
    ]

    route = [{"lat": targets[0][0], "lon": targets[0][1],
               "alt_m": targets[0][2], "clearance_m": targets[0][2]}]

    for i in range(1, len(targets)):
        lat1, lon1, alt1 = targets[i - 1]
        lat2, lon2, alt2 = targets[i]
        diff = alt2 - alt1

        if abs(diff) > ROUTE_MAX_CLIMB_RATE_M_PER_WP:
            # 중간 waypoint 보간 — 물리적 상승/하강률 강제
            n_steps = math.ceil(abs(diff) / ROUTE_MAX_CLIMB_RATE_M_PER_WP)
            for step in range(1, n_steps):
                t = step / n_steps
                interp_alt = alt1 + t * diff
                route.append({
                    "lat": lat1 + t * (lat2 - lat1),
                    "lon": lon1 + t * (lon2 - lon1),
                    "alt_m": interp_alt,
                    "clearance_m": interp_alt,
                })

        route.append({"lat": lat2, "lon": lon2, "alt_m": alt2, "clearance_m": alt2})

    return route


def _rtl_route(waypoints: list[dict], bases: dict) -> list[dict]:
    """RTL: corridor 역순 + emergency base 를 최종 목적지로 추가.

    base 고도가 corridor 고도보다 낮을 때 급강하를 방지하기 위해
    base 를 corridor 목록에 포함시켜 _apply_delta 의 보간 적용.
    """
    reversed_wps = list(reversed(waypoints))
    base = bases.get("emergency")
    if base:
        reversed_wps = reversed_wps + [base]
    return _apply_delta(reversed_wps, 0)
