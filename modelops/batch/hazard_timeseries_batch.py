"""
파일명: hazard_timeseries_batch.py
최종 수정일: 2025-12-15
버전: v01
파일 개요: Hazard Score (H) 시계열 배치 계산 전용 (2021-2100)
스케줄: 매년 1월 1일 04:00 실행
변경 이력:
    - 2025-12-15: v01 - H 전용 배치 생성
        * hazard_probability_timeseries_batch.py에서 H 계산 로직 분리
        * ProcessPoolExecutor를 사용한 멀티프로세싱
        * tqdm 진행률 표시
        * SSP126, SSP245, SSP370, SSP585 4개 시나리오
        * 2021-2100년 (80년) 1년 단위 계산
        * 9개 리스크 타입별 H 계산
"""

import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

# Hazard Agents
from ..agents.hazard_calculate.extreme_heat_hscore_agent import ExtremeHeatHScoreAgent
from ..agents.hazard_calculate.extreme_cold_hscore_agent import ExtremeColdHScoreAgent
from ..agents.hazard_calculate.drought_hscore_agent import DroughtHScoreAgent
from ..agents.hazard_calculate.river_flood_hscore_agent import RiverFloodHScoreAgent
from ..agents.hazard_calculate.urban_flood_hscore_agent import UrbanFloodHScoreAgent
from ..agents.hazard_calculate.sea_level_rise_hscore_agent import SeaLevelRiseHScoreAgent
from ..agents.hazard_calculate.typhoon_hscore_agent import TyphoonHScoreAgent
from ..agents.hazard_calculate.wildfire_hscore_agent import WildfireHScoreAgent
from ..agents.hazard_calculate.water_stress_hscore_agent import WaterStressHScoreAgent

# Utils
from ..utils.hazard_data_collector import HazardDataCollector
from ..database.connection import DatabaseConnection
from ..database.connection_long import DatabaseConnectionLong
from ..data_loaders.long_term_mapper import LongTermDataMapper

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ========== 상수 정의 ==========
SCENARIOS = ["SSP126", "SSP245", "SSP370", "SSP585"]
YEARS = list(range(2021, 2101))  # 2021-2100 (80년)

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


# ========== 병렬 처리 워커 함수 (H 전용) ==========
def _process_hazard_task_worker(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    워커 프로세스에서 실행되는 독립 함수 (pickle 가능)
    하나의 격자점, 시나리오, 연도에 대해 9개 리스크의 H를 계산

    Args:
        task: {
            'latitude': float,
            'longitude': float,
            'scenario': str,
            'year': int,
            'risk_types': List[str],
            'time_scope': str  # 'yearly' or 'decadal'
        }

    Returns:
        {
            'status': 'success' or 'failed',
            'task': task,
            'hazard_results': List[Dict],
            'error': str (실패 시)
        }
    """
    lat = task["latitude"]
    lon = task["longitude"]
    scenario = task["scenario"]
    year = task["year"]
    risk_types = task["risk_types"]
    time_scope = task.get("time_scope", "yearly")

    try:
        # 각 워커마다 독립적으로 에이전트 생성
        hazard_agents = {
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

        hazard_results = []

        # 장기(decadal) 분석인 경우 해당 Decade의 기후 데이터 한 번 조회 (최적화)
        long_term_data = None
        if time_scope == "decadal":
            try:
                # 2030 -> 2030s 등 decade 식별
                decade = (year // 10) * 10
                long_term_data = DatabaseConnectionLong.fetch_climate_data_by_decade(
                    lat, lon, decade, scenario.lower() if scenario.startswith("SSP") else "ssp2"
                )
            except Exception as e:
                logger.error(f"Long-term data fetch failed for {year} at ({lat}, {lon}): {e}")
                long_term_data = {}

        # 각 리스크 타입별로 H 계산
        for risk_type in risk_types:
            try:
                collected_data = {}

                if time_scope == "decadal":
                    if not long_term_data:
                        raise ValueError("Long-term data is empty")

                    base_info = {
                        "latitude": lat,
                        "longitude": lon,
                        "scenario": scenario,
                        "target_year": year,
                        "time_scope": time_scope,
                        "building_data": None,  # H 계산시 건물정보 불필요
                    }
                    collected_data = LongTermDataMapper.map_data(
                        risk_type, long_term_data, base_info
                    )
                else:
                    # 기존 Yearly 방식
                    collector = HazardDataCollector(scenario=scenario, target_year=year)
                    collected_data = collector.collect_data(lat=lat, lon=lon, risk_type=risk_type)

                h_agent = hazard_agents[risk_type]
                h_result = h_agent.calculate_hazard_score(collected_data)

                hazard_results.append(
                    {
                        "latitude": lat,
                        "longitude": lon,
                        "scenario": scenario,
                        "target_year": year,
                        "risk_type": risk_type,
                        "hazard_score": h_result.get("hazard_score", 0.0),
                        "hazard_score_100": h_result.get("hazard_score_100", 0.0),
                        "hazard_level": h_result.get("hazard_level", "Very Low"),
                    }
                )

            except Exception as e:
                # 개별 리스크 실패는 로깅만 하고 계속 진행
                # logger.error(
                #     f"Risk {risk_type} failed for {scenario} {year} "
                #     f"at ({lat}, {lon}): {e}"
                # )
                pass

        return {
            "status": "success",
            "task": task,
            "hazard_results": hazard_results,
            "risks_calculated": len(hazard_results),
        }

    except Exception as e:
        return {"status": "failed", "task": task, "error": str(e)}


# ========== 격자점 조회 ==========
def get_all_grid_points() -> List[Tuple[float, float]]:
    """
    DB에서 모든 격자점 좌표 조회

    Returns:
        [(latitude, longitude), ...]
    """
    try:
        db = DatabaseConnection()
        grid_points = db.fetch_all_grid_points()
        logger.info(f"Total grid points fetched: {len(grid_points)}")
        return grid_points
    except Exception as e:
        logger.error(f"Failed to fetch grid points: {e}")
        raise


# ========== DB 저장 ==========
def save_hazard_results(results: List[Dict[str, Any]]) -> None:
    """H 결과를 DB에 배치 저장"""
    try:
        db = DatabaseConnection()
        db.save_hazard_results(results)
        logger.debug(f"Saved {len(results)} hazard results to DB")
    except Exception as e:
        logger.error(f"Failed to save hazard results: {e}")


# ========== 메인 배치 실행 (병렬 처리) ==========
def run_hazard_batch(
    grid_points: List[Tuple[float, float]] = None,
    scenarios: List[str] = None,
    years: List[int] = None,
    risk_types: List[str] = None,
    batch_size: int = 100,
    max_workers: int = 4,
) -> None:
    """
    모든 격자점에 대해 H 시계열 계산 (병렬 처리)

    Args:
        grid_points: 계산할 격자점 리스트 (None이면 전체)
        scenarios: 계산할 시나리오 리스트 (None이면 전체)
        years: 계산할 연도 리스트 (None이면 2021-2100)
        risk_types: 계산할 리스크 타입 (None이면 전체 9개)
        batch_size: DB 저장 배치 크기
        max_workers: 병렬 워커 수 (기본 4)
    """
    # 기본값 설정
    if grid_points is None:
        grid_points = get_all_grid_points()
    if scenarios is None:
        scenarios = SCENARIOS
    if years is None:
        years = YEARS
    if risk_types is None:
        risk_types = RISK_TYPES

    start_time = datetime.now()

    # 작업 단위 생성: 각 (격자점, 시나리오, 연도) 조합마다 하나의 태스크
    tasks = []
    for scenario in scenarios:
        for year in years:
            for lat, lon in grid_points:
                tasks.append(
                    {
                        "latitude": lat,
                        "longitude": lon,
                        "scenario": scenario,
                        "year": year,
                        "risk_types": risk_types,
                    }
                )

    total_tasks = len(tasks)
    total_calculations = total_tasks * len(risk_types)  # 실제 계산량

    logger.info("=" * 80)
    logger.info("Hazard Score (H) Timeseries Batch Calculation Started (Parallel)")
    logger.info(f"Grid Points: {len(grid_points)}")
    logger.info(f"Scenarios: {scenarios}")
    logger.info(f"Years: {min(years)}-{max(years)} ({len(years)} years)")
    logger.info(f"Risk Types: {len(risk_types)}")
    logger.info(f"Total Tasks: {total_tasks:,} (each with {len(risk_types)} risks)")
    logger.info(f"Total Calculations: {total_calculations:,}")
    logger.info(f"Parallel Workers: {max_workers}")
    logger.info(f"Batch Size: {batch_size}")
    logger.info("=" * 80)

    hazard_batch = []
    completed_count = 0
    failed_count = 0

    # ProcessPoolExecutor로 병렬 처리
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 모든 태스크 제출
        futures = {executor.submit(_process_hazard_task_worker, task): task for task in tasks}

        # tqdm으로 진행률 표시
        with tqdm(total=total_tasks, desc="Processing Hazard Scores", unit="task") as pbar:
            for future in as_completed(futures):
                task = futures[future]
                try:
                    result = future.result(timeout=300)  # 개별 태스크 5분 timeout

                    if result["status"] == "success":
                        # 결과 배치에 추가
                        hazard_batch.extend(result["hazard_results"])
                        completed_count += 1

                        # 진행률 업데이트
                        pbar.set_postfix(
                            {
                                "success": completed_count,
                                "failed": failed_count,
                                "risks": f"{result['risks_calculated']}/{len(risk_types)}",
                                "pending_save": len(hazard_batch),
                            }
                        )

                        # 배치 저장
                        if len(hazard_batch) >= batch_size:
                            save_hazard_results(hazard_batch)
                            logger.debug(f"Saved batch: {len(hazard_batch)} hazard results")
                            hazard_batch = []

                    else:
                        failed_count += 1
                        logger.error(
                            f"Task failed for {task['scenario']} {task['year']} "
                            f"at ({task['latitude']}, {task['longitude']}): "
                            f"{result.get('error')}"
                        )
                        pbar.set_postfix({"success": completed_count, "failed": failed_count})

                except Exception as e:
                    failed_count += 1
                    logger.error(
                        f"Task exception for {task['scenario']} {task['year']} "
                        f"at ({task['latitude']}, {task['longitude']}): {e}"
                    )
                    pbar.set_postfix({"success": completed_count, "failed": failed_count})

                pbar.update(1)

    # 남은 배치 저장
    if hazard_batch:
        save_hazard_results(hazard_batch)
        logger.debug(f"Saved final hazard batch: {len(hazard_batch)} results")

    # 완료 요약
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    success_rate = (completed_count / total_tasks * 100) if total_tasks > 0 else 0

    logger.info("\n" + "=" * 80)
    logger.info("HAZARD SCORE BATCH CALCULATION COMPLETED")
    logger.info(f"Total Tasks: {total_tasks:,}")
    logger.info(f"Completed: {completed_count:,}")
    logger.info(f"Failed: {failed_count:,}")
    logger.info(f"Success Rate: {success_rate:.2f}%")
    logger.info(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
    logger.info(f"Avg Speed: {completed_count/duration:.2f} tasks/sec")
    logger.info("=" * 80)


# ========== 실행 진입점 ==========
if __name__ == "__main__":
    """
    실행 예시:

    # 전체 격자점, 전체 시나리오, 전체 연도, 전체 리스크 (기본 4 워커)
    python -m modelops.batch.hazard_timeseries_batch

    # 특정 시나리오만 (SSP245)
    python -m modelops.batch.hazard_timeseries_batch --scenario SSP245

    # 특정 연도 범위만 (2021-2050)
    python -m modelops.batch.hazard_timeseries_batch --start-year 2021 --end-year 2050

    # 워커 수 조정 (8개 병렬 프로세스)
    python -m modelops.batch.hazard_timeseries_batch --workers 8

    # 조합 예시 (SSP245, 2021-2030, 배치 50, 워커 6)
    python -m modelops.batch.hazard_timeseries_batch --scenario SSP245 --start-year 2021 --end-year 2030 --batch-size 50 --workers 6
    """

    try:
        # CLI 인자 파싱
        import argparse

        parser = argparse.ArgumentParser(
            description="Hazard Score (H) Timeseries Batch Calculation (Parallel Processing)"
        )
        parser.add_argument(
            "--scenario", type=str, help="Single scenario (SSP126, SSP245, SSP370, SSP585)"
        )
        parser.add_argument(
            "--start-year", type=int, default=2021, help="Start year (default: 2021)"
        )
        parser.add_argument("--end-year", type=int, default=2100, help="End year (default: 2100)")
        parser.add_argument(
            "--batch-size", type=int, default=100, help="DB batch size (default: 100)"
        )
        parser.add_argument(
            "--workers", type=int, default=4, help="Number of parallel workers (default: 4)"
        )

        args = parser.parse_args()

        # 시나리오 설정
        scenarios = [args.scenario] if args.scenario else SCENARIOS

        # 연도 설정
        if args.time_scope == "decadal":
            # 10년 단위 (2020, 2030, ..., 2090 등)
            # 입력된 시작 연도가 속한 10년대의 시작점 (내림 처리)
            start = (args.start_year // 10) * 10

            # 데이터 시작 범위 보정 (2020년 미만은 2020년으로)
            if start < 2020:
                start = 2020

            years = list(range(start, args.end_year + 1, 10))
        else:
            years = list(range(args.start_year, args.end_year + 1))

        # 배치 실행
        run_hazard_batch(
            scenarios=scenarios, years=years, batch_size=args.batch_size, max_workers=args.workers
        )

        sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("\nHazard batch calculation interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"\nHazard batch calculation failed: {e}", exc_info=True)
        sys.exit(1)
