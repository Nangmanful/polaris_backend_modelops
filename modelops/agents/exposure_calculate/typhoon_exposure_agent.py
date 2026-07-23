"""
파일명: typhoon_exposure_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 태풍(Typhoon) Exposure 점수 산출 Agent
변경 이력:
    - v1: DB에서 해안선 거리 조회
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


class TyphoonExposureAgent(BaseExposureAgent):
    """
    Typhoon Exposure 계산 Agent

    계산 방법론:
    - 해안선 거리 기반 태풍 노출도 산출
    - 해안에 가까울수록 노출도 증가

    데이터 흐름:
    - ExposureDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__()

    def calculate_exposure(
        self, building_data: Dict[str, Any], spatial_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        Calculate typhoon exposure.

        Args:
            building_data: Building information (from BuildingDataFetcher)
            spatial_data: Spatial information (from SpatialDataLoader)
            **kwargs: Additional parameters (latitude, longitude)

        Returns:
            Typhoon exposure data
        """
        # collected_data에서 해안선 거리 추출 (data_loaders가 DB에서 수집)
        distance_to_coast = self.get_value_with_fallback(
            {**building_data, **spatial_data},
            ["distance_to_coast_m", "coast_distance_m", "coastal_distance"],
            50000.0,
        )

        score = self._calculate_typhoon_distance_score(distance_to_coast)

        return {
            "distance_to_coast_m": distance_to_coast,
            "coastal_exposure": distance_to_coast < 10000,
            "coastal_distance_score": score,
            "score": score,
            "exposure_level": self._classify_typhoon_exposure_level(distance_to_coast),
            "data_source": "collected",
        }

    def _calculate_typhoon_distance_score(self, distance_m: float) -> int:
        """Calculate typhoon exposure score based on distance to coast."""
        if not config:
            if distance_m < 5000:
                return 90
            elif distance_m < 20000:
                return 70
            elif distance_m < 50000:
                return 40
            return 10

        thresholds = config.TYPHOON_EXPOSURE_SCORES
        if distance_m < thresholds["very_high"]["distance_m"]:
            return thresholds["very_high"]["score"]
        elif distance_m < thresholds["high"]["distance_m"]:
            return thresholds["high"]["score"]
        elif distance_m < thresholds["medium"]["distance_m"]:
            return thresholds["medium"]["score"]
        else:
            return thresholds["low"]["score"]

    def _classify_typhoon_exposure_level(self, distance_m: float) -> str:
        """Classify typhoon exposure level."""
        if not config:
            if distance_m < 5000:
                return "critical"
            elif distance_m < 20000:
                return "high"
            elif distance_m < 50000:
                return "medium"
            return "low"

        thresholds = config.TYPHOON_EXPOSURE_SCORES
        if distance_m < thresholds["very_high"]["distance_m"]:
            return "critical"
        elif distance_m < thresholds["high"]["distance_m"]:
            return "high"
        elif distance_m < thresholds["medium"]["distance_m"]:
            return "medium"
        else:
            return "low"
