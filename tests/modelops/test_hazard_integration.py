import sys
import os
import logging

# 프로젝트 루트 경로 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, "..", "..")
sys.path.append(project_root)

# 로거 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IntegrationTest")

from modelops.utils.hazard_data_collector import HazardDataCollector
from modelops.agents.hazard_calculate.extreme_heat_hscore_agent import ExtremeHeatHScoreAgent
from modelops.agents.hazard_calculate.extreme_cold_hscore_agent import ExtremeColdHScoreAgent
from modelops.agents.hazard_calculate.drought_hscore_agent import DroughtHScoreAgent
from modelops.agents.hazard_calculate.river_flood_hscore_agent import RiverFloodHScoreAgent
from modelops.agents.hazard_calculate.urban_flood_hscore_agent import UrbanFloodHScoreAgent
from modelops.agents.hazard_calculate.sea_level_rise_hscore_agent import SeaLevelRiseHScoreAgent
from modelops.agents.hazard_calculate.typhoon_hscore_agent import TyphoonHScoreAgent
from modelops.agents.hazard_calculate.wildfire_hscore_agent import WildfireHScoreAgent
from modelops.agents.hazard_calculate.water_stress_hscore_agent import WaterStressHScoreAgent


def test_hazard_integration():
    logger.info("Starting Hazard Integration Test...")

    # 1. 설정
    lat = 37.5172  # 서울 강남
    lon = 127.0473
    scenario = "SSP245"
    target_year = 2030

    # 2. Collector 초기화
    logger.info("Initializing HazardDataCollector...")
    collector = HazardDataCollector(scenario=scenario, target_year=target_year)

    # 3. 에이전트 매핑
    agents = {
        "extreme_heat": ExtremeHeatHScoreAgent(),
        "extreme_cold": ExtremeColdHScoreAgent(),
        "drought": DroughtHScoreAgent(),
        "river_flood": RiverFloodHScoreAgent(),
        "urban_flood": UrbanFloodHScoreAgent(),
        "sea_level_rise": SeaLevelRiseHScoreAgent(),
        "typhoon": TyphoonHScoreAgent(),
        "wildfire": WildfireHScoreAgent(),
        "water_stress": WaterStressHScoreAgent(),
    }

    results = {}

    # 4. 각 리스크별 실행
    for risk_type, agent in agents.items():
        logger.info(f"Testing {risk_type}...")

        # 데이터 수집
        try:
            collected_data = collector.collect_data(lat, lon, risk_type)
            logger.info(f"  - Data collected for {risk_type}")
        except Exception as e:
            logger.error(f"  - Data collection failed for {risk_type}: {e}")
            continue

        # 에이전트 실행
        try:
            result = agent.calculate_hazard_score(collected_data)
            logger.info(
                f"  - Calculation success: Score={result.get('hazard_score')}, Level={result.get('hazard_level')}"
            )
            results[risk_type] = result
        except Exception as e:
            logger.error(f"  - Calculation failed for {risk_type}: {e}")

    # 5. 결과 요약
    logger.info("=" * 50)
    logger.info("Integration Test Summary")
    logger.info("=" * 50)
    for risk, res in results.items():
        logger.info(f"{risk}: {res.get('hazard_score')} ({res.get('hazard_level')})")

    logger.info("Test Complete.")


if __name__ == "__main__":
    test_hazard_integration()
