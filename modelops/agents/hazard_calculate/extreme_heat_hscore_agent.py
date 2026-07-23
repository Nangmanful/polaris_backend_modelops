"""
파일명: extreme_heat_hscore_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 극심한 고온(Extreme Heat) 리스크 Hazard 점수(H) 산출 Agent
변경 이력:
    - v1: HazardCalculator 로직 통합 (HCI 지표 기반)
    - v2: 원래 설계 복원 (DB 로직 제거, 순수 계산만)
"""

from typing import Dict, Any
from .base_hazard_hscore_agent import BaseHazardHScoreAgent


class ExtremeHeatHScoreAgent(BaseHazardHScoreAgent):
    """
    극심한 고온(Extreme Heat) 리스크 Hazard 점수(H) 산출 Agent

    계산 방법론:
    - HCI (Heat Compound Index) 기반 평가
    - 근거: IPCC AR6 + TCFD 공식 지표 (ETCCDI)
    - 공식: HCI = 0.3×(SU25/100) + 0.3×(WSDI/30) + 0.2×(TR25/50) + 0.2×(TX90P/100)

    데이터 흐름:
    - HazardDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__(risk_type="extreme_heat")

    def calculate_hazard(self, collected_data: Dict[str, Any]) -> float:
        """
        폭염 Hazard 점수 계산

        Args:
            collected_data: HazardDataCollector가 수집한 데이터
                - climate_data: ClimateDataLoader를 통해 수집된 기후 데이터

        Returns:
            Hazard 점수 (0.0 ~ 1.0)
        """
        climate_data = collected_data.get("climate_data", {})

        # 데이터가 없는 경우 Fallback (전국 평균 수준)
        if not climate_data:
            self.logger.warning("Extreme Heat: 기후 데이터가 없습니다. 기본값(0.4)을 사용합니다.")
            return 0.4

        try:
            # Step 1: ETCCDI 지표 추출 (data_loaders가 DB에서 수집)
            # su25: 폭염일수 (일최고기온 ≥ 33°C, KMA 기준)
            su25 = self.get_value_with_fallback(
                climate_data, ["heatwave_days_per_year", "su25", "heatwave_days"], 25
            )
            # wsdi: 폭염 지속일수 (Warm Spell Duration Index)
            wsdi = self.get_value_with_fallback(
                climate_data, ["heat_wave_duration", "wsdi", "warm_spell_days"], 10
            )
            # tr25: 열대야일수 (일최저기온 ≥ 25°C)
            tr25 = self.get_value_with_fallback(
                climate_data, ["tropical_nights", "tr25", "tropical_night_days"], 15
            )
            # tx90p: 90백분위 초과일수 (su25와 유사하게 취급)
            tx90p = su25

            # Step 2: 절대값 기준 정규화 (0~1)
            su25_norm = min(su25 / 100.0, 1.0)  # 연간 100일 이상이면 만점
            wsdi_norm = min(wsdi / 30.0, 1.0)  # 지속 30일 이상이면 만점
            tr25_norm = min(tr25 / 50.0, 1.0)  # 열대야 50일 이상이면 만점
            tx90p_norm = min(tx90p / 100.0, 1.0)

            # Step 3: HCI 계산 (가중평균)
            # 폭염일수(30%) + 지속일수(30%) + 열대야(20%) + 강도(20%)
            hci = 0.3 * su25_norm + 0.3 * wsdi_norm + 0.2 * tr25_norm + 0.2 * tx90p_norm

            # 상세 결과 기록
            if "calculation_details" not in collected_data:
                collected_data["calculation_details"] = {}

            collected_data["calculation_details"]["extreme_heat"] = {
                "hci": hci,
                "su25": su25,
                "wsdi": wsdi,
                "tr25": tr25,
                "factors": {"su25_norm": su25_norm, "wsdi_norm": wsdi_norm, "tr25_norm": tr25_norm},
            }

            return round(hci, 4)

        except Exception as e:
            self.logger.error(f"Extreme Heat 계산 중 오류 발생: {e}")
            return 0.4
