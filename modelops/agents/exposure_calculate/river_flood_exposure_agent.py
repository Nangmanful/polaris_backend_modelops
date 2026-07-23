"""
River Flood Exposure Agent
Calculates exposure to river flooding hazards.
"""

from typing import Dict, Any, Tuple
import logging
from .base_exposure_agent import BaseExposureAgent

try:
    from modelops.config import hazard_config as config
except ImportError:
    config = None

logger = logging.getLogger(__name__)


class RiverFloodExposureAgent(BaseExposureAgent):
    """
    River Flood Exposure calculation agent.

    Evaluates exposure to river flooding based on distance to river,
    watershed area, stream order, and flood zone status.
    """

    def __init__(self):
        super().__init__()

    def calculate_exposure(
        self, building_data: Dict[str, Any], spatial_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        Calculate river flood exposure.

        Args:
            building_data: Building information
            spatial_data: Spatial information (not used for this hazard)
            **kwargs: Additional parameters (latitude, longitude for DB lookup)

        Returns:
            River flood exposure data
        """
        # DB에서 spatial 데이터 조회 (좌표가 있으면)
        latitude = kwargs.get("latitude")
        longitude = kwargs.get("longitude")

        # get_spatial_data: DB 우선, 없으면 입력 데이터 사용
        merged_spatial = self.get_spatial_data(
            building_data, spatial_data, latitude=latitude, longitude=longitude
        )

        distance_to_river = merged_spatial.get("distance_to_river_m", 1000.0)
        proximity_category, score = self._calculate_river_flood_exposure_score(distance_to_river)

        # in_flood_zone 체크에 필요한 데이터 준비
        flood_check_data = {
            "distance_to_river_m": distance_to_river,
            "elevation_m": merged_spatial.get("elevation_m", 50.0),
        }

        # data_source 판단 (river_name이 있으면 DB에서 온 것)
        data_source = "database" if merged_spatial.get("river_name") else "default"

        return {
            "distance_to_river_m": distance_to_river,
            "proximity_category": proximity_category,
            "score": score,
            "distance_to_coast_m": merged_spatial.get("distance_to_coast_m", 50000.0),
            "watershed_area_km2": merged_spatial.get("watershed_area_km2", 100.0),
            "stream_order": merged_spatial.get("stream_order", 2),
            "elevation_m": merged_spatial.get("elevation_m", 50.0),
            "in_flood_zone": self._is_in_flood_zone(flood_check_data),
            # 추가 메타데이터 (DB에서 가져온 경우)
            "river_name": merged_spatial.get("river_name"),
            "basin_name": merged_spatial.get("basin_name"),
            "flood_capacity": merged_spatial.get("flood_capacity"),
            "data_source": data_source,
        }

    def _is_in_flood_zone(self, data: Dict) -> bool:
        """Check if location is in flood zone."""
        distance_to_river = data.get("distance_to_river_m", 1000)
        elevation = data.get("elevation_m", 50)
        return distance_to_river < 100 and elevation < 50

    def _calculate_river_flood_exposure_score(self, distance_m: float) -> Tuple[str, int]:
        """
        Calculate flood exposure score based on distance to river.

        Returns:
            Tuple of (proximity_category, score)
        """
        if not config:
            return "low", 10

        thresholds = config.RIVER_FLOOD_EXPOSURE_SCORES
        if distance_m < thresholds["very_high"]["distance_m"]:
            return "very_high", thresholds["very_high"]["score"]
        elif distance_m < thresholds["high"]["distance_m"]:
            return "high", thresholds["high"]["score"]
        elif distance_m < thresholds["medium"]["distance_m"]:
            return "medium", thresholds["medium"]["score"]
        else:
            return "low", thresholds["low"]["score"]
