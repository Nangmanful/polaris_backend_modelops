"""
파일명: river_flood_probability_agent.py
최종 수정일: 2025-12-14
버전: v2
파일 개요: 내륙 홍수 리스크 확률 P(H) 계산 Agent
변경 이력:
        - 2025-12-14: v2 - Hazard/Exposure 패턴 적용
                * _build_collected_data() 메서드 추가
                * calculate(lat, lon, ssp_scenario) 지원
                * ClimateDataLoader 기반 데이터 fetch
        - 2025-11-21: v1 - AAL에서 확률 계산으로 분리
                * 강도지표: X_rflood(t) = RX1DAY(t)
                * bin: 기준기간 분위수 기반 (<Q80), [Q80~Q95), [Q95~Q99), [≥Q99)
                * DR_intensity: [0.00, 0.02, 0.08, 0.20]
                * 취약성 스케일링 제거
"""

from typing import Dict, Any
import numpy as np
from .base_probability_agent import BaseProbabilityAgent


class RiverFloodProbabilityAgent(BaseProbabilityAgent):
    """
    내륙 홍수 리스크 확률 P(H) 계산 Agent

    사용 데이터: KMA 연간 강수 극값 지수 RX1DAY
    강도지표: X_rflood(t) = RX1DAY(t)
    bin: 기준기간(예: 1991-2020) 분포 기반 분위수로 구간 설정
    """

    def __init__(self):
        """
        RiverFloodProbabilityAgent 초기화

        bin 구간은 기준기간 데이터 분석 후 동적으로 설정
        초기값은 임시값이며, calculate_probability 호출 시 재설정됨
        """
        bins = [
            (0, 100),  # bin1: < Q80 (임시)
            (100, 150),  # bin2: Q80 ~ Q95 (임시)
            (150, 200),  # bin3: Q95 ~ Q99 (임시)
            (200, float("inf")),  # bin4: >= Q99 (임시)
        ]

        dr_intensity = [
            0.00,  # 0% - 평범한 강우
            0.02,  # 2% - 상위 20% 강우
            0.08,  # 8% - 상위 5% 강우
            0.20,  # 20% - 상위 1% 강우
        ]

        super().__init__(risk_type="river_flood", bins=bins, dr_intensity=dr_intensity)

    def calculate_intensity_indicator(self, collected_data: Dict[str, Any]) -> np.ndarray:
        """
        내륙 홍수 강도지표 X_rflood(t) 계산
        X_rflood(t) = RX1DAY(t)

        Args:
                collected_data: 수집된 기후 데이터
                        - rx1day: 연도별 RX1DAY 값 리스트 또는 배열
                        - baseline_years: 기준기간 데이터 (옵션, 분위수 계산용)

        Returns:
                연도별 RX1DAY 값 배열
        """
        climate_data = collected_data.get("climate_data", {})
        rx1day_data = climate_data.get("rx1day", [])

        if not rx1day_data:
            self.logger.warning("RX1DAY 데이터가 없습니다. 기본값 0으로 설정합니다.")
            return np.array([0.0])

        rx1day_array = np.array(rx1day_data, dtype=float)

        # 기준기간 데이터가 있으면 분위수 기반 bin 재설정
        baseline_data = climate_data.get("baseline_rx1day", rx1day_data)
        baseline_array = np.array(baseline_data, dtype=float)

        # 분위수 계산 (80%, 95%, 99%)
        q80 = np.percentile(baseline_array, 80)
        q95 = np.percentile(baseline_array, 95)
        q99 = np.percentile(baseline_array, 99)

        # bin 재설정
        self.bins = [(0, q80), (q80, q95), (q95, q99), (q99, float("inf"))]

        self.logger.info(f"RX1DAY 기준기간 분위수: Q80={q80:.2f}, Q95={q95:.2f}, Q99={q99:.2f}")
        self.logger.info(
            f"RX1DAY 데이터: {len(rx1day_array)}개 연도, "
            f"범위: {rx1day_array.min():.2f} ~ {rx1day_array.max():.2f}"
        )

        return rx1day_array

    def _build_collected_data(self, timeseries_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        ClimateDataLoader에서 가져온 시계열 데이터를 collected_data 형식으로 변환

        Args:
                timeseries_data: get_flood_timeseries() 반환값
                        - years: 연도 리스트
                        - rx1day: RX1DAY 값 리스트
                        - rx5day: RX5DAY 값 리스트
                        - rain80: RAIN80 값 리스트
                        - climate_scenario: SSP 시나리오

        Returns:
                calculate_probability()에 전달할 collected_data
        """
        rx1day_list = timeseries_data.get("rx1day", [])

        # 기준기간 데이터 (첫 30년을 baseline으로 사용)
        baseline_rx1day = rx1day_list[:30] if len(rx1day_list) >= 30 else rx1day_list

        return {
            "climate_data": {
                "rx1day": rx1day_list,
                "baseline_rx1day": baseline_rx1day,
            },
            "years": timeseries_data.get("years", []),
            "climate_scenario": timeseries_data.get("climate_scenario", "SSP245"),
        }

    def _get_fallback_data(self) -> Dict[str, Any]:
        """ClimateDataLoader가 없을 때 사용할 기본 데이터"""
        # 30년치 기본 RX1DAY 데이터 생성 (100~200mm 범위)
        default_rx1day = [100 + i * 3 for i in range(30)]
        return {
            "climate_data": {
                "rx1day": default_rx1day,
                "baseline_rx1day": default_rx1day,
            },
        }
