"""
파일명: wildfire_exposure_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 산불(Wildfire) Exposure 점수 산출 Agent
변경 이력:
    - v1: DB에서 토지피복/경사도 조회
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


class WildfireExposureAgent(BaseExposureAgent):
    """
    산불(Wildfire) Exposure 계산 Agent

    계산 방법론:
    - 산림 거리 + 경사도 + 토지피복 기반
    - Canadian FWI 시스템 호환

    데이터 흐름:
    - ExposureDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__()

    def calculate_exposure(
        self, building_data: Dict[str, Any], spatial_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        산불 Exposure 계산

        Args:
            building_data: Building information (from BuildingDataFetcher)
            spatial_data: Spatial information (from SpatialDataLoader)
            **kwargs: Additional parameters

        Returns:
            산불 Exposure 데이터
        """
        # 1. 산림 거리 및 토지피복 추출 (이미 data_loaders가 수집한 데이터)
        forest_data = self._get_forest_data(spatial_data)
        forest_distance = forest_data["distance_to_forest_m"]
        landcover_type = forest_data["landcover_type"]

        # 2. 경사도 추출 (DEM 기반)
        slope_data = self._get_slope_data(building_data, spatial_data)
        slope_degree = slope_data["slope_degree"]
        elevation_m = slope_data["elevation_m"]

        # 3. exposure 점수 계산
        proximity_category, score = self._calculate_wildfire_exposure_score(forest_distance)

        return {
            "distance_to_forest_m": forest_distance,
            "proximity_category": proximity_category,
            "score": score,
            "vegetation_type": self._get_vegetation_type_from_landcover(landcover_type),
            "slope_degree": slope_degree,
            "aspect": slope_data.get("aspect"),
            "landcover_type": landcover_type,
            "landcover_code": forest_data.get("landcover_code"),
            "elevation_m": elevation_m,
            "data_source": "collected",
        }

    def _get_forest_data(self, spatial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        산림 거리 및 토지피복 추출 (collected_data에서)

        Args:
            spatial_data: Spatial information from data_loaders

        Returns:
            산림 관련 데이터 딕셔너리
        """
        landcover_type = self.get_value_with_fallback(
            spatial_data, ["landcover_type", "land_cover_type"], "urban"
        )

        # distance_to_forest_m가 없으면 토지피복 기반 추정
        distance_to_forest = self.get_value_with_fallback(
            spatial_data, ["distance_to_forest_m", "forest_distance_m"], None
        )

        if distance_to_forest is None:
            distance_to_forest = self._estimate_forest_distance_from_landcover(landcover_type)

        return {
            "distance_to_forest_m": distance_to_forest,
            "landcover_code": spatial_data.get("landcover_code"),
            "landcover_type": landcover_type,
        }

    def _get_slope_data(
        self, building_data: Dict[str, Any], spatial_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        DEM 기반 경사도 추출 (collected_data에서)

        Args:
            building_data: Building information
            spatial_data: Spatial information

        Returns:
            경사도 관련 데이터 딕셔너리
        """
        # spatial_data에서 먼저 확인
        elevation = self.get_value_with_fallback(
            {**building_data, **spatial_data}, ["elevation_m", "elevation", "dem_value"], 50.0
        )

        slope_degree = self.get_value_with_fallback(spatial_data, ["slope_degree", "slope"], None)

        if slope_degree is None:
            slope_degree = self._estimate_slope_from_elevation(elevation)

        aspect = self.get_value_with_fallback(spatial_data, ["aspect", "slope_aspect"], "N")

        return {
            "slope_degree": slope_degree,
            "elevation_m": elevation,
            "aspect": aspect,
        }

    def _estimate_forest_distance_from_landcover(self, landcover_type: str) -> float:
        """토지피복 기반 산림 거리 추정"""
        distance_map = {
            "forest": 0,
            "agricultural": 300,
            "grassland": 500,
            "wetland": 1000,
            "barren": 1500,
            "residential": 1500,
            "urban": 2000,
            "water": 5000,
        }
        return distance_map.get(landcover_type, 2000)

    def _estimate_slope_from_elevation(self, elevation: float) -> float:
        """고도 기반 경사도 추정"""
        if elevation < 100:
            return 2
        elif elevation < 300:
            return 8
        elif elevation < 500:
            return 15
        else:
            return 25

    def _get_vegetation_type_from_landcover(self, landcover_type: str) -> str:
        """토지피복에서 식생 유형 분류"""
        vegetation_map = {
            "forest": "dense_forest",
            "grassland": "grassland",
            "agricultural": "cultivated",
            "wetland": "wetland",
            "urban": "urban",
            "barren": "bare",
            "water": "none",
        }
        return vegetation_map.get(landcover_type, "urban")

    def _calculate_wildfire_exposure_score(self, distance_m: float) -> Tuple[str, int]:
        """
        산림 거리 기반 산불 노출도 점수 계산

        Args:
            distance_m: 산림까지 거리 (미터)

        Returns:
            Tuple of (proximity_category, score)
        """
        if not config:
            if distance_m <= 0:
                return "extreme", 95
            elif distance_m <= 100:
                return "high", 80
            elif distance_m <= 500:
                return "medium", 50
            elif distance_m <= 1500:
                return "low", 25
            return "safe", 10

        thresholds = config.WILDFIRE_EXPOSURE_SCORES
        if distance_m <= thresholds["extreme"]["distance_m"]:
            return "extreme", thresholds["extreme"]["score"]
        elif distance_m <= thresholds["high"]["distance_m"]:
            return "high", thresholds["high"]["score"]
        elif distance_m <= thresholds["medium"]["distance_m"]:
            return "medium", thresholds["medium"]["score"]
        elif distance_m <= thresholds["low"]["distance_m"]:
            return "low", thresholds["low"]["score"]
        else:
            return "safe", thresholds["safe"]["score"]
