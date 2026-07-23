"""
파일명: drought_probability_agent.py
최종 수정일: 2025-12-14
버전: v3.0
파일 개요: 가뭄 리스크 확률 P(H) 계산 Agent
변경 이력:
        - 2025-12-14: v3.0 - Hazard/Exposure 패턴 적용
                * _build_collected_data() 메서드 추가
                * calculate(lat, lon, ssp_scenario) 지원
                * ClimateDataLoader 기반 데이터 fetch
        - 2025-12-11: v2.0 - 월별 SPEI12에서 연도별 최솟값으로 변경
                * 강도지표: X_drought(t) = min SPEI12(t,m) (연도별 최솟값)
                * 연도별 AAL 계산으로 다른 에이전트와 통일
                * time_unit='monthly' 제거
        - 2025-11-22: v1.1 - flat list 데이터 형식 지원 추가
                * spei12 (flat list) 또는 spei12_monthly (nested dict) 모두 처리
        - 2025-11-21: v1 - AAL에서 확률 계산으로 분리
                * 강도지표: X_drought(t,m) = SPEI12(t,m) (월별)
                * bin: (>-1), [-1~-1.5), [-1.5~-2.0), (≤-2.0)
                * DR_intensity: [0.00, 0.02, 0.07, 0.20]
                * 월 기반 발생확률: P_drought[i] = (해당 bin에 속한 월 수) / (총 월 수)
                * 취약성 스케일링 제거
"""

from typing import Dict, Any
import numpy as np
from .base_probability_agent import BaseProbabilityAgent


class DroughtProbabilityAgent(BaseProbabilityAgent):
    """
    가뭄 리스크 확률 P(H) 계산 Agent

    사용 데이터: KMA SPEI12 (Standardized Precipitation-Evapotranspiration Index 12개월)
    강도지표: X_drought(t) = min SPEI12(t,m) (연도별 최솟값 - 가장 심한 가뭄)
    """

    def __init__(self):
        """
        DroughtProbabilityAgent 초기화

        bin 구간:
                - bin1: SPEI12 > -1 (정상~약한 가뭄)
                - bin2: -1 >= SPEI12 > -1.5 (중간 가뭄)
                - bin3: -1.5 >= SPEI12 > -2.0 (심각 가뭄)
                - bin4: SPEI12 <= -2.0 (극심 가뭄)

        기본 손상률 (DR_intensity):
                - bin1: 0%
                - bin2: 2%
                - bin3: 7%
                - bin4: 20%
        """
        bins = [
            (-1, float("inf")),  # SPEI12 > -1
            (-1.5, -1),  # -1.5 < SPEI12 <= -1
            (-2.0, -1.5),  # -2.0 < SPEI12 <= -1.5
            (float("-inf"), -2.0),  # SPEI12 <= -2.0
        ]

        dr_intensity = [0.00, 0.02, 0.07, 0.20]  # 0%  # 2%  # 7%  # 20%

        super().__init__(risk_type="drought", bins=bins, dr_intensity=dr_intensity)

    def calculate_intensity_indicator(self, collected_data: Dict[str, Any]) -> np.ndarray:
        """
        가뭄 강도지표 X_drought(t) 계산
        X_drought(t) = min SPEI12(t,m) (연도별 최솟값 - 가장 심한 가뭄)

        Args:
                collected_data: 수집된 기후 데이터
                        - climate_data:
                                - spei12: 월별 SPEI12 flat list [v1, v2, ...] (권장)
                                  (연도별로 12개월씩 정렬된 것으로 가정)
                                - spei12_monthly: 연도별 월별 SPEI12 데이터 리스트 (레거시)
                                        각 원소는 {'year': int, 'months': [spei12_values]}

        Returns:
                연도별 최솟값 SPEI12 값 배열
        """
        climate_data = collected_data.get("climate_data", {})

        # 1. flat list 형식 (우선)
        spei12_flat = climate_data.get("spei12", [])
        if spei12_flat:
            # 연도별 최솟값 계산 (12개월씩 묶음)
            yearly_min_spei12 = self._calculate_yearly_min(spei12_flat)

            self.logger.info(
                f"SPEI12 데이터 (flat): {len(spei12_flat)}개 월 → {len(yearly_min_spei12)}개 연도, "
                f"범위: {yearly_min_spei12.min():.2f} ~ {yearly_min_spei12.max():.2f}"
            )
            return yearly_min_spei12

        # 2. nested dict 형식 (레거시)
        spei12_monthly = climate_data.get("spei12_monthly", [])
        if spei12_monthly:
            yearly_min_spei12 = []

            for year_data in spei12_monthly:
                months = year_data.get("months", [])

                # 해당 연도의 최솟값 SPEI12 (가장 심한 가뭄)
                if months:
                    yearly_min_spei12.append(min(months))
                else:
                    yearly_min_spei12.append(0.0)

            if yearly_min_spei12:
                spei12_array = np.array(yearly_min_spei12, dtype=float)
                self.logger.info(
                    f"SPEI12 데이터 (nested): {len(yearly_min_spei12)}개 연도, "
                    f"범위: {spei12_array.min():.2f} ~ {spei12_array.max():.2f}"
                )
                return spei12_array

        self.logger.warning("SPEI12 데이터가 없습니다. 기본값 0으로 설정합니다.")
        return np.array([0.0])

    def _calculate_yearly_min(self, monthly_spei12: list) -> np.ndarray:
        """
        월별 SPEI12 데이터를 연도별 최솟값으로 변환

        Args:
                monthly_spei12: 월별 SPEI12 값 리스트 (12개월 단위로 정렬됨)

        Returns:
                연도별 최솟값 SPEI12 값 배열
        """
        if not monthly_spei12:
            return np.array([0.0])

        # 12개월씩 묶어서 최솟값 계산
        n_years = len(monthly_spei12) // 12
        yearly_min = []

        for year_idx in range(n_years):
            start_idx = year_idx * 12
            end_idx = start_idx + 12
            year_months = monthly_spei12[start_idx:end_idx]

            if year_months:
                yearly_min.append(min(year_months))
            else:
                yearly_min.append(0.0)

        # 나머지 월이 있으면 (12로 나누어떨어지지 않는 경우)
        remaining_months = len(monthly_spei12) % 12
        if remaining_months > 0:
            self.logger.warning(
                f"월별 SPEI12 데이터가 12로 나누어떨어지지 않습니다. "
                f"전체 {len(monthly_spei12)}개월 중 마지막 {remaining_months}개월은 별도 연도로 처리됩니다. "
                f"데이터 정합성을 확인하세요."
            )
            remaining_spei12 = monthly_spei12[n_years * 12 :]
            if remaining_spei12:
                yearly_min.append(min(remaining_spei12))

        return np.array(yearly_min, dtype=float)

    def _classify_into_bins(self, intensity_values: np.ndarray) -> np.ndarray:
        """
        SPEI12 값을 bin으로 분류 (가뭄 전용 - 음수 값 처리)

        Args:
                intensity_values: 연도별 SPEI12 값 배열

        Returns:
                각 연도의 bin 인덱스 배열 (0-based)
        """
        bin_indices = np.zeros(len(intensity_values), dtype=int)

        for idx, value in enumerate(intensity_values):
            if value > -1:
                bin_indices[idx] = 0  # bin1: SPEI12 > -1
            elif value > -1.5:
                bin_indices[idx] = 1  # bin2: -1.5 < SPEI12 <= -1
            elif value > -2.0:
                bin_indices[idx] = 2  # bin3: -2.0 < SPEI12 <= -1.5
            else:
                bin_indices[idx] = 3  # bin4: SPEI12 <= -2.0

        return bin_indices

    def _build_collected_data(self, timeseries_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        ClimateDataLoader에서 가져온 시계열 데이터를 collected_data 형식으로 변환

        Args:
                timeseries_data: get_drought_timeseries() 반환값
                        - years: 연도 리스트
                        - cdd: CDD 값 리스트
                        - spei12: SPEI12 값 리스트
                        - climate_scenario: SSP 시나리오

        Returns:
                calculate_probability()에 전달할 collected_data
        """
        spei12_list = timeseries_data.get("spei12", [])

        return {
            "climate_data": {
                "spei12": spei12_list,
            },
            "years": timeseries_data.get("years", []),
            "climate_scenario": timeseries_data.get("climate_scenario", "SSP245"),
        }

    def _get_fallback_data(self) -> Dict[str, Any]:
        """ClimateDataLoader가 없을 때 사용할 기본 데이터"""
        # 30년치 기본 SPEI12 데이터 생성 (-0.5 ~ -1.5 범위)
        default_spei12 = [-0.5 - i * 0.03 for i in range(30)]
        return {
            "climate_data": {
                "spei12": default_spei12,
            },
        }
