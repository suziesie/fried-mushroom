"""07. Flight Planning — ResponseOutput → FlightPlanOutput."""

from ..shared.constants import TIME_TO_COLLISION_THRESHOLD_S
from ..shared.schemas import FlightPlanOutput, ResponseOutput
from . import altitude, bearing, route as route_gen

_REPLAN_SCOPE: dict[str, str] = {
    "RTL":                     "LOCAL",
    "REROUTE":                 "FULL",
    "ALTITUDE_CHANGE_REROUTE": "FULL",
    "ALTITUDE_CHANGE":         "LOCAL",
    "POSTURE_ELEVATE":         "LOCAL",
    "MAINTAIN":                "NONE",
}


def run(
    response: ResponseOutput,
    primary_context: dict | None,
    cycle_context: dict,
) -> FlightPlanOutput:
    """06의 ResponseOutput과 04의 primary_context·cycle_context → MAVLink급 지시값.

    primary_context: 04의 candidates[0].context. 위협 없거나 미탐지 시 None.
    cycle_context: obstacle_ttc_s 포함 시 CFIT 결정론적 override 적용.
    """
    effective_action = response["flight_action"]
    scope = _REPLAN_SCOPE[effective_action]

    threat_bearing: float | None = None
    if primary_context is not None:
        threat_bearing = primary_context.get("bearing_deg")

    tgt_bearing, b_anchor = bearing.compute_bearing(
        response["threat_category"], threat_bearing, cycle_context
    )
    delta, alt_anchor = altitude.compute_altitude_delta(effective_action)

    # CFIT 결정론적 override: TTC<3s + 고도변화 없음 → ALTITUDE_CHANGE 강제 (RAC 무관, SCC-1)
    ttc = cycle_context.get("obstacle_ttc_s")
    if ttc is not None and ttc < TIME_TO_COLLISION_THRESHOLD_S and delta == 0:
        effective_action = "ALTITUDE_CHANGE"
        delta, alt_anchor = altitude.compute_altitude_delta("ALTITUDE_CHANGE")
        scope = _REPLAN_SCOPE["ALTITUDE_CHANGE"]

    # MAINTAIN(replan_scope=NONE) → 재계획 없으므로 anchor 불필요
    final_anchor = None if scope == "NONE" else (b_anchor or alt_anchor)

    generated_route = route_gen.generate_route(effective_action, delta, scope, cycle_context)

    return FlightPlanOutput(
        flight_action=effective_action,
        target_bearing_deg=tgt_bearing,
        altitude_delta_m=delta,
        replan_scope=scope,
        reroute_anchor=final_anchor,
        route=generated_route,
    )
