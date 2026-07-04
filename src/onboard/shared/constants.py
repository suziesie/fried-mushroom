"""D4D 파이프라인 공유 상수.

D4D 문서 (docs/D4D/*.md) 의 파라미터 표를 그대로 옮긴 소스 오브 트루스.
- 04. Threat Modeling.md — THREAT_CATALOG, SIGNAL_TO_THREAT, PHASE_THREAT_MULTIPLIER, CHANNEL_WEIGHTS 등
- 05. Risk Assessment.md — BASE_RATE, L_VALUE_TO_CLASS_THRESHOLDS, RAC_MATRIX, SEVERITY_ORDER 등

CRITICAL:
- 값을 임의로 반올림/보정하지 말 것. 값 변경은 반드시 D4D 문서 먼저 수정.
- RAC_MATRIX 등 core matrix 는 MappingProxyType 으로 read-only 보증 (ADR-003, MIL-STD-882E SCC-1).
- 이 상수들은 함수 인자로 오버라이드 금지 (CLAUDE.md CRITICAL).
"""

from types import MappingProxyType
from typing import Final, Mapping

# ---------------------------------------------------------------------------
# 04. Threat Modeling — 위협 카탈로그 & 매핑
# ---------------------------------------------------------------------------

THREAT_CATALOG: Final[Mapping[str, str]] = MappingProxyType(
    {
        "T1": "EW/GPS 스푸핑",
        "T2": "사이버/C2 하이재킹",
        "T3": "근접 소화기",
        "T4": "물리 포획",
        "T5": "레이저",
        "T6": "환경노출도(배경)",
        "T7": "지형충돌/CFIT",
    }
)

# 04 Step D — threat_event -> potential_outcome
POTENTIAL_OUTCOME_MAP: Final[Mapping[str, str]] = MappingProxyType(
    {
        "T1": "mission_abort",
        "T2": "hull_loss",
        "T3": "attrition_kill",
        "T4": "hull_loss",
        "T5": "mission_abort",
        "T7": "attrition_kill",
    }
)

# 04 Step D — potential_outcome -> MIL-STD-882E 심각도 카테고리
OUTCOME_TO_SEVERITY: Final[Mapping[str, str]] = MappingProxyType(
    {
        "mission_abort": "Marginal",
        "hull_loss": "Catastrophic",
        "attrition_kill": "Critical",
    }
)

# MIL-STD-882E 심각도 순위. 1 = 가장 심각.
SEVERITY_ORDER: Final[Mapping[str, int]] = MappingProxyType(
    {
        "Catastrophic": 1,
        "Critical": 2,
        "Marginal": 3,
        "Negligible": 4,
    }
)

# 04 Step B — 신호 -> 위협 매핑표.
# condition 은 문자열 (판정 로직은 05+ layer 에서 컴파일).
SIGNAL_TO_THREAT: Final[tuple[Mapping[str, str], ...]] = tuple(
    MappingProxyType(entry)
    for entry in (
        {
            "channel": "proximity_object",
            "condition": "state=anomaly AND payload.weapon_shape=True",
            "threat": "T3",
        },
        {
            "channel": "acoustic_event",
            "condition": "payload.event_type='gunshot'",
            "threat": "T3",
        },
        {
            "channel": "position_consistency",
            "condition": "payload.gps_imu_residual_m > 5.0",
            "threat": "T1",
        },
        {
            "channel": "rf_spectrum",
            "condition": "payload.wideband_anomaly=True",
            "threat": "T1",
        },
        {
            "channel": "link_integrity",
            "condition": "payload.checksum_fail_rate > 0.05 OR payload.seq_gap_count > 0",
            "threat": "T2",
        },
        {
            "channel": "encryption_status",
            "condition": "payload.downgrade_detected=True",
            "threat": "T2",
        },
        {
            "channel": "obstacle_proximity",
            "condition": "payload.distance_m / payload.closure_rate_mps < 3.0",
            "threat": "T7",
        },
        {
            "channel": "proximity_object",
            "condition": "quality_delta < -0.3",
            "threat": "T5",
        },
        {
            "channel": "terrain_class",
            "condition": "quality_delta < -0.3",
            "threat": "T5",
        },
    )
)

# 04 Step B — T4 다중채널 동시조건 (세 조건이 모두 참일 때만 매칭).
T4_MULTI_CHANNEL_CONDITIONS: Final[tuple[Mapping[str, str], ...]] = tuple(
    MappingProxyType(entry)
    for entry in (
        {
            "channel": "proximity_object",
            "condition": "payload.class in {person, vehicle} AND payload.closing=True",
        },
        {
            "channel": "mission_phase",
            "condition": "payload.match=False",
        },
        {
            "channel": "link_status",
            "condition": "state != normal",
        },
    )
)

# 04 Step A — (declared_phase, threat_event) -> 배수. 표에 없는 조합은 1.0 (조회 시 .get(..., 1.0)).
PHASE_THREAT_MULTIPLIER: Final[Mapping[tuple[str, str], float]] = MappingProxyType(
    {
        ("LOITER_ROI", "T3"): 1.1,
        ("LOITER_ROI", "T7"): 0.9,
        ("LOITER_ROI", "T4"): 1.1,
        ("RTL", "T3"): 0.9,
        ("LAND", "T7"): 1.2,
        ("LAND", "T4"): 1.2,
        ("TAKEOFF", "T7"): 1.1,
        ("TAKEOFF", "T4"): 1.1,
    }
)

# 04 Step C — 채널별 기본 가중치.
CHANNEL_WEIGHTS: Final[Mapping[str, float]] = MappingProxyType(
    {
        "proximity_object": 0.40,
        "position_consistency": 0.35,
        "link_integrity": 0.35,
        "obstacle_proximity": 0.35,
        "encryption_status": 0.35,
        "acoustic_event": 0.30,
        "rf_spectrum": 0.25,
        "terrain_class": 0.25,
        "mission_phase": 0.25,
        "link_status": 0.15,
    }
)

# CHANNEL_WEIGHTS 에 없는 채널의 기본값 (04 Step C 표 각주).
DEFAULT_CHANNEL_WEIGHT: Final[float] = 0.20

# 04 Step C — 결정론적 confidence 표.
CONFIDENCE_BY_MATCH_COUNT: Final[Mapping[int, float]] = MappingProxyType(
    {
        1: 0.70,
        2: 0.90,
        3: 0.95,  # 3 이상은 0.95 상한
    }
)

# 04 Step C — quality/weight 하한 및 교차검증 허용치.
W_MIN: Final[float] = 0.20
Q_MIN: Final[float] = 0.65
CROSS_CHECK_TOLERANCE: Final[float] = 0.15

# 04 Step C — confidence 상한 (국면배수 적용 후 clip).
CONFIDENCE_UPPER_BOUND: Final[float] = 0.95

# ---------------------------------------------------------------------------
# 05. Risk Assessment — mission_context / base_rate / L·S / RAC
# ---------------------------------------------------------------------------

MISSION_CONTEXTS: Final[tuple[str, ...]] = ("정찰", "타격", "호송", "수송")

# 05 — PHYSICAL 위협 (T3/T4) 만 mission_context 별로 다른 base_rate.
BASE_RATE_PHYSICAL: Final[Mapping[tuple[str, str], float]] = MappingProxyType(
    {
        ("T3", "정찰"): 0.15,
        ("T3", "타격"): 0.35,
        ("T3", "호송"): 0.20,
        ("T3", "수송"): 0.10,
        ("T4", "정찰"): 0.08,
        ("T4", "타격"): 0.20,
        ("T4", "호송"): 0.12,
        ("T4", "수송"): 0.05,
    }
)

# 05 — REMOTE / NAVIGATION 위협은 컨텍스트 무관 단일값.
BASE_RATE_REMOTE_NAV: Final[Mapping[str, float]] = MappingProxyType(
    {
        "T1": 0.12,
        "T2": 0.10,
        "T5": 0.08,
        "T7": 0.10,
    }
)

# 05 — l_value -> l_class (내림차순, 첫 매칭이 등급).
# 표 밑은 "F".
L_VALUE_TO_CLASS_THRESHOLDS: Final[tuple[tuple[float, str], ...]] = (
    (0.50, "A"),
    (0.30, "B"),
    (0.15, "C"),
    (0.05, "D"),
    (0.01, "E"),
)

# 05 — RAC 매트릭스 (6x4). MIL-STD-882E Table III.
# 키: (l_class, severity_num). 값: RAC.
# CRITICAL: AI 가 절대 바꾸지 않음 (SCC-1 원칙, ADR-003).
RAC_MATRIX: Final[Mapping[tuple[str, int], str]] = MappingProxyType(
    {
        ("A", 1): "High",
        ("A", 2): "High",
        ("A", 3): "Serious",
        ("A", 4): "Medium",
        ("B", 1): "High",
        ("B", 2): "Serious",
        ("B", 3): "Medium",
        ("B", 4): "Low",
        ("C", 1): "Serious",
        ("C", 2): "Serious",
        ("C", 3): "Medium",
        ("C", 4): "Low",
        ("D", 1): "Serious",
        ("D", 2): "Medium",
        ("D", 3): "Low",
        ("D", 4): "Low",
        ("E", 1): "Medium",
        ("E", 2): "Medium",
        ("E", 3): "Low",
        ("E", 4): "Low",
        ("F", 1): "Medium",
        ("F", 2): "Low",
        ("F", 3): "Low",
        ("F", 4): "Low",
    }
)

# 05 — RAC 순위 (교차검증 거리 계산용).
RAC_ORDER: Final[Mapping[str, int]] = MappingProxyType(
    {
        "High": 1,
        "Serious": 2,
        "Medium": 3,
        "Low": 4,
    }
)

# 05 — AI 강화판 continuous_S 기준점 (severity_label -> base_score).
CONTINUOUS_S_BASE_SCORE: Final[Mapping[str, float]] = MappingProxyType(
    {
        "Catastrophic": 0.90,
        "Critical": 0.60,
        "Marginal": 0.30,
        "Negligible": 0.10,
    }
)

# 05 — continuous_S -> severity_num_ai 임계값 (내림차순).
CONTINUOUS_S_TO_NUM_THRESHOLDS: Final[tuple[tuple[float, int], ...]] = (
    (0.75, 1),
    (0.45, 2),
    (0.20, 3),
)

# 05 — 배경 노출도 임계값 (ambient_rac 하한 판정용).
AMBIENT_EXPOSURE_THRESHOLD: Final[float] = 0.7

# 05 — AI 교차검증 거리 (RAC_ORDER 차이 2 이상이면 ai_reliability=low).
AI_RELIABILITY_DELTA_THRESHOLD: Final[int] = 2

# 05 — kill_chain_stage 후기 보너스 (compound_urgency_score).
KILL_CHAIN_LATE_BONUS: Final[float] = 0.10

# 05 — compound_urgency_score / continuous_L 상한.
COMPOUND_UPPER_BOUND: Final[float] = 0.95

# 04 CONFIDENCE_ANCHOR (continuous_L 재사용 기준값 = 매치 1채널 confidence).
CONFIDENCE_ANCHOR: Final[float] = 0.70

# ---------------------------------------------------------------------------
# 03 / 04 — 채널 임계값
# ---------------------------------------------------------------------------

# 04 Step B — obstacle_proximity 충돌예상시간 (초).
TIME_TO_COLLISION_THRESHOLD_S: Final[float] = 3.0

# 04 Step B — T5 quality_delta 급락 임계값.
QUALITY_DELTA_DROP_THRESHOLD: Final[float] = -0.3

# 07 Flight Planning — altitude_delta_m 상수.
ALTITUDE_DELTA_PREVENTIVE_M: Final[int] = 15
POSTURE_ELEVATE_ALTITUDE_M: Final[int] = 25
ALTITUDE_DELTA_TERRAIN_M: Final[int] = 50

# 07 Flight Planning — terrain-aware 경로 생성 상수 (stub DEM: 지형고도=0m).
ROUTE_MIN_CLEARANCE_M: Final[float] = 50.0
ROUTE_MAX_CLIMB_RATE_M_PER_WP: Final[float] = 10.0

# 06 Response — 위협 이벤트 → 3분류 (PHYSICAL / REMOTE / NAVIGATION).
# 06 이 참조하는 공유 taxonomy. 레이어 간 직접 import 를 피하려 shared 에 둔다
# (이전 layer_05_risk.likelihood 에서 이관, CLAUDE.md 레이어 격리 규칙 준수).
THREAT_CATEGORY: Final[Mapping[str, str]] = MappingProxyType(
    {
        "T1": "REMOTE",
        "T2": "REMOTE",
        "T5": "REMOTE",
        "T3": "PHYSICAL",
        "T4": "PHYSICAL",
        "T7": "NAVIGATION",
    }
)
