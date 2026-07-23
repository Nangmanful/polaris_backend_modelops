import sys
import os
import logging

# 프로젝트 루트 경로 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, "..", "..")
sys.path.append(project_root)

# 로거 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EVIntegrationTest")

from modelops.utils.hazard_data_collector import HazardDataCollector
from modelops.agents.risk_assessment.exposure_agent import ExposureAgent
from modelops.agents.risk_assessment.vulnerability_agent import VulnerabilityAgent


def test_ev_integration():
    logger.info("Starting Exposure & Vulnerability Integration Test...")

    # 1. 설정
    lat = 37.5172  # 서울 강남
    lon = 127.0473
    scenario = "SSP245"
    target_year = 2030

    # 2. Collector 초기화
    logger.info("Initializing HazardDataCollector...")
    collector = HazardDataCollector(scenario=scenario, target_year=target_year)

    # 3. 데이터 수집 (Exposure용)
    # risk_type='exposure'로 호출하여 building_data와 spatial_data(landcover 등)를 모두 수집
    try:
        collected_data = collector.collect_data(lat, lon, risk_type="exposure")
        logger.info("✅ Data collected for Exposure/Vulnerability calculation")
    except Exception as e:
        logger.error(f"❌ Data collection failed: {e}")
        return

    # 4. Exposure 계산
    exposure_agent = ExposureAgent()
    try:
        exposure_results = exposure_agent.calculate_exposure(collected_data)
        logger.info("✅ Exposure calculation success")
        # 간략한 결과 출력
        bldg = exposure_results.get("building", {})
        loc = exposure_results.get("location", {})
        logger.info(f"   - Building: {bldg.get('main_purpose')}, {bldg.get('ground_floors')}F")
        logger.info(f"   - Land Use: {loc.get('land_use')}")

        # collected_data에 결과 저장 (VulnerabilityAgent가 사용하도록)
        collected_data["exposure_results"] = exposure_results
    except Exception as e:
        logger.error(f"❌ Exposure calculation failed: {e}")
        return

    # 5. Vulnerability 계산
    vulnerability_agent = VulnerabilityAgent()
    try:
        vulnerability_results = vulnerability_agent.calculate_vulnerability(collected_data)
        logger.info("✅ Vulnerability calculation success")

        # 결과 출력
        logger.info("=" * 50)
        logger.info("Vulnerability Scores:")
        for risk, res in vulnerability_results.items():
            logger.info(f"   - {risk}: {res.get('score')} ({res.get('level')})")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"❌ Vulnerability calculation failed: {e}")
        return

    logger.info("Test Complete.")


if __name__ == "__main__":
    test_ev_integration()
