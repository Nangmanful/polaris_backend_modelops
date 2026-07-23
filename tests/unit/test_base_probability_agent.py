"""BaseProbabilityAgent 단위 테스트.

검증 대상 (modelops/agents/probability_calculate/base_probability_agent.py):
- KDE 경로: 샘플 >= MIN_SAMPLES_FOR_KDE(3)에서 bin 확률 합 ~1, 각 확률 [0,1]
- 샘플 부족(< 3) 시 카운트(count) 폴백 발동
- 분산 0(모든 샘플 동일) 데이터에서 KDE 실패 -> count 폴백
- AAL = sum(P[i] x DR[i]) 계산 정확성
- calculation_details에 사용한 method('kde'/'count')와 time_unit 기록
- _classify_into_bins 경계값 (bin_min 포함, bin_max 미포함)

강도지표는 테스트용 서브클래스로 주입한다 (DB/네트워크 없음).
"""

import numpy as np
import pytest

from modelops.agents.probability_calculate.base_probability_agent import (
    MIN_SAMPLES_FOR_KDE,
    BaseProbabilityAgent,
)

DEFAULT_BINS = [(0.0, 10.0), (10.0, 20.0), (20.0, float("inf"))]
DEFAULT_DR = [0.001, 0.010, 0.050]


class StubProbabilityAgent(BaseProbabilityAgent):
    """강도지표를 직접 주입하는 테스트용 에이전트 (DB 로더 미사용)."""

    def __init__(self, intensity_values, bins=None, dr_intensity=None, time_unit="yearly"):
        super().__init__(
            risk_type="stub",
            bins=bins if bins is not None else list(DEFAULT_BINS),
            dr_intensity=dr_intensity if dr_intensity is not None else list(DEFAULT_DR),
            time_unit=time_unit,
        )
        self._intensity = np.array(intensity_values, dtype=float)
        # DB 로더 경로 차단 (calculate()를 쓰지 않지만 안전망)
        self._climate_loader_available = False

    def calculate_intensity_indicator(self, collected_data):
        return self._intensity


class TestKDEPath:
    def test_kde_used_when_enough_samples(self):
        # 30개 샘플 (연속적 분포, 분산 존재)
        rng = np.random.default_rng(42)
        samples = rng.uniform(1.0, 25.0, size=30)
        agent = StubProbabilityAgent(samples)

        result = agent.calculate_probability({})

        assert result["status"] == "completed"
        assert result["calculation_details"]["method"] == "kde"
        probs = result["bin_probabilities"]
        assert len(probs) == len(DEFAULT_BINS)
        assert all(0.0 <= p <= 1.0 for p in probs)
        # 정규화 불변식: 합이 ~1 (반환값은 소수 4자리 반올림)
        assert sum(probs) == pytest.approx(1.0, abs=1e-3)

    def test_kde_minimum_sample_threshold(self):
        # 정확히 MIN_SAMPLES_FOR_KDE개면 KDE 시도
        agent = StubProbabilityAgent([2.0, 12.0, 22.0])
        result = agent.calculate_probability({})
        assert result["status"] == "completed"
        assert result["calculation_details"]["method"] == "kde"
        assert sum(result["bin_probabilities"]) == pytest.approx(1.0, abs=1e-3)

    def test_aal_equals_sum_of_prob_times_dr(self):
        rng = np.random.default_rng(7)
        samples = rng.normal(15.0, 5.0, size=50)
        agent = StubProbabilityAgent(samples)

        result = agent.calculate_probability({})

        probs = result["bin_probabilities"]
        drs = result["bin_base_damage_rates"]
        expected_aal = sum(p * dr for p, dr in zip(probs, drs))
        # aal은 반올림 전 확률로 계산되므로 반올림 오차 허용
        assert result["aal"] == pytest.approx(expected_aal, abs=1e-4)


class TestCountFallback:
    def test_count_fallback_when_too_few_samples(self):
        # 샘플 2개 < MIN_SAMPLES_FOR_KDE(3) -> 이산적 카운트 방식
        assert MIN_SAMPLES_FOR_KDE == 3
        agent = StubProbabilityAgent([5.0, 15.0])

        result = agent.calculate_probability({})

        assert result["calculation_details"]["method"] == "count"
        assert result["bin_probabilities"] == [0.5, 0.5, 0.0]
        # AAL = 0.5*0.001 + 0.5*0.010 = 0.0055 (정확값)
        assert result["aal"] == pytest.approx(0.0055, abs=1e-9)

    def test_count_fallback_when_variance_zero(self):
        # 모든 샘플 동일 -> gaussian_kde 특이행렬 실패 -> count 폴백
        agent = StubProbabilityAgent([7.0] * 10)

        result = agent.calculate_probability({})

        assert result["status"] == "completed"
        assert result["calculation_details"]["method"] == "count"
        assert result["bin_probabilities"] == [1.0, 0.0, 0.0]
        assert result["aal"] == pytest.approx(0.001, abs=1e-9)

    def test_count_probabilities_sum_to_one(self):
        agent = StubProbabilityAgent([1.0, 11.0])
        probs = agent._calculate_bin_probabilities_count(np.array([1.0, 11.0, 21.0, 25.0]))
        assert sum(probs) == pytest.approx(1.0)
        assert probs == [0.25, 0.25, 0.5]


class TestBinClassification:
    def test_boundaries_min_inclusive_max_exclusive(self):
        agent = StubProbabilityAgent([0.0])
        values = np.array([0.0, 9.999, 10.0, 19.999, 20.0, 100.0])
        indices = agent._classify_into_bins(values)
        assert list(indices) == [0, 0, 1, 1, 2, 2]

    def test_value_below_first_bin_goes_to_lowest_bin(self):
        # 버그 리포트: 첫 bin 하한(0) 미만 값(예: 음수)이 for-else 폴백으로
        # "가장 극한" 마지막 bin에 분류되어 AAL을 과대평가한다.
        # 수정: 어떤 bin에도 속하지 않는 값 중 첫 bin 하한 미만은 bin 0으로 분류.
        agent = StubProbabilityAgent([0.0])
        indices = agent._classify_into_bins(np.array([-5.0]))
        assert list(indices) == [0]

    def test_value_above_last_finite_bin_goes_to_last_bin(self):
        # 마지막 bin 상한이 유한한 경우에도 초과 값은 마지막 bin으로
        agent = StubProbabilityAgent([0.0], bins=[(0.0, 10.0), (10.0, 20.0)], dr_intensity=[0.1, 0.2])
        indices = agent._classify_into_bins(np.array([25.0]))
        assert list(indices) == [1]


class TestCalculateAAL:
    def test_direct_formula(self):
        agent = StubProbabilityAgent([0.0])
        aal = agent._calculate_aal([0.7, 0.2, 0.1], [0.001, 0.010, 0.050])
        assert aal == pytest.approx(0.7 * 0.001 + 0.2 * 0.010 + 0.1 * 0.050)

    def test_zero_probabilities_give_zero_aal(self):
        agent = StubProbabilityAgent([0.0])
        assert agent._calculate_aal([0.0, 0.0, 0.0], DEFAULT_DR) == 0.0


class TestCalculationDetails:
    def test_details_record_method_and_bins(self):
        agent = StubProbabilityAgent([5.0, 15.0])  # count 경로
        result = agent.calculate_probability({})
        details = result["calculation_details"]

        assert details["method"] == "count"
        assert details["time_unit"] == "yearly"
        assert details["total_years"] == 2
        assert len(details["bins"]) == len(DEFAULT_BINS)
        # bin별 실제 샘플 수 기록
        assert [b["sample_count"] for b in details["bins"]] == [1, 1, 0]

    def test_monthly_time_unit_recorded(self):
        agent = StubProbabilityAgent([5.0, 15.0], time_unit="monthly")
        details = agent.calculate_probability({})["calculation_details"]
        assert details["time_unit"] == "monthly"
        assert details["total_months"] == 2
        assert "월" in details["formula"]

    def test_kde_method_recorded_in_details(self):
        rng = np.random.default_rng(1)
        agent = StubProbabilityAgent(rng.uniform(0.0, 30.0, size=20))
        details = agent.calculate_probability({})["calculation_details"]
        assert details["method"] == "kde"
        assert "KDE" in details["formula"]
