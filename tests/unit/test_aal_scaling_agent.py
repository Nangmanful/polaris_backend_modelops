"""AALScalingAgent 단위 테스트.

검증 대상 (modelops/agents/risk_assessment/aal_scaling_agent.py):
- F_vuln = 0.9 + (V/100) x 0.2 공식과 경계값 (V=0 -> 0.9, V=50 -> 1.0, V=100 -> 1.1)
- final_aal = base_aal x F_vuln x (1 - insurance_rate), % 단위 변환
- 예상손실액 expected_loss = int(final_aal_ratio x asset_value)
- AAL 등급 7단계 경계값 ('-', '0~3%', '~6%', '~10%', '~16%', '~30%', '30%~')
"""

import pytest

from modelops.agents.risk_assessment.aal_scaling_agent import AALScalingAgent


@pytest.fixture()
def agent():
    return AALScalingAgent()


class TestVulnerabilityScale:
    """F_vuln = 0.9 + (V/100) x 0.2"""

    @pytest.mark.parametrize(
        "v_score, expected",
        [
            (0.0, 0.9),      # 하한 경계
            (50.0, 1.0),     # 중앙값 -> 변화 없음
            (100.0, 1.1),    # 상한 경계
            (25.0, 0.95),
            (75.0, 1.05),
        ],
    )
    def test_formula_boundaries(self, agent, v_score, expected):
        assert agent._calculate_vulnerability_scale(v_score) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "v_score, expected",
        [
            (-10.0, 0.9),    # 범위 밖 하한 -> 0.9로 클램프
            (150.0, 1.1),    # 범위 밖 상한 -> 1.1로 클램프
        ],
    )
    def test_out_of_range_clamped(self, agent, v_score, expected):
        assert agent._calculate_vulnerability_scale(v_score) == pytest.approx(expected)


class TestScaleAAL:
    """final_aal = base_aal x F_vuln x (1 - insurance_rate)"""

    def test_neutral_vulnerability_no_insurance(self, agent):
        result = agent.scale_aal(base_aal=0.05, vulnerability_score=50.0)
        # V=50 -> F_vuln=1.0, 보험 없음 -> final == base (% 단위)
        assert result["vulnerability_scale"] == pytest.approx(1.0)
        assert result["base_aal"] == pytest.approx(5.0)
        assert result["final_aal"] == pytest.approx(5.0)
        assert result["insurance_rate"] == 0.0
        assert result["expected_loss"] is None

    def test_full_formula_with_insurance_and_asset(self, agent):
        result = agent.scale_aal(
            base_aal=0.05,
            vulnerability_score=100.0,
            insurance_rate=0.2,
            asset_value=1_000_000_000,
        )
        # F_vuln = 1.1, ratio = 0.05 * 1.1 * 0.8 = 0.044
        assert result["vulnerability_scale"] == pytest.approx(1.1)
        assert result["final_aal"] == pytest.approx(4.4)
        # expected_loss = int(0.044 * 10억) = 44,000,000
        assert result["expected_loss"] == 44_000_000

    def test_vulnerability_zero_reduces_aal(self, agent):
        result = agent.scale_aal(base_aal=0.10, vulnerability_score=0.0)
        assert result["vulnerability_scale"] == pytest.approx(0.9)
        assert result["final_aal"] == pytest.approx(9.0)

    def test_full_insurance_zeroes_final_aal(self, agent):
        result = agent.scale_aal(
            base_aal=0.10, vulnerability_score=50.0, insurance_rate=1.0, asset_value=1_000_000
        )
        assert result["final_aal"] == pytest.approx(0.0)
        assert result["expected_loss"] == 0

    def test_no_expected_loss_when_asset_zero_or_none(self, agent):
        assert agent.scale_aal(0.05, 50.0, asset_value=None)["expected_loss"] is None
        assert agent.scale_aal(0.05, 50.0, asset_value=0)["expected_loss"] is None
        assert agent.scale_aal(0.05, 50.0, asset_value=-100)["expected_loss"] is None

    def test_zero_base_aal(self, agent):
        result = agent.scale_aal(base_aal=0.0, vulnerability_score=100.0, asset_value=1_000_000)
        assert result["final_aal"] == 0.0
        assert result["expected_loss"] == 0


class TestBatchScaleAALs:
    def test_batch_applies_per_risk(self, agent):
        aal_data = {
            "extreme_heat": {"base_aal": 0.02, "vulnerability_score": 100.0},
            "drought": {"base_aal": 0.01, "vulnerability_score": 0.0},
        }
        results = agent.batch_scale_aals(aal_data)
        assert set(results.keys()) == {"extreme_heat", "drought"}
        assert results["extreme_heat"]["final_aal"] == pytest.approx(2.2)
        assert results["drought"]["final_aal"] == pytest.approx(0.9)

    def test_batch_default_vulnerability_is_50(self, agent):
        results = agent.batch_scale_aals({"typhoon": {"base_aal": 0.03}})
        assert results["typhoon"]["vulnerability_scale"] == pytest.approx(1.0)


class TestClassifyAALGrade:
    """등급 7단계 경계값 (final_aal은 % 단위)"""

    @pytest.mark.parametrize(
        "final_aal, expected",
        [
            (-1.0, "-"),       # 음수 -> 발생 원천 없음
            (0.0, "-"),        # 0% 이하 경계
            (0.0001, "0~3%"),  # 0 초과 첫 구간
            (2.999, "0~3%"),
            (3.0, "~6%"),      # 3% 경계 (상위 구간 편입)
            (5.999, "~6%"),
            (6.0, "~10%"),     # 6% 경계
            (9.999, "~10%"),
            (10.0, "~16%"),    # 10% 경계
            (15.999, "~16%"),
            (16.0, "~30%"),    # 16% 경계
            (29.999, "~30%"),
            (30.0, "30%~"),    # 30% 경계
            (100.0, "30%~"),
        ],
    )
    def test_grade_boundaries(self, agent, final_aal, expected):
        assert agent.classify_aal_grade(final_aal) == expected

    def test_classify_aal_grades_returns_grade_string_per_risk(self, agent):
        # 참고: docstring은 dict 반환을 명시하지만 실제 구현은 등급 문자열을 반환한다.
        # (grade_description 등을 담는 dict 구성 코드는 주석 처리되어 있음)
        # 여기서는 현재 동작을 고정한다.
        scaled = {
            "extreme_heat": {"final_aal": 4.4},
            "typhoon": {"final_aal": 0.0},
        }
        grades = agent.classify_aal_grades(scaled)
        assert grades == {"extreme_heat": "~6%", "typhoon": "-"}
