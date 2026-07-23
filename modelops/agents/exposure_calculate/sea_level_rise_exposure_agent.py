"""
파일명: sea_level_rise_exposure_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 해수면 상승(Sea Level Rise) Exposure 점수 산출 Agent
변경 이력:
    - v1: DB에서 해수면 데이터 조회
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


class SeaLevelRiseExposureAgent(BaseExposureAgent):
    """
    Sea Level Rise Exposure 계산 Agent

    계산 방법론:
    - 해안선 거리 기반 노출도 산출
    - 거리가 가까울수록 노출도 증가

    데이터 흐름:
    - ExposureDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__()

    def calculate_exposure(
        self, building_data: Dict[str, Any], spatial_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        Calculate sea level rise exposure.

        Args:
            building_data: Building information (from BuildingDataFetcher)
            spatial_data: Spatial information (from SpatialDataLoader)
            **kwargs: Additional parameters (latitude, longitude, ssp_scenario)

        Returns:
            Sea level rise exposure data
        """
        # collected_data에서 해안선 거리 추출 (data_loaders가 DB에서 수집)
        distance_to_coast = self.get_value_with_fallback(
            {**building_data, **spatial_data},
            ["distance_to_coast_m", "coast_distance_m", "coastal_distance"],
            50000.0,
        )

        # 해수면 상승 예측값 (collected_data에서)
        sea_level_2050 = self.get_value_with_fallback(
            spatial_data, ["sea_level_rise_2050_cm", "slr_2050"], 10.0
        )
        sea_level_2100 = self.get_value_with_fallback(
            spatial_data, ["sea_level_rise_2100_cm", "slr_2100"], 30.0
        )

        score = self._calculate_coastal_distance_score(distance_to_coast)

        return {
            "distance_to_coast_m": distance_to_coast,
            "sea_level_rise_2050_cm": sea_level_2050,
            "sea_level_rise_2100_cm": sea_level_2100,
            "coastal_distance_score": score,
            "score": score,
            "exposure_level": self._classify_coastal_exposure_level(distance_to_coast),
            "data_source": "collected",
        }

    def _calculate_coastal_distance_score(self, distance_m: float) -> int:
        """Calculate sea level rise exposure score based on distance to coast."""
        if not config:
            if distance_m < 500:
                return 90
            elif distance_m < 2000:
                return 70
            elif distance_m < 10000:
                return 40
            return 10

        thresholds = config.SEA_LEVEL_RISE_EXPOSURE_SCORES
        if distance_m < thresholds["critical"]["distance_m"]:
            return thresholds["critical"]["score"]
        elif distance_m < thresholds["high"]["distance_m"]:
            return thresholds["high"]["score"]
        elif distance_m < thresholds["medium"]["distance_m"]:
            return thresholds["medium"]["score"]
        else:
            return thresholds["low"]["score"]

    def _classify_coastal_exposure_level(self, distance_m: float) -> str:
        """Classify sea level rise exposure level."""
        if not config:
            if distance_m < 500:
                return "critical"
            elif distance_m < 2000:
                return "high"
            elif distance_m < 10000:
                return "medium"
            return "low"

        thresholds = config.SEA_LEVEL_RISE_EXPOSURE_SCORES
        if distance_m < thresholds["critical"]["distance_m"]:
            return "critical"
        elif distance_m < thresholds["high"]["distance_m"]:
            return "high"
        elif distance_m < thresholds["medium"]["distance_m"]:
            return "medium"
        else:
            return "low"
