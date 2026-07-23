"""
파일명: evaal_ondemand_api.py
최종 수정일: 2025-12-13
버전: v01
파일 개요: E, V, AAL On-Demand 계산 함수 (API 호출용)
변경 이력:
    - 2025-12-13: v01 - 최초 생성
        * 사용자 요청 위경도 기반 E, V, AAL 계산
        * API에서 직접 호출 가능한 함수 형태
        * DB에서 H, P(H) 조회 후 E, V, AAL 계산
        * 통합 리스크 계산 포함 (H × E × V)
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

# Exposure Agents
from ..agents.exposure_calculate.river_flood_exposure_agent import RiverFloodExposureAgent
from ..agents.exposure_calculate.extreme_heat_exposure_agent import ExtremeHeatExposureAgent
from ..agents.exposure_calculate.extreme_cold_exposure_agent import ExtremeColdExposureAgent
from ..agents.exposure_calculate.urban_flood_exposure_agent import UrbanFloodExposureAgent
from ..agents.exposure_calculate.drought_exposure_agent import DroughtExposureAgent
from ..agents.exposure_calculate.typhoon_exposure_agent import TyphoonExposureAgent
from ..agents.exposure_calculate.sea_level_rise_exposure_agent import SeaLevelRiseExposureAgent
from ..agents.exposure_calculate.wildfire_exposure_agent import WildfireExposureAgent
from ..agents.exposure_calculate.water_stress_exposure_agent import WaterStressExposureAgent

# Vulnerability Agents
from ..agents.vulnerability_calculate.extreme_heat_vulnerability_agent import (
    ExtremeHeatVulnerabilityAgent,
)
from ..agents.vulnerability_calculate.extreme_cold_vulnerability_agent import (
    ExtremeColdVulnerabilityAgent,
)
from ..agents.vulnerability_calculate.drought_vulnerability_agent import DroughtVulnerabilityAgent
from ..agents.vulnerability_calculate.river_flood_vulnerability_agent import (
    RiverFloodVulnerabilityAgent,
)
from ..agents.vulnerability_calculate.urban_flood_vulnerability_agent import (
    UrbanFloodVulnerabilityAgent,
)
from ..agents.vulnerability_calculate.sea_level_rise_vulnerability_agent import (
    SeaLevelRiseVulnerabilityAgent,
)
from ..agents.vulnerability_calculate.typhoon_vulnerability_agent import TyphoonVulnerabilityAgent
from ..agents.vulnerability_calculate.wildfire_vulnerability_agent import WildfireVulnerabilityAgent
from ..agents.vulnerability_calculate.water_stress_vulnerability_agent import (
    WaterStressVulnerabilityAgent,
)

# AAL Agent
from ..agents.risk_assessment.aal_scaling_agent import AALScalingAgent

# Site Assessment
from ..agents.site_assessment.relocation_recommender import RelocationRecommender

# Utils
from ..database.connection import DatabaseConnection
from ..utils.hazard_data_collector import HazardDataCollector
from ..data_loaders.long_term_mapper import LongTermDataMapper

logger = logging.getLogger(__name__)


# ========== Agent 매핑 ==========
EXPOSURE_AGENTS = {
    "extreme_heat": ExtremeHeatExposureAgent(),
    "extreme_cold": ExtremeColdExposureAgent(),
    "drought": DroughtExposureAgent(),
    "river_flood": RiverFloodExposureAgent(),
    "urban_flood": UrbanFloodExposureAgent(),
    "sea_level_rise": SeaLevelRiseExposureAgent(),
    "typhoon": TyphoonExposureAgent(),
    "wildfire": WildfireExposureAgent(),
    "water_stress": WaterStressExposureAgent(),
}

VULNERABILITY_AGENTS = {
    "extreme_heat": ExtremeHeatVulnerabilityAgent(),
    "extreme_cold": ExtremeColdVulnerabilityAgent(),
    "drought": DroughtVulnerabilityAgent(),
    "river_flood": RiverFloodVulnerabilityAgent(),
    "urban_flood": UrbanFloodVulnerabilityAgent(),
    "sea_level_rise": SeaLevelRiseVulnerabilityAgent(),
    "typhoon": TyphoonVulnerabilityAgent(),
    "wildfire": WildfireVulnerabilityAgent(),
    "water_stress": WaterStressVulnerabilityAgent(),
}

AAL_AGENT = AALScalingAgent()


# ========== DB 조회 함수 ==========
def fetch_hazard_from_db(
    latitude: float, longitude: float, scenario: str, target_year: int, risk_type: str
) -> Dict[str, Any]:
    """
    DB에서 H 결과 조회

    Args:
        latitude: 위도
        longitude: 경도
        scenario: SSP 시나리오
        target_year: 분석 연도
        risk_type: 리스크 타입

    Returns:
        {
            'hazard_score': float,           # 0-1
            'hazard_score_100': float,       # 0-100
            'hazard_level': str              # Very High/High/Medium/Low/Very Low
        }
    """
    try:
        # DB 스키마 numeric(9,6)에 맞게 좌표 반올림
        rounded_lat = round(latitude, 6)
        rounded_lon = round(longitude, 6)

        # fetch_hazard_results (복수형) 사용 - risk_type별 결과 반환
        h_results = DatabaseConnection.fetch_hazard_results(
            latitude=rounded_lat,
            longitude=rounded_lon,
            risk_types=[risk_type],
            target_year=target_year,
            scenario=scenario,
        )

        if not h_results or risk_type not in h_results:
            logger.warning(
                f"Hazard not found for {risk_type} at ({latitude}, {longitude}), "
                f"{scenario}, {target_year} - using default value 1.0"
            )
            return {"hazard_score": 0.1, "hazard_score_100": 10.0, "hazard_level": "Very High"}

        # 결과 추출 및 변환
        h_data = h_results[risk_type]
        scenario_col = f"{scenario.lower()}_score_100"
        score_100 = h_data.get("hazard_score_100") or h_data.get(scenario_col, 0.0) or 0.0

        # Drought 트렌드 보정 (2050년 이후)
        if risk_type == "drought" and target_year >= 2050:
            try:
                # 2030년대 평균 (2030-2039)
                h_2030s = DatabaseConnection.fetch_hazard_results(
                    latitude=rounded_lat,
                    longitude=rounded_lon,
                    risk_types=[risk_type],
                    target_year=None,  # 전체 조회
                    scenario=scenario,
                )

                # 2030년대와 2040년대 데이터 필터링
                scores_2030s = []
                scores_2040s = []

                for key, data in h_2030s.items():
                    if key.startswith("drought_"):
                        year_str = data.get("target_year", "")
                        try:
                            year_int = int(year_str)
                            h_val = data.get(scenario_col, 0.0) or 0.0

                            if 2030 <= year_int < 2040:
                                scores_2030s.append(h_val)
                            elif 2040 <= year_int < 2050:
                                scores_2040s.append(h_val)
                        except (ValueError, TypeError):
                            continue

                # 평균 계산
                if scores_2030s and scores_2040s:
                    avg_2030s = sum(scores_2030s) / len(scores_2030s)
                    avg_2040s = sum(scores_2040s) / len(scores_2040s)

                    # 증가율 계산
                    if avg_2030s > 0:
                        growth_rate = (avg_2040s - avg_2030s) / avg_2030s
                        # 2040년대 기준으로 동일 비율 증가
                        years_from_2040 = target_year - 2040
                        corrected_score = avg_2040s * (1 + growth_rate * (years_from_2040 / 10.0))

                        logger.info(
                            f"Drought trend correction: {score_100:.1f} → {corrected_score:.1f} "
                            f"(2030s avg: {avg_2030s:.1f}, 2040s avg: {avg_2040s:.1f}, "
                            f"growth: {growth_rate*100:.1f}%)"
                        )
                        score_100 = corrected_score  # 감소/증가 모두 적용
            except Exception as e:
                logger.debug(f"Failed to apply drought trend correction: {e}")

        # 등급 분류
        if score_100 >= 80:
            level = "Very High"
        elif score_100 >= 60:
            level = "High"
        elif score_100 >= 40:
            level = "Medium"
        elif score_100 >= 20:
            level = "Low"
        else:
            level = "Very Low"

        return {
            "hazard_score": score_100 / 100.0,
            "hazard_score_100": score_100,
            "hazard_level": level,
        }

    except Exception as e:
        logger.error(f"Failed to fetch hazard from DB: {e}")
        return {"hazard_score": 0.0, "hazard_score_100": 0.0, "hazard_level": "Very Low"}


def fetch_probability_from_db(
    latitude: float, longitude: float, scenario: str, target_year: int, risk_type: str
) -> Dict[str, Any]:
    """
    DB에서 P(H) 결과 조회

    Args:
        latitude: 위도
        longitude: 경도
        scenario: SSP 시나리오
        target_year: 분석 연도
        risk_type: 리스크 타입

    Returns:
        {
            'aal': float,                    # Annual Average Loss
            'return_period_years': float,    # 재현주기
            'probability_level': str         # Very High/High/Medium/Low/Very Low
        }
    """
    try:
        # DB 스키마 numeric(9,6)에 맞게 좌표 반올림
        rounded_lat = round(latitude, 6)
        rounded_lon = round(longitude, 6)

        # fetch_probability_results (복수형) 사용 - risk_type별 결과 반환
        p_results = DatabaseConnection.fetch_probability_results(
            latitude=rounded_lat,
            longitude=rounded_lon,
            risk_types=[risk_type],
            target_year=target_year,
            scenario=scenario,
        )

        if not p_results or risk_type not in p_results:
            logger.warning(
                f"Probability not found for {risk_type} at ({latitude}, {longitude}), "
                f"{scenario}, {target_year} - using default value 1.0"
            )
            return {"aal": 0.001, "return_period_years": 1000.0, "probability_level": "Very High"}

        # 결과 추출 및 변환
        p_data = p_results[risk_type]
        aal = p_data.get("aal", 0.0) or 0.0

        # AAL 기반 재현주기 추정 (1/AAL, 최대 1000년)
        return_period = (1.0 / aal) if aal > 0 else 0.0
        return_period = min(return_period, 1000.0)

        # 등급 분류 (AAL 기반)
        if aal >= 0.1:
            level = "Very High"
        elif aal >= 0.05:
            level = "High"
        elif aal >= 0.02:
            level = "Medium"
        elif aal >= 0.01:
            level = "Low"
        else:
            level = "Very Low"

        return {
            "aal": aal,
            "return_period_years": return_period,
            "probability_level": level,
            "bin_probabilities": p_data.get("bin_probabilities"),
            "calculation_details": p_data.get("calculation_details"),
            "bin_data": p_data.get("bin_data"),
        }

    except Exception as e:
        logger.error(f"Failed to fetch probability from DB: {e}")
        return {"aal": 0.0, "return_period_years": 0.0, "probability_level": "Very Low"}


def fetch_building_info(latitude: float, longitude: float) -> Dict[str, Any]:
    """
    건물 정보 조회

    Args:
        latitude: 위도
        longitude: 경도

    Returns:
        건물 정보 딕셔너리
    """
    try:
        db = DatabaseConnection()
        building_info = db.fetch_building_info(latitude, longitude)

        if not building_info:
            logger.warning(f"Building info not found at ({latitude}, {longitude}) - using default")
            return _get_default_building_info()

        return building_info

    except Exception as e:
        logger.error(f"Failed to fetch building info: {e}")
        return _get_default_building_info()


def _get_default_building_info() -> Dict[str, Any]:
    """기본 건물 정보"""
    return {
        "building_age": 20,
        "structure": "철근콘크리트",
        "main_purpose": "주거시설",
        "floors_below": 0,
        "floors_above": 5,
        "total_area": 1000.0,
        "arch_area": 200.0,
        "has_piloti": False,
        "has_seismic_design": True,
        "elevation": 50.0,
    }


# ========== E 계산 ==========
def calculate_exposure(
    latitude: float,
    longitude: float,
    scenario: str,
    target_year: int,
    risk_type: str,
    pre_collected_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    E (Exposure) 계산

    Args:
        latitude: 위도
        longitude: 경도
        scenario: SSP 시나리오
        target_year: 분석 연도
        risk_type: 리스크 타입
        pre_collected_data: 사전 수집된 데이터 (선택적)

    Returns:
        {
            'exposure_score': float,  # 0-100 점수
            'raw_data': Dict          # 원본 계산 결과
        }
    """
    try:
        agent = EXPOSURE_AGENTS.get(risk_type)
        if not agent:
            logger.warning(f"Unknown risk_type for exposure: {risk_type}")
            return {
                "exposure_score": 0.0,
                "raw_data": {},
                "error": f"Unknown risk_type: {risk_type}",
            }

        # pre_collected_data가 있으면 사용, 없으면 새로 수집
        if pre_collected_data:
            collected_data = pre_collected_data
        else:
            # HazardDataCollector로 데이터 수집
            collector = HazardDataCollector(scenario=scenario, target_year=target_year)
            collected_data = collector.collect_data(
                lat=latitude, lon=longitude, risk_type=risk_type
            )

        # 필요한 데이터 추출
        building_data = collected_data.get("building_data", {})
        spatial_data = collected_data.get("spatial_data", {})
        climate_data = collected_data.get("climate_data", {})

        # ExposureAgent 호출 (climate_data도 kwargs로 전달)
        e_result = agent.calculate_exposure(
            building_data=building_data,
            spatial_data=spatial_data,
            latitude=latitude,
            longitude=longitude,
            climate_data=climate_data,
        )

        exposure_score = e_result.get("score", 0.0)

        return {
            "exposure_score": exposure_score,
            "raw_data": e_result,
            "building_data": building_data,  # Vulnerability에서 사용
        }

    except Exception as e:
        logger.error(f"Exposure calculation failed for {risk_type}: {e}")
        return {"exposure_score": 0.0, "raw_data": {}, "error": str(e)}


# ========== V 계산 ==========
def calculate_vulnerability(
    latitude: float, longitude: float, risk_type: str, exposure_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    V (Vulnerability) 계산

    Args:
        latitude: 위도
        longitude: 경도
        risk_type: 리스크 타입
        exposure_data: Exposure 계산 결과

    Returns:
        {
            'vulnerability_score': float,  # 0-100 점수
            'vulnerability_level': str,    # very_high/high/medium/low/very_low
            'factors': Dict,               # 취약성 요인
            'raw_data': Dict               # 원본 계산 결과
        }
    """
    try:
        agent = VULNERABILITY_AGENTS.get(risk_type)
        if not agent:
            logger.warning(f"Unknown risk_type for vulnerability: {risk_type}")
            return {
                "vulnerability_score": 50.0,
                "vulnerability_level": "medium",
                "factors": {},
                "raw_data": {},
                "error": f"Unknown risk_type: {risk_type}",
            }

        # VulnerabilityAgent 호출
        # exposure_data에 building_data 포함 → Vulnerability가 DB 데이터 사용 가능
        raw_data = exposure_data.get("raw_data", {})
        building_data = exposure_data.get("building_data", {})

        # raw_data에 building 정보 추가 (Vulnerability가 사용할 수 있도록)
        # flood_exposure 구조 추가 (River Flood Vulnerability가 사용)
        # has_water_tank 등을 building에 병합 (Water Stress Vulnerability가 사용)
        merged_building = {
            **building_data,
            "has_water_tank": raw_data.get("has_water_tank", building_data.get("has_water_tank")),
            "water_tank_method": raw_data.get("water_tank_method", "not_available"),
            "elevation_m": raw_data.get("elevation_m", building_data.get("elevation_m", 50.0)),
        }

        raw_data_with_building = {
            **raw_data,
            "building": merged_building,
            "flood_exposure": {
                "in_flood_zone": raw_data.get("in_flood_zone", False),
                "flood_zone_type": raw_data.get("flood_zone_type"),
            },
        }

        v_result = agent.calculate_vulnerability(
            raw_data_with_building, latitude=latitude, longitude=longitude
        )

        return {
            "vulnerability_score": v_result.get("score", 50.0),
            "vulnerability_level": v_result.get("level", "medium"),
            "factors": v_result.get("factors", {}),
            "raw_data": v_result,
        }

    except Exception as e:
        logger.error(f"Vulnerability calculation failed for {risk_type}: {e}")
        return {
            "vulnerability_score": 50.0,
            "vulnerability_level": "medium",
            "factors": {},
            "raw_data": {},
            "error": str(e),
        }


# ========== AAL 계산 ==========
def calculate_aal(
    base_aal: float,
    vulnerability_score: float,
    insurance_rate: float = 0.0,
    asset_value: Optional[float] = None,
) -> Dict[str, Any]:
    """
    AAL (Average Annual Loss) 계산

    Args:
        base_aal: 기본 AAL (P(H)의 aal)
        vulnerability_score: V 점수 (0-100)
        insurance_rate: 보험 가입률 (0-1)
        asset_value: 자산 가치 (선택)

    Returns:
        {
            'base_aal': float,
            'vulnerability_scale': float,
            'final_aal': float,
            'insurance_rate': float,
            'expected_loss': Optional[float],
            'grade': str
        }
    """
    try:
        aal_result = AAL_AGENT.scale_aal(
            base_aal=base_aal,
            vulnerability_score=vulnerability_score,
            insurance_rate=insurance_rate,
            asset_value=asset_value,
        )

        # AAL 등급 분류
        final_aal = aal_result.get("final_aal", 0.0)
        grade = AAL_AGENT.classify_aal_grade(final_aal)
        aal_result["grade"] = grade

        return aal_result

    except Exception as e:
        logger.error(f"AAL calculation failed: {e}")
        return {
            "base_aal": base_aal,
            "vulnerability_scale": 1.0,
            "final_aal": base_aal,
            "insurance_rate": insurance_rate,
            "expected_loss": None,
            "grade": "-",
            "error": str(e),
        }


# ========== 통합 리스크 계산 ==========
def calculate_integrated_risk(h_score: float, e_score: float, v_score: float) -> Dict[str, Any]:
    """
    통합 리스크 계산 (H × E × V)

    Args:
        h_score: Hazard 점수 (0-100)
        e_score: Exposure 점수 (0-100)
        v_score: Vulnerability 점수 (0-100)

    Returns:
        {
            'h_score': float,
            'e_score': float,
            'v_score': float,
            'integrated_risk_score': float,  # 0-100
            'risk_level': str,               # Very High/High/Medium/Low/Very Low
            'calculation_method': str,
            'formula': str
        }
    """
    # H × E × V / 10000 (0-100 범위로 정규화)
    raw_risk = (h_score * e_score * v_score) / 10000.0

    # 위험도 등급 분류
    if raw_risk >= 80:
        risk_level = "Very High"
    elif raw_risk >= 60:
        risk_level = "High"
    elif raw_risk >= 40:
        risk_level = "Medium"
    elif raw_risk >= 20:
        risk_level = "Low"
    else:
        risk_level = "Very Low"

    return {
        "h_score": round(h_score, 2),
        "e_score": round(e_score, 2),
        "v_score": round(v_score, 2),
        "integrated_risk_score": round(raw_risk, 2),
        "risk_level": risk_level,
        "calculation_method": "H × E × V / 10000",
        "formula": f"{h_score:.2f} × {e_score:.2f} × {v_score:.2f} / 10000 = {raw_risk:.2f}",
    }


def _classify_score(score: float) -> str:
    """
    점수를 등급으로 분류 (0-100)

    Args:
        score: 점수 (0-100)

    Returns:
        등급 (Very High / High / Medium / Low / Very Low)
    """
    if score >= 80:
        return "Very High"
    elif score >= 60:
        return "High"
    elif score >= 40:
        return "Medium"
    elif score >= 20:
        return "Low"
    else:
        return "Very Low"


# ========== DB 저장 함수 ==========
def _save_results_to_db(
    latitude: float,
    longitude: float,
    risk_types: List[str],
    results: Dict[str, Any],
    target_year: str = "2050",
    scenario: str = "SSP245",
    site_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    계산 결과를 DB에 저장

    Args:
        latitude: 위도
        longitude: 경도
        risk_types: 리스크 타입 리스트
        results: 계산 결과 딕셔너리
        target_year: 목표 연도 (문자열, "2030" 또는 "2020s" 형식)
        scenario: SSP 시나리오
        site_id: 사업장 ID (선택)

    Returns:
        저장 결과 요약
    """
    save_summary = {"exposure_saved": 0, "vulnerability_saved": 0, "aal_saved": 0, "errors": []}

    try:
        # 1. Exposure 결과 저장
        exposure_records = []
        for risk_type in risk_types:
            e_data = results["exposure"].get(risk_type, {})

            exposure_records.append(
                {
                    "site_id": site_id,
                    "latitude": latitude,
                    "longitude": longitude,
                    "risk_type": risk_type,
                    "target_year": target_year,
                    "exposure_score": e_data.get("exposure_score", 0.0),
                }
            )

        if exposure_records:
            DatabaseConnection.save_exposure_results(exposure_records)
            save_summary["exposure_saved"] = len(exposure_records)
            logger.info(f"Saved {len(exposure_records)} exposure results")

        # 2. Vulnerability 결과 저장
        vulnerability_records = []
        for risk_type in risk_types:
            v_data = results["vulnerability"].get(risk_type, {})

            vulnerability_records.append(
                {
                    "site_id": site_id,
                    "latitude": latitude,
                    "longitude": longitude,
                    "risk_type": risk_type,
                    "target_year": target_year,
                    "vulnerability_score": v_data.get("vulnerability_score", 50.0),
                }
            )

        if vulnerability_records:
            DatabaseConnection.save_vulnerability_results(vulnerability_records)
            save_summary["vulnerability_saved"] = len(vulnerability_records)
            logger.info(f"Saved {len(vulnerability_records)} vulnerability results")

        # 3. AAL Scaled 결과 저장
        aal_records = []
        for risk_type in risk_types:
            aal_data = results["aal"].get(risk_type, {})

            aal_records.append(
                {
                    "site_id": site_id,
                    "latitude": latitude,
                    "longitude": longitude,
                    "risk_type": risk_type,
                    "target_year": target_year,
                    "scenario": scenario,
                    "final_aal": aal_data.get("final_aal", 0.0),
                }
            )

        if aal_records:
            DatabaseConnection.save_aal_scaled_results(aal_records)
            save_summary["aal_saved"] = len(aal_records)
            logger.info(f"Saved {len(aal_records)} AAL scaled results")

    except Exception as e:
        error_msg = f"DB save error: {str(e)}"
        logger.error(error_msg)
        save_summary["errors"].append(error_msg)

    return save_summary


# ========== 메인 API 함수 ==========
def calculate_evaal_ondemand(
    latitude: float,
    longitude: float,
    scenario: str = "SSP245",
    target_year: int = 2030,
    risk_types: Optional[List[str]] = None,
    insurance_rate: float = 0.0,
    asset_value: Optional[float] = None,
    save_to_db: bool = False,
    site_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    E, V, AAL On-Demand 계산 (API 호출용 메인 함수)

    Args:
        latitude: 위도
        longitude: 경도
        scenario: SSP 시나리오 (SSP126, SSP245, SSP370, SSP585)
        target_year: 분석 연도 (2021-2100)
        risk_types: 리스크 타입 리스트 (None이면 전체 9개)
        insurance_rate: 보험 가입률 (0-1)
        asset_value: 자산 가치 (선택)
        save_to_db: DB 저장 여부 (기본 False)

    Returns:
        {
            'status': 'success' | 'error',
            'latitude': float,
            'longitude': float,
            'scenario': str,
            'target_year': int,
            'results': {
                'hazard': {risk_type: {...}},
                'probability': {risk_type: {...}},
                'exposure': {risk_type: {...}},
                'vulnerability': {risk_type: {...}},
                'aal': {risk_type: {...}},
                'integrated_risk': {risk_type: {...}}
            },
            'summary': {...},
            'metadata': {...}
        }
    """
    start_time = datetime.now()

    try:
        # Time Scope 및 Year 파싱
        time_scope = "yearly"
        int_year = 2030

        if isinstance(target_year, str) and target_year.endswith("s"):
            try:
                int_year = int(target_year.replace("s", ""))
                time_scope = "decadal"
            except ValueError:
                logger.warning(
                    f"Invalid target_year string: {target_year}. Defaulting to 2030 yearly."
                )
                int_year = 2030
        else:
            int_year = int(target_year)

        # Decadal 분석 시 연도 보정 (예: 2025 -> 2020)
        if time_scope == "decadal":
            int_year = (int_year // 10) * 10
            if int_year < 2020:
                int_year = 2020

        # 기본값 설정
        if risk_types is None:
            risk_types = [
                "extreme_heat",
                "extreme_cold",
                "drought",
                "river_flood",
                "urban_flood",
                "sea_level_rise",
                "typhoon",
                "wildfire",
                "water_stress",
            ]

        logger.info(
            f"Starting E, V, AAL calculation: "
            f"({latitude}, {longitude}), {scenario}, {target_year}"
        )

        results = {
            "hazard": {},
            "probability": {},
            "exposure": {},
            "vulnerability": {},
            "aal": {},
            "integrated_risk": {},
        }

        # Decadal 분석 시 10년치 기후 데이터 조회
        long_term_data = None
        if time_scope == "decadal":
            try:
                from ..database.connection_long import DatabaseConnectionLong

                decade = int_year  # 이미 보정된 값 (2020, 2030 등)
                long_term_data = DatabaseConnectionLong.fetch_climate_data_by_decade(
                    latitude, longitude, decade, scenario.lower()
                )
                logger.info(
                    f"Loaded decadal climate data for {decade}s: {len(long_term_data)} records"
                )
            except Exception as e:
                logger.error(f"Failed to fetch decadal climate data for {int_year}: {e}")
                long_term_data = {}

        # 리스크별 계산
        for risk_type in risk_types:
            logger.debug(f"Calculating {risk_type}...")

            # Step 1: DB에서 H, P(H) 조회
            h_result = fetch_hazard_from_db(latitude, longitude, scenario, target_year, risk_type)
            p_result = fetch_probability_from_db(
                latitude, longitude, scenario, target_year, risk_type
            )

            results["hazard"][risk_type] = h_result
            results["probability"][risk_type] = p_result

            # Step 2: E, V 계산
            if time_scope == "decadal":
                # Decadal 분석: 10년치 E, V 계산 후 평균
                # 2020s → 2021~2029년 (9년)
                # 2030s → 2030~2039년 (10년)
                start_year = int_year + (1 if int_year == 2020 else 0)
                end_year = int_year + 9

                # 2050년 초과 시 범위 조정
                end_year = min(end_year, 2050)

                logger.info(f"Decadal E, V calculation for {risk_type}: {start_year}-{end_year}")

                e_scores = []
                v_scores = []

                for year in range(start_year, end_year + 1):
                    # 각 연도별 E 계산 (long_term_data 사용)
                    if long_term_data:
                        base_info = {
                            "latitude": latitude,
                            "longitude": longitude,
                            "scenario": scenario,
                            "target_year": year,
                            "time_scope": "yearly",  # 연도별 계산
                            "building_data": None,
                        }
                        pre_collected_data = LongTermDataMapper.map_data(
                            risk_type, long_term_data, base_info
                        )
                    else:
                        pre_collected_data = None

                    e_result_yearly = calculate_exposure(
                        latitude,
                        longitude,
                        scenario,
                        year,
                        risk_type,
                        pre_collected_data=pre_collected_data,
                    )
                    e_scores.append(e_result_yearly.get("exposure_score", 0.0))

                    # 각 연도별 V 계산
                    v_result_yearly = calculate_vulnerability(
                        latitude, longitude, risk_type, e_result_yearly
                    )
                    v_scores.append(v_result_yearly.get("vulnerability_score", 50.0))

                # 평균 계산
                avg_e_score = sum(e_scores) / len(e_scores) if e_scores else 0.0
                avg_v_score = sum(v_scores) / len(v_scores) if v_scores else 50.0

                e_result = {
                    "exposure_score": avg_e_score,
                    "exposure_level": _classify_score(avg_e_score),
                }
                v_result = {
                    "vulnerability_score": avg_v_score,
                    "vulnerability_level": _classify_score(avg_v_score),
                }

                logger.info(f"{risk_type} decadal avg: E={avg_e_score:.2f}, V={avg_v_score:.2f}")

            else:
                # Yearly 분석: 단년도 계산
                year_for_ev_calculation = min(int_year, 2050)

                # LongTermDataMapper는 yearly에서는 사용하지 않음
                e_result = calculate_exposure(
                    latitude,
                    longitude,
                    scenario,
                    year_for_ev_calculation,
                    risk_type,
                    pre_collected_data=None,
                )
                v_result = calculate_vulnerability(latitude, longitude, risk_type, e_result)

            results["exposure"][risk_type] = e_result
            results["vulnerability"][risk_type] = v_result

            # Step 4: AAL 계산
            base_aal = p_result.get("aal", 0.0)
            v_score = v_result.get("vulnerability_score", 50.0)
            aal_result = calculate_aal(base_aal, v_score, insurance_rate, asset_value)
            results["aal"][risk_type] = aal_result

            # Step 5: 통합 리스크 계산 (H × E × V)
            h_score = h_result.get("hazard_score_100", 0.0)
            e_score = e_result.get("exposure_score", 0.0)
            integrated_risk = calculate_integrated_risk(h_score, e_score, v_score)
            results["integrated_risk"][risk_type] = integrated_risk

        # 요약 통계 계산
        summary = _calculate_summary(results)

        # DB 저장 (옵션)
        save_summary = None
        if save_to_db:
            logger.info("Saving results to DB...")

            # target_year를 원본 형식으로 변환 (DB는 varchar이므로 "2020s" 형식 지원)
            # yearly: target_year=2030 → "2030"
            # decadal: target_year="2020s" → "2020s" (원본 유지)
            if time_scope == "decadal":
                db_target_year = f"{int_year}s"  # 2020 → "2020s"
            else:
                db_target_year = str(target_year) if isinstance(target_year, int) else target_year

            save_summary = _save_results_to_db(
                latitude,
                longitude,
                risk_types,
                results,
                target_year=db_target_year,  # "2020s" 또는 "2030" 형식
                scenario=scenario,
                site_id=site_id,
            )
            logger.info(f"DB save completed: {save_summary}")

        # 메타데이터
        end_time = datetime.now()
        metadata = {
            "latitude": latitude,
            "longitude": longitude,
            "scenario": scenario,
            "target_year": target_year,  # 원본 형식 반환 ("2020s" 또는 2030)
            "time_scope": time_scope,
            "calculation_time": (end_time - start_time).total_seconds(),
            "calculated_at": end_time.isoformat(),
            "total_risks_processed": len(risk_types),
            "saved_to_db": save_to_db,
        }

        logger.info(f"E, V, AAL calculation completed: {metadata['calculation_time']:.2f}s")

        response = {
            "status": "success",
            "latitude": latitude,
            "longitude": longitude,
            "scenario": scenario,
            "target_year": target_year,
            "results": results,
            "summary": summary,
            "metadata": metadata,
        }

        # 저장 결과 포함
        if save_summary:
            response["save_summary"] = save_summary

        return response

    except Exception as e:
        logger.error(f"E, V, AAL calculation failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "latitude": latitude,
            "longitude": longitude,
            "scenario": scenario,
            "target_year": target_year,
        }


# ========== 후보지 추천 (Relocation) ==========
def recommend_locations_ondemand(
    candidate_grids: List[Dict[str, float]],
    building_info: Optional[Dict[str, Any]] = None,
    asset_info: Optional[Dict[str, Any]] = None,
    scenario: str = "SSP245",
    target_year: int = 2040,
    max_candidates: int = 3,
) -> Dict[str, Any]:
    """
    사업장 이전 후보지 추천 (On-Demand)

    Args:
        candidate_grids: 후보 격자 리스트 [{'latitude': ..., 'longitude': ...}, ...]
        building_info: 건물 정보 (None이면 기본값 사용)
        asset_info: 자산 정보 (선택)
        scenario: SSP 시나리오
        target_year: 목표 연도
        max_candidates: 추천 개수

    Returns:
        추천 결과 딕셔너리
    """
    try:
        # 건물 정보가 없으면 기본값 사용
        if not building_info:
            building_info = _get_default_building_info()

        recommender = RelocationRecommender(scenario=scenario, target_year=target_year)

        result = recommender.recommend_locations(
            candidate_grids=candidate_grids,
            building_info=building_info,
            asset_info=asset_info,
            max_candidates=max_candidates,
        )

        return {
            "status": "success",
            "scenario": scenario,
            "target_year": target_year,
            "recommendation_result": result,
        }

    except Exception as e:
        logger.error(f"Location recommendation failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "scenario": scenario,
            "target_year": target_year,
        }


def compare_current_and_candidates_ondemand(
    current_site: Dict[str, float],  # {'latitude': ..., 'longitude': ...}
    recommended_candidates_result: Dict[
        str, Any
    ],  # The 'recommendation_result' from recommend_locations_ondemand
    building_info: Optional[Dict[str, Any]] = None,
    asset_info: Optional[Dict[str, Any]] = None,
    scenario: str = "SSP245",
    target_year: int = 2040,
) -> Dict[str, Any]:
    """
    현재 사업장과 추천 후보지들 간의 리스크를 비교 (On-Demand)

    Args:
        current_site: 현재 사업장 정보 {'latitude': ..., 'longitude': ...}
        recommended_candidates_result: recommend_locations_ondemand의 'recommendation_result' 필드 값
        building_info: 건물 정보 (None이면 기본값 사용)
        asset_info: 자산 정보 (선택)
        scenario: SSP 시나리오
        target_year: 목표 연도

    Returns:
        비교 결과 딕셔너리
    """
    try:
        if not building_info:
            building_info = _get_default_building_info()

        recommender = RelocationRecommender(scenario=scenario, target_year=target_year)

        comparison_result = recommender.compare_current_and_candidates(
            current_site=current_site,
            candidate_result=recommended_candidates_result,
            building_info=building_info,
            asset_info=asset_info,
        )

        return {
            "status": "success",
            "scenario": scenario,
            "target_year": target_year,
            "comparison_result": comparison_result,
        }

    except Exception as e:
        logger.error(f"Comparison between current site and candidates failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "scenario": scenario,
            "target_year": target_year,
        }


# ========== 요약 통계 ==========
def _calculate_summary(results: Dict[str, Any]) -> Dict[str, Any]:
    """요약 통계 계산"""
    # 평균 점수
    h_scores = [h.get("hazard_score_100", 0.0) for h in results["hazard"].values()]
    e_scores = [e.get("exposure_score", 0.0) for e in results["exposure"].values()]
    v_scores = [v.get("vulnerability_score", 0.0) for v in results["vulnerability"].values()]
    risk_scores = [r.get("integrated_risk_score", 0.0) for r in results["integrated_risk"].values()]

    avg_hazard = sum(h_scores) / len(h_scores) if h_scores else 0.0
    avg_exposure = sum(e_scores) / len(e_scores) if e_scores else 0.0
    avg_vulnerability = sum(v_scores) / len(v_scores) if v_scores else 0.0
    avg_integrated_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0.0

    # 최고 통합 리스크
    highest_integrated_risk = max(
        results["integrated_risk"].items(),
        key=lambda x: x[1].get("integrated_risk_score", 0.0),
        default=(None, {}),
    )

    # 최고 AAL 리스크
    highest_aal_risk = max(
        results["aal"].items(), key=lambda x: x[1].get("final_aal", 0.0), default=(None, {})
    )

    # Top 3 리스크
    top_3_risks = sorted(
        results["integrated_risk"].items(),
        key=lambda x: x[1].get("integrated_risk_score", 0.0),
        reverse=True,
    )[:3]

    return {
        "average_hazard": round(avg_hazard, 2),
        "average_exposure": round(avg_exposure, 2),
        "average_vulnerability": round(avg_vulnerability, 2),
        "average_integrated_risk": round(avg_integrated_risk, 2),
        "highest_integrated_risk": (
            {
                "risk_type": highest_integrated_risk[0],
                "score": highest_integrated_risk[1].get("integrated_risk_score", 0.0),
                "level": highest_integrated_risk[1].get("risk_level", "Very Low"),
            }
            if highest_integrated_risk[0]
            else None
        ),
        "highest_aal_risk": (
            {
                "risk_type": highest_aal_risk[0],
                "final_aal": highest_aal_risk[1].get("final_aal", 0.0),
                "grade": highest_aal_risk[1].get("grade", "-"),
            }
            if highest_aal_risk[0]
            else None
        ),
        "top_3_risks": [
            {
                "rank": i + 1,
                "risk_type": risk_type,
                "score": risk_data.get("integrated_risk_score", 0.0),
                "level": risk_data.get("risk_level", "Very Low"),
            }
            for i, (risk_type, risk_data) in enumerate(top_3_risks)
        ],
    }
