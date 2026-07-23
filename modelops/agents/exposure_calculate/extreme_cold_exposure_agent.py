"""
파일명: extreme_cold_exposure_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 극심한 저온(Extreme Cold) Exposure 점수 산출 Agent
변경 이력:
    - v1: DB에서 고도 데이터 조회
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


class ExtremeColdExposureAgent(BaseExposureAgent):
    """
    Extreme Cold Exposure 계산 Agent

    계산 방법론:
    - 위도 + 고도 기반 한파 노출도 산출
    - 북쪽일수록, 고도가 높을수록 노출도 증가

    데이터 흐름:
    - ExposureDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__()

    def calculate_exposure(
        self, building_data: Dict[str, Any], spatial_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        Calculate extreme cold exposure.

        Args:
            building_data: Building information (from BuildingDataFetcher)
            spatial_data: Spatial information (from SpatialDataLoader)
            **kwargs: Additional parameters (latitude, longitude)

        Returns:
            Extreme cold exposure data
        """
        latitude = kwargs.get("latitude", 37.5)

        # collected_data에서 고도 추출 (data_loaders가 DB에서 수집)
        elevation_m = self.get_value_with_fallback(
            {**building_data, **spatial_data}, ["elevation_m", "elevation", "dem_value"], 50.0
        )

        # 점수 계산
        score = self._calculate_cold_exposure_score(latitude, elevation_m)

        return {
            "latitude": latitude,
            "elevation_m": elevation_m,
            "score": score,
            "exposure_level": "high" if score > 60 else "medium" if score > 40 else "low",
            "data_source": "collected",
        }

    def _calculate_cold_exposure_score(self, latitude: float, elevation_m: float) -> int:
        """한파 노출도 점수 계산"""
        score = 30  # 기본 점수

        # 위도 기반 (북쪽일수록 노출도 증가)
        if latitude > 38:
            score += 20
        elif latitude > 36:
            score += 10

        # 고도 기반 (높을수록 노출도 증가)
        if elevation_m > 500:
            score += 15
        elif elevation_m > 200:
            score += 10

        return min(score, 100)
