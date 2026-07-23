"""
파일명: extreme_heat_exposure_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 극심한 고온(Extreme Heat) Exposure 점수 산출 Agent
변경 이력:
    - v1: DB에서 토지피복 데이터 조회
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


class ExtremeHeatExposureAgent(BaseExposureAgent):
    """
    Extreme Heat Exposure 계산 Agent

    계산 방법론:
    - 도시열섬 효과, 녹지 근접성, 토지이용 기반
    - 불투수면 비율 + 식생 비율 기반

    데이터 흐름:
    - ExposureDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__()

    def calculate_exposure(
        self, building_data: Dict[str, Any], spatial_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        Calculate extreme heat exposure.

        Args:
            building_data: Building information (from BuildingDataFetcher)
            spatial_data: Spatial information (from SpatialDataLoader)
            **kwargs: Additional parameters (latitude, longitude)

        Returns:
            Extreme heat exposure data
        """
        latitude = kwargs.get("latitude", 37.5)

        # collected_data에서 토지피복 데이터 추출 (data_loaders가 DB에서 수집)
        landcover_data = self._get_landcover_data(spatial_data)

        uhi_risk = self._classify_uhi_risk(landcover_data)
        uhi_intensity = self._calculate_uhi_intensity_from_landcover(landcover_data)
        green_space_nearby = landcover_data.get("vegetation_ratio", 0.2) > 0.3

        return {
            "urban_heat_island": uhi_intensity,
            "green_space_nearby": green_space_nearby,
            "building_orientation": self._estimate_building_orientation(latitude),
            "uhi_risk": uhi_risk,
            "score": self._calculate_heat_exposure_score(landcover_data),
            "landcover_type": landcover_data.get("landcover_type"),
            "landcover_code": landcover_data.get("landcover_code"),
            "imperviousness_ratio": landcover_data.get("imperviousness_ratio"),
            "vegetation_ratio": landcover_data.get("vegetation_ratio"),
            "data_source": "collected",
        }

    def _get_landcover_data(self, spatial_data: Dict[str, Any]) -> Dict[str, Any]:
        """토지피복 데이터 추출 (collected_data에서)"""
        landcover_type = self.get_value_with_fallback(
            spatial_data, ["landcover_type", "land_cover_type", "land_use"], "urban"
        )
        imperviousness_ratio = self.get_value_with_fallback(
            spatial_data, ["imperviousness_ratio", "impervious_ratio"], 0.6
        )
        vegetation_ratio = self.get_value_with_fallback(
            spatial_data, ["vegetation_ratio", "vegetation"], 0.2
        )

        return {
            "landcover_type": landcover_type,
            "landcover_code": spatial_data.get("landcover_code"),
            "imperviousness_ratio": imperviousness_ratio,
            "vegetation_ratio": vegetation_ratio,
        }

    def _calculate_uhi_intensity_from_landcover(self, landcover_data: Dict) -> str:
        """
        DB 토지피복 데이터 기반 도시열섬 강도 계산

        Args:
            landcover_data: 토지피복 데이터 (from DB)

        Returns:
            UHI intensity (high/medium/low)
        """
        landcover_type = landcover_data.get("landcover_type", "urban")
        imperviousness = landcover_data.get("imperviousness_ratio", 0.6)
        vegetation = landcover_data.get("vegetation_ratio", 0.2)

        # 불투수면 비율 기반 판단 (DB 데이터)
        if imperviousness >= 0.8:
            return "high"
        elif imperviousness >= 0.5:
            # 식생 비율로 보정
            if vegetation < 0.2:
                return "high"
            return "medium"
        elif imperviousness >= 0.3:
            return "medium"
        else:
            return "low"

    def _estimate_green_space_proximity(self, landcover_data: Dict) -> bool:
        """Evaluate proximity to green spaces."""
        land_use = landcover_data.get("landcover_type", "urban")
        vegetation_ratio = landcover_data.get("vegetation_ratio", 0.0)
        return vegetation_ratio > 0.3 or land_use in ["agricultural", "grassland", "forest"]

    def _estimate_building_orientation(self, lat: float) -> str:
        """Estimate building orientation based on latitude."""
        if lat > 37.5:
            return "north"
        elif lat > 35:
            return "mixed"
        else:
            return "south"

    def _classify_uhi_risk(self, landcover_data: Dict) -> str:
        """Classify urban heat island risk."""
        land_use = landcover_data.get("landcover_type", "urban")
        if land_use in ["commercial", "industrial", "urban"]:
            return "high"
        elif land_use in ["residential", "mixed-use"]:
            return "medium"
        else:
            return "low"

    def _calculate_heat_exposure_score(self, landcover_data: Dict) -> int:
        """
        Calculate heat exposure score.

        Reference: High=70, Medium=50, Low=30
        """
        if not config:
            uhi_risk = self._classify_uhi_risk(landcover_data)
            if uhi_risk == "high":
                return 70
            elif uhi_risk == "medium":
                return 50
            return 30

        uhi_risk = self._classify_uhi_risk(landcover_data)
        scores = config.EXTREME_HEAT_EXPOSURE_SCORES

        if uhi_risk == "high":
            return scores["high"]
        elif uhi_risk == "medium":
            return scores["medium"]
        else:
            return scores["low"]
