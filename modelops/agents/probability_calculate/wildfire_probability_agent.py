"""
파일명: wildfire_probability_agent.py
최종 수정일: 2025-12-14
버전: v4.0
파일 개요: 산불 리스크 확률 P(H) 계산 Agent
변경 이력:
        - 2025-12-14: v4.0 - Hazard/Exposure 패턴 적용
                * _build_collected_data() 메서드 추가
                * calculate(lat, lon, ssp_scenario) 지원
                * ClimateDataLoader 기반 데이터 fetch
        - 2025-12-11: v3.0 - 월별 FWI에서 연도별 최대 FWI로 변경
                * 강도지표: X_fire(t) = max FWI(t,m) (연도별 최대값)
                * 연도별 AAL 계산으로 다른 에이전트와 통일
                * time_unit='monthly' 제거
        - 2025-11-24: v2.0 - FWI 공식 수정 (캐나다 ISI 방식 근사)
                * 습도: 제곱근으로 영향 완화 → (1 - RHM/100)^0.5
                * 풍속: m/s → km/h 변환 후 지수적 반영 → exp(0.05039 × WS_kmh)
                * 온도: 계수 강화 (0.05 → 0.08), 기준 온도 조정 (10 → 5)
                * 강수: 감쇠 완화 (0.001 → 0.0005)
                * 스케일링: ×5 적용하여 EFFIS bin과 호환
        - 2025-11-22: v1.2 - bin 0~11.2 (Low) 추가
                * bin: [0~11.2), [11.2~21.3), [21.3~38), [38~50), [50~)
                * DR_intensity: [0.00, 0.01, 0.03, 0.10, 0.25]
        - 2025-11-22: v1.1 - flat list 데이터 형식 지원 추가
                * ta, rhm, ws, rn (flat lists) 또는 monthly_data (nested dict) 모두 처리
        - 2025-11-21: v1 - AAL에서 확률 계산으로 분리
                * 강도지표: X_fire(t,m) = FWI(t,m) (Fire Weather Index, 월별)
                * FWI 계산식 적용
                * 월 기반 발생확률: P_fire[i] = (해당 bin에 속한 월 수) / (총 월 수)
                * 취약성 스케일링 제거
"""

from typing import Dict, Any
import numpy as np
from .base_probability_agent import BaseProbabilityAgent


class WildfireProbabilityAgent(BaseProbabilityAgent):
    """
    산불 리스크 확률 P(H) 계산 Agent

    사용 데이터: 월별 기상 데이터 (TA, RHM, WS, RN)
    강도지표: X_fire(t) = max FWI(t,m) (연도별 최대 FWI)

    FWI 계산식 (캐나다 ISI 방식 근사, v2.0):
            FWI(t,m) = (1 - RHM/100)^0.5 × exp(0.05039 × WS_kmh)
                       × exp(0.08 × (TA - 5)) × exp(-0.0005 × RN) × 5

            - 습도: 제곱근으로 영향 완화
            - 풍속: m/s → km/h 변환 후 지수적 반영 (캐나다 ISI 방식)
            - 온도: 계수 강화 및 기준온도 하향
            - 강수: 감쇠 완화
            - 스케일링: ×5 (EFFIS bin 호환)

    연도별 최대값 사용: 각 연도의 12개월 중 최대 FWI 값을 그 해의 강도지표로 사용
    """

    def __init__(self):
        """
        WildfireProbabilityAgent 초기화

        bin 구간 (EFFIS FWI 기준):
                - bin1: 0 <= FWI < 11.2 (Low)
                - bin2: 11.2 <= FWI < 21.3 (Moderate)
                - bin3: 21.3 <= FWI < 38 (High)
                - bin4: 38 <= FWI < 50 (Very High)
                - bin5: FWI >= 50 (Extreme)

        기본 손상률 (DR_intensity):
                - bin1: 0%
                - bin2: 1%
                - bin3: 3%
                - bin4: 10%
                - bin5: 25%
        """
        bins = [(0, 11.2), (11.2, 21.3), (21.3, 38), (38, 50), (50, float("inf"))]

        dr_intensity = [
            0.00,  # 0% (Low)
            0.01,  # 1% (Moderate)
            0.03,  # 3% (High)
            0.10,  # 10% (Very High)
            0.25,  # 25% (Extreme)
        ]

        super().__init__(risk_type="wildfire", bins=bins, dr_intensity=dr_intensity)

    def calculate_intensity_indicator(self, collected_data: Dict[str, Any]) -> np.ndarray:
        """
        산불 강도지표 X_fire(t) 계산
        X_fire(t) = max FWI(t,m) (연도별 최대 FWI)

        Args:
                collected_data: 수집된 기후 데이터
                        - climate_data:
                                - ta, rhm, ws, rn: 월별 데이터 flat lists
                                  (연도별로 12개월씩 정렬된 것으로 가정)
                                - monthly_data: 연도별 월별 데이터 리스트 (레거시)
                                        각 원소는 {'year': int, 'months': [{'ta': float, 'rhm': float, 'ws': float, 'rn': float}, ...]}

        Returns:
                연도별 최대 FWI 값 배열
        """
        climate_data = collected_data.get("climate_data", {})

        # 1. flat list 형식 (우선)
        ta_list = climate_data.get("ta", [])
        rhm_list = climate_data.get("rhm", [])
        ws_list = climate_data.get("ws", [])
        rn_list = climate_data.get("rn", [])

        if ta_list and rhm_list and ws_list and rn_list:
            n_months = min(len(ta_list), len(rhm_list), len(ws_list), len(rn_list))

            # 월별 FWI 계산
            all_monthly_fwi = []
            for i in range(n_months):
                fwi = self._calculate_fwi(ta_list[i], rhm_list[i], ws_list[i], rn_list[i])
                all_monthly_fwi.append(fwi)

            # 연도별 최대값 계산 (12개월씩 묶음)
            yearly_max_fwi = self._calculate_yearly_max(all_monthly_fwi)

            self.logger.info(
                f"FWI 데이터 (flat): {len(all_monthly_fwi)}개 월 → {len(yearly_max_fwi)}개 연도, "
                f"범위: {yearly_max_fwi.min():.2f} ~ {yearly_max_fwi.max():.2f}"
            )
            return yearly_max_fwi

        # 2. nested dict 형식 (레거시)
        monthly_data = climate_data.get("monthly_data", [])
        if monthly_data:
            yearly_max_fwi = []

            for year_data in monthly_data:
                months = year_data.get("months", [])
                year_fwi_values = []

                for month in months:
                    ta = month.get("ta", 10.0)
                    rhm = month.get("rhm", 50.0)
                    ws = month.get("ws", 2.0)
                    rn = month.get("rn", 0.0)
                    fwi = self._calculate_fwi(ta, rhm, ws, rn)
                    year_fwi_values.append(fwi)

                # 해당 연도의 최대 FWI
                if year_fwi_values:
                    yearly_max_fwi.append(max(year_fwi_values))
                else:
                    yearly_max_fwi.append(0.0)

            if yearly_max_fwi:
                fwi_array = np.array(yearly_max_fwi, dtype=float)
                self.logger.info(
                    f"FWI 데이터 (nested): {len(yearly_max_fwi)}개 연도, "
                    f"범위: {fwi_array.min():.2f} ~ {fwi_array.max():.2f}"
                )
                return fwi_array

        self.logger.warning("월별 기상 데이터가 없습니다. 기본값 0으로 설정합니다.")
        return np.array([0.0])

    def _calculate_yearly_max(self, monthly_fwi: list) -> np.ndarray:
        """
        월별 FWI 데이터를 연도별 최대값으로 변환

        Args:
                monthly_fwi: 월별 FWI 값 리스트 (12개월 단위로 정렬됨)

        Returns:
                연도별 최대 FWI 값 배열
        """
        if not monthly_fwi:
            return np.array([0.0])

        # 12개월씩 묶어서 최대값 계산
        n_years = len(monthly_fwi) // 12
        yearly_max = []

        for year_idx in range(n_years):
            start_idx = year_idx * 12
            end_idx = start_idx + 12
            year_months = monthly_fwi[start_idx:end_idx]

            if year_months:
                yearly_max.append(max(year_months))
            else:
                yearly_max.append(0.0)

        # 나머지 월이 있으면 (12로 나누어떨어지지 않는 경우)
        remaining_months = len(monthly_fwi) % 12
        if remaining_months > 0:
            self.logger.warning(
                f"월별 FWI 데이터가 12로 나누어떨어지지 않습니다. "
                f"전체 {len(monthly_fwi)}개월 중 마지막 {remaining_months}개월은 별도 연도로 처리됩니다. "
                f"데이터 정합성을 확인하세요."
            )
            remaining_fwi = monthly_fwi[n_years * 12 :]
            if remaining_fwi:
                yearly_max.append(max(remaining_fwi))

        return np.array(yearly_max, dtype=float)

    def _calculate_fwi(self, ta: float, rhm: float, ws: float, rn: float) -> float:
        """
        Fire Weather Index (FWI) 계산 (캐나다 ISI 방식 근사, v2.0)

        FWI = (1 - RHM/100)^0.5 × exp(0.05039 × WS_kmh)
              × exp(0.08 × (TA - 5)) × exp(-0.0005 × RN) × 5

        Args:
                ta: 평균 기온 (°C)
                rhm: 상대습도 (%)
                ws: 평균 풍속 (m/s)
                rn: 강수량 (mm)

        Returns:
                FWI 값 (EFFIS bin 호환 스케일)
        """
        # 습도 영향 (제곱근으로 완화)
        humidity_factor = (1 - (rhm / 100.0)) ** 0.5

        # 풍속 영향 (m/s → km/h 변환 후 지수적 반영, 캐나다 ISI 방식)
        ws_kmh = ws * 3.6
        wind_factor = np.exp(0.05039 * ws_kmh)

        # 온도 영향 (계수 강화, 기준온도 하향)
        temp_factor = np.exp(0.08 * (ta - 5))

        # 강수 영향 (감쇠 완화)
        rain_factor = np.exp(-0.0005 * rn)

        # 스케일링 적용 (EFFIS bin 호환)
        fwi = humidity_factor * wind_factor * temp_factor * rain_factor * 5

        return max(fwi, 0.0)  # 음수 방지

    def _build_collected_data(self, timeseries_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        ClimateDataLoader에서 가져온 시계열 데이터를 collected_data 형식으로 변환

        Args:
                timeseries_data: get_wildfire_timeseries() 반환값
                        - years: 연도 리스트
                        - ta: 평균기온 리스트
                        - rhm: 상대습도 리스트
                        - ws: 풍속 리스트
                        - rn: 강수량 리스트
                        - cdd: 연속무강수일 리스트
                        - climate_scenario: SSP 시나리오

        Returns:
                calculate_probability()에 전달할 collected_data
        """
        years = timeseries_data.get("years", [])
        ta_list = timeseries_data.get("ta", [])
        rhm_list = timeseries_data.get("rhm", [])
        ws_list = timeseries_data.get("ws", [])
        rn_list = timeseries_data.get("rn", [])

        # 연간 데이터를 월별로 확장 (12개월 반복)
        n_years = len(years)
        monthly_ta = []
        monthly_rhm = []
        monthly_ws = []
        monthly_rn = []

        for i in range(n_years):
            ta_val = ta_list[i] if i < len(ta_list) else 15.0
            rhm_val = rhm_list[i] if i < len(rhm_list) else 65.0
            ws_val = ws_list[i] if i < len(ws_list) else 3.5
            rn_val = (rn_list[i] / 12.0) if i < len(rn_list) else 100.0  # 연강수량을 월평균으로
            for _ in range(12):
                monthly_ta.append(ta_val)
                monthly_rhm.append(rhm_val)
                monthly_ws.append(ws_val)
                monthly_rn.append(rn_val)

        return {
            "climate_data": {
                "ta": monthly_ta,
                "rhm": monthly_rhm,
                "ws": monthly_ws,
                "rn": monthly_rn,
            },
            "years": years,
            "climate_scenario": timeseries_data.get("climate_scenario", "SSP245"),
        }

    def _get_fallback_data(self) -> Dict[str, Any]:
        """ClimateDataLoader가 없을 때 사용할 기본 데이터"""
        # 30년치 월별 기본 데이터 생성
        n_months = 30 * 12
        return {
            "climate_data": {
                "ta": [20.0] * n_months,
                "rhm": [65.0] * n_months,
                "ws": [3.5] * n_months,
                "rn": [50.0] * n_months,
            },
        }
