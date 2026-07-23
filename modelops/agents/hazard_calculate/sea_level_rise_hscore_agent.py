"""
파일명: sea_level_rise_hscore_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 해수면 상승(Sea Level Rise) 리스크 Hazard 점수(H) 산출 Agent
변경 이력:
    - v1: HazardCalculator 로직 통합 (CMIP6 SSP 시나리오 기반)
    - v2: 원래 설계 복원 (DB 로직 제거, 순수 계산만)
"""

from typing import Dict, Any
from .base_hazard_hscore_agent import BaseHazardHScoreAgent


class SeaLevelRiseHScoreAgent(BaseHazardHScoreAgent):
    """
    해수면 상승(Sea Level Rise) 리스크 Hazard 점수(H) 산출 Agent

    계산 방법론:
    - KMA CMIP6 SSP 시나리오 기반 해수면 상승량(cm) 예측값 사용
    - 내륙 지역(해안 10km 이상)은 0점 처리
    - Hazard Score 변환:
        - SLR ≥ 100cm: 1.0 (Extreme)
        - SLR ≥ 50cm: 0.7 (High)
        - SLR ≥ 30cm: 0.4 (Medium)
        - SLR < 30cm: 선형 비례

    데이터 흐름:
    - HazardDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__(risk_type="sea_level_rise")

    def calculate_hazard(self, collected_data: Dict[str, Any]) -> float:
        """
        해수면 상승 Hazard 점수 계산

        Args:
            collected_data: HazardDataCollector가 수집한 데이터
                - climate_data: slr_increase_cm 포함
                - building_data: distance_to_coast_m 포함

        Returns:
            Hazard 점수 (0.0 ~ 1.0)
        """
        climate_data = collected_data.get("climate_data", {})
        building_data = collected_data.get("building_data", {})
        spatial_data = collected_data.get("spatial_data", {})

        try:
            # 1. 해안 노출도 판단
            # BuildingDataFetcher (DB 기반)가 distance_to_coast_m 제공
            distance_to_coast = self.get_value_with_fallback(
                {**building_data, **spatial_data},
                ["distance_to_coast_m", "coast_distance_m"],
                50000.0,
            )

            # 내륙 지역 (해안선 10km 이상)
            if distance_to_coast >= 10000:
                if "calculation_details" not in collected_data:
                    collected_data["calculation_details"] = {}
                collected_data["calculation_details"]["sea_level_rise"] = {
                    "hazard_score": 0.0,
                    "slr": 0.0,  # 내륙은 해수면상승 영향 없음
                    "distance": distance_to_coast,  # 해안 거리
                    "note": "Inland area (>10km from coast)",
                }
                return 0.0

            # 2. 해수면 상승량 데이터 추출
            slr_cm = self.get_value_with_fallback(
                climate_data,
                ["slr_increase_cm", "sea_level_rise_cm", "sea_level_rise_2100_cm"],
                30.0,
            )

            # 3. Hazard Score 변환
            if slr_cm >= 100:
                hazard_score = 1.0
            elif slr_cm >= 50:
                # 50~100cm 사이: 0.7 ~ 1.0 선형 보간
                hazard_score = 0.7 + (slr_cm - 50) / 50 * 0.3
            elif slr_cm >= 30:
                # 30~50cm 사이: 0.4 ~ 0.7 선형 보간
                hazard_score = 0.4 + (slr_cm - 30) / 20 * 0.3
            else:
                # 0~30cm 사이: 0.0 ~ 0.4 선형 보간
                hazard_score = (slr_cm / 30.0) * 0.4

            hazard_score = min(max(hazard_score, 0.0), 1.0)

            # 상세 결과 기록
            if "calculation_details" not in collected_data:
                collected_data["calculation_details"] = {}

            collected_data["calculation_details"]["sea_level_rise"] = {
                "hazard_score": hazard_score,
                "slr": slr_cm,  # DB에서 가져온 해수면상승 (cm)
                "distance": distance_to_coast,  # 해안 거리 (m)
            }

            return round(hazard_score, 4)

        except Exception as e:
            self.logger.error(f"Sea Level Rise 계산 중 오류 발생: {e}")
            return 0.0  # 기본적으로 안전하다고 가정
