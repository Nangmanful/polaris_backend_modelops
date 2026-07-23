"""
Site Assessment API
사업장 리스크 계산 및 이전 후보지 추천 API
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from ..schemas.site_models import (
    SiteRiskRequest,
    SiteRelocationRequest,
    SearchCriteria,
)
from ...batch.evaal_ondemand_api import calculate_evaal_ondemand
from ...config.settings import settings
from ...utils.background_task_manager import task_manager
from ...utils.log_writer import log_writer
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
import httpx
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/site-assessment", tags=["site-assessment"])

# ========== 상수 정의 ==========
# 계산할 시나리오와 연도 목록
SCENARIOS = ["SSP126", "SSP245", "SSP370", "SSP585"]
TARGET_YEARS = list(range(2021, 2101))  # 2021-2100 (80년)
# 병렬 처리 워커 수
MAX_WORKERS = 8
# 9개 리스크 타입
RISK_TYPES = [
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


async def _notify_recommendation_completed(batch_id: str):
    """
    FastAPI 서버에 후보지 추천 완료 알림

    Args:
        batch_id: 배치 작업 ID
    """
    if not batch_id:
        logger.warning("batch_id가 없어 콜백을 건너뜁니다.")
        return

    callback_url = f"{settings.fastapi_url}/api/analysis/modelops/recommendation-completed"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {}
            if settings.fastapi_api_key:
                headers["X-API-Key"] = settings.fastapi_api_key

            response = await client.post(
                callback_url, params={"batchId": batch_id}, headers=headers
            )

            if response.status_code == 200:
                logger.info(f"콜백 성공: batch_id={batch_id}")
            else:
                logger.warning(f"콜백 실패 (HTTP {response.status_code}): {response.text}")

    except Exception as e:
        logger.error(f"콜백 호출 중 오류 (batch_id={batch_id}): {e}", exc_info=True)


def _calculate_single_site_scenario_year(
    site_id: str,
    latitude: float,
    longitude: float,
    scenario: str,
    target_year: int,
    insurance_rate: float,
    asset_value: Optional[float],
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    단일 사업장의 단일 시나리오/연도 조합 계산 (병렬 처리용 헬퍼 함수)

    Returns:
        Dict: {
            'site_id': str,
            'scenario': str,
            'year': int,
            'status': 'success'|'failed',
            'error_message': Optional[str]
        }
    """
    try:
        result = calculate_evaal_ondemand(
            latitude=latitude,
            longitude=longitude,
            scenario=scenario,
            target_year=target_year,
            risk_types=RISK_TYPES,
            insurance_rate=insurance_rate,
            asset_value=asset_value,
            save_to_db=True,  # DB에 결과 저장
            site_id=site_id,  # 사업장 ID 전달
        )

        if result.get("status") == "error":
            error_msg = result.get("error", "E, V, AAL 계산 중 알 수 없는 오류 발생")

            # 로그 파일 작성 (실패)
            log_writer.write_year_completed_log(
                site_id=site_id,
                year=target_year,
                scenario=scenario,
                status="failed",
                error_message=error_msg,
                task_type="calculate",
            )

            return {
                "site_id": site_id,
                "scenario": scenario,
                "year": target_year,
                "status": "failed",
                "error_message": error_msg,
            }

        # 로그 파일 작성 (성공)
        log_writer.write_year_completed_log(
            site_id=site_id,
            year=target_year,
            scenario=scenario,
            status="success",
            task_type="calculate",
        )

        return {
            "site_id": site_id,
            "scenario": scenario,
            "year": target_year,
            "status": "success",
            "error_message": None,
        }

    except Exception as e:
        error_msg = str(e)

        # 로그 파일 작성 (예외)
        log_writer.write_year_completed_log(
            site_id=site_id,
            year=target_year,
            scenario=scenario,
            status="failed",
            error_message=error_msg,
            task_type="calculate",
        )

        return {
            "site_id": site_id,
            "scenario": scenario,
            "year": target_year,
            "status": "failed",
            "error_message": error_msg,
        }


def _background_calculate_site_risk(
    task_id: str, sites: Dict[str, Any], insurance_rate: float, asset_value: Optional[float]
):
    """
    백그라운드 사업장 리스크 계산 함수
    """
    total_sites = len(sites)
    total_calculations = total_sites * len(SCENARIOS) * len(TARGET_YEARS)

    logger.info(
        f"[{task_id}] 백그라운드 계산 시작: {total_sites}개 사업장, {total_calculations}개 조합"
    )

    # 작업 시작
    task_manager.start_task(task_id)

    successful_sites = 0
    failed_sites = 0
    site_errors = {}

    try:
        # 각 사업장별로 시작 로그 작성
        for site_id in sites.keys():
            log_writer.write_task_start_log(
                site_id=site_id,
                task_type="calculate",
                total_years=len(TARGET_YEARS),
                scenarios=SCENARIOS,
            )

        # 병렬 처리로 모든 사업장의 모든 시나리오/연도 조합 계산
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # 모든 작업 제출
            futures = []
            for site_id, site_location in sites.items():
                for scenario in SCENARIOS:
                    for year in TARGET_YEARS:
                        future = executor.submit(
                            _calculate_single_site_scenario_year,
                            site_id,
                            site_location["latitude"],
                            site_location["longitude"],
                            scenario,
                            year,
                            insurance_rate,
                            asset_value,
                            task_id,
                        )
                        futures.append(future)

            # 결과 수집 및 사업장별 성공/실패 추적
            completed_count = 0
            site_results = {site_id: {"success": 0, "failed": 0} for site_id in sites.keys()}

            for future in as_completed(futures):
                try:
                    result = future.result()
                    site_id = result["site_id"]

                    if result["status"] == "success":
                        site_results[site_id]["success"] += 1
                        task_manager.update_site_progress(task_id, site_id, completed_years=1)
                    else:
                        site_results[site_id]["failed"] += 1
                        task_manager.update_site_progress(task_id, site_id, failed_years=1)
                        # 첫 번째 에러만 기록
                        if site_id not in site_errors:
                            site_errors[site_id] = result["error_message"]

                    completed_count += 1

                    # 진행 상황 로그 (10% 단위)
                    if completed_count % max(1, total_calculations // 10) == 0:
                        progress = (completed_count / total_calculations) * 100
                        logger.info(
                            f"[{task_id}] 진행률: {completed_count}/{total_calculations} ({progress:.1f}%)"
                        )

                except Exception as e:
                    logger.error(f"[{task_id}] 결과 수집 중 오류: {e}")
                    completed_count += 1

            # 사업장별 성공/실패 집계 및 요약 로그 작성
            for site_id, counts in site_results.items():
                total_years_per_site = len(SCENARIOS) * len(TARGET_YEARS)

                # 요약 로그 작성
                log_writer.write_site_summary_log(
                    site_id=site_id,
                    total_years=total_years_per_site,
                    completed_years=counts["success"],
                    failed_years=counts["failed"],
                    task_type="calculate",
                    scenarios=SCENARIOS,
                )

                if counts["failed"] == 0:
                    successful_sites += 1
                    task_manager.complete_site(task_id, site_id, success=True)
                else:
                    failed_sites += 1
                    task_manager.complete_site(task_id, site_id, success=False)

        logger.info(f"[{task_id}] 사업장 리스크 계산 완료")
        logger.info(f"[{task_id}] 성공: {successful_sites}/{total_sites} 사업장")
        logger.info(f"[{task_id}] 실패: {failed_sites}/{total_sites} 사업장")

        # 작업 완료
        task_manager.complete_task(task_id)

    except Exception as e:
        logger.error(f"[{task_id}] 백그라운드 계산 중 오류: {e}", exc_info=True)
        task_manager.complete_task(task_id, error_message=str(e))


@router.post(
    "/calculate",
    responses={
        200: {"description": "작업이 백그라운드에서 시작됨"},
        422: {"description": "요청 데이터 유효성 검증 실패"},
    },
)
async def calculate_site_risk(request: SiteRiskRequest, background_tasks: BackgroundTasks):
    """
    사업장 리스크 계산 API (백그라운드 처리)
    (모든 시나리오 × 모든 연도 조합에 대해 E, V, AAL 계산 및 DB 저장)

    Returns:
        task_id: 백그라운드 작업 ID (작업 상태 조회용)
    """
    total_sites = len(request.sites)
    logger.info(f"사업장 리스크 계산 요청: {total_sites}개 사업장")

    # asset_info 처리
    insurance_rate = request.asset_info.insurance_coverage_rate if request.asset_info else 0.0
    asset_value = request.asset_info.total_value if request.asset_info else None

    # 작업 ID 생성
    task_id = str(uuid.uuid4())

    # 작업 등록
    task_manager.create_task(
        task_id=task_id,
        task_type="calculate",
        total_sites=total_sites,
        total_years=len(SCENARIOS) * len(TARGET_YEARS),
        metadata={
            "scenarios": SCENARIOS,
            "target_years": TARGET_YEARS,
            "insurance_rate": insurance_rate,
            "asset_value": asset_value,
        },
    )

    # sites를 직렬화 가능한 형태로 변환
    sites_dict = {
        site_id: {"latitude": loc.latitude, "longitude": loc.longitude}
        for site_id, loc in request.sites.items()
    }

    # 백그라운드 작업 추가
    background_tasks.add_task(
        _background_calculate_site_risk, task_id, sites_dict, insurance_rate, asset_value
    )

    logger.info(f"백그라운드 작업 등록 완료: task_id={task_id}")

    return {
        "task_id": task_id,
        "status": "accepted",
        "message": f"{total_sites}개 사업장 계산 작업이 백그라운드에서 시작되었습니다.",
        "total_sites": total_sites,
        "total_calculations": total_sites * len(SCENARIOS) * len(TARGET_YEARS),
    }


def _calculate_single_site_candidates(
    site_id: str,
    candidate_grids: List[Dict[str, float]],
    building_info: Dict[str, Any],
    asset_info: Optional[Dict[str, Any]],
    scenario: str,
    target_year: int,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    단일 사업장의 후보지 계산 (병렬 처리용 헬퍼 함수)

    Returns:
        Dict: {
            'site_id': str,
            'status': 'success'|'failed',
            'candidates_saved': int,
            'error_message': Optional[str],
            'year': int
        }
    """
    try:
        from modelops.database.connection import DatabaseConnection

        # 보험 가입률 추출
        insurance_rate = asset_info.get("insurance_coverage_rate", 0.0) if asset_info else 0.0
        asset_value = asset_info.get("total_value") if asset_info else None

        saved_count = 0
        failed_count = 0

        # 각 후보지에 대해 계산
        for grid in candidate_grids:
            lat, lon = grid["latitude"], grid["longitude"]

            # 이미 평가된 위치는 건너뛰기
            if DatabaseConnection.check_candidate_exists(lat, lon, scenario, target_year):
                logger.debug(f"[{site_id}] 이미 존재하는 후보지 건너뜀: ({lat}, {lon})")
                continue

            # calculate_evaal_ondemand 호출 (save_to_db=False)
            result = calculate_evaal_ondemand(
                latitude=lat,
                longitude=lon,
                scenario=scenario,
                target_year=target_year,
                risk_types=RISK_TYPES,
                insurance_rate=insurance_rate,
                asset_value=asset_value,
                save_to_db=False,  # 후보지는 별도 테이블에 저장
            )

            if result.get("status") == "error":
                logger.warning(
                    f"[{site_id}] 후보지 ({lat}, {lon}) 계산 실패: {result.get('error')}"
                )
                failed_count += 1
                continue

            # candidate_sites 테이블에 저장
            results_data = result.get("results", {})

            # AAL 합산 및 risk_details 구성
            aal_by_risk = {}
            total_aal = 0.0
            risk_scores = []

            # risks JSONB 구성 (9개 리스크의 점수만 저장: H × E × V / 10000)
            risks = {}

            for risk_type in RISK_TYPES:
                # AAL 및 aal_by_risk 구성
                aal_data = results_data.get("aal", {}).get(risk_type, {})
                final_aal = aal_data.get("final_aal", 0.0)
                aal_by_risk[risk_type] = final_aal
                total_aal += final_aal

                # 통합 리스크 점수 (H × E × V / 10000)
                integrated_risk_data = results_data.get("integrated_risk", {}).get(risk_type, {})
                integrated_risk_score = integrated_risk_data.get("integrated_risk_score", 0.0)
                risk_scores.append(integrated_risk_score)

                # risks JSONB: 9개 리스크별 점수만 저장
                risks[risk_type] = integrated_risk_score

            average_integrated_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0.0
            risk_score = int(round(average_integrated_risk))  # 0-100 정수

            # candidate_sites 테이블에 저장
            DatabaseConnection.save_candidate_site(
                latitude=lat,
                longitude=lon,
                aal=total_aal,
                aal_by_risk=aal_by_risk,
                risk_score=risk_score,
                risks=risks,  # 9개 리스크별 점수 (H × E × V / 10000)
                reference_site_id=site_id,
            )

            saved_count += 1

        # 연도별 로그 작성
        if failed_count == 0:
            log_writer.write_year_completed_log(
                site_id=site_id,
                year=target_year,
                scenario=scenario,
                status="success",
                task_type="recommend",
            )
        else:
            log_writer.write_year_completed_log(
                site_id=site_id,
                year=target_year,
                scenario=scenario,
                status="partial",
                error_message=f"{failed_count}개 후보지 계산 실패",
                task_type="recommend",
            )

        return {
            "site_id": site_id,
            "status": "success",
            "candidates_saved": saved_count,
            "error_message": None,
            "year": target_year,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{site_id}] 후보지 계산 실패: {e}", exc_info=True)

        # 로그 작성 (실패)
        log_writer.write_year_completed_log(
            site_id=site_id,
            year=target_year,
            scenario=scenario,
            status="failed",
            error_message=error_msg,
            task_type="recommend",
        )

        return {
            "site_id": site_id,
            "status": "failed",
            "candidates_saved": 0,
            "error_message": error_msg,
            "year": target_year,
        }


def _check_candidates_in_db(
    candidate_grids: List[Dict[str, float]], tolerance: float = 0.0001
) -> int:
    """
    candidate_sites 테이블에 이미 있는 후보지 개수 확인

    Args:
        candidate_grids: 확인할 후보지 목록
        tolerance: 좌표 허용 오차 (기본 0.0001도 ≈ 11m)

    Returns:
        DB에 이미 존재하는 후보지 개수
    """
    from modelops.database.connection import DatabaseConnection

    existing_count = 0

    try:
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()

            for grid in candidate_grids:
                lat = grid["latitude"]
                lon = grid["longitude"]

                # candidate_sites 테이블에서 좌표 매칭
                cursor.execute(
                    """
                    SELECT COUNT(*) as cnt
                    FROM candidate_sites
                    WHERE ABS(latitude - %s) < %s
                      AND ABS(longitude - %s) < %s
                """,
                    (lat, tolerance, lon, tolerance),
                )

                result = cursor.fetchone()
                if result and result["cnt"] > 0:
                    existing_count += 1

    except Exception as e:
        logger.warning(f"DB 데이터 확인 중 오류: {e}")

    return existing_count


def _background_recommend_relocation_locations(
    task_id: str,
    sites: Dict[str, Any],
    candidate_grids: List[Dict[str, float]],
    building_info: Optional[Dict[str, Any]],
    asset_info: Optional[Dict[str, Any]],
    scenario: str,
    target_year: int,
    batch_id: Optional[str],
):
    """
    백그라운드 후보지 추천 함수
    """
    total_sites = len(sites)
    logger.info(f"[{task_id}] 백그라운드 후보지 추천 시작: {total_sites}개 사업장")

    # 작업 시작
    task_manager.start_task(task_id)

    # DB에 기존 데이터가 충분히 있는지 확인 (Early Callback)
    early_callback_triggered = False
    if batch_id and len(candidate_grids) > 0:
        try:
            total_candidates = len(candidate_grids)
            existing_count = _check_candidates_in_db(candidate_grids)

            existing_ratio = existing_count / total_candidates
            logger.info(
                f"[{task_id}] 기존 데이터: {existing_count}/{total_candidates} ({existing_ratio*100:.1f}%)"
            )

            # 90% 이상 데이터가 있으면 즉시 콜백 호출
            if existing_ratio >= 0.9:
                logger.info(
                    f"[{task_id}] 충분한 데이터 존재 ({existing_ratio*100:.1f}%) - 즉시 콜백 호출"
                )
                try:
                    import asyncio

                    asyncio.run(_notify_recommendation_completed(batch_id))
                    early_callback_triggered = True
                    logger.info(f"[{task_id}] Early callback 성공")
                except Exception as callback_error:
                    logger.error(f"[{task_id}] Early callback 실패: {callback_error}")
            else:
                logger.info(
                    f"[{task_id}] 데이터 부족 ({existing_ratio*100:.1f}%) - 계산 후 콜백 호출"
                )

        except Exception as e:
            logger.warning(f"[{task_id}] DB 데이터 확인 실패: {e} - 계산 진행")

    successful_sites = 0
    failed_sites = 0
    total_candidates_saved = 0
    site_errors = {}

    try:
        # 각 사업장별로 시작 로그 작성
        for site_id in sites.keys():
            log_writer.write_task_start_log(
                site_id=site_id,
                task_type="recommend",
                total_years=1,  # recommend는 단일 연도만 처리
                scenarios=[scenario],
            )

        # 병렬 처리로 모든 사업장의 후보지 계산
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []

            for site_id in sites.keys():
                future = executor.submit(
                    _calculate_single_site_candidates,
                    site_id,
                    candidate_grids,
                    building_info,
                    asset_info,
                    scenario,
                    target_year,
                    task_id,
                )
                futures.append(future)

            # 결과 수집
            for future in as_completed(futures):
                try:
                    result = future.result()
                    site_id = result["site_id"]

                    if result["status"] == "success":
                        successful_sites += 1
                        total_candidates_saved += result["candidates_saved"]
                        task_manager.complete_site(task_id, site_id, success=True)
                        task_manager.update_site_progress(task_id, site_id, completed_years=1)
                        logger.info(
                            f"[{task_id}][{site_id}] 후보지 {result['candidates_saved']}개 저장 완료"
                        )

                        # 요약 로그 작성
                        log_writer.write_site_summary_log(
                            site_id=site_id,
                            total_years=1,
                            completed_years=1,
                            failed_years=0,
                            task_type="recommend",
                            scenarios=[scenario],
                        )
                    else:
                        failed_sites += 1
                        site_errors[site_id] = result["error_message"]
                        task_manager.complete_site(task_id, site_id, success=False)
                        task_manager.update_site_progress(task_id, site_id, failed_years=1)
                        logger.error(
                            f"[{task_id}][{site_id}] 후보지 계산 실패: {result['error_message']}"
                        )

                        # 요약 로그 작성 (실패)
                        log_writer.write_site_summary_log(
                            site_id=site_id,
                            total_years=1,
                            completed_years=0,
                            failed_years=1,
                            task_type="recommend",
                            scenarios=[scenario],
                        )

                except Exception as e:
                    logger.error(f"[{task_id}] 결과 수집 중 오류: {e}")
                    failed_sites += 1

        logger.info(f"[{task_id}] 후보지 추천 완료")
        logger.info(f"[{task_id}] 성공: {successful_sites}/{total_sites} 사업장")
        logger.info(f"[{task_id}] 실패: {failed_sites}/{total_sites} 사업장")
        logger.info(f"[{task_id}] 총 저장 후보지: {total_candidates_saved}개")

        # 작업 완료
        task_manager.complete_task(task_id)

        # 콜백 호출 (Early callback이 이미 호출되지 않은 경우에만)
        if batch_id and not early_callback_triggered:
            try:
                import asyncio

                asyncio.run(_notify_recommendation_completed(batch_id))
                logger.info(f"[{task_id}] 계산 완료 후 콜백 호출 성공")
            except Exception as callback_error:
                logger.error(f"[{task_id}] 콜백 호출 실패: {callback_error}")
        elif batch_id and early_callback_triggered:
            logger.info(f"[{task_id}] Early callback 이미 호출됨 - 중복 콜백 방지")

    except Exception as e:
        logger.error(f"[{task_id}] 백그라운드 후보지 추천 중 오류: {e}", exc_info=True)
        task_manager.complete_task(task_id, error_message=str(e))


@router.post(
    "/recommend-locations",
    responses={
        200: {"description": "작업이 백그라운드에서 시작됨"},
        422: {"description": "요청 데이터 유효성 검증 실패"},
    },
)
async def recommend_relocation_locations(
    request: SiteRelocationRequest, background_tasks: BackgroundTasks
):
    """
    사업장 이전 후보지 추천 API (백그라운드 처리)
    (On-Demand 계산 + candidate_sites DB 저장)

    Returns:
        task_id: 백그라운드 작업 ID (작업 상태 조회용)
    """
    total_sites = len(request.sites)
    logger.info(f"이전 후보지 추천 요청: {total_sites}개 사업장, batch_id={request.batch_id}")

    # 1. candidate_grids 처리: 없으면 고정 위치 사용
    if request.candidate_grids is None or len(request.candidate_grids) == 0:
        from ...utils.candidate_location import LOCATION_MAP

        # LOCATION_MAP: set of {"lat": ..., "lng": ...}
        # Convert to list of {"latitude": ..., "longitude": ...}
        candidate_grids = [
            {"latitude": loc["lat"], "longitude": loc["lng"]} for loc in LOCATION_MAP
        ]
        logger.info(f"고정 위치 사용: {len(candidate_grids)}개")
    else:
        candidate_grids = [
            {"latitude": grid.latitude, "longitude": grid.longitude}
            for grid in request.candidate_grids
        ]
        logger.info(f"사용자 제공 위치: {len(candidate_grids)}개")

    total_grids = len(candidate_grids)

    if total_grids > 2000:
        logger.warning(
            f"candidate_grids가 {total_grids}개로 많습니다. 처리 시간이 오래 걸릴 수 있습니다."
        )

    # 검색 기준 처리
    search_criteria = request.search_criteria or SearchCriteria()
    scenario = search_criteria.scenario or "SSP245"
    target_year = search_criteria.target_year or 2040

    # building_info, asset_info 변환
    building_info = request.building_info.model_dump() if request.building_info else None
    asset_info = request.asset_info.model_dump() if request.asset_info else None

    # 작업 ID 생성
    task_id = str(uuid.uuid4())

    # 작업 등록
    task_manager.create_task(
        task_id=task_id,
        task_type="recommend",
        total_sites=total_sites,
        total_years=1,  # recommend는 단일 연도만 처리
        metadata={
            "scenario": scenario,
            "target_year": target_year,
            "total_grids": total_grids,
            "batch_id": request.batch_id,
        },
    )

    # sites를 직렬화 가능한 형태로 변환
    sites_dict = {
        site_id: {"latitude": loc.latitude, "longitude": loc.longitude}
        for site_id, loc in request.sites.items()
    }

    # 백그라운드 작업 추가
    background_tasks.add_task(
        _background_recommend_relocation_locations,
        task_id,
        sites_dict,
        candidate_grids,
        building_info,
        asset_info,
        scenario,
        target_year,
        request.batch_id,
    )

    logger.info(f"백그라운드 작업 등록 완료: task_id={task_id}")

    return {
        "task_id": task_id,
        "status": "accepted",
        "message": f"{total_sites}개 사업장 후보지 추천 작업이 백그라운드에서 시작되었습니다.",
        "total_sites": total_sites,
        "total_grids": total_grids,
        "scenario": scenario,
        "target_year": target_year,
    }


@router.get(
    "/task-status/{task_id}",
    responses={
        200: {"description": "작업 상태 조회 성공"},
        404: {
            "description": "작업 ID를 찾을 수 없음",
            "content": {"application/json": {"example": {"detail": "Task not found: abc-123"}}},
        },
    },
)
async def get_task_status(task_id: str):
    """
    작업 상태 조회 API

    Args:
        task_id: 작업 ID

    Returns:
        작업 상태 정보
    """
    task_info = task_manager.get_task(task_id)

    if task_info is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    # datetime 객체를 문자열로 변환
    response = {
        "task_id": task_info["task_id"],
        "task_type": task_info["task_type"],
        "status": task_info["status"],
        "total_sites": task_info["total_sites"],
        "completed_sites": task_info["completed_sites"],
        "failed_sites": task_info["failed_sites"],
        "total_years": task_info["total_years"],
        "created_at": task_info["created_at"].isoformat() if task_info["created_at"] else None,
        "started_at": task_info["started_at"].isoformat() if task_info["started_at"] else None,
        "completed_at": (
            task_info["completed_at"].isoformat() if task_info["completed_at"] else None
        ),
        "error_message": task_info["error_message"],
        "metadata": task_info["metadata"],
    }

    # 진행률 계산
    if task_info["status"] == "running":
        total_progress = sum(
            prog["completed_years"] + prog["failed_years"]
            for prog in task_info["current_progress"].values()
        )
        total_expected = task_info["total_sites"] * task_info["total_years"]
        progress_percentage = (total_progress / total_expected * 100) if total_expected > 0 else 0
        response["progress_percentage"] = round(progress_percentage, 2)
        response["current_progress"] = task_info["current_progress"]

    return response


@router.get("/tasks", responses={200: {"description": "모든 작업 상태 조회 성공"}})
async def get_all_tasks():
    """
    모든 작업 상태 조회 API

    Returns:
        모든 작업의 상태 정보 목록
    """
    all_tasks = task_manager.get_all_tasks()

    tasks_list = []
    for task_id, task_info in all_tasks.items():
        task_summary = {
            "task_id": task_info["task_id"],
            "task_type": task_info["task_type"],
            "status": task_info["status"],
            "total_sites": task_info["total_sites"],
            "completed_sites": task_info["completed_sites"],
            "failed_sites": task_info["failed_sites"],
            "created_at": task_info["created_at"].isoformat() if task_info["created_at"] else None,
            "started_at": task_info["started_at"].isoformat() if task_info["started_at"] else None,
            "completed_at": (
                task_info["completed_at"].isoformat() if task_info["completed_at"] else None
            ),
        }

        # 진행률 계산
        if task_info["status"] == "running":
            total_progress = sum(
                prog["completed_years"] + prog["failed_years"]
                for prog in task_info["current_progress"].values()
            )
            total_expected = task_info["total_sites"] * task_info["total_years"]
            progress_percentage = (
                (total_progress / total_expected * 100) if total_expected > 0 else 0
            )
            task_summary["progress_percentage"] = round(progress_percentage, 2)

        tasks_list.append(task_summary)

    # 최신 순으로 정렬 (created_at 기준)
    tasks_list.sort(key=lambda x: x["created_at"] if x["created_at"] else "", reverse=True)

    return {"total_tasks": len(tasks_list), "tasks": tasks_list}


@router.delete(
    "/task/{task_id}",
    responses={
        200: {"description": "작업 삭제 성공"},
        404: {
            "description": "작업 ID를 찾을 수 없음",
            "content": {"application/json": {"example": {"detail": "Task not found: abc-123"}}},
        },
    },
)
async def delete_task(task_id: str):
    """
    작업 삭제 API

    Args:
        task_id: 삭제할 작업 ID

    Returns:
        삭제 결과
    """
    success = task_manager.delete_task(task_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    return {"status": "success", "message": f"Task {task_id} deleted successfully"}
