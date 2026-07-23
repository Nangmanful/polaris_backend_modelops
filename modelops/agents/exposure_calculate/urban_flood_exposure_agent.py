"""
파일명: urban_flood_exposure_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 도시 홍수(Urban Flood) Exposure 점수 산출 Agent
변경 이력:
    - v1: DB에서 토지피복/건물 연령 조회
    - v2: 원래 설계 복원 (DB 로직 제거, 순수 계산만)
"""

from typing import Dict, Any, Tuple
import logging
from .base_exposure_agent import BaseExposureAgent

try:
    from modelops.config import hazard_config as config
except ImportError:
    config = None

logger = logging.getLogger(__name__)


class UrbanFloodExposureAgent(BaseExposureAgent):
    """
    도시 홍수(Urban Flood) Exposure 계산 Agent

    계산 방법론:
    - 불투수면 비율 + 건물 연령 기반
    - 토지피복 유형에 따른 배수 용량 추정

    데이터 흐름:
    - ExposureDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__()

    def calculate_exposure(
        self, building_data: Dict[str, Any], spatial_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        도시 홍수 Exposure 계산

        Args:
            building_data: Building information (from BuildingDataFetcher)
            spatial_data: Spatial information (from SpatialDataLoader)
            **kwargs: Additional parameters

        Returns:
            도시 홍수 Exposure 데이터
        """
        # 1. 토지피복 + 불투수면 비율 추출 (이미 data_loaders가 수집한 데이터)
        landcover_data = self._get_landcover_data(spatial_data)

        # 2. 건물 연령 추출
        building_age_data = self._get_building_age_data(building_data)

        land_use = landcover_data.get("landcover_type", "urban")
        imperviousness_ratio = landcover_data.get("imperviousness_ratio", 0.6)
        building_age = building_age_data.get("building_age_years", 30)

        # 3. 불투수면 기반 점수 계산
        urban_intensity, score = self._calculate_urban_flood_score(imperviousness_ratio, land_use)

        # 4. 배수 용량 계산 (불투수면 + 건물 연령 조합)
        drainage_capacity = self._calculate_drainage_capacity(
            imperviousness_ratio, building_age, land_use
        )

        return {
            "urban_intensity": urban_intensity,
            "score": score,
            "imperviousness_percent": int(imperviousness_ratio * 100),
            "impervious_surface_ratio": imperviousness_ratio,
            "drainage_capacity": drainage_capacity,
            "urban_area": land_use
            in ["urban", "commercial", "residential", "mixed-use", "industrial"],
            "landcover_type": land_use,
            "landcover_code": landcover_data.get("landcover_code"),
            "building_age_years": building_age,
            "oldest_approval_date": building_age_data.get("oldest_approval_date"),
            "data_source": "collected",
        }

    def _get_landcover_data(self, spatial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        토지피복 + 불투수면 비율 추출 (collected_data에서)

        Args:
            spatial_data: Spatial information from data_loaders

        Returns:
            토지피복 관련 데이터 딕셔너리
        """
        landcover_type = self.get_value_with_fallback(
            spatial_data, ["landcover_type", "land_cover_type", "land_use"], "urban"
        )

        imperviousness_ratio = self.get_value_with_fallback(
            spatial_data, ["imperviousness_ratio", "impervious_ratio", "imperviousness"], 0.6
        )

        vegetation_ratio = self.get_value_with_fallback(
            spatial_data, ["vegetation_ratio", "vegetation"], 0.2
        )

        return {
            "landcover_code": spatial_data.get("landcover_code"),
            "landcover_type": landcover_type,
            "imperviousness_ratio": imperviousness_ratio,
            "vegetation_ratio": vegetation_ratio,
        }

    def _get_building_age_data(self, building_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        건물 연령 추출 (collected_data에서)

        Args:
            building_data: Building information from data_loaders

        Returns:
            건물 연령 관련 데이터 딕셔너리
        """
        building_age = self.get_value_with_fallback(
            building_data, ["building_age", "building_age_years", "age"], 30
        )

        return {
            "building_age_years": building_age,
            "oldest_approval_date": building_data.get("oldest_approval_date"),
            "newest_approval_date": building_data.get("newest_approval_date"),
        }

    def _calculate_drainage_capacity(
        self, imperviousness_ratio: float, building_age_years: int, landcover_type: str
    ) -> str:
        """
        배수 용량 계산 (불투수면 + 건물 연령 + 토지피복 조합)

        Args:
            imperviousness_ratio: 불투수면 비율 (0.0 ~ 1.0)
            building_age_years: 건물 연령
            landcover_type: 토지피복 유형

        Returns:
            배수 용량 (good/standard/poor)
        """
        # 기본 점수 계산 (0~100, 높을수록 배수 용량 좋음)
        base_score = 50

        # 1. 불투수면 비율 기반 (낮을수록 좋음)
        if imperviousness_ratio < 0.3:
            base_score += 25
        elif imperviousness_ratio < 0.5:
            base_score += 10
        elif imperviousness_ratio > 0.7:
            base_score -= 20
        elif imperviousness_ratio > 0.5:
            base_score -= 10

        # 2. 건물 연령 기반 (최신일수록 좋음)
        if building_age_years < 10:
            base_score += 20
        elif building_age_years < 20:
            base_score += 10
        elif building_age_years > 40:
            base_score -= 15
        elif building_age_years > 30:
            base_score -= 5

        # 3. 토지피복 유형 기반
        if landcover_type in ["forest", "grassland", "wetland"]:
            base_score += 15
        elif landcover_type in ["urban", "commercial"]:
            base_score -= 10

        # 점수 → 등급 변환
        if base_score >= 60:
            return "good"
        elif base_score >= 40:
            return "standard"
        else:
            return "poor"

    def _calculate_urban_flood_score(
        self, imperviousness_ratio: float, landcover_type: str
    ) -> Tuple[str, int]:
        """
        불투수면 비율 기반 도시홍수 점수 계산

        Args:
            imperviousness_ratio: 불투수면 비율 (0.0 ~ 1.0)
            landcover_type: 토지피복 유형

        Returns:
            Tuple of (urban_intensity, score)
        """
        # 불투수면 비율 기반 점수 (주요 지표)
        if imperviousness_ratio >= 0.8:
            base_score = 85
            intensity = "very_high"
        elif imperviousness_ratio >= 0.6:
            base_score = 65
            intensity = "high"
        elif imperviousness_ratio >= 0.4:
            base_score = 45
            intensity = "medium"
        elif imperviousness_ratio >= 0.2:
            base_score = 25
            intensity = "low"
        else:
            base_score = 10
            intensity = "very_low"

        # 토지피복 유형에 따른 보정
        if landcover_type in ["urban", "commercial"]:
            base_score = min(100, base_score + 10)
        elif landcover_type in ["forest", "grassland", "wetland"]:
            base_score = max(0, base_score - 10)

        return intensity, base_score
