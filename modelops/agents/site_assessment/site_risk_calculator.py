"""
사업장 리스크 계산기
H는 DB 조회, E/V는 building_info 기반 계산
"""

from typing import Dict, Any, Optional
import logging
from datetime import datetime

from ..exposure_calculate.base_exposure_agent import BaseExposureAgent
from ..vulnerability_calculate.base_vulnerability_agent import BaseVulnerabilityAgent
from ...database.connection import DatabaseConnection
from ...utils.hazard_data_collector import HazardDataCollector

logger = logging.getLogger(__name__)


class SiteRiskCalculator:
    """
    사업장 리스크 계산기

    역할:
    - H (Hazard)와 base_aal은 DB에서 조회 (스케줄러로 이미 계산됨)
    - E (Exposure)와 V (Vulnerability)는 building_info 기반으로 계산
    - 통합 리스크 Score = H × E × V / 10000
    - 최종 AAL = base_aal × F_vuln × (1 - insurance_rate)
    """

    # 9개 리스크 타입
    RISK_TYPES = [
        "extreme_heat",
        "extreme_cold",
        "wildfire",
        "drought",
        "water_stress",
        "sea_level_rise",
        "river_flood",
        "urban_flood",
        "typhoon",
    ]

    def __init__(self, scenario="SSP245", target_year=2030):
        """
        SiteRiskCalculator 초기화

        Args:
            scenario: SSP 시나리오
            target_year: 목표 연도
        """
        self.scenario = scenario
        self.target_year = target_year

        # HazardDataCollector for E 계산용 데이터 수집
        self.hazard_data_collector = HazardDataCollector(scenario=scenario, target_year=target_year)

        # E, V Agents
        self.exposure_agent = BaseExposureAgent()
        self.vulnerability_agent = BaseVulnerabilityAgent()

    def calculate_site_risks(
        self,
        latitude: float,
        longitude: float,
        building_info: Dict[str, Any],
        asset_info: Optional[Dict[str, Any]] = None,
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        사업장 리스크 통합 계산

        Process:
        1. H, base_aal 조회 (DB)
        2. collected_data 구성 (building_info 포함)
        3. 9개 리스크 순회:
           - E 계산 (ExposureAgent)
           - V 계산 (VulnerabilityAgent)
           - Score 계산 (H × E × V / 10000)
           - AAL 계산 (base_aal × F_vuln × (1 - insurance_rate))
        4. 요약 통계 계산

        Args:
            latitude: 위도
            longitude: 경도
            building_info: 건물 정보 dict
            asset_info: 자산 정보 dict (선택)
            site_id: 사업장 ID (선택)

        Returns:
            {
                'site_id': str,
                'latitude': float,
                'longitude': float,
                'hazard': {risk_type: {...}},
                'exposure': {risk_type: {...}},
                'vulnerability': {risk_type: {...}},
                'integrated_risk': {risk_type: {...}},
                'aal_scaled': {risk_type: {...}},
                'summary': {...},
                'calculated_at': datetime
            }
        """
        start_time = datetime.now()
        logger.info(f"사업장 리스크 계산 시작: ({latitude}, {longitude})")
        if site_id:
            logger.info(f"  site_id: {site_id}")

        try:
            # Step 1: DB에서 H, base_aal 조회
            hazard_data = DatabaseConnection.fetch_hazard_results(latitude, longitude)
            base_aals = DatabaseConnection.fetch_probability_results(latitude, longitude)

            if not hazard_data:
                raise ValueError(
                    f"Hazard data not found for ({latitude}, {longitude}). "
                    "스케줄러가 해당 격자를 계산하지 않았을 수 있습니다."
                )

            # Step 2: collected_data 구성
            collected_data = self._prepare_collected_data(latitude, longitude, building_info)

            # 결과 저장소
            results = {
                "hazard": {},
                "exposure": {},
                "vulnerability": {},
                "integrated_risk": {},
                "aal_scaled": {},
            }

            # Step 3: 9개 리스크 순회
            insurance_rate = asset_info.get("insurance_coverage_rate", 0.0) if asset_info else 0.0

            for risk_type in self.RISK_TYPES:
                logger.debug(f"  - {risk_type} 계산 중...")

                # H (DB 조회 결과)
                if risk_type not in hazard_data:
                    logger.warning(f"{risk_type} hazard data not found, 기본값 사용")
                    h_score_100 = 0.0
                    h_score = 0.0
                    h_level = "Very Low"
                else:
                    h_score_100 = hazard_data[risk_type].get("hazard_score_100", 0.0)
                    h_score = hazard_data[risk_type].get("hazard_score", 0.0)
                    h_level = hazard_data[risk_type].get("hazard_level", "Very Low")

                # E 계산
                exposure_full = self.exposure_agent.calculate_exposure(collected_data)
                e_score = self._extract_exposure_score(exposure_full, risk_type)

                # V 계산
                # VulnerabilityAgent는 collected_data에서 exposure_results를 사용
                collected_data_with_exposure = collected_data.copy()
                collected_data_with_exposure["exposure_results"] = exposure_full

                vulnerability_full = self.vulnerability_agent.calculate_vulnerability(
                    collected_data_with_exposure
                )

                v_info = vulnerability_full.get(risk_type, {})
                v_score = v_info.get("score", 50.0)
                v_level = v_info.get("level", "medium")
                v_factors = v_info.get("factors", {})

                # Score 계산 (H × E × V / 10000)
                integrated_score = (h_score_100 * e_score * v_score) / 10000.0

                # 위험도 등급 분류
                risk_level = self._classify_risk_level(integrated_score)

                # AAL 계산
                base_aal = (
                    base_aals.get(risk_type, {}).get("aal", 0.01)
                    if base_aals.get(risk_type)
                    else 0.01
                )
                f_vuln = 0.9 + (v_score / 100.0) * 0.2
                final_aal = base_aal * f_vuln * (1 - insurance_rate)

                # 결과 저장
                results["hazard"][risk_type] = {
                    "hazard_score": h_score,
                    "hazard_score_100": h_score_100,
                    "hazard_level": h_level,
                }

                results["exposure"][risk_type] = {
                    "exposure_score": e_score,
                    "details": exposure_full,
                }

                results["vulnerability"][risk_type] = {
                    "vulnerability_score": v_score,
                    "vulnerability_level": v_level,
                    "factors": v_factors,
                }

                results["integrated_risk"][risk_type] = {
                    "h_score": round(h_score_100, 2),
                    "e_score": round(e_score, 2),
                    "v_score": round(v_score, 2),
                    "integrated_risk_score": round(integrated_score, 2),
                    "risk_level": risk_level,
                    "formula": f"{h_score_100:.2f} × {e_score:.2f} × {v_score:.2f} / 10000 = {integrated_score:.2f}",
                }

                results["aal_scaled"][risk_type] = {
                    "base_aal": round(base_aal, 6),
                    "vulnerability_scale": round(f_vuln, 4),
                    "insurance_rate": round(insurance_rate, 4),
                    "final_aal": round(final_aal, 6),
                }

            # Step 4: 요약 통계
            summary = self._calculate_summary(results)

            end_time = datetime.now()
            logger.info(f"사업장 리스크 계산 완료: {(end_time - start_time).total_seconds():.2f}초")

            return {
                "site_id": site_id,
                "latitude": latitude,
                "longitude": longitude,
                "hazard": results["hazard"],
                "exposure": results["exposure"],
                "vulnerability": results["vulnerability"],
                "integrated_risk": results["integrated_risk"],
                "aal_scaled": results["aal_scaled"],
                "summary": summary,
                "calculated_at": end_time,
            }

        except Exception as e:
            logger.error(f"사업장 리스크 계산 실패: {e}", exc_info=True)
            raise

    def _prepare_collected_data(
        self, latitude: float, longitude: float, building_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        ExposureAgent 및 VulnerabilityAgent 입력용 collected_data 구성

        Args:
            latitude: 위도
            longitude: 경도
            building_info: 건물 정보

        Returns:
            collected_data dict
        """
        # building_data 변환 (ExposureAgent 형식에 맞춤)
        building_data = {
            "latitude": latitude,
            "longitude": longitude,
            "building_type": building_info.get("building_type", "office"),
            "structure": building_info.get("structure", "철근콘크리트"),
            "building_age": building_info.get("building_age", 20),
            "total_area_m2": building_info.get("total_area_m2", 1000),
            "ground_floors": building_info.get("ground_floors", 3),
            "basement_floors": building_info.get("basement_floors", 0),
            "has_piloti": building_info.get("has_piloti", False),
            "elevation_m": building_info.get("elevation_m", 0),
        }

        # spatial_data (토지피복 등)
        spatial_data = {"landcover_type": "urban"}  # 기본값

        return {
            "latitude": latitude,
            "longitude": longitude,
            "building_data": building_data,
            "spatial_data": spatial_data,
        }

    def _extract_exposure_score(self, exposure_full: Dict, risk_type: str) -> float:
        """
        ExposureAgent 결과에서 리스크별 exposure score 추출

        Note: ExposureAgent는 전체 exposure dict를 반환하므로,
        리스크 타입별로 적절한 점수를 추출해야 함

        Args:
            exposure_full: ExposureAgent.calculate_exposure() 결과
            risk_type: 리스크 타입

        Returns:
            exposure_score (0-100)
        """
        # flood 관련
        if risk_type in ["river_flood", "urban_flood"]:
            if risk_type == "river_flood":
                return exposure_full.get("flood_exposure", {}).get("score", 50.0)
            else:  # urban_flood
                return exposure_full.get("urban_flood_exposure", {}).get("score", 50.0)

        # heat 관련
        elif risk_type in ["extreme_heat"]:
            # UHI risk를 점수로 변환 (예: very_high=90, high=70, medium=50, low=30, very_low=10)
            uhi_risk = exposure_full.get("heat_exposure", {}).get("uhi_risk", "medium")
            uhi_score_map = {
                "very_high": 90.0,
                "high": 70.0,
                "medium": 50.0,
                "low": 30.0,
                "very_low": 10.0,
            }
            return uhi_score_map.get(uhi_risk, 50.0)

        # 기타 리스크는 기본값 사용
        else:
            return 50.0

    def _classify_risk_level(self, integrated_score: float) -> str:
        """통합 리스크 점수를 등급으로 분류"""
        if integrated_score >= 80:
            return "Very High"
        elif integrated_score >= 60:
            return "High"
        elif integrated_score >= 40:
            return "Medium"
        elif integrated_score >= 20:
            return "Low"
        else:
            return "Very Low"

    def _calculate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """요약 통계 계산"""
        hazard_scores = [h.get("hazard_score_100", 0.0) for h in results["hazard"].values()]
        exposure_scores = [e.get("exposure_score", 0.0) for e in results["exposure"].values()]
        vulnerability_scores = [
            v.get("vulnerability_score", 0.0) for v in results["vulnerability"].values()
        ]
        integrated_scores = [
            ir.get("integrated_risk_score", 0.0) for ir in results["integrated_risk"].values()
        ]
        final_aals = [aal.get("final_aal", 0.0) for aal in results["aal_scaled"].values()]

        # 평균 계산
        avg_hazard = sum(hazard_scores) / len(hazard_scores) if hazard_scores else 0
        avg_exposure = sum(exposure_scores) / len(exposure_scores) if exposure_scores else 0
        avg_vulnerability = (
            sum(vulnerability_scores) / len(vulnerability_scores) if vulnerability_scores else 0
        )
        avg_integrated_risk = (
            sum(integrated_scores) / len(integrated_scores) if integrated_scores else 0
        )
        total_final_aal = sum(final_aals)

        # 최고 통합 리스크
        if results["integrated_risk"]:
            highest_risk = max(
                results["integrated_risk"].items(),
                key=lambda x: x[1].get("integrated_risk_score", 0.0),
            )
            highest_integrated_risk = {
                "risk_type": highest_risk[0],
                "integrated_risk_score": highest_risk[1].get("integrated_risk_score", 0.0),
                "risk_level": highest_risk[1].get("risk_level", "Very Low"),
            }
        else:
            highest_integrated_risk = None

        return {
            "average_hazard": round(avg_hazard, 2),
            "average_exposure": round(avg_exposure, 2),
            "average_vulnerability": round(avg_vulnerability, 2),
            "average_integrated_risk": round(avg_integrated_risk, 2),
            "highest_integrated_risk": highest_integrated_risk,
            "total_final_aal": round(total_final_aal, 6),
            "risk_count": len(self.RISK_TYPES),
        }
