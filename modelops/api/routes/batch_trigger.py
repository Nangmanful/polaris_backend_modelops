"""
Batch Trigger API
배치 작업 강제 실행 API
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batch-trigger", tags=["batch-trigger"])


class CustomScheduleRequest(BaseModel):
    """사용자 정의 스케줄 요청"""

    batch_type: str = Field(..., description="배치 타입: 'probability' 또는 'hazard'")


# @router.post(
#     "/trigger-custom-schedule",
#     responses={
#         200: {"description": "배치 작업 예약 성공"},
#         400: {
#             "description": "잘못된 배치 타입",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "batch_type must be 'probability' or 'hazard'"}
#                 }
#             }
#         },
#         500: {
#             "description": "배치 트리거 실패",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Failed to trigger batch: Internal error"}
#                 }
#             }
#         },
#         503: {
#             "description": "스케줄러가 실행되지 않음",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Scheduler is not running"}
#                 }
#             }
#         }
#     }
# )
# async def trigger_custom_schedule(request: CustomScheduleRequest):
#     """
#     배치 작업을 서버 현재 시각 + 1분 후에 실행

#     사용자가 batch_type만 지정하면, 서버의 현재 시각 기준으로 1분 후에 자동 실행됩니다.

#     - **batch_type**: 'probability' (P(H) 배치) 또는 'hazard' (H 배치)
#     """
#     try:
#         from main import scheduler, probability_batch_job, hazard_batch_job
#         from apscheduler.triggers.cron import CronTrigger

#         if scheduler is None:
#             raise HTTPException(status_code=503, detail="Scheduler is not running")

#         # 배치 타입 검증
#         if request.batch_type not in ['probability', 'hazard']:
#             raise HTTPException(
#                 status_code=400,
#                 detail="batch_type must be 'probability' or 'hazard'"
#             )

#         # 서버 현재 시각 + 1분
#         trigger_time = datetime.now() + timedelta(minutes=1)

#         # 배치 작업 및 job_id 설정
#         if request.batch_type == 'probability':
#             batch_job = probability_batch_job
#             job_id = 'probability_batch_custom'
#             job_name = 'P(H) Batch (Custom Trigger)'
#         else:
#             batch_job = hazard_batch_job
#             job_id = 'hazard_batch_custom'
#             job_name = 'Hazard Score Batch (Custom Trigger)'

#         # 기존 커스텀 작업 제거 (있다면)
#         if scheduler.get_job(job_id):
#             scheduler.remove_job(job_id)

#         # 1분 후 실행되도록 CronTrigger 설정
#         scheduler.add_job(
#             batch_job,
#             trigger=CronTrigger(
#                 year=trigger_time.year,
#                 month=trigger_time.month,
#                 day=trigger_time.day,
#                 hour=trigger_time.hour,
#                 minute=trigger_time.minute,
#                 second=trigger_time.second
#             ),
#             id=job_id,
#             name=job_name,
#             replace_existing=True
#         )

#         logger.info(f"{request.batch_type.upper()} 배치 작업이 {trigger_time.isoformat()}에 실행되도록 예약되었습니다.")

#         return {
#             'status': 'success',
#             'batch_type': request.batch_type,
#             'message': f'{request.batch_type.upper()} 배치 작업이 1분 후에 실행됩니다.',
#             'server_current_time': datetime.now().isoformat(),
#             'scheduled_time': trigger_time.isoformat(),
#             'job_id': job_id
#         }

#     except ImportError as e:
#         logger.error(f"Scheduler import 실패: {e}")
#         raise HTTPException(status_code=500, detail=f"Scheduler import failed: {str(e)}")
#     except Exception as e:
#         logger.error(f"배치 트리거 실패: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to trigger batch: {str(e)}")


# @router.post(
#     "/run-probability-batch",
#     responses={
#         200: {"description": "P(H) 배치 작업 예약 성공"},
#         500: {
#             "description": "배치 트리거 실패",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Failed to trigger P(H) batch: Internal error"}
#                 }
#             }
#         },
#         503: {
#             "description": "스케줄러가 실행되지 않음",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Scheduler is not running"}
#                 }
#             }
#         }
#     }
# )
# async def trigger_probability_batch():
#     """
#     P(H) 배치 작업을 1초 후에 강제 실행

#     CronTrigger를 현재시간 + 1초로 설정하여 즉시 실행
#     """
#     try:
#         from main import scheduler, probability_batch_job
#         from apscheduler.triggers.cron import CronTrigger

#         if scheduler is None:
#             raise HTTPException(status_code=503, detail="Scheduler is not running")

#         # 현재 시간 + 1초
#         trigger_time = datetime.now() + timedelta(seconds=1)

#         # 기존 작업 제거 (있다면)
#         if scheduler.get_job('probability_batch_manual'):
#             scheduler.remove_job('probability_batch_manual')

#         # 1초 후 실행되도록 CronTrigger 설정
#         scheduler.add_job(
#             probability_batch_job,
#             trigger=CronTrigger(
#                 year=trigger_time.year,
#                 month=trigger_time.month,
#                 day=trigger_time.day,
#                 hour=trigger_time.hour,
#                 minute=trigger_time.minute,
#                 second=trigger_time.second
#             ),
#             id='probability_batch_manual',
#             name='P(H) Batch (Manual Trigger)',
#             replace_existing=True
#         )

#         logger.info(f"P(H) 배치 작업이 {trigger_time.isoformat()}에 실행되도록 예약되었습니다.")

#         return {
#             'status': 'success',
#             'message': 'P(H) 배치 작업이 1초 후에 실행됩니다.',
#             'scheduled_time': trigger_time.isoformat(),
#             'job_id': 'probability_batch_manual'
#         }

#     except ImportError as e:
#         logger.error(f"Scheduler import 실패: {e}")
#         raise HTTPException(status_code=500, detail=f"Scheduler import failed: {str(e)}")
#     except Exception as e:
#         logger.error(f"P(H) 배치 트리거 실패: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to trigger P(H) batch: {str(e)}")


# @router.post(
#     "/run-hazard-batch",
#     responses={
#         200: {"description": "H 배치 작업 예약 성공"},
#         500: {
#             "description": "배치 트리거 실패",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Failed to trigger H batch: Internal error"}
#                 }
#             }
#         },
#         503: {
#             "description": "스케줄러가 실행되지 않음",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Scheduler is not running"}
#                 }
#             }
#         }
#     }
# )
# async def trigger_hazard_batch():
#     """
#     H(Hazard Score) 배치 작업을 1초 후에 강제 실행

#     CronTrigger를 현재시간 + 1초로 설정하여 즉시 실행
#     """
#     try:
#         from main import scheduler, hazard_batch_job
#         from apscheduler.triggers.cron import CronTrigger

#         if scheduler is None:
#             raise HTTPException(status_code=503, detail="Scheduler is not running")

#         # 현재 시간 + 1초
#         trigger_time = datetime.now() + timedelta(seconds=1)

#         # 기존 작업 제거 (있다면)
#         if scheduler.get_job('hazard_batch_manual'):
#             scheduler.remove_job('hazard_batch_manual')

#         # 1초 후 실행되도록 CronTrigger 설정
#         scheduler.add_job(
#             hazard_batch_job,
#             trigger=CronTrigger(
#                 year=trigger_time.year,
#                 month=trigger_time.month,
#                 day=trigger_time.day,
#                 hour=trigger_time.hour,
#                 minute=trigger_time.minute,
#                 second=trigger_time.second
#             ),
#             id='hazard_batch_manual',
#             name='Hazard Score Batch (Manual Trigger)',
#             replace_existing=True
#         )

#         logger.info(f"H 배치 작업이 {trigger_time.isoformat()}에 실행되도록 예약되었습니다.")

#         return {
#             'status': 'success',
#             'message': 'H 배치 작업이 1초 후에 실행됩니다.',
#             'scheduled_time': trigger_time.isoformat(),
#             'job_id': 'hazard_batch_manual'
#         }

#     except ImportError as e:
#         logger.error(f"Scheduler import 실패: {e}")
#         raise HTTPException(status_code=500, detail=f"Scheduler import failed: {str(e)}")
#     except Exception as e:
#         logger.error(f"H 배치 트리거 실패: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to trigger H batch: {str(e)}")


@router.get(
    "/scheduled-jobs",
    responses={
        200: {"description": "스케줄된 작업 목록 조회 성공"},
        500: {
            "description": "스케줄 작업 조회 실패",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to get scheduled jobs: Internal error"}
                }
            },
        },
        503: {
            "description": "스케줄러가 실행되지 않음",
            "content": {"application/json": {"example": {"detail": "Scheduler is not running"}}},
        },
    },
)
async def get_scheduled_jobs():
    """
    현재 스케줄러에 등록된 모든 작업 조회
    """
    try:
        from main import scheduler

        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler is not running")

        jobs = []
        for job in scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
            )

        return {"total_jobs": len(jobs), "jobs": jobs}

    except ImportError as e:
        logger.error(f"Scheduler import 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Scheduler import failed: {str(e)}")
    except Exception as e:
        logger.error(f"스케줄 작업 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get scheduled jobs: {str(e)}")


# @router.post(
#     "/run-candidate-locations-hazard-batch",
#     responses={
#         200: {"description": "후보지 H 배치 작업 시작 성공"},
#         500: {
#             "description": "배치 작업 실패",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Failed to run candidate locations hazard batch: Internal error"}
#                 }
#             }
#         }
#     }
# )
# async def run_candidate_locations_hazard_batch():
#     """
#     10개 후보지 위치에 대한 H(Hazard) 배치 계산

#     - **위치**: 10개 후보지 (LOCATION_MAP)
#     - **연도**: 2040년만
#     - **시나리오**: SSP245만
#     - **리스크 타입**: 9가지 (extreme_heat, extreme_cold, wildfire, drought, water_stress, sea_level_rise, river_flood, urban_flood, typhoon)

#     백그라운드에서 실행되며, 결과는 hazard_results 테이블에 저장됩니다.
#     """
#     try:
#         from ...utils.candidate_location import LOCATION_MAP
#         from ...batch.hazard_timeseries_batch import run_hazard_batch
#         from concurrent.futures import ThreadPoolExecutor

#         # 10개 후보지 좌표 준비
#         candidate_locations = []
#         for loc in LOCATION_MAP:
#             lat = loc.get('lat')
#             lng = loc.get('lng')
#             if lat and lng:
#                 candidate_locations.append((float(lat), float(lng)))

#         if len(candidate_locations) != 10:
#             raise HTTPException(
#                 status_code=500,
#                 detail=f"Expected 10 locations, but got {len(candidate_locations)}"
#             )

#         # 연도 설정: 2040년만
#         all_years = ["2040"]

#         # 시나리오: SSP245만
#         scenarios = ["SSP245"]

#         # 백그라운드 실행 함수
#         def run_batch():
#             try:
#                 logger.info("=" * 80)
#                 logger.info("후보지 Hazard 배치 계산 시작 (SSP245, 2040년)")
#                 logger.info(f"위치 개수: {len(candidate_locations)}")
#                 logger.info(f"연도: {all_years}")
#                 logger.info(f"시나리오: {scenarios}")
#                 logger.info("=" * 80)

#                 run_hazard_batch(
#                     grid_points=candidate_locations,
#                     scenarios=scenarios,
#                     years=all_years,
#                     risk_types=None,  # 전체 9개 리스크
#                     batch_size=100,
#                     max_workers=2
#                 )

#                 logger.info("=" * 80)
#                 logger.info("후보지 Hazard 배치 계산 완료!")
#                 logger.info("=" * 80)

#             except Exception as e:
#                 logger.error(f"후보지 Hazard 배치 실행 중 오류 발생: {e}", exc_info=True)

#         # 백그라운드에서 실행
#         executor = ThreadPoolExecutor(max_workers=1)
#         executor.submit(run_batch)

#         return {
#             'status': 'started',
#             'message': '후보지 Hazard 배치 계산이 백그라운드에서 시작되었습니다 (SSP245, 2040년).',
#             'locations_count': len(candidate_locations),
#             'years_count': len(all_years),
#             'year': '2040',
#             'scenarios': scenarios,
#             'total_calculations': len(candidate_locations) * len(all_years) * len(scenarios) * 9,  # 10 * 1 * 1 * 9 = 90
#             'note': 'Hazard 결과는 hazard_results 테이블에 저장됩니다.'
#         }

#     except ImportError as e:
#         logger.error(f"배치 모듈 import 실패: {e}")
#         raise HTTPException(status_code=500, detail=f"Batch module import failed: {str(e)}")
#     except Exception as e:
#         logger.error(f"후보지 Hazard 배치 실행 실패: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to run candidate locations hazard batch: {str(e)}")


# @router.post(
#     "/run-candidate-locations-probability-batch",
#     responses={
#         200: {"description": "후보지 P(H) 배치 작업 시작 성공"},
#         500: {
#             "description": "배치 작업 실패",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Failed to run candidate locations probability batch: Internal error"}
#                 }
#             }
#         }
#     }
# )
# async def run_candidate_locations_probability_batch():
#     """
#     10개 후보지 위치에 대한 P(H)(Probability) 배치 계산

#     - **위치**: 10개 후보지 (LOCATION_MAP)
#     - **연도**: 2040년만
#     - **시나리오**: SSP245만
#     - **리스크 타입**: 9가지 (extreme_heat, extreme_cold, wildfire, drought, water_stress, sea_level_rise, river_flood, urban_flood, typhoon)

#     백그라운드에서 실행되며, 결과는 probability_results 테이블에 저장됩니다.
#     """
#     try:
#         from ...utils.candidate_location import LOCATION_MAP
#         from ...batch.probability_timeseries_batch import run_probability_batch
#         from concurrent.futures import ThreadPoolExecutor

#         # 10개 후보지 좌표 준비
#         candidate_locations = []
#         for loc in LOCATION_MAP:
#             lat = loc.get('lat')
#             lng = loc.get('lng')
#             if lat and lng:
#                 candidate_locations.append((float(lat), float(lng)))

#         if len(candidate_locations) != 10:
#             raise HTTPException(
#                 status_code=500,
#                 detail=f"Expected 10 locations, but got {len(candidate_locations)}"
#             )

#         # 연도 설정: 2040년만
#         all_years = ["2040"]

#         # 시나리오: SSP245만
#         scenarios = ["SSP245"]

#         # 백그라운드 실행 함수
#         def run_batch():
#             try:
#                 logger.info("=" * 80)
#                 logger.info("후보지 Probability 배치 계산 시작")
#                 logger.info(f"위치 개수: {len(candidate_locations)}")
#                 logger.info(f"연도: {all_years}")
#                 logger.info(f"시나리오: {scenarios}")
#                 logger.info("=" * 80)

#                 run_probability_batch(
#                     grid_points=candidate_locations,
#                     scenarios=scenarios,
#                     years=all_years,
#                     risk_types=None,  # 전체 9개 리스크
#                     batch_size=100,
#                     max_workers=4
#                 )

#                 logger.info("=" * 80)
#                 logger.info("후보지 Probability 배치 계산 완료!")
#                 logger.info("=" * 80)

#             except Exception as e:
#                 logger.error(f"후보지 Probability 배치 실행 중 오류 발생: {e}", exc_info=True)

#         # 백그라운드에서 실행
#         executor = ThreadPoolExecutor(max_workers=1)
#         executor.submit(run_batch)

#         return {
#             'status': 'started',
#             'message': '후보지 Probability 배치 계산이 백그라운드에서 시작되었습니다.',
#             'locations_count': len(candidate_locations),
#             'years_count': len(all_years),
#             'years': all_years,
#             'scenarios': scenarios,
#             'total_calculations': len(candidate_locations) * len(all_years) * len(scenarios) * 9,
#             'note': 'Probability 결과는 probability_results 테이블에 저장됩니다.'
#         }

#     except ImportError as e:
#         logger.error(f"배치 모듈 import 실패: {e}")
#         raise HTTPException(status_code=500, detail=f"Batch module import failed: {str(e)}")
#     except Exception as e:
#         logger.error(f"후보지 Probability 배치 실행 실패: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to run candidate locations probability batch: {str(e)}")


# @router.post(
#     "/run-regional-locations-batch-group1",
#     responses={
#         200: {"description": "250개 시군구 배치 작업 (그룹1) 시작 성공"},
#         500: {
#             "description": "배치 작업 실패",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Failed to run regional locations batch group1: Internal error"}
#                 }
#             }
#         }
#     }
# )
# async def run_regional_locations_batch_group1():
#     """
#     250개 시군구 위치에 대한 H(Hazard) 배치 계산 - 그룹1 (P(H)는 제외)

#     - **위치**: 250개 시군구 (REGION_COORD_MAP)
#     - **연도**: 2025, 2030, 2035, 2040 (그룹1 - 4개 연도)
#     - **시나리오**: SSP126, SSP245, SSP370, SSP585
#     - **리스크 타입**: 9가지 (extreme_heat, extreme_cold, wildfire, drought, water_stress, sea_level_rise, river_flood, urban_flood, typhoon)

#     백그라운드에서 실행되며, 결과는 hazard_results 테이블에 저장됩니다.
#     """
#     try:
#         from ...utils.region_mapper import REGION_COORD_MAP
#         from ...batch.hazard_timeseries_batch import run_hazard_batch
#         from concurrent.futures import ThreadPoolExecutor

#         # 250개 시군구 좌표 준비
#         regional_locations = []
#         for code, coords in REGION_COORD_MAP.items():
#             lat = coords.get('lat')
#             lng = coords.get('lng')
#             if lat and lng and lat != 0.0 and lng != 0.0:  # 기본값 제외
#                 regional_locations.append((float(lat), float(lng)))

#         logger.info(f"총 {len(regional_locations)}개 시군구 좌표 로드 완료")

#         # 연도 설정: 그룹1 (2025-2040)
#         all_years = ["2025", "2030", "2035", "2040"]

#         # 시나리오
#         scenarios = ["SSP126", "SSP245", "SSP370", "SSP585"]

#         # 백그라운드 실행 함수
#         def run_batches():
#             try:
#                 logger.info("=" * 80)
#                 logger.info("250개 시군구 Hazard 배치 계산 시작 (그룹1: 2025-2040)")
#                 logger.info(f"위치 개수: {len(regional_locations)}")
#                 logger.info(f"연도: {all_years}")
#                 logger.info(f"시나리오: {scenarios}")
#                 logger.info("=" * 80)

#                 # Hazard 배치 실행 (P(H)는 제외)
#                 logger.info("Hazard Score 배치 계산 시작...")
#                 run_hazard_batch(
#                     grid_points=regional_locations,
#                     scenarios=scenarios,
#                     years=all_years,
#                     risk_types=None,  # 전체 9개 리스크
#                     batch_size=100,
#                     max_workers=6  # 250개 위치이므로 워커 수 증가
#                 )
#                 logger.info("Hazard 배치 완료!")

#                 logger.info("=" * 80)
#                 logger.info("250개 시군구 Hazard 배치 계산 완료! (그룹1)")
#                 logger.info("=" * 80)

#             except Exception as e:
#                 logger.error(f"시군구 배치 실행 중 오류 발생 (그룹1): {e}", exc_info=True)

#         # 백그라운드에서 실행
#         executor = ThreadPoolExecutor(max_workers=1)
#         executor.submit(run_batches)

#         return {
#             'status': 'started',
#             'message': '250개 시군구 Hazard 배치 계산이 백그라운드에서 시작되었습니다 (그룹1: 2025-2040).',
#             'group': 1,
#             'locations_count': len(regional_locations),
#             'years_count': len(all_years),
#             'years': all_years,
#             'scenarios': scenarios,
#             'total_calculations': len(regional_locations) * len(all_years) * len(scenarios) * 9,  # 250 * 4 * 4 * 9 = 36,000
#             'note': 'Hazard 결과는 hazard_results 테이블에 저장됩니다 (P(H)는 계산하지 않음).'
#         }

#     except ImportError as e:
#         logger.error(f"배치 모듈 import 실패: {e}")
#         raise HTTPException(status_code=500, detail=f"Batch module import failed: {str(e)}")
#     except Exception as e:
#         logger.error(f"시군구 배치 실행 실패 (그룹1): {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to run regional locations batch group1: {str(e)}")


# @router.post(
#     "/run-regional-locations-batch-group2",
#     responses={
#         200: {"description": "250개 시군구 배치 작업 (그룹2) 시작 성공"},
#         500: {
#             "description": "배치 작업 실패",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Failed to run regional locations batch group2: Internal error"}
#                 }
#             }
#         }
#     }
# )
# async def run_regional_locations_batch_group2():
#     """
#     250개 시군구 위치에 대한 H(Hazard) 배치 계산 - 그룹2 (P(H)는 제외)

#     - **위치**: 250개 시군구 (REGION_COORD_MAP)
#     - **연도**: 2045, 2050, 2055, 2060 (그룹2 - 4개 연도)
#     - **시나리오**: SSP126, SSP245, SSP370, SSP585
#     - **리스크 타입**: 9가지 (extreme_heat, extreme_cold, wildfire, drought, water_stress, sea_level_rise, river_flood, urban_flood, typhoon)

#     백그라운드에서 실행되며, 결과는 hazard_results 테이블에 저장됩니다.
#     """
#     try:
#         from ...utils.region_mapper import REGION_COORD_MAP
#         from ...batch.hazard_timeseries_batch import run_hazard_batch
#         from concurrent.futures import ThreadPoolExecutor

#         # 250개 시군구 좌표 준비
#         regional_locations = []
#         for code, coords in REGION_COORD_MAP.items():
#             lat = coords.get('lat')
#             lng = coords.get('lng')
#             if lat and lng and lat != 0.0 and lng != 0.0:  # 기본값 제외
#                 regional_locations.append((float(lat), float(lng)))

#         logger.info(f"총 {len(regional_locations)}개 시군구 좌표 로드 완료")

#         # 연도 설정: 그룹2 (2045-2060)
#         all_years = ["2045", "2050", "2055", "2060"]

#         # 시나리오
#         scenarios = ["SSP126", "SSP245", "SSP370", "SSP585"]

#         # 백그라운드 실행 함수
#         def run_batches():
#             try:
#                 logger.info("=" * 80)
#                 logger.info("250개 시군구 Hazard 배치 계산 시작 (그룹2: 2045-2060)")
#                 logger.info(f"위치 개수: {len(regional_locations)}")
#                 logger.info(f"연도: {all_years}")
#                 logger.info(f"시나리오: {scenarios}")
#                 logger.info("=" * 80)

#                 # Hazard 배치 실행 (P(H)는 제외)
#                 logger.info("Hazard Score 배치 계산 시작...")
#                 run_hazard_batch(
#                     grid_points=regional_locations,
#                     scenarios=scenarios,
#                     years=all_years,
#                     risk_types=None,  # 전체 9개 리스크
#                     batch_size=100,
#                     max_workers=6  # 250개 위치이므로 워커 수 증가
#                 )
#                 logger.info("Hazard 배치 완료!")

#                 logger.info("=" * 80)
#                 logger.info("250개 시군구 Hazard 배치 계산 완료! (그룹2)")
#                 logger.info("=" * 80)

#             except Exception as e:
#                 logger.error(f"시군구 배치 실행 중 오류 발생 (그룹2): {e}", exc_info=True)

#         # 백그라운드에서 실행
#         executor = ThreadPoolExecutor(max_workers=1)
#         executor.submit(run_batches)

#         return {
#             'status': 'started',
#             'message': '250개 시군구 Hazard 배치 계산이 백그라운드에서 시작되었습니다 (그룹2: 2045-2060).',
#             'group': 2,
#             'locations_count': len(regional_locations),
#             'years_count': len(all_years),
#             'years': all_years,
#             'scenarios': scenarios,
#             'total_calculations': len(regional_locations) * len(all_years) * len(scenarios) * 9,  # 250 * 4 * 4 * 9 = 36,000
#             'note': 'Hazard 결과는 hazard_results 테이블에 저장됩니다 (P(H)는 계산하지 않음).'
#         }

#     except ImportError as e:
#         logger.error(f"배치 모듈 import 실패: {e}")
#         raise HTTPException(status_code=500, detail=f"Batch module import failed: {str(e)}")
#     except Exception as e:
#         logger.error(f"시군구 배치 실행 실패 (그룹2): {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to run regional locations batch group2: {str(e)}")


# @router.post(
#     "/run-regional-locations-batch-group3",
#     responses={
#         200: {"description": "250개 시군구 배치 작업 (그룹3) 시작 성공"},
#         500: {
#             "description": "배치 작업 실패",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Failed to run regional locations batch group3: Internal error"}
#                 }
#             }
#         }
#     }
# )
# async def run_regional_locations_batch_group3():
#     """
#     250개 시군구 위치에 대한 H(Hazard) 배치 계산 - 그룹3 (P(H)는 제외)

#     - **위치**: 250개 시군구 (REGION_COORD_MAP)
#     - **연도**: 2065, 2070, 2075, 2080 (그룹3 - 4개 연도)
#     - **시나리오**: SSP126, SSP245, SSP370, SSP585
#     - **리스크 타입**: 9가지 (extreme_heat, extreme_cold, wildfire, drought, water_stress, sea_level_rise, river_flood, urban_flood, typhoon)

#     백그라운드에서 실행되며, 결과는 hazard_results 테이블에 저장됩니다.
#     """
#     try:
#         from ...utils.region_mapper import REGION_COORD_MAP
#         from ...batch.hazard_timeseries_batch import run_hazard_batch
#         from concurrent.futures import ThreadPoolExecutor

#         # 250개 시군구 좌표 준비
#         regional_locations = []
#         for code, coords in REGION_COORD_MAP.items():
#             lat = coords.get('lat')
#             lng = coords.get('lng')
#             if lat and lng and lat != 0.0 and lng != 0.0:  # 기본값 제외
#                 regional_locations.append((float(lat), float(lng)))

#         logger.info(f"총 {len(regional_locations)}개 시군구 좌표 로드 완료")

#         # 연도 설정: 그룹3 (2065-2080)
#         all_years = ["2065", "2070", "2075", "2080"]

#         # 시나리오
#         scenarios = ["SSP126", "SSP245", "SSP370", "SSP585"]

#         # 백그라운드 실행 함수
#         def run_batches():
#             try:
#                 logger.info("=" * 80)
#                 logger.info("250개 시군구 Hazard 배치 계산 시작 (그룹3: 2065-2080)")
#                 logger.info(f"위치 개수: {len(regional_locations)}")
#                 logger.info(f"연도: {all_years}")
#                 logger.info(f"시나리오: {scenarios}")
#                 logger.info("=" * 80)

#                 # Hazard 배치 실행 (P(H)는 제외)
#                 logger.info("Hazard Score 배치 계산 시작...")
#                 run_hazard_batch(
#                     grid_points=regional_locations,
#                     scenarios=scenarios,
#                     years=all_years,
#                     risk_types=None,  # 전체 9개 리스크
#                     batch_size=100,
#                     max_workers=6  # 250개 위치이므로 워커 수 증가
#                 )
#                 logger.info("Hazard 배치 완료!")

#                 logger.info("=" * 80)
#                 logger.info("250개 시군구 Hazard 배치 계산 완료! (그룹3)")
#                 logger.info("=" * 80)

#             except Exception as e:
#                 logger.error(f"시군구 배치 실행 중 오류 발생 (그룹3): {e}", exc_info=True)

#         # 백그라운드에서 실행
#         executor = ThreadPoolExecutor(max_workers=1)
#         executor.submit(run_batches)

#         return {
#             'status': 'started',
#             'message': '250개 시군구 Hazard 배치 계산이 백그라운드에서 시작되었습니다 (그룹3: 2065-2080).',
#             'group': 3,
#             'locations_count': len(regional_locations),
#             'years_count': len(all_years),
#             'years': all_years,
#             'scenarios': scenarios,
#             'total_calculations': len(regional_locations) * len(all_years) * len(scenarios) * 9,  # 250 * 4 * 4 * 9 = 36,000
#             'note': 'Hazard 결과는 hazard_results 테이블에 저장됩니다 (P(H)는 계산하지 않음).'
#         }

#     except ImportError as e:
#         logger.error(f"배치 모듈 import 실패: {e}")
#         raise HTTPException(status_code=500, detail=f"Batch module import failed: {str(e)}")
#     except Exception as e:
#         logger.error(f"시군구 배치 실행 실패 (그룹3): {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to run regional locations batch group3: {str(e)}")


# @router.post(
#     "/run-regional-locations-batch-group4",
#     responses={
#         200: {"description": "250개 시군구 배치 작업 (그룹4) 시작 성공"},
#         500: {
#             "description": "배치 작업 실패",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Failed to run regional locations batch group4: Internal error"}
#                 }
#             }
#         }
#     }
# )
# async def run_regional_locations_batch_group4():
#     """
#     250개 시군구 위치에 대한 H(Hazard) 배치 계산 - 그룹4 (P(H)는 제외)

#     - **위치**: 250개 시군구 (REGION_COORD_MAP)
#     - **연도**: 2085, 2090, 2095, 2100 (그룹4 - 4개 연도)
#     - **시나리오**: SSP126, SSP245, SSP370, SSP585
#     - **리스크 타입**: 9가지 (extreme_heat, extreme_cold, wildfire, drought, water_stress, sea_level_rise, river_flood, urban_flood, typhoon)

#     백그라운드에서 실행되며, 결과는 hazard_results 테이블에 저장됩니다.
#     """
#     try:
#         from ...utils.region_mapper import REGION_COORD_MAP
#         from ...batch.hazard_timeseries_batch import run_hazard_batch
#         from concurrent.futures import ThreadPoolExecutor

#         # 250개 시군구 좌표 준비
#         regional_locations = []
#         for code, coords in REGION_COORD_MAP.items():
#             lat = coords.get('lat')
#             lng = coords.get('lng')
#             if lat and lng and lat != 0.0 and lng != 0.0:  # 기본값 제외
#                 regional_locations.append((float(lat), float(lng)))

#         logger.info(f"총 {len(regional_locations)}개 시군구 좌표 로드 완료")

#         # 연도 설정: 그룹4 (2085-2100)
#         all_years = ["2085", "2090", "2095", "2100"]

#         # 시나리오
#         scenarios = ["SSP126", "SSP245", "SSP370", "SSP585"]

#         # 백그라운드 실행 함수
#         def run_batches():
#             try:
#                 logger.info("=" * 80)
#                 logger.info("250개 시군구 Hazard 배치 계산 시작 (그룹4: 2085-2100)")
#                 logger.info(f"위치 개수: {len(regional_locations)}")
#                 logger.info(f"연도: {all_years}")
#                 logger.info(f"시나리오: {scenarios}")
#                 logger.info("=" * 80)

#                 # Hazard 배치 실행 (P(H)는 제외)
#                 logger.info("Hazard Score 배치 계산 시작...")
#                 run_hazard_batch(
#                     grid_points=regional_locations,
#                     scenarios=scenarios,
#                     years=all_years,
#                     risk_types=None,  # 전체 9개 리스크
#                     batch_size=100,
#                     max_workers=6  # 250개 위치이므로 워커 수 증가
#                 )
#                 logger.info("Hazard 배치 완료!")

#                 logger.info("=" * 80)
#                 logger.info("250개 시군구 Hazard 배치 계산 완료! (그룹4)")
#                 logger.info("=" * 80)

#             except Exception as e:
#                 logger.error(f"시군구 배치 실행 중 오류 발생 (그룹4): {e}", exc_info=True)

#         # 백그라운드에서 실행
#         executor = ThreadPoolExecutor(max_workers=1)
#         executor.submit(run_batches)

#         return {
#             'status': 'started',
#             'message': '250개 시군구 Hazard 배치 계산이 백그라운드에서 시작되었습니다 (그룹4: 2085-2100).',
#             'group': 4,
#             'locations_count': len(regional_locations),
#             'years_count': len(all_years),
#             'years': all_years,
#             'scenarios': scenarios,
#             'total_calculations': len(regional_locations) * len(all_years) * len(scenarios) * 9,  # 250 * 4 * 4 * 9 = 36,000
#             'note': 'Hazard 결과는 hazard_results 테이블에 저장됩니다 (P(H)는 계산하지 않음).'
#         }

#     except ImportError as e:
#         logger.error(f"배치 모듈 import 실패: {e}")
#         raise HTTPException(status_code=500, detail=f"Batch module import failed: {str(e)}")
#     except Exception as e:
#         logger.error(f"시군구 배치 실행 실패 (그룹4): {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to run regional locations batch group4: {str(e)}")


# @router.post(
#     "/run-real-map-hazard-batch",
#     responses={
#         200: {"description": "REAL_MAP H 배치 작업 시작 성공"},
#         500: {
#             "description": "배치 작업 실패",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Failed to run REAL_MAP hazard batch: Internal error"}
#                 }
#             }
#         }
#     }
# )
# async def run_real_map_hazard_batch():
#     """
#     REAL_MAP 3개 위치에 대한 H(Hazard) 배치 계산

#     - **위치**: 3개 실제 위치 (REAL_MAP)
#     - **연도**: 2021-2100 (80년) + 10년 단위 (2020s, 2030s, 2040s, 2050s)
#     - **시나리오**: SSP126, SSP245, SSP370, SSP585
#     - **리스크 타입**: 9가지 (extreme_heat, extreme_cold, wildfire, drought, water_stress, sea_level_rise, river_flood, urban_flood, typhoon)

#     백그라운드에서 실행되며, 결과는 hazard_results 테이블에 저장됩니다.
#     """
#     try:
#         from ...utils.real_map import REAL_MAP
#         from ...batch.hazard_timeseries_batch import run_hazard_batch
#         from concurrent.futures import ThreadPoolExecutor

#         # REAL_MAP 좌표 준비
#         real_locations = []
#         for loc in REAL_MAP:
#             lat = loc.get('lat')
#             lng = loc.get('lng')
#             if lat and lng:
#                 real_locations.append((float(lat), float(lng)))

#         if len(real_locations) != 3:
#             raise HTTPException(
#                 status_code=500,
#                 detail=f"Expected 3 locations, but got {len(real_locations)}"
#             )

#         # 연도 설정: 2021-2100 (80년) + 10년 단위 (2020s~2050s)
#         yearly_years = [str(year) for year in range(2021, 2101)]  # "2021"-"2100"
#         decadal_years = ["2020s", "2030s", "2040s", "2050s"]
#         all_years = yearly_years + decadal_years  # 문자열 연도 리스트

#         # 시나리오
#         scenarios = ["SSP126", "SSP245", "SSP370", "SSP585"]

#         # 백그라운드 실행 함수
#         def run_batch():
#             try:
#                 logger.info("=" * 80)
#                 logger.info("REAL_MAP Hazard 배치 계산 시작")
#                 logger.info(f"위치 개수: {len(real_locations)}")
#                 logger.info(f"연도 개수: {len(all_years)} (2021-2100 + 2020s~2050s)")
#                 logger.info(f"시나리오: {scenarios}")
#                 logger.info("=" * 80)

#                 run_hazard_batch(
#                     grid_points=real_locations,
#                     scenarios=scenarios,
#                     years=all_years,
#                     risk_types=None,  # 전체 9개 리스크
#                     batch_size=50,
#                     max_workers=2
#                 )

#                 logger.info("=" * 80)
#                 logger.info("REAL_MAP Hazard 배치 계산 완료!")
#                 logger.info("=" * 80)

#             except Exception as e:
#                 logger.error(f"REAL_MAP Hazard 배치 실행 중 오류 발생: {e}", exc_info=True)

#         # 백그라운드에서 실행
#         executor = ThreadPoolExecutor(max_workers=1)
#         executor.submit(run_batch)

#         return {
#             'status': 'started',
#             'message': 'REAL_MAP Hazard 배치 계산이 백그라운드에서 시작되었습니다.',
#             'locations_count': len(real_locations),
#             'years_count': len(all_years),
#             'years_range': f"2021-2100 + 2020s~2050s",
#             'yearly_years_count': len(yearly_years),
#             'decadal_years': decadal_years,
#             'scenarios': scenarios,
#             'total_calculations': len(real_locations) * len(all_years) * len(scenarios) * 9,
#             'note': 'Hazard 결과는 hazard_results 테이블에 저장됩니다.'
#         }

#     except ImportError as e:
#         logger.error(f"배치 모듈 import 실패: {e}")
#         raise HTTPException(status_code=500, detail=f"Batch module import failed: {str(e)}")
#     except Exception as e:
#         logger.error(f"REAL_MAP Hazard 배치 실행 실패: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to run REAL_MAP hazard batch: {str(e)}")


# @router.post(
#     "/run-real-map-probability-batch",
#     responses={
#         200: {"description": "REAL_MAP P(H) 배치 작업 시작 성공"},
#         500: {
#             "description": "배치 작업 실패",
#             "content": {
#                 "application/json": {
#                     "example": {"detail": "Failed to run REAL_MAP probability batch: Internal error"}
#                 }
#             }
#         }
#     }
# )
# async def run_real_map_probability_batch():
#     """
#     REAL_MAP 3개 위치에 대한 P(H)(Probability) 배치 계산

#     - **위치**: 3개 실제 위치 (REAL_MAP)
#     - **연도**: 2021-2100 (80년) + 10년 단위 (2020s, 2030s, 2040s, 2050s)
#     - **시나리오**: SSP126, SSP245, SSP370, SSP585
#     - **리스크 타입**: 9가지 (extreme_heat, extreme_cold, wildfire, drought, water_stress, sea_level_rise, river_flood, urban_flood, typhoon)

#     백그라운드에서 실행되며, 결과는 probability_results 테이블에 저장됩니다.
#     """
#     try:
#         from ...utils.real_map import REAL_MAP
#         from ...batch.probability_timeseries_batch import run_probability_batch
#         from concurrent.futures import ThreadPoolExecutor

#         # REAL_MAP 좌표 준비
#         real_locations = []
#         for loc in REAL_MAP:
#             lat = loc.get('lat')
#             lng = loc.get('lng')
#             if lat and lng:
#                 real_locations.append((float(lat), float(lng)))

#         if len(real_locations) != 3:
#             raise HTTPException(
#                 status_code=500,
#                 detail=f"Expected 3 locations, but got {len(real_locations)}"
#             )

#         # 연도 설정: 2021-2100 (80년) + 10년 단위 (2020s~2050s)
#         yearly_years = [str(year) for year in range(2021, 2101)]  # "2021"-"2100"
#         decadal_years = ["2020s", "2030s", "2040s", "2050s"]
#         all_years = yearly_years + decadal_years  # 문자열 연도 리스트

#         # 시나리오
#         scenarios = ["SSP126", "SSP245", "SSP370", "SSP585"]

#         # 백그라운드 실행 함수
#         def run_batch():
#             try:
#                 logger.info("=" * 80)
#                 logger.info("REAL_MAP Probability 배치 계산 시작")
#                 logger.info(f"위치 개수: {len(real_locations)}")
#                 logger.info(f"연도 개수: {len(all_years)} (2021-2100 + 2020s~2050s)")
#                 logger.info(f"시나리오: {scenarios}")
#                 logger.info("=" * 80)

#                 run_probability_batch(
#                     grid_points=real_locations,
#                     scenarios=scenarios,
#                     years=all_years,
#                     risk_types=None,  # 전체 9개 리스크
#                     batch_size=50,
#                     max_workers=2
#                 )

#                 logger.info("=" * 80)
#                 logger.info("REAL_MAP Probability 배치 계산 완료!")
#                 logger.info("=" * 80)

#             except Exception as e:
#                 logger.error(f"REAL_MAP Probability 배치 실행 중 오류 발생: {e}", exc_info=True)

#         # 백그라운드에서 실행
#         executor = ThreadPoolExecutor(max_workers=1)
#         executor.submit(run_batch)

#         return {
#             'status': 'started',
#             'message': 'REAL_MAP Probability 배치 계산이 백그라운드에서 시작되었습니다.',
#             'locations_count': len(real_locations),
#             'years_count': len(all_years),
#             'years_range': f"2021-2100 + 2020s~2050s",
#             'yearly_years_count': len(yearly_years),
#             'decadal_years': decadal_years,
#             'scenarios': scenarios,
#             'total_calculations': len(real_locations) * len(all_years) * len(scenarios) * 9,
#             'note': 'Probability 결과는 probability_results 테이블에 저장됩니다.'
#         }

#     except ImportError as e:
#         logger.error(f"배치 모듈 import 실패: {e}")
#         raise HTTPException(status_code=500, detail=f"Batch module import failed: {str(e)}")
#     except Exception as e:
#         logger.error(f"REAL_MAP Probability 배치 실행 실패: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to run REAL_MAP probability batch: {str(e)}")
