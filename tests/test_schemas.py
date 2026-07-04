"""schemas.py 검증 — 필수 키 이름이 D4D 문서와 일치하는지."""

from typing import get_type_hints

from onboard.shared import schemas as S


class TestChannelOutput:
    def test_required_keys(self) -> None:
        hints = get_type_hints(S.ChannelOutput)
        assert set(hints.keys()) == {"channel", "state", "quality", "quality_delta", "payload"}


class TestAbstractionOutput:
    def test_required_keys(self) -> None:
        hints = get_type_hints(S.AbstractionOutput)
        assert set(hints.keys()) == {"schema_version", "id", "ts", "channels"}


class TestThreatCandidate:
    def test_required_keys(self) -> None:
        hints = get_type_hints(S.ThreatCandidate)
        expected_required = {
            "threat_event",
            "match_count",
            "confidence",
            "confidence_source",
            "kill_chain_stage",
            "potential_outcome",
        }
        # context 는 NotRequired 지만 get_type_hints 는 반환에 포함.
        assert expected_required.issubset(set(hints.keys()))


class TestThreatModelingOutput:
    def test_required_keys(self) -> None:
        hints = get_type_hints(S.ThreatModelingOutput)
        expected = {
            "declared_phase",
            "mission_phase_confidence",
            "candidates",
            "primary",
            "background_exposure_score",
        }
        assert expected.issubset(set(hints.keys()))


class TestRiskCandidate:
    def test_inherits_threat_candidate_fields(self) -> None:
        hints = get_type_hints(S.RiskCandidate)
        # ThreatCandidate 상속 → threat_event 등 그대로.
        assert "threat_event" in hints
        # RiskCandidate 자체 필드.
        assert "rac" in hints
        assert "l_class_final" in hints
        assert "severity_label_final" in hints
        assert "compound_risk_assessment" in hints
        assert "compound_urgency_score" in hints
        assert "priority_rank" in hints


class TestRiskAssessmentOutput:
    def test_required_keys(self) -> None:
        hints = get_type_hints(S.RiskAssessmentOutput)
        assert "candidates" in hints
        assert "ambient_rac" in hints


class TestResponseOutput:
    def test_required_keys(self) -> None:
        hints = get_type_hints(S.ResponseOutput)
        expected = {
            "primary_threat_event",
            "rac",
            "kill_chain_stage",
            "threat_category",
            "flight_action",
            "comms_level",
            "payload_action",
            "nav_mode",
            "special_action",
            "secondary_threats",
            "ai_reliability",
        }
        assert expected == set(hints.keys())


class TestFlightPlanOutput:
    def test_required_keys(self) -> None:
        hints = get_type_hints(S.FlightPlanOutput)
        expected = {
            "flight_action",
            "target_bearing_deg",
            "altitude_delta_m",
            "replan_scope",
            "reroute_anchor",
            "route",
        }
        assert expected == set(hints.keys())


class TestMissionBrief:
    def test_required_keys(self) -> None:
        hints = get_type_hints(S.MissionBrief)
        assert "sortie_id" in hints
        assert "mission_context" in hints
        assert "posture" in hints
        assert "drone_profile" in hints
        assert "corridor" in hints
        assert "weights" in hints
