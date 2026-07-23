"""
파일명: probability_timeseries_batch.py
최종 수정일: 2025-12-15
버전: v01
파일 개요: Probability P(H) 시계열 배치 계산 전용 (2021-2100)
스케줄: 매년 1월 1일 02:00 실행
변경 이력:
    - 2025-12-15: v01 - P(H) 전용 배치 생성
        * hazard_probability_timeseries_batch.py에서 P(H) 계산 로직 분리
        * ProcessPoolExecutor를 사용한 멀티프로세싱
        * tqdm 진행률 표시
        * SSP126, SSP245, SSP370, SSP585 4개 시나리오
        * 2021-2100년 (80년) 1년 단위 계산
        * 9개 리스크 타입별 P(H) 계산
"""

import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

# Probability Agents
from ..agents.probability_calculate.extreme_heat_probability_agent import (
    ExtremeHeatProbabilityAgent,
)
from ..agents.probability_calculate.extreme_cold_probability_agent import (
    ExtremeColdProbabilityAgent,
)
from ..agents.probability_calculate.drought_probability_agent import DroughtProbabilityAgent
from ..agents.probability_calculate.river_flood_probability_agent import RiverFloodProbabilityAgent
from ..agents.probability_calculate.urban_flood_probability_agent import UrbanFloodProbabilityAgent
from ..agents.probability_calculate.sea_level_rise_probability_agent import (
    SeaLevelRiseProbabilityAgent,
)
from ..agents.probability_calculate.typhoon_probability_agent import TyphoonProbabilityAgent
from ..agents.probability_calculate.wildfire_probability_agent import WildfireProbabilityAgent
from ..agents.probability_calculate.water_stress_probability_agent import (
    WaterStressProbabilityAgent,
)

# Utils
from ..database.connection import DatabaseConnection

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


# ========== 병렬 처리 워커 함수 (P(H) 전용) ==========
def _process_probability_task_worker(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    워커 프로세스에서 실행되는 독립 함수 (pickle 가능)
    하나의 격자점, 시나리오, 연도에 대해 9개 리스크의 P(H)를 계산

    Args:
        task: {
            'latitude': float,
            'longitude': float,
            'scenario': str,
            'year': int,
            'risk_types': List[str]
        }

    Returns:
        {
            'status': 'success' or 'failed',
            'task': task,
            'probability_results': List[Dict],
            'error': str (실패 시)
        }
    """
    lat = task["latitude"]
    lon = task["longitude"]
    scenario = task["scenario"]
    year = task["year"]
    risk_types = task["risk_types"]

    try:
        # 각 워커마다 독립적으로 에이전트 생성
        probability_agents = {
            "extreme_heat": ExtremeHeatProbabilityAgent(),
            "extreme_cold": ExtremeColdProbabilityAgent(),
            "drought": DroughtProbabilityAgent(),
            "river_flood": RiverFloodProbabilityAgent(),
            "urban_flood": UrbanFloodProbabilityAgent(),
            "sea_level_rise": SeaLevelRiseProbabilityAgent(),
            "typhoon": TyphoonProbabilityAgent(),
            "wildfire": WildfireProbabilityAgent(),
            "water_stress": WaterStressProbabilityAgent(),
        }

        probability_results = []

        # 각 리스크 타입별로 P(H) 계산
        for risk_type in risk_types:
            try:
                # P(H) 계산
                p_agent = probability_agents[risk_type]
                p_result = p_agent.calculate(
                    lat=lat, lon=lon, ssp_scenario=scenario, start_year=2021, end_year=2100
                )

                aal = p_result.get("aal", 0.0)
                if aal >= 0.03:
                    probability_level = "Very High"
                elif aal >= 0.02:
                    probability_level = "High"
                elif aal >= 0.01:
                    probability_level = "Medium"
                elif aal >= 0.005:
                    probability_level = "Low"
                else:
                    probability_level = "Very Low"

                probability_results.append(
                    {
                        "latitude": lat,
                        "longitude": lon,
                        "scenario": scenario,
                        "target_year": year,
                        "risk_type": risk_type,
                        "aal": aal,
                        "bin_probabilities": p_result.get("bin_probabilities", []),
                        "probability_level": probability_level,
                    }
                )

            except Exception as e:
                # 개별 리스크 실패는 로깅만 하고 계속 진행
                logger.error(
                    f"Risk {risk_type} failed for {scenario} {year} " f"at ({lat}, {lon}): {e}"
                )

        return {
            "status": "success",
            "task": task,
            "probability_results": probability_results,
            "risks_calculated": len(probability_results),
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
def save_probability_results(results: List[Dict[str, Any]]) -> None:
    """P(H) 결과를 DB에 배치 저장"""
    try:
        db = DatabaseConnection()
        db.save_probability_results(results)
        logger.debug(f"Saved {len(results)} probability results to DB")
    except Exception as e:
        logger.error(f"Failed to save probability results: {e}")


# ========== 메인 배치 실행 (병렬 처리) ==========
def run_probability_batch(
    grid_points: List[Tuple[float, float]] = None,
    scenarios: List[str] = None,
    years: List[int] = None,
    risk_types: List[str] = None,
    batch_size: int = 100,
    max_workers: int = 4,
) -> None:
    """
    모든 격자점에 대해 P(H) 시계열 계산 (병렬 처리)

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
    logger.info("Probability P(H) Timeseries Batch Calculation Started (Parallel)")
    logger.info(f"Grid Points: {len(grid_points)}")
    logger.info(f"Scenarios: {scenarios}")
    logger.info(f"Years: {min(years)}-{max(years)} ({len(years)} years)")
    logger.info(f"Risk Types: {len(risk_types)}")
    logger.info(f"Total Tasks: {total_tasks:,} (each with {len(risk_types)} risks)")
    logger.info(f"Total Calculations: {total_calculations:,}")
    logger.info(f"Parallel Workers: {max_workers}")
    logger.info(f"Batch Size: {batch_size}")
    logger.info("=" * 80)

    probability_batch = []
    completed_count = 0
    failed_count = 0

    # ProcessPoolExecutor로 병렬 처리
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 모든 태스크 제출
        futures = {executor.submit(_process_probability_task_worker, task): task for task in tasks}

        # tqdm으로 진행률 표시
        with tqdm(total=total_tasks, desc="Processing Probabilities", unit="task") as pbar:
            for future in as_completed(futures):
                task = futures[future]
                try:
                    result = future.result(timeout=300)  # 개별 태스크 5분 timeout

                    if result["status"] == "success":
                        # 결과 배치에 추가
                        probability_batch.extend(result["probability_results"])
                        completed_count += 1

                        # 진행률 업데이트
                        pbar.set_postfix(
                            {
                                "success": completed_count,
                                "failed": failed_count,
                                "risks": f"{result['risks_calculated']}/{len(risk_types)}",
                                "pending_save": len(probability_batch),
                            }
                        )

                        # 배치 저장
                        if len(probability_batch) >= batch_size:
                            save_probability_results(probability_batch)
                            logger.debug(
                                f"Saved batch: {len(probability_batch)} probability results"
                            )
                            probability_batch = []

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
    if probability_batch:
        save_probability_results(probability_batch)
        logger.debug(f"Saved final probability batch: {len(probability_batch)} results")

    # 완료 요약
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    success_rate = (completed_count / total_tasks * 100) if total_tasks > 0 else 0

    logger.info("\n" + "=" * 80)
    logger.info("PROBABILITY BATCH CALCULATION COMPLETED")
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
    python -m modelops.batch.probability_timeseries_batch

    # 특정 시나리오만 (SSP245)
    python -m modelops.batch.probability_timeseries_batch --scenario SSP245

    # 특정 연도 범위만 (2021-2050)
    python -m modelops.batch.probability_timeseries_batch --start-year 2021 --end-year 2050

    # 워커 수 조정 (8개 병렬 프로세스)
    python -m modelops.batch.probability_timeseries_batch --workers 8

    # 조합 예시 (SSP245, 2021-2030, 배치 50, 워커 6)
    python -m modelops.batch.probability_timeseries_batch --scenario SSP245 --start-year 2021 --end-year 2030 --batch-size 50 --workers 6
    """

    try:
        # CLI 인자 파싱
        import argparse

        parser = argparse.ArgumentParser(
            description="Probability P(H) Timeseries Batch Calculation (Parallel Processing)"
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

            # 데이터 시작 범위 보정
            if start < 2020:
                start = 2020

            years = list(range(start, args.end_year + 1, 10))
        else:
            years = list(range(args.start_year, args.end_year + 1))

        # 배치 실행
        run_probability_batch(
            scenarios=scenarios, years=years, batch_size=args.batch_size, max_workers=args.workers
        )

        sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("\nProbability batch calculation interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"\nProbability batch calculation failed: {e}", exc_info=True)
        sys.exit(1)
