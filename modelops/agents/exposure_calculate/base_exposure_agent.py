"""
파일명: base_exposure_agent.py
최종 수정일: 2025-12-14
버전: v2
파일 개요: Exposure 점수(E) 계산 베이스 Agent (순수 계산 로직만)
변경 이력:
    - v1: 기본 Exposure 계산 Agent
    - v2: 원래 설계 복원 (DB 로직 제거, 순수 계산만)
"""

from typing import Dict, Any
import logging

try:
    from modelops.config import hazard_config as config
except ImportError:
    config = None

logger = logging.getLogger(__name__)


class BaseExposureAgent:
    """
    Exposure 점수(E) 계산 베이스 Agent

    원래 설계:
    - Agent는 순수 계산 로직만 담당
    - 데이터는 ExposureDataCollector → data_loaders에서 수집
    - Agent는 collected_data를 받아 계산만 수행
    """

    def __init__(self):
        self.logger = logger
        logger.debug("BaseExposureAgent initialized (pure calculation mode)")

    def calculate_exposure(
        self, building_data: Dict[str, Any], spatial_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        Calculate exposure for a specific hazard type.
        Must be implemented by child classes.

        Args:
            building_data: Building information (from BuildingDataFetcher)
            spatial_data: Spatial information (from SpatialDataLoader)
            **kwargs: Additional parameters

        Returns:
            Exposure data dictionary
        """
        raise NotImplementedError("Subclasses must implement calculate_exposure()")

    def _get_config_or_default(self, config_key: str, default_value: Any) -> Any:
        """
        Get configuration value or return default.

        Args:
            config_key: Configuration key to lookup
            default_value: Default value if config is not available

        Returns:
            Configuration value or default
        """
        if not config:
            return default_value
        return getattr(config, config_key, default_value)

    # ==================== 유틸리티 메서드 ====================

    def normalize_score(
        self, value: float, min_val: float, max_val: float, clip: bool = True
    ) -> float:
        """
        값을 0-1 범위로 정규화

        Args:
            value: 정규화할 값
            min_val: 최소값
            max_val: 최대값
            clip: True이면 0-1 범위로 클리핑

        Returns:
            정규화된 값 (0.0 ~ 1.0)
        """
        if max_val == min_val:
            return 0.5

        normalized = (value - min_val) / (max_val - min_val)

        if clip:
            return max(0.0, min(1.0, normalized))
        return normalized

    def get_value_with_fallback(self, data: Dict, keys: list, fallback: Any) -> Any:
        """
        딕셔너리에서 값을 찾되, 여러 키를 순차적으로 시도

        Args:
            data: 데이터 딕셔너리
            keys: 시도할 키 목록
            fallback: 모든 키가 없을 때 반환할 기본값

        Returns:
            찾은 값 또는 기본값
        """
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return fallback

    def get_spatial_data(
        self, building_data: Dict[str, Any], spatial_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        Spatial 데이터 조회 (입력된 데이터에서 추출, DB 조회 없음)

        Args:
            building_data: Building information (may contain spatial info)
            spatial_data: Spatial information from data_loaders

        Returns:
            Merged spatial data dictionary
        """
        # 기본값 설정
        defaults = {
            "distance_to_river_m": 10000.0,
            "watershed_area_km2": 100.0,
            "stream_order": 2,
            "elevation_m": 50.0,
            "distance_to_coast_m": 50000.0,
        }

        # 데이터 병합 (우선순위: spatial_data > building_data > defaults)
        result = defaults.copy()

        # building_data에서 덮어쓰기
        for key in defaults.keys():
            if key in building_data and building_data[key] is not None:
                result[key] = building_data[key]

        # spatial_data에서 덮어쓰기
        if spatial_data:
            for key in defaults.keys():
                if key in spatial_data and spatial_data[key] is not None:
                    result[key] = spatial_data[key]

            # 추가 메타데이터
            result["river_name"] = spatial_data.get("river_name")
            result["basin_name"] = spatial_data.get("basin_name")
            result["flood_capacity"] = spatial_data.get("flood_capacity")
            result["landcover_type"] = spatial_data.get("landcover_type")

        return result

    def get_exposure_level(self, exposure_score_100: float) -> str:
        """
        Exposure 점수에 따른 노출 등급 반환

        Args:
            exposure_score_100: Exposure 점수 (0 ~ 100)

        Returns:
            노출 등급 문자열
                - 'Very High': 80 이상
                - 'High': 60 ~ 80
                - 'Medium': 40 ~ 60
                - 'Low': 20 ~ 40
                - 'Very Low': 20 미만
        """
        if exposure_score_100 >= 80:
            return "Very High"
        elif exposure_score_100 >= 60:
            return "High"
        elif exposure_score_100 >= 40:
            return "Medium"
        elif exposure_score_100 >= 20:
            return "Low"
        else:
            return "Very Low"

    def classify_building_purpose(self, main_purpose: str) -> str:
        """
        건물 용도 분류

        Args:
            main_purpose: 건물 주용도 문자열

        Returns:
            분류된 용도 (residential, commercial, industrial, public, mixed)
        """
        if not main_purpose:
            return "residential"

        purpose_lower = main_purpose.lower()

        if any(
            kw in purpose_lower
            for kw in ["주거", "아파트", "주택", "다세대", "연립", "residential"]
        ):
            return "residential"
        elif any(
            kw in purpose_lower for kw in ["상업", "사무", "오피스", "업무", "commercial", "office"]
        ):
            return "commercial"
        elif any(
            kw in purpose_lower for kw in ["공장", "산업", "제조", "창고", "industrial", "factory"]
        ):
            return "industrial"
        elif any(kw in purpose_lower for kw in ["공공", "관공서", "교육", "학교", "public"]):
            return "public"
        else:
            return "mixed"
