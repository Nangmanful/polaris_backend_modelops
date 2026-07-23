"""
파일명: urban_flood_hscore_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 도시 홍수(Urban Flood) 리스크 Hazard 점수(H) 산출 Agent
변경 이력:
    - v1: HazardCalculator 로직 통합 (배수능력 + 강수초과량)
    - v2: 원래 설계 복원 (DB 로직 제거, 순수 계산만)
"""

from typing import Dict, Any
from .base_hazard_hscore_agent import BaseHazardHScoreAgent


class UrbanFloodHScoreAgent(BaseHazardHScoreAgent):
    """
    도시 홍수(Urban Flood) 리스크 Hazard 점수(H) 산출 Agent

    계산 방법론:
    - 토지피복도 + 건물밀도 + 강수량 기반
    - Hazard Score = 0.5 × 배수능력_점수 + 0.5 × 강수_초과량_점수
    - 근거: 도시수문학 표준 (투수율 기반), 건물밀도-배수망 연관성

    데이터 흐름:
    - HazardDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__(risk_type="urban_flood")

    def calculate_hazard(self, collected_data: Dict[str, Any]) -> float:
        """
        도시 홍수 Hazard 점수 계산

        Args:
            collected_data: HazardDataCollector가 수집한 데이터
                - spatial_data: landcover_type, impervious_ratio
                - climate_data: max_1day_rainfall_mm
                - building_data: building_count

        Returns:
            Hazard 점수 (0.0 ~ 1.0)
        """
        spatial_data = collected_data.get("spatial_data", {})
        climate_data = collected_data.get("climate_data", {})
        building_data = collected_data.get("building_data", {})

        try:
            # 1. 토지피복도 기반 배수능력 추정
            impervious_ratio = self.get_value_with_fallback(
                spatial_data, ["impervious_ratio", "imperviousness_ratio"], 0.7
            )
            landcover_type = self.get_value_with_fallback(
                spatial_data, ["landcover_type", "land_cover_type"], "urban"
            )

            # 토지피복도 기반 배수능력 (mm/hr)
            if landcover_type == "water":
                drainage_capacity = 0
            elif landcover_type == "forest":
                drainage_capacity = 8
            elif landcover_type == "agricultural":
                drainage_capacity = 15
            elif impervious_ratio > 0.75:
                drainage_capacity = 75  # 고밀도 상업지역
            elif impervious_ratio > 0.6:
                drainage_capacity = 55  # 중밀도 주거지역
            else:
                drainage_capacity = 40  # 저밀도 주거/농촌

            # 2. 건물밀도 기반 배수망 발달도 보정
            # 건물 밀도가 높을수록 배수관거가 잘 발달되어 있을 가능성 높음
            # building_data에 building_count가 없다면 기본값 사용
            building_count = building_data.get("building_count", 100)
            # area_km2: 격자 기반 분석이므로 1km² 고정값 사용
            area_km2 = 1.0

            building_density = building_count / max(area_km2, 0.1)

            if building_density > 1000:
                drainage_correction = 1.0
            elif building_density > 500:
                drainage_correction = 0.9
            elif building_density > 100:
                drainage_correction = 0.8
            else:
                drainage_correction = 0.7

            effective_drainage = drainage_capacity * drainage_correction

            # 3. 강수량 기반 침수 위험
            extreme_rainfall_1day = self.get_value_with_fallback(
                climate_data, ["max_1day_rainfall_mm", "rx1day", "extreme_rain_95p"], 100.0
            )
            # 1시간 강수량 추정 (1일 강수량 / 12)
            extreme_rainfall_1hr = extreme_rainfall_1day / 12.0

            # 강수 초과량 = 강수량 - 배수능력
            rainfall_excess = extreme_rainfall_1hr - effective_drainage

            # 강수 초과량 점수화 (0~1)
            # 초과량 > 30mm: 0.9 (심각한 침수)
            if rainfall_excess < 0:
                rainfall_excess_score = 0
            elif rainfall_excess > 30:
                rainfall_excess_score = 0.9
            else:
                rainfall_excess_score = (rainfall_excess / 30.0) * 0.9

            # 4. 배수능력 점수화 (역수 개념)
            # 배수능력이 좋을수록 점수 낮음. 80mm/hr 이상이면 0점 처리하고 싶지만
            # 여기서는 (1 - score) 방식을 사용
            drainage_score = min(1.0, effective_drainage / 80.0)

            # 5. 결합 점수
            # 배수능력 부족(50%) + 강수 초과량(50%)
            # 배수능력 부족 점수 = 1 - drainage_score
            hazard_score = (1.0 - drainage_score) * 0.5 + rainfall_excess_score * 0.5

            # 상세 결과 기록
            if "calculation_details" not in collected_data:
                collected_data["calculation_details"] = {}

            collected_data["calculation_details"]["urban_flood"] = {
                "hazard_score": hazard_score,
                "rx1day": extreme_rainfall_1day,  # DB에서 가져온 1일 최대강수량
                "effective_drainage": effective_drainage,
                "rainfall_excess": rainfall_excess,
                "factors": {
                    "drainage_score": drainage_score,
                    "rainfall_excess_score": rainfall_excess_score,
                },
            }

            return round(min(hazard_score, 1.0), 4)

        except Exception as e:
            self.logger.error(f"Urban Flood 계산 중 오류 발생: {e}")
            return 0.5
