"""
파일명: wildfire_hscore_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 산불(Wildfire) 리스크 Hazard 점수(H) 산출 Agent
변경 이력:
    - v1: HazardCalculator 로직 통합 (Canadian FWI 시스템 기반)
    - v2: 원래 설계 복원 (DB 로직 제거, 순수 계산만)
"""

from typing import Dict, Any
from .base_hazard_hscore_agent import BaseHazardHScoreAgent


class WildfireHScoreAgent(BaseHazardHScoreAgent):
    """
    산불(Wildfire) 리스크 Hazard 점수(H) 산출 Agent

    계산 방법론:
    - Canadian FWI (Fire Weather Index) 시스템 기반
    - 기온, 습도, 풍속, 강수량 등을 종합하여 화재 기상 지수 산출
    - FWI 값을 0~100 스케일로 변환 후 정규화

    데이터 흐름:
    - HazardDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__(risk_type="wildfire")

    def calculate_hazard(self, collected_data: Dict[str, Any]) -> float:
        """
        산불 Hazard 점수 계산

        Args:
            collected_data: HazardDataCollector가 수집한 데이터
                - climate_data: temperature, relative_humidity, wind_speed, annual_rainfall_mm 등
                - spatial_data: landcover_type, ndvi 등

        Returns:
            Hazard 점수 (0.0 ~ 1.0)
        """
        climate_data = collected_data.get("climate_data", {})
        spatial_data = collected_data.get("spatial_data", {})

        try:
            # 1. 데이터 추출 (data_loaders가 DB에서 수집한 데이터 사용)
            temp = self.get_value_with_fallback(
                climate_data, ["temperature", "avg_temperature", "ta", "tamax"], 25.0
            )
            rh = self.get_value_with_fallback(
                climate_data, ["relative_humidity", "humidity", "rhm"], 50.0
            )
            wind_speed = self.get_value_with_fallback(
                climate_data, ["wind_speed", "ws"], 3.0
            )  # m/s
            annual_rainfall = self.get_value_with_fallback(
                climate_data, ["annual_rainfall_mm", "rn", "total_rainfall"], 1200.0
            )

            landcover_type = self.get_value_with_fallback(
                spatial_data, ["landcover_type", "land_cover_type"], "mixed"
            )

            # 2. Canadian FWI 계산 (간단 근사 버전)

            # FFMC (Fine Fuel Moisture Code): 세밀한 연료 수분
            # 온도와 습도에 의존
            ffmc = 85 - (rh / 100) * 50 + (temp / 50) * 15
            ffmc = max(0, min(101, ffmc))

            # DC (Drought Code): 깊은 토양 건조도
            if annual_rainfall < 500:
                dc = 400
            elif annual_rainfall < 1000:
                dc = 250
            elif annual_rainfall < 1500:
                dc = 150
            else:
                dc = 50

            # ISI (Initial Spread Index): 초기 확산 지수
            # 풍속과 온도에 의존
            isi = (wind_speed / 5) * 20 + (temp / 40) * 15
            isi = max(0, min(37, isi))

            # BUI (Buildup Index): 연료 축적 지수
            bui = dc * 0.8

            # FWI (Fire Weather Index): 최종 화재 기상 지수
            # 근사식: 정규화된 지수 계산
            fwi_normalized = (ffmc / 101) * 0.4 + (isi / 37) * 0.3 + (bui / 292) * 0.3
            fwi = fwi_normalized * 81  # 0-81 범위로 정규화

            # 3. 위험도 지수 계산 (0-100 스케일)
            wildfire_risk_index = (fwi / 81) * 100

            # 토지피복도에 따른 조정
            if landcover_type == "forest":
                wildfire_risk_index *= 1.3
            elif landcover_type == "grassland":
                wildfire_risk_index *= 1.2
            elif landcover_type == "agricultural":
                wildfire_risk_index *= 0.8

            wildfire_risk_index = min(wildfire_risk_index, 100)

            # Hazard Score (0~1)
            hazard_score = wildfire_risk_index / 100.0

            # 상세 결과 기록
            if "calculation_details" not in collected_data:
                collected_data["calculation_details"] = {}

            collected_data["calculation_details"]["wildfire"] = {
                "hazard_score": hazard_score,
                "ta": temp,  # DB에서 가져온 평균기온
                "rhm": rh,  # DB에서 가져온 상대습도
                "ws": wind_speed,  # DB에서 가져온 풍속
                "rn": annual_rainfall,  # DB에서 가져온 연강수량
                "fwi": fwi,
                "wildfire_risk_index": wildfire_risk_index,
                "sub_indices": {"ffmc": ffmc, "dc": dc, "isi": isi, "bui": bui},
            }

            return round(hazard_score, 4)

        except Exception as e:
            self.logger.error(f"Wildfire 계산 중 오류 발생: {e}")
            return 0.3
