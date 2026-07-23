"""ExtremeHeatProbabilityAgent 단위 테스트.

검증 대상 (modelops/agents/probability_calculate/extreme_heat_probability_agent.py):
- 강도지표 X_heat(t) = WSDI(t) (입력 그대로 반환, 순수 함수)
- 기준기간 분위수(Q80/Q90/Q95/Q99) 기반 bin 동적 설정
- 기준기간 데이터 부족(<10) 시 기본 임계값 폴백 {80:3, 90:8, 95:15, 99:25}
- 분위수 기반 bin 분류 경계값
- calculate_probability 엔드투엔드 (DB 없이 collected_data 주입)
"""

import numpy as np
import pytest

from modelops.agents.probability_calculate.extreme_heat_probability_agent import (
    ExtremeHeatProbabilityAgent,
)


@pytest.fixture()
def agent():
    return ExtremeHeatProbabilityAgent()


class TestIntensityIndicator:
    def test_wsdi_passthrough(self, agent):
        collected = {
            "climate_data": {"wsdi": [3.0, 8.0, 15.0]},
            "baseline_wsdi": list(range(20)),  # 분위수 설정용
        }
        values = agent.calculate_intensity_indicator(collected)
        np.testing.assert_allclose(values, [3.0, 8.0, 15.0])

    def test_missing_wsdi_defaults_to_zero(self, agent):
        values = agent.calculate_intensity_indicator({"climate_data": {}})
        np.testing.assert_allclose(values, [0.0])


class TestBaselinePercentiles:
    def test_percentiles_from_baseline_data(self, agent):
        baseline = np.arange(0, 101, dtype=float)  # 0..100
        agent.set_baseline_percentiles(baseline)

        assert agent.percentile_thresholds[80] == pytest.approx(80.0)
        assert agent.percentile_thresholds[90] == pytest.approx(90.0)
        assert agent.percentile_thresholds[95] == pytest.approx(95.0)
        assert agent.percentile_thresholds[99] == pytest.approx(99.0)

        # bins가 분위수 기준으로 갱신됨
        assert agent.bins[0] == (0, pytest.approx(80.0))
        assert agent.bins[4][0] == pytest.approx(99.0)
        assert agent.bins[4][1] == float("inf")

    def test_fallback_thresholds_when_insufficient_baseline(self, agent):
        agent.set_baseline_percentiles(np.array([1.0, 2.0, 3.0]))  # < 10개
        assert agent.percentile_thresholds == {80: 3, 90: 8, 95: 15, 99: 25}
        assert agent.bins[0] == (0, 3)
        assert agent.bins[4] == (25, float("inf"))


class TestQuantileBinClassification:
    def test_classification_against_known_thresholds(self, agent):
        agent.set_baseline_percentiles(np.array([1.0]))  # 폴백: Q80=3, Q90=8, Q95=15, Q99=25
        values = np.array([0.0, 2.9, 3.0, 7.9, 8.0, 14.9, 15.0, 24.9, 25.0, 40.0])
        indices = agent._classify_into_bins(values)
        #        <3 ->0, [3,8) ->1, [8,15) ->2, [15,25) ->3, >=25 ->4
        assert list(indices) == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]


class TestEndToEnd:
    def test_calculate_probability_deterministic(self, agent):
        # 40년 WSDI 시계열 (결정론적), 첫 30년을 baseline으로 사용
        wsdi = [float(2 + (i % 20)) for i in range(40)]
        collected = {
            "climate_data": {"wsdi": wsdi},
            "baseline_wsdi": wsdi[:30],
        }

        result = agent.calculate_probability(collected)

        assert result["status"] == "completed"
        assert result["risk_type"] == "extreme_heat"
        probs = result["bin_probabilities"]
        assert len(probs) == 5
        assert all(0.0 <= p <= 1.0 for p in probs)
        assert sum(probs) == pytest.approx(1.0, abs=1e-3)
        # AAL은 DR 범위(0.001~0.035) 안의 가중평균이어야 함
        assert 0.001 <= result["aal"] <= 0.035
        assert result["calculation_details"]["method"] in ("kde", "count")

    def test_fallback_data_runs_without_loader(self, agent):
        # _get_fallback_data() 기반 계산 (ClimateDataLoader 불필요)
        collected = agent._get_fallback_data()
        result = agent.calculate_probability(collected)
        assert result["status"] == "completed"
        assert sum(result["bin_probabilities"]) == pytest.approx(1.0, abs=1e-3)


class TestBuildCollectedData:
    def test_baseline_is_first_30_years(self, agent):
        wsdi = list(range(40))
        collected = agent._build_collected_data({"wsdi": wsdi, "txx": [], "years": []})
        assert collected["baseline_wsdi"] == wsdi[:30]
        assert collected["climate_data"]["wsdi"] == wsdi

    def test_short_series_uses_all_as_baseline(self, agent):
        wsdi = list(range(10))
        collected = agent._build_collected_data({"wsdi": wsdi})
        assert collected["baseline_wsdi"] == wsdi
