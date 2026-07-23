"""
파일명: water_stress_exposure_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 물 스트레스(Water Stress) Exposure 점수 산출 Agent
변경 이력:
    - v1: DB에서 건물 정보/물 의존도 조회
    - v2: 원래 설계 복원 (DB 로직 제거, 순수 계산만)
"""

from typing import Dict, Any
import logging
from .base_exposure_agent import BaseExposureAgent

try:
    from modelops.config import hazard_config as config
except ImportError:
    config = None

logger = logging.getLogger(__name__)


class WaterStressExposureAgent(BaseExposureAgent):
    """
    물 스트레스(Water Stress) Exposure 계산 Agent

    계산 방법론:
    - 건물 용도별 물 의존도
    - 저수조 보유 여부
    - 층수 기반 물 저장 용량

    데이터 흐름:
    - ExposureDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__()

    def calculate_exposure(
        self, building_data: Dict[str, Any], spatial_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        물 스트레스 Exposure 계산

        Args:
            building_data: Building information (from BuildingDataFetcher)
            spatial_data: Spatial information (from SpatialDataLoader)
            **kwargs: Additional parameters

        Returns:
            물 스트레스 Exposure 데이터
        """
        # 건물 정보 및 물 의존도 추출 (이미 data_loaders가 수집한 데이터)
        building_info = self._get_building_info(building_data)

        water_dependency = building_info["water_dependency"]
        has_water_tank = building_info.get("has_water_tank", False)
        ground_floors = building_info.get("ground_floors", 3)

        water_storage = self._calculate_water_storage(building_info)
        score = self._calculate_water_stress_exposure_score(
            water_dependency, water_storage, has_water_tank
        )

        return {
            "water_dependency": water_dependency,
            "water_storage_capacity": water_storage,
            "backup_water_supply": has_water_tank,
            "has_water_tank": has_water_tank,
            "score": score,
            "main_purpose": building_info.get("main_purpose"),
            "ground_floors": ground_floors,
            "building_age_years": building_info.get("building_age_years"),
            "data_source": "collected",
        }

    def _get_building_info(self, building_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        건물 정보 및 물 의존도 추출 (collected_data에서)

        Args:
            building_data: Building information from data_loaders

        Returns:
            건물 정보 딕셔너리
        """
        main_purpose = self.get_value_with_fallback(
            building_data, ["main_purpose", "building_purpose", "purpose"], "residential"
        )

        ground_floors = self.get_value_with_fallback(
            building_data, ["ground_floors", "floors_above", "floors", "floor_count"], 3
        )

        building_age = self.get_value_with_fallback(
            building_data, ["building_age", "building_age_years", "age"], 30
        )

        # 저수조 보유 여부 (법적 기준: 6층 이상)
        has_water_tank = building_data.get("has_water_tank", ground_floors >= 6)

        return {
            "main_purpose": main_purpose,
            "water_dependency": self._classify_water_dependency(main_purpose),
            "ground_floors": ground_floors,
            "building_age_years": building_age,
            "has_water_tank": has_water_tank,
        }

    def _classify_water_dependency(self, building_purpose: str) -> str:
        """건물 용도 기반 물 의존도 분류"""
        if not building_purpose:
            return "low"

        high_keywords = [
            "factory",
            "manufacturing",
            "cooling",
            "car_wash",
            "bath",
            "power",
            "공장",
            "동물및식물관련시설",
            "industrial",
        ]
        medium_keywords = [
            "office",
            "commercial",
            "retail",
            "제1종근린생활시설",
            "제2종근린생활시설",
            "문화및집회시설",
            "사무",
        ]

        purpose_str = str(building_purpose).lower()

        if any(keyword in purpose_str for keyword in high_keywords):
            return "high"
        elif any(keyword in purpose_str for keyword in medium_keywords):
            return "medium"
        else:
            return "low"

    def _calculate_water_storage(self, data: Dict) -> str:
        """
        물 저장 용량 계산

        Args:
            data: Building data

        Returns:
            저장 용량 (large/medium/limited)
        """
        has_water_tank = data.get("has_water_tank", False)
        ground_floors = data.get("ground_floors", 3)

        # 저수조가 있으면 large
        if has_water_tank:
            if ground_floors > 10:
                return "large"
            else:
                return "medium"

        # 저수조가 없으면 층수 기반
        if ground_floors > 10:
            return "medium"
        elif ground_floors > 5:
            return "limited"
        else:
            return "limited"

    def _calculate_water_stress_exposure_score(
        self, water_dependency: str, water_storage: str, has_water_tank: bool = False
    ) -> int:
        """
        물 스트레스 노출도 점수 계산

        Args:
            water_dependency: 물 의존도 (high/medium/low)
            water_storage: 저장 용량 (large/medium/limited)
            has_water_tank: 저수조 보유 여부

        Returns:
            Exposure 점수 (0-100)
        """
        # 기본 점수 (물 의존도 기반)
        if water_dependency == "high":
            score = 70
        elif water_dependency == "medium":
            score = 50
        else:
            score = 30

        # 저장 용량에 따른 조정
        if water_storage == "limited":
            score += 20
        elif water_storage == "medium":
            score += 10

        # 저수조가 있으면 노출도 감소
        if has_water_tank:
            score -= 10

        return max(0, min(score, 100))
