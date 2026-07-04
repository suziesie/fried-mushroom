"""온보드 파이프라인 오케스트레이터 (하니스).

한 사이클을 03→04→05→06→07 순서로 엮는다 (step9.md 계약).
각 레이어는 `src/onboard/layer_XX_*/run.py` 의 순수 함수:

    layer_03.run(raw, previous_qualities)
    layer_04.run(abstraction, cycle_context)
    layer_05.run(threat, mission_brief, link_quality=...)
    layer_06.run(risk, mission_brief)
    layer_07.run(response, primary_context, cycle_context)

아직 미구현인 레이어는 스키마 적합 passthrough(canned)로 대체한다 (try-import 배선).
dev 가 layer_XX/run.py 에 run() 을 추가하면 orchestrator 수정 없이 자동 배선된다.

파이프라인은 순수(IO 없음). 파일 read / stdout 은 __main__.py(CLI) 가 담당.
로깅(JSONL 등)은 유즈사이트 책임 — 오케스트레이터에 넣지 않는다 (ARCHITECTURE 상태 관리).
"""

from __future__ import annotations

import importlib
import math

_LAYER_MODULE = {
    "03": "onboard.layer_03_abstraction.run",
    "04": "onboard.layer_04_threat.run",
    "05": "onboard.layer_05_risk.run",
    "06": "onboard.layer_06_response.run",
    "07": "onboard.layer_07_planning.run",
}


def run_cycle(
    raw: dict,
    mission_brief: dict,
    previous_qualities: dict | None = None,
    cycle_context: dict | None = None,
) -> dict:
    """한 사이클 실행. 반환:

        {"abstraction": ..., "threat": ..., "risk": ...,
         "response": ..., "flight_plan": ...}
    """
    cycle_context = cycle_context or _compute_terrain_bearings(mission_brief)

    abstraction = _run_layer("03", lambda run: run(raw, previous_qualities))
    threat = _run_layer("04", lambda run: run(abstraction, cycle_context))
    link_quality = _extract_link_quality(abstraction)
    risk = _run_layer("05", lambda run: run(threat, mission_brief, link_quality=link_quality))
    response = _run_layer("06", lambda run: run(risk, mission_brief))

    primary = threat.get("primary")
    primary_context = primary.get("context") if primary else None
    obstacle_ttc_s = _extract_obstacle_ttc(abstraction)
    cycle_context_07 = {
        **cycle_context,
        **_extract_terrain_bearings(abstraction),  # 03 terrain_class 방위가 있으면 코리더 heuristic 을 덮어씀
        **({"obstacle_ttc_s": obstacle_ttc_s} if obstacle_ttc_s is not None else {}),
        "corridor_waypoints": mission_brief.get("corridor", {}).get("waypoints", []),
        "corridor_bases": mission_brief.get("corridor", {}).get("bases", {}),
    }
    flight_plan = _run_layer("07", lambda run: run(response, primary_context, cycle_context_07))

    return {
        "abstraction": abstraction,
        "threat": threat,
        "risk": risk,
        "response": response,
        "flight_plan": flight_plan,
    }


def _compute_terrain_bearings(mission_brief: dict) -> dict:
    """코리더 waypoints에서 지형 방위 산출. GIS 실조회는 후순위 — heuristic stub.

    waypoints >= 2개: wp[0]→wp[-1] bearing. 위도별 경도 거리 보정(cos(mean_lat)) 적용.
    - optimal_terrain_bearing_deg: 코리더 헤딩 (장애물 통과 방향)
    - lowest_exposure_bearing_deg: 헤딩 + 90° (교차 방향 이탈)
    waypoints < 2개: (0.0, 0.0) fallback.
    """
    wps = mission_brief.get("corridor", {}).get("waypoints", [])
    if len(wps) >= 2:
        dlat = wps[-1]["lat"] - wps[0]["lat"]
        dlon = wps[-1]["lon"] - wps[0]["lon"]
        mean_lat = math.radians((wps[0]["lat"] + wps[-1]["lat"]) / 2)
        dlon_corr = dlon * math.cos(mean_lat)
        # atan2/cos 의 마지막 ULP 는 libm(파이썬/플랫폼)마다 달라 골든을 CI(3.11)와
        # 로컬(3.13)에서 어긋나게 한다. 6자리(≈0.1m)로 반올림해 이식성 확보.
        optimal = round(math.degrees(math.atan2(dlon_corr, dlat)) % 360, 6)
        lowest = round((optimal + 90) % 360, 6)
    else:
        optimal = 0.0
        lowest = 0.0
    return {"optimal_terrain_bearing_deg": optimal, "lowest_exposure_bearing_deg": lowest}


def _extract_link_quality(abstraction: dict) -> float | None:
    """abstraction 채널에서 link_status quality 추출 (없으면 None). 05 link_quality 인자용."""
    for channel in abstraction.get("channels", []):
        if channel.get("channel") == "link_status":
            return channel.get("quality")
    return None


def _extract_terrain_bearings(abstraction: dict) -> dict:
    """terrain_class 채널 payload에서 지형 방위(non-None만) 추출. 07 cycle_context 오버라이드용.

    실제 GIS/세그멘테이션이 방위를 산출하면 코리더 heuristic(_compute_terrain_bearings)보다
    우선한다. 스텁이 None 을 주면 빈 dict 를 반환해 코리더 값을 보존한다.
    """
    for channel in abstraction.get("channels", []):
        if channel.get("channel") == "terrain_class":
            p = channel.get("payload", {})
            return {
                k: p[k]
                for k in ("optimal_terrain_bearing_deg", "lowest_exposure_bearing_deg")
                if p.get(k) is not None
            }
    return {}


def _extract_obstacle_ttc(abstraction: dict) -> float | None:
    """obstacle_proximity 채널 payload에서 TTC(s) 계산. 07 CFIT override 판정용."""
    for channel in abstraction.get("channels", []):
        if channel.get("channel") == "obstacle_proximity":
            p = channel.get("payload", {})
            d = p.get("distance_m")
            v = p.get("closure_rate_mps")
            if d is not None and v is not None and v > 0:
                return d / v
    return None


def extract_qualities(result: dict) -> dict[str, float]:
    """run_cycle 결과에서 채널명→quality 맵 추출. 다음 사이클 previous_qualities 인자용."""
    return {ch["channel"]: ch["quality"] for ch in result["abstraction"]["channels"]}


def _run_layer(num: str, invoke):
    """레이어 run() 이 있으면 invoke(run) 으로 호출, 없으면 canned passthrough."""
    run = _import_layer_run(num)
    if run is not None:
        return invoke(run)
    return _STUB_OUTPUT[num]()


def _import_layer_run(num: str):
    try:
        module = importlib.import_module(_LAYER_MODULE[num])
    except ModuleNotFoundError:
        return None
    run = getattr(module, "run", None)
    return run if callable(run) else None


# 미구현 레이어용 최소 스키마 적합 고정 출력 (각 OutputSchema 의 최소 인스턴스).
_STUB_OUTPUT = {
    "03": lambda: {
        "schema_version": "0.0-stub",
        "id": "stub",
        "ts": 0,
        "channels": [],
    },
    "04": lambda: {
        "declared_phase": "unknown",
        "mission_phase_confidence": 0.0,
        "candidates": [],
        "primary": None,
        "background_exposure_score": 0.0,
    },
    "05": lambda: {
        "candidates": [],
    },
    "06": lambda: {
        "primary_threat_event": None,
        "rac": "Low",
        "kill_chain_stage": None,
        "threat_category": None,
        "flight_action": "MAINTAIN",
        "comms_level": "L0",
        "payload_action": [],
        "nav_mode": None,
        "special_action": None,
        "secondary_threats": [],
        "ai_reliability": "normal",
    },
    "07": lambda: {
        "flight_action": "MAINTAIN",
        "target_bearing_deg": None,
        "altitude_delta_m": 0,
        "replan_scope": "NONE",
        "reroute_anchor": None,
        "route": [],
    },
}
