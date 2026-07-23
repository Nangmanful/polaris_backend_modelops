"""
파일명: drought_exposure_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 가뭄(Drought) Exposure 점수 산출 Agent
변경 이력:
    - v1: DB에서 강수량/물 의존도 조회
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


class DroughtExposureAgent(BaseExposureAgent):
    """
    가뭄(Drought) Exposure 계산 Agent

    계산 방법론:
    - 연평균 강수량, 연속 무강수일 기반
    - 건물 용도별 물 의존도 고려

    데이터 흐름:
    - ExposureDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__()

    def calculate_exposure(
        self, building_data: Dict[str, Any], spatial_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        가뭄 Exposure 계산

        Args:
            building_data: Building information (from BuildingDataFetcher)
            spatial_data: Spatial information (from SpatialDataLoader)
            **kwargs: Additional parameters (climate_data 포함)

        Returns:
            가뭄 Exposure 데이터
        """
        climate_data = kwargs.get("climate_data", {})

        # 1. 강수량 데이터 추출 (이미 data_loaders가 수집한 데이터)
        rainfall_data = self._get_rainfall_data(building_data, climate_data)

        annual_rainfall = rainfall_data["annual_rainfall_mm"]
        rain80_days = rainfall_data.get("rain80_days", 5.0)
        cdd_days = rainfall_data.get("cdd_days", 30.0)

        # 2. 건물 용도 기반 물 의존도 분류
        water_dep_data = self._get_water_dependency(building_data)
        water_dependency = water_dep_data["water_dependency"]
        main_purpose = water_dep_data.get("main_purpose")

        # 3. 가뭄 노출도 점수 계산
        score = self._calculate_drought_exposure_score(water_dependency, annual_rainfall, cdd_days)

        return {
            "annual_rainfall_mm": annual_rainfall,
            "rain80_days": rain80_days,
            "cdd_days": cdd_days,
            "water_dependency": water_dependency,
            "main_purpose": main_purpose,
            "score": score,
            "data_source": "collected",
        }

    def _get_rainfall_data(
        self, building_data: Dict[str, Any], climate_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        강수량 데이터 추출 (collected_data에서)

        Args:
            building_data: Building information
            climate_data: Climate data from data_loaders

        Returns:
            강수량 관련 데이터 딕셔너리
        """
        # 기본값 설정
        if not config:
            hydro_defaults = {"annual_rainfall_mm": 1200}
        else:
            hydro_defaults = config.DEFAULT_HYDROLOGICAL_VALUES

        defaults = {
            "annual_rainfall_mm": hydro_defaults.get("annual_rainfall_mm", 1200),
            "rain80_days": 5.0,
            "cdd_days": 30.0,
        }

        # climate_data에서 추출 (data_loaders가 DB에서 수집)
        annual_rainfall = self.get_value_with_fallback(
            climate_data,
            ["annual_rainfall_mm", "rn", "total_rainfall"],
            defaults["annual_rainfall_mm"],
        )

        rain80_days = self.get_value_with_fallback(
            climate_data, ["rain80_days", "rain80"], defaults["rain80_days"]
        )

        cdd_days = self.get_value_with_fallback(
            climate_data, ["cdd_days", "cdd", "consecutive_dry_days"], defaults["cdd_days"]
        )
        # cdd가 리스트인 경우 평균값 사용
        if isinstance(cdd_days, list):
            cdd_days = sum(cdd_days) / len(cdd_days) if cdd_days else defaults["cdd_days"]

        # building_data에서도 확인
        if (
            "annual_rainfall_mm" in building_data
            and building_data["annual_rainfall_mm"] is not None
        ):
            annual_rainfall = building_data["annual_rainfall_mm"]

        return {
            "annual_rainfall_mm": annual_rainfall,
            "rain80_days": rain80_days,
            "cdd_days": cdd_days,
        }

    def _get_water_dependency(self, building_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        건물 용도 기반 물 의존도 분류

        Args:
            building_data: Building information

        Returns:
            {
                'water_dependency': str,  # high/medium/low
                'main_purpose': str
            }
        """
        main_purpose = self.get_value_with_fallback(
            building_data, ["main_purpose", "building_purpose", "purpose"], "residential"
        )

        return {
            "water_dependency": self._classify_water_dependency(main_purpose),
            "main_purpose": main_purpose,
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

    def _calculate_drought_exposure_score(
        self, water_dependency: str, annual_rainfall_mm: float, cdd_days: float = 30.0
    ) -> int:
        """
        가뭄 노출도 점수 계산

        Args:
            water_dependency: 물 의존도 (high/medium/low)
            annual_rainfall_mm: 연평균 강수량 (mm)
            cdd_days: 연속 무강수일 (일)

        Returns:
            Exposure 점수 (0-100)
        """
        # 기본 점수 (물 의존도 기반)
        if water_dependency == "high":
            score = 70
        elif water_dependency == "medium":
            score = 45
        else:
            score = 25

        # 강수량 기반 조정 (낮을수록 노출도 증가)
        if annual_rainfall_mm < 800:
            score += 15
        elif annual_rainfall_mm < 1000:
            score += 10
        elif annual_rainfall_mm < 1200:
            score += 5

        # 연속 무강수일 기반 조정 (길수록 노출도 증가)
        if cdd_days > 50:
            score += 10
        elif cdd_days > 40:
            score += 5

        return min(100, score)
