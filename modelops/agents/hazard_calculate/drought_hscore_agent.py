"""
파일명: drought_hscore_agent.py
최종 수정일: 2025-12-14
버전: v2
설명: 가뭄(Drought) 리스크 Hazard 점수(H) 산출 Agent
변경 이력:
    - v1: HazardCalculator 로직 통합 (SPEI-12 기반)
    - v2: 원래 설계 복원 (DB 로직 제거, 순수 계산만)
"""

from typing import Dict, Any
from .base_hazard_hscore_agent import BaseHazardHScoreAgent

try:
    from modelops.config import hazard_config as config
except ImportError:
    config = None


class DroughtHScoreAgent(BaseHazardHScoreAgent):
    """
    가뭄(Drought) 리스크 Hazard 점수(H) 산출 Agent

    계산 방법론:
    - SPEI-12 (Standardized Precipitation Evapotranspiration Index) 기반
    - SPEI = (P - ET - μ) / σ
    - 범위: -3 to +3 (일반적), 낮을수록 가뭄 심각

    점수 변환 (Hazard Score):
    - SPEI 값을 0~1 Hazard Score로 역변환
    - SPEI ≤ -2.0 → Score 1.0 (Extreme) - WMO 국제 표준
    - SPEI ≥ 0.0 → Score 0.0 (Normal/Wet)

    데이터 흐름:
    - HazardDataCollector → data_loaders (DB) → collected_data → 이 Agent
    """

    def __init__(self):
        super().__init__(risk_type="drought")

    def calculate_hazard(self, collected_data: Dict[str, Any]) -> float:
        """
        가뭄 Hazard 점수 계산

        Args:
            collected_data: HazardDataCollector가 수집한 데이터
                - climate_data: ClimateDataLoader 데이터 (spei12_index, annual_rainfall_mm 등)
                - spatial_data: SpatialDataLoader 데이터 (soil_moisture 등)

        Returns:
            Hazard 점수 (0.0 ~ 1.0)
        """
        climate_data = collected_data.get("climate_data", {})

        # 데이터 부재 시 기본값
        if not climate_data:
            return 0.2  # 평년 수준

        try:
            # 1. 데이터 추출 (data_loaders가 DB에서 수집)
            spei12 = self.get_value_with_fallback(
                climate_data, ["spei12_index", "spei12", "spei"], None
            )
            annual_rainfall = self.get_value_with_fallback(
                climate_data, ["annual_rainfall_mm", "rn", "total_rainfall"], 1200.0
            )
            cdd = self.get_value_with_fallback(
                climate_data, ["consecutive_dry_days", "cdd", "cdd_days"], 15
            )

            final_spei = 0.0

            # 2. SPEI-12 값 결정 (실제 데이터 vs Fallback 추정)
            if spei12 is not None:
                # KMA SPEI-12 데이터 사용
                # spei12가 리스트인 경우 평균값 사용
                if isinstance(spei12, (list, tuple)):
                    spei12 = sum(spei12) / len(spei12) if len(spei12) > 0 else 0.0
                final_spei = float(spei12)
                final_spei = max(-3.0, min(3.0, final_spei))
            else:
                # Fallback: 강수량 기반 SPI 추정
                if config and hasattr(config, "DROUGHT_HAZARD_PARAMS"):
                    params = config.DROUGHT_HAZARD_PARAMS
                    korea_mean_rainfall = params.get("korea_mean_rainfall", 1300.0)
                    korea_std_rainfall = params.get("korea_std_rainfall", 300.0)
                    cdd_norm_avg = params.get("cdd_norm_avg", 10.0)
                    cdd_norm_std = params.get("cdd_norm_std", 10.0)
                else:
                    korea_mean_rainfall = 1300.0
                    korea_std_rainfall = 300.0
                    cdd_norm_avg = 10.0
                    cdd_norm_std = 10.0

                # SPI 추정
                if korea_std_rainfall > 0:
                    spi_estimated = (annual_rainfall - korea_mean_rainfall) / korea_std_rainfall
                else:
                    spi_estimated = 0.0

                # CDD 정규화
                if cdd_norm_std > 0:
                    cdd_normalized = (cdd - cdd_norm_avg) / cdd_norm_std
                else:
                    cdd_normalized = 0.0

                # 복합 가뭄지수 = SPI(60%) - CDD_norm(40%)
                final_spei = (spi_estimated * 0.6) - (cdd_normalized * 0.4)
                final_spei = max(-3.0, min(3.0, final_spei))

            # 3. Hazard Score 변환 (0.0 ~ 1.0)
            if final_spei >= 0:
                hazard_score = 0.0
            else:
                hazard_score = min(1.0, -final_spei / 2.0)

            # 상세 결과 기록
            if "calculation_details" not in collected_data:
                collected_data["calculation_details"] = {}

            collected_data["calculation_details"]["drought"] = {
                "spei12": final_spei,
                "hazard_score_raw": hazard_score,
                "annual_rainfall": annual_rainfall,
                "cdd": cdd,
            }

            return round(hazard_score, 4)

        except Exception as e:
            self.logger.error(f"Drought 계산 중 오류 발생: {e}")
            return 0.2
