"""
파일명: urban_flood_probability_agent.py
최종 수정일: 2025-12-14
버전: v5
파일 개요: 도시 집중 홍수 리스크 확률 P(H) 계산 Agent
변경 이력:
        - 2025-12-14: v5 - Hazard/Exposure 패턴 적용
                * _build_collected_data() 메서드 추가
                * calculate(lat, lon, ssp_scenario) 지원
                * ClimateDataLoader 기반 데이터 fetch
        - 2025-11-24: v4 - bin 구간 세분화 (5단계)
                * bin: [0], [1~2], [3~4], [5~7], [≥8] 호우일수 기준
                * DR_intensity: [0.00, 0.03, 0.10, 0.25, 0.45]
                * 고빈도 홍수 지역 판정 기준 반영
        - 2025-11-22: v3 - 순수 RAIN80 기반 (취약성 분리)
                * 강도지표: X_pflood = RAIN80 (호우일수)
                * bin: 호우일수 기준 [0~1), [1~3), [3~5), [≥5)
                * DR_intensity: [0.00, 0.05, 0.15, 0.35]
                * vulnerability_factor 제거 (취약성 에이전트에서 별도 처리)
        - 2025-11-22: v2 - RAIN80 + vulnerability_factor 방식 (deprecated)
        - 2025-11-21: v1 - AAL에서 확률 계산으로 분리
"""

from typing import Dict, Any
import numpy as np
from .base_probability_agent import BaseProbabilityAgent


class UrbanFloodProbabilityAgent(BaseProbabilityAgent):
    """
    도시 집중 홍수 리스크 확률 P(H) 계산 Agent

    사용 데이터: KMA RAIN80 (연간 80mm 이상 호우일수)
    강도지표: X_pflood(t) = RAIN80(t)
    취약성은 별도 취약성 에이전트에서 처리

    bin 설정 (호우일수 기준):
            - bin1: RAIN80 = 0일 (위험 거의 없음)
            - bin2: 1-2일 (저빈도 호우, 국지적 침수 가능)
            - bin3: 3-4일 (중간 위험, 배수 용량 초과 가능)
            - bin4: 5-7일 (반복적 도시침수 영역)
            - bin5: ≥8일 (고빈도 홍수 지역)
    """

    def __init__(self):
        """
        UrbanFloodProbabilityAgent 초기화

        bin 구간 (호우일수):
                - bin1: RAIN80 = 0일 (위험 거의 없음)
                - bin2: 1-2일 (저빈도 호우, 국지적 침수 가능)
                - bin3: 3-4일 (중간 위험, 배수 용량 초과 가능)
                - bin4: 5-7일 (반복적 도시침수 영역)
                - bin5: ≥8일 (고빈도 홍수 지역 판정 사례 다수)

        기본 손상률 (DR_intensity):
                - bin1: 0%
                - bin2: 3%
                - bin3: 10%
                - bin4: 25%
                - bin5: 45%
        """
        bins = [
            (0, 1),  # bin1: 0일 (위험 거의 없음)
            (1, 3),  # bin2: 1-2일 (저빈도 호우)
            (3, 5),  # bin3: 3-4일 (중간 위험)
            (5, 8),  # bin4: 5-7일 (반복적 침수)
            (8, float("inf")),  # bin5: ≥8일 (고빈도 홍수 지역)
        ]

        dr_intensity = [
            0.00,  # 0% (위험 거의 없음)
            0.03,  # 3% (저빈도 호우)
            0.10,  # 10% (중간 위험)
            0.25,  # 25% (반복적 침수)
            0.45,  # 45% (고빈도 홍수 지역)
        ]

        super().__init__(risk_type="urban_flood", bins=bins, dr_intensity=dr_intensity)

    def calculate_intensity_indicator(self, collected_data: Dict[str, Any]) -> np.ndarray:
        """
        도시 집중 홍수 강도지표 X_pflood(t) 계산

        X_pflood = RAIN80
        - RAIN80: 연간 80mm 이상 호우일수 (일)
        - 취약성은 별도 취약성 에이전트에서 처리

        Args:
                collected_data: 수집된 기후 데이터
                        - climate_data.rain80: 연도별 RAIN80 값 리스트 (호우일수)

        Returns:
                연도별 호우일수 배열
        """
        climate_data = collected_data.get("climate_data", {})
        rain80_data = climate_data.get("rain80", [])

        if not rain80_data:
            self.logger.warning("RAIN80 데이터가 없습니다. 기본값 0으로 설정합니다.")
            return np.array([0.0])

        rain80_array = np.array(rain80_data, dtype=float)

        self.logger.info(
            f"도시홍수 강도지표: {len(rain80_array)}개 연도, "
            f"RAIN80 범위: {rain80_array.min():.1f} ~ {rain80_array.max():.1f}일"
        )

        return rain80_array

    def _classify_into_bins(self, intensity_values: np.ndarray) -> np.ndarray:
        """
        RAIN80 값을 bin으로 분류 (도시 홍수 전용)

        Args:
                intensity_values: 연도별 RAIN80 값 배열 (호우일수)

        Returns:
                각 연도의 bin 인덱스 배열 (0-based)
        """
        bin_indices = np.zeros(len(intensity_values), dtype=int)

        for idx, value in enumerate(intensity_values):
            if value < 1:
                bin_indices[idx] = 0  # bin1: 0일 (위험 거의 없음)
            elif value < 3:
                bin_indices[idx] = 1  # bin2: 1-2일 (저빈도 호우)
            elif value < 5:
                bin_indices[idx] = 2  # bin3: 3-4일 (중간 위험)
            elif value < 8:
                bin_indices[idx] = 3  # bin4: 5-7일 (반복적 침수)
            else:
                bin_indices[idx] = 4  # bin5: ≥8일 (고빈도 홍수 지역)

        return bin_indices

    def _build_collected_data(self, timeseries_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        ClimateDataLoader에서 가져온 시계열 데이터를 collected_data 형식으로 변환

        Args:
                timeseries_data: get_flood_timeseries() 반환값
                        - years: 연도 리스트
                        - rx1day: RX1DAY 값 리스트
                        - rx5day: RX5DAY 값 리스트
                        - rain80: RAIN80 값 리스트 (호우일수)
                        - climate_scenario: SSP 시나리오

        Returns:
                calculate_probability()에 전달할 collected_data
        """
        rain80_list = timeseries_data.get("rain80", [])

        return {
            "climate_data": {
                "rain80": rain80_list,
            },
            "years": timeseries_data.get("years", []),
            "climate_scenario": timeseries_data.get("climate_scenario", "SSP245"),
        }

    def _get_fallback_data(self) -> Dict[str, Any]:
        """ClimateDataLoader가 없을 때 사용할 기본 데이터"""
        # 30년치 기본 RAIN80 데이터 생성 (3~8일 범위)
        default_rain80 = [3 + i * 0.1 for i in range(30)]
        return {
            "climate_data": {
                "rain80": default_rain80,
            },
        }
