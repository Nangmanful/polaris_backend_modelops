"""SiteRiskCalculator H x E x V 통합 점수 단위 테스트.

검증 대상 (modelops/agents/site_assessment/site_risk_calculator.py):
- 통합 점수 = H x E x V / 10000 (H,E,V 모두 100 -> 100, 하나라도 0 -> 0)
- _classify_risk_level 5단계 경계값 (80/60/40/20)
- AAL 경로: final_aal = base_aal x F_vuln x (1 - insurance_rate)

DB 조회(DatabaseConnection)와 E/V 에이전트는 monkeypatch/스텁으로 대체한다.
실제 DB 연결은 절대 발생하지 않는다.
"""

import pytest

import modelops.agents.site_assessment.site_risk_calculator as src_module
from modelops.agents.site_assessment.site_risk_calculator import SiteRiskCalculator


def _bare_calculator():
    """__init__(DB 의존 준비 코드)을 우회한 인스턴스 생성."""
    calc = SiteRiskCalculator.__new__(SiteRiskCalculator)
    calc.scenario = "SSP245"
    calc.target_year = 2030
    return calc


class TestClassifyRiskLevel:
    @pytest.mark.parametrize(
        "score, expected",
        [
            (100.0, "Very High"),
            (80.0, "Very High"),   # 경계 포함
            (79.99, "High"),
            (60.0, "High"),
            (59.99, "Medium"),
            (40.0, "Medium"),
            (39.99, "Low"),
            (20.0, "Low"),
            (19.99, "Very Low"),
            (0.0, "Very Low"),
        ],
    )
    def test_boundaries(self, score, expected):
        calc = _bare_calculator()
        assert calc._classify_risk_level(score) == expected


class _StubExposureAgent:
    """리스크별 노출도 스텁: extreme_heat=90(very_high UHI), river_flood=100, urban_flood=0, 기타=50."""

    def calculate_exposure(self, collected_data):
        return {
            "heat_exposure": {"uhi_risk": "very_high"},
            "flood_exposure": {"score": 100.0},
            "urban_flood_exposure": {"score": 0.0},
        }


class _StubVulnerabilityAgent:
    """취약성 스텁: typhoon=0, 기타=100."""

    def calculate_vulnerability(self, collected_data):
        result = {}
        for risk in SiteRiskCalculator.RISK_TYPES:
            score = 0.0 if risk == "typhoon" else 100.0
            result[risk] = {"score": score, "level": "high", "factors": {}}
        return result


@pytest.fixture()
def patched_calculator(monkeypatch):
    """DB 조회를 결정론적 데이터로 대체한 계산기."""
    hazard_data = {
        risk: {"hazard_score": 1.0, "hazard_score_100": 100.0, "hazard_level": "Very High"}
        for risk in SiteRiskCalculator.RISK_TYPES
    }
    base_aals = {risk: {"aal": 0.02} for risk in SiteRiskCalculator.RISK_TYPES}

    monkeypatch.setattr(
        src_module.DatabaseConnection,
        "fetch_hazard_results",
        staticmethod(lambda lat, lon: hazard_data),
    )
    monkeypatch.setattr(
        src_module.DatabaseConnection,
        "fetch_probability_results",
        staticmethod(lambda lat, lon: base_aals),
    )

    calc = _bare_calculator()
    calc.exposure_agent = _StubExposureAgent()
    calc.vulnerability_agent = _StubVulnerabilityAgent()
    return calc


class TestIntegratedScore:
    def test_hev_formula_and_boundaries(self, patched_calculator):
        result = patched_calculator.calculate_site_risks(
            latitude=37.5665,
            longitude=126.9780,
            building_info={},
            asset_info={"insurance_coverage_rate": 0.1},
            site_id="test-site",
        )

        integrated = result["integrated_risk"]

        # H=100, E=100, V=100 -> 100 x 100 x 100 / 10000 = 100 (최대)
        assert integrated["river_flood"]["integrated_risk_score"] == pytest.approx(100.0)
        assert integrated["river_flood"]["risk_level"] == "Very High"

        # E=0 이면 점수 0 (0 포함 시 0)
        assert integrated["urban_flood"]["integrated_risk_score"] == pytest.approx(0.0)
        assert integrated["urban_flood"]["risk_level"] == "Very Low"

        # V=0 이면 점수 0
        assert integrated["typhoon"]["integrated_risk_score"] == pytest.approx(0.0)
        assert integrated["typhoon"]["risk_level"] == "Very Low"

        # extreme_heat: UHI very_high -> E=90 -> 100 x 90 x 100 / 10000 = 90
        assert integrated["extreme_heat"]["integrated_risk_score"] == pytest.approx(90.0)

        # 기타 리스크 (기본 E=50): 100 x 50 x 100 / 10000 = 50 -> Medium
        assert integrated["drought"]["integrated_risk_score"] == pytest.approx(50.0)
        assert integrated["drought"]["risk_level"] == "Medium"

    def test_aal_scaling_path(self, patched_calculator):
        result = patched_calculator.calculate_site_risks(
            latitude=37.5665,
            longitude=126.9780,
            building_info={},
            asset_info={"insurance_coverage_rate": 0.1},
        )

        aal = result["aal_scaled"]

        # V=100 -> F_vuln=1.1: 0.02 x 1.1 x 0.9 = 0.0198
        assert aal["extreme_heat"]["vulnerability_scale"] == pytest.approx(1.1)
        assert aal["extreme_heat"]["final_aal"] == pytest.approx(0.0198)

        # V=0 -> F_vuln=0.9: 0.02 x 0.9 x 0.9 = 0.0162
        assert aal["typhoon"]["vulnerability_scale"] == pytest.approx(0.9)
        assert aal["typhoon"]["final_aal"] == pytest.approx(0.0162)

    def test_summary_consistency(self, patched_calculator):
        result = patched_calculator.calculate_site_risks(
            latitude=37.5665, longitude=126.9780, building_info={}
        )
        summary = result["summary"]
        assert summary["risk_count"] == len(SiteRiskCalculator.RISK_TYPES)
        # 최고 통합 리스크는 river_flood (score 100)
        assert summary["highest_integrated_risk"]["risk_type"] == "river_flood"
        assert summary["highest_integrated_risk"]["integrated_risk_score"] == pytest.approx(100.0)
