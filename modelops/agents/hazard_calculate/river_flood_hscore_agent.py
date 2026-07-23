"""
파일명: river_flood_hscore_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 하천 홍수(River Flood) 리스크 Hazard 점수(H) 산출 Agent
변경 이력:
    - v1: HazardCalculator 로직 통합 (TWI + 강수량 기반)
    - v2: 원래 설계 복원 (DB 로직 제거, 순수 계산만)
"""

from typing import Dict, Any
from .base_hazard_hscore_agent import BaseHazardHScoreAgent


class RiverFloodHScoreAgent(BaseHazardHScoreAgent):
    """
    하천 홍수(River Flood) 리스크 Hazard 점수(H) 산출 Agent

    계산 방법론:
    - TWI (Topographic Wetness Index) + 극한 강수량 결합
    - Hazard Score = 0.4 × TWI_score + 0.6 × 강수_score
    - 근거: USGS 표준 지형 지수, 수문학 표준 (Beven & Kirkby 1979)

    데이터 흐름:
    - HazardDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__(risk_type="river_flood")

    def calculate_hazard(self, collected_data: Dict[str, Any]) -> float:
        """
        하천 홍수 Hazard 점수 계산

        Args:
            collected_data: HazardDataCollector가 수집한 데이터
                - spatial_data: landcover_type, distance_to_river_m, elevation_m
                - climate_data: max_1day_rainfall_mm, rx1day, annual_rainfall_mm

        Returns:
            Hazard 점수 (0.0 ~ 1.0)
        """
        spatial_data = collected_data.get("spatial_data", {})
        climate_data = collected_data.get("climate_data", {})
        building_data = collected_data.get("building_data", {})

        try:
            # 1. TWI 기반 지형 취약도 계산
            landcover_type = self.get_value_with_fallback(
                spatial_data, ["landcover_type", "land_cover_type"], "urban"
            )
            twi = self._calculate_twi(landcover_type)

            # TWI 정규화 (0~1 점수)
            if twi > 10:
                twi_score = 0.9
            elif twi > 7:
                twi_score = 0.5 + (twi - 7) / 6
            else:
                twi_score = twi / 20

            # 2. 강수량 기반 홍수 빈도 점수
            extreme_rainfall = self.get_value_with_fallback(
                climate_data, ["max_1day_rainfall_mm", "rx1day", "extreme_rain_95p"], 250.0
            )

            # 강수량 정규화 (0~1 점수)
            if extreme_rainfall > 300:
                rainfall_score = 0.9
            elif extreme_rainfall > 200:
                rainfall_score = 0.5 + (extreme_rainfall - 200) / 200
            else:
                rainfall_score = extreme_rainfall / 300

            # 3. 하천 거리 보정 (가까울수록 위험)
            distance_to_river = self.get_value_with_fallback(
                {**spatial_data, **building_data},
                ["distance_to_river_m", "river_distance_m"],
                10000.0,
            )

            # 거리 보정 계수 (1km 이내 1.2, 5km 이내 1.0, 그 외 0.8)
            if distance_to_river < 1000:
                distance_factor = 1.2
            elif distance_to_river < 5000:
                distance_factor = 1.0
            else:
                distance_factor = 0.8

            # 4. 결합 점수 (TWI 40% + 강수 60%) * 거리 보정
            hazard_score = (twi_score * 0.4 + rainfall_score * 0.6) * distance_factor

            # 상세 결과 기록
            if "calculation_details" not in collected_data:
                collected_data["calculation_details"] = {}

            collected_data["calculation_details"]["river_flood"] = {
                "hazard_score": hazard_score,
                "rx1day": extreme_rainfall,  # DB에서 가져온 1일 최대강수량
                "twi": twi,
                "twi_score": twi_score,
                "rainfall_score": rainfall_score,
                "distance_to_river": distance_to_river,
                "distance_factor": distance_factor,
            }

            return round(min(hazard_score, 1.0), 4)

        except Exception as e:
            self.logger.error(f"River Flood 계산 중 오류 발생: {e}")
            return 0.5

    def _calculate_twi(self, landcover_type: str) -> float:
        """
        TWI (Topographic Wetness Index) 추정
        토지피복도 기반의 경험적 추정치 사용
        """
        twi_map = {
            "forest": 10.5,
            "grassland": 9.0,
            "agricultural": 7.5,
            "water": 14.0,
            "wetland": 12.0,
            "urban": 6.5,
            "barren": 5.0,
        }
        return twi_map.get(landcover_type, 6.5)
