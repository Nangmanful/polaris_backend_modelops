"""
파일명: typhoon_hscore_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 태풍(Typhoon) 리스크 Hazard 점수(H) 산출 Agent
변경 이력:
    - v1: HazardCalculator 로직 통합 (TCI 기반)
    - v2: 원래 설계 복원 (DB 로직 제거, 순수 계산만)
"""

from typing import Dict, Any, Tuple
import math
from .base_hazard_hscore_agent import BaseHazardHScoreAgent

try:
    from modelops.config import hazard_config as config
except ImportError:
    config = None


class TyphoonHScoreAgent(BaseHazardHScoreAgent):
    """
    태풍(Typhoon) 리스크 Hazard 점수(H) 산출 Agent

    계산 방법론:
    - KMA 태풍 베스트트랙 데이터 기반 과거 태풍 영향 분석
    - TCI (Typhoon Comprehensive Index) = 0.55×Wind + 0.45×Rain
    - 거리 감쇠 적용

    데이터 흐름:
    - HazardDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__(risk_type="typhoon")

    def calculate_hazard(self, collected_data: Dict[str, Any]) -> float:
        """
        태풍 Hazard 점수 계산

        Args:
            collected_data: HazardDataCollector가 수집한 데이터
                - typhoon_data: typhoons 리스트 포함
                - climate_data: Rx1day 데이터 포함 (max_1day_precipitation)
                - latitude, longitude: 분석 위치

        Returns:
            Hazard 점수 (0.0 ~ 1.0)
        """
        typhoon_data_dict = collected_data.get("typhoon_data", {})
        typhoons = typhoon_data_dict.get("typhoons", [])
        climate_data = collected_data.get("climate_data", {})

        lat = collected_data.get("latitude")
        lon = collected_data.get("longitude")

        # collected_data에서 태풍 빈도/최대풍속 추출 (data_loaders가 DB에서 수집)
        typhoon_frequency = self.get_value_with_fallback(
            typhoon_data_dict, ["typhoon_frequency", "frequency", "count"], 0
        )
        max_wind_speed = self.get_value_with_fallback(
            typhoon_data_dict, ["max_wind_speed_ms", "max_wind_speed", "wind_speed"], 30.0
        )

        # collected_data에서 rx1day 추출
        rx1day = self.get_value_with_fallback(
            climate_data, ["max_1day_precipitation", "rx1day", "max_1day_rainfall_mm"], 200.0
        )
        climate_data["max_1day_precipitation"] = rx1day

        # 태풍 데이터가 없고 빈도 데이터가 있으면 빈도 기반 계산
        if not typhoons and typhoon_frequency > 0:
            freq_score = min(typhoon_frequency / 20.0, 1.0)
            wind_score = min(max_wind_speed / 50.0, 1.0)
            hazard_score = 0.6 * wind_score + 0.4 * freq_score

            # 상세 결과 기록
            if "calculation_details" not in collected_data:
                collected_data["calculation_details"] = {}
            collected_data["calculation_details"]["typhoon"] = {
                "hazard_score": hazard_score,
                "frequency": typhoon_frequency,  # DB에서 가져온 태풍 빈도
                "max_wind": max_wind_speed,  # DB에서 가져온 최대풍속
                "rx1day": rx1day,  # DB에서 가져온 1일 최대강수량
            }
            return round(hazard_score, 4)

        if not typhoons or lat is None or lon is None:
            # 데이터 없음 Fallback
            return 0.1

        try:
            # TCI 값 수집
            impacts = []
            max_wind_speeds = []

            # config 로드
            if config and hasattr(config, "TYPHOON_HAZARD_PARAMS"):
                params = config.TYPHOON_HAZARD_PARAMS
            else:
                # 기본값 하드코딩 (fallback_constants 참고)
                params = {
                    "gale_radius_km": 300,
                    "wind_norm_max_ms": 50,
                    "rain_norm_max_mm": 500,
                    "estimated_rx1day": {"strong": 400, "medium": 200, "weak": 100},
                }

            # Rx1day 데이터 연동 (climate_data에서 실제 데이터 가져오기)
            rx1day_mm = climate_data.get("max_1day_precipitation") or climate_data.get("rx1day")

            for typhoon in typhoons:
                tci, wind_speed, _ = self._calculate_typhoon_impact(
                    lat, lon, typhoon, params, rx1day_mm
                )
                if tci > 0:
                    impacts.append(tci)
                    max_wind_speeds.append(wind_speed)

            # 통계 계산
            if impacts:
                avg_impact = sum(impacts) / len(impacts)

                # 상세 결과 기록
                if "calculation_details" not in collected_data:
                    collected_data["calculation_details"] = {}

                collected_data["calculation_details"]["typhoon"] = {
                    "hazard_score": min(avg_impact, 1.0),
                    "frequency": typhoon_frequency,  # DB에서 가져온 태풍 빈도
                    "max_wind": max_wind_speed,  # DB에서 가져온 최대풍속
                    "impact_count": len(impacts),
                    "max_wind_speed_avg": (
                        sum(max_wind_speeds) / len(max_wind_speeds) if max_wind_speeds else 0
                    ),
                    "rx1day_mm": rx1day_mm,
                    "rx1day_source": "climate_data" if rx1day_mm else "estimated",
                }

                return round(min(avg_impact, 1.0), 4)
            else:
                return 0.1  # 영향권 내 태풍 없음

        except Exception as e:
            self.logger.error(f"Typhoon 계산 중 오류 발생: {e}")
            return 0.1

    def _calculate_typhoon_impact(
        self, lat: float, lon: float, typhoon: Dict, params: Dict, rx1day_mm: float = None
    ) -> Tuple[float, int, Dict]:
        """
        위치별 태풍 영향도 계산 (TCI 방식)
        """
        try:
            typhoon_lat = typhoon.get("lat", 0)
            typhoon_lon = typhoon.get("lon", 0)
            max_wind = typhoon.get("max_wind_speed", 0)  # m/s

            # 태풍 중심까지의 거리 계산
            distance_km = self._haversine_distance(lat, lon, typhoon_lat, typhoon_lon)

            # 강풍 반경
            gale_radius = params.get("gale_radius_km", 300)

            if distance_km >= gale_radius:
                return 0, 0, {}

            # 1. Wind 정규화
            wind_max_ref = params.get("wind_norm_max_ms", 50)
            wind_normalized = min(max_wind / wind_max_ref, 1.0)

            # 2. Rain 정규화
            rain_max_ref = params.get("rain_norm_max_mm", 500)
            if rx1day_mm is not None:
                rain_normalized = min(rx1day_mm / rain_max_ref, 1.0)
            else:
                # Fallback: 태풍 등급 기반 추정
                estimates = params.get(
                    "estimated_rx1day", {"strong": 400, "medium": 200, "weak": 100}
                )
                if max_wind >= 33:
                    est_rain = estimates["strong"]
                elif max_wind >= 25:
                    est_rain = estimates["medium"]
                else:
                    est_rain = estimates["weak"]
                rain_normalized = min(est_rain / rain_max_ref, 1.0)

            # TCI 계산 (0.55:0.45)
            tci = 0.55 * wind_normalized + 0.45 * rain_normalized

            # 거리 감쇠 적용
            distance_factor = 1.0 - (distance_km / gale_radius)
            tci_adjusted = tci * distance_factor

            return tci_adjusted, max_wind, {}

        except Exception:
            return 0, 0, {}

    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        """두 지점 간 거리 계산 (km)"""
        R = 6371  # 지구 반지름 (km)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        return R * c
