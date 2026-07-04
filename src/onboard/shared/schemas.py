"""D4D 파이프라인 레이어 간 I/O 스키마.

TypedDict 로 IDE 힌트만 제공. 런타임 검증 없음 (ADR-004).
채널별 payload 세부 필드는 dict 로 두고, 각 채널 구현 단계에서 확정한다.
"""

from typing import Literal, NotRequired, TypedDict

# ---------------------------------------------------------------------------
# 03. Sensor Abstraction Layer 출력
# ---------------------------------------------------------------------------

ChannelState = Literal["normal", "degraded", "anomaly"]


class ChannelOutput(TypedDict):
    channel: str
    state: ChannelState
    quality: float
    quality_delta: float
    payload: dict


class AbstractionOutput(TypedDict):
    schema_version: str
    id: str
    ts: int
    channels: list[ChannelOutput]


# ---------------------------------------------------------------------------
# 04. Threat Modeling 출력
# ---------------------------------------------------------------------------

ConfidenceSource = Literal["ai", "deterministic"]
KillChainStage = Literal["초기", "중기", "후기"]


class ThreatCandidate(TypedDict):
    threat_event: str
    match_count: int
    confidence: float
    confidence_source: ConfidenceSource
    kill_chain_stage: KillChainStage
    potential_outcome: str
    context: NotRequired[dict]


class ThreatModelingOutput(TypedDict):
    declared_phase: str
    mission_phase_confidence: float
    candidates: list[ThreatCandidate]
    primary: ThreatCandidate | None
    background_exposure_score: float
    cycle_context: NotRequired[dict]


# ---------------------------------------------------------------------------
# 05. Risk Assessment 출력
# ---------------------------------------------------------------------------

RacLabel = Literal["High", "Serious", "Medium", "Low"]
LClass = Literal["A", "B", "C", "D", "E", "F"]
SeverityLabel = Literal["Catastrophic", "Critical", "Marginal", "Negligible"]


class RiskCandidate(ThreatCandidate):
    rac: RacLabel
    l_class_final: LClass
    severity_label_final: SeverityLabel
    compound_risk_assessment: dict
    compound_urgency_score: float
    priority_rank: int


class RiskAssessmentOutput(TypedDict):
    candidates: list[RiskCandidate]
    ambient_rac: NotRequired[Literal["Medium", "Low"] | None]


# ---------------------------------------------------------------------------
# 06. Response 출력
# ---------------------------------------------------------------------------

ThreatCategory = Literal["PHYSICAL", "REMOTE", "NAVIGATION"]
AiReliability = Literal["normal", "low"]


class ResponseOutput(TypedDict):
    primary_threat_event: str | None
    rac: str
    kill_chain_stage: str | None
    threat_category: ThreatCategory | None
    flight_action: str
    comms_level: str
    payload_action: list[str]
    nav_mode: str | None
    special_action: str | None
    secondary_threats: list[dict]
    ai_reliability: AiReliability


# ---------------------------------------------------------------------------
# 07. Flight Planning 출력
# ---------------------------------------------------------------------------

ReplanScope = Literal["NONE", "LOCAL", "FULL"]


class FlightPlanOutput(TypedDict):
    flight_action: str
    target_bearing_deg: float | None
    altitude_delta_m: int
    replan_scope: ReplanScope
    reroute_anchor: str | None
    route: list  # terrain-aware waypoints: [{lat, lon, alt_m, clearance_m}, ...]


# ---------------------------------------------------------------------------
# mission_brief — 임무 시작 시 확정, 사이클 동안 불변
# ---------------------------------------------------------------------------

MissionContext = Literal["정찰", "타격", "호송", "수송"]


class MissionBrief(TypedDict):
    sortie_id: str
    mission_context: MissionContext
    posture: dict
    drone_profile: dict
    corridor: dict
    weights: dict
