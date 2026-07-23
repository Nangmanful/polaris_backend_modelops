"""
ModelOps Site Assessment API
사업장 리스크 평가 및 이전 후보지 추천 API

FastAPI 메인 앱
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from modelops.api.routes import health, site_assessment, batch_trigger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from modelops.batch.probability_timeseries_batch import run_probability_batch
from modelops.batch.hazard_timeseries_batch import run_hazard_batch
import logging
import sys
from datetime import datetime
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def probability_batch_job():
    """
    P(H) 배치 작업 실행 함수
    """
    logger.info("=" * 80)
    logger.info("P(H) BATCH JOB STARTED")
    logger.info(f"Execution Time: {datetime.now().isoformat()}")
    logger.info("=" * 80)

    try:
        run_probability_batch(
            grid_points=None,  # 전체 격자점
            scenarios=None,  # 전체 시나리오
            years=None,  # 2021-2100
            risk_types=None,  # 전체 리스크
            batch_size=100,
            max_workers=4,
        )
        logger.info("P(H) BATCH JOB COMPLETED SUCCESSFULLY")
    except Exception as e:
        logger.error(f"P(H) BATCH JOB FAILED: {e}", exc_info=True)


def hazard_batch_job():
    """
    H 배치 작업 실행 함수
    """
    logger.info("=" * 80)
    logger.info("HAZARD SCORE BATCH JOB STARTED")
    logger.info(f"Execution Time: {datetime.now().isoformat()}")
    logger.info("=" * 80)

    try:
        run_hazard_batch(
            grid_points=None,  # 전체 격자점
            scenarios=None,  # 전체 시나리오
            years=None,  # 2021-2100
            risk_types=None,  # 전체 리스크
            batch_size=100,
            max_workers=4,
        )
        logger.info("HAZARD SCORE BATCH JOB COMPLETED SUCCESSFULLY")
    except Exception as e:
        logger.error(f"HAZARD SCORE BATCH JOB FAILED: {e}", exc_info=True)


def emergency_messages_batch_job():
    """
    재난안전데이터 긴급재난문자 ETL 배치 작업 실행 함수
    """
    logger.info("=" * 80)
    logger.info("EMERGENCY MESSAGES ETL BATCH JOB STARTED")
    logger.info(f"Execution Time: {datetime.now().isoformat()}")
    logger.info("=" * 80)

    try:
        # ETL 스크립트 경로 추가
        etl_path = Path(__file__).parent / "ETL" / "etl_base" / "api" / "scripts"
        if str(etl_path) not in sys.path:
            sys.path.insert(0, str(etl_path))

        # ETL 스크립트 동적 import
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "load_emergency_messages", etl_path / "02_load_emergency_messages.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 최근 5년 데이터 수집 (sample_limit 없이 전체 수집)
        module.load_emergency_messages(sample_limit=None, years=5)

        logger.info("EMERGENCY MESSAGES ETL BATCH JOB COMPLETED SUCCESSFULLY")
    except Exception as e:
        logger.error(f"EMERGENCY MESSAGES ETL BATCH JOB FAILED: {e}", exc_info=True)


# 스케줄러 인스턴스
scheduler = None

# FastAPI 앱 생성
app = FastAPI(
    title="ModelOps Site Assessment API",
    description="""
    사업장 리스크 평가 및 이전 후보지 추천 API

    ## Features
    - **사업장 리스크 계산**: 건물 정보 기반 9개 기후 리스크 통합 평가
    - **이전 후보지 추천**: ~1000개 후보 격자를 평가하여 최적 입지 추천
    - **AAL 기반 의사결정**: 기후 리스크와 건물 취약성을 결합한 연평균 손실 계산
    - **자동 배치 처리**: Hazard, Probability 스케줄러로 전국 격자 데이터 자동 계산
    - **결과 저장**: 계산 결과 자동 DB 저장

    ## 계산 프로세스
    1. **H (Hazard)**: DB 조회 (스케줄러가 미리 계산)
    2. **E (Exposure)**: 건물 정보 기반 노출도 계산
    3. **V (Vulnerability)**: 건물 특성 기반 취약성 계산
    4. **통합 리스크**: H × E × V / 10000
    5. **AAL 계산**: base_aal × F_vuln × (1 - insurance_rate)
       - base_aal: DB 조회 (기후만 고려)
       - F_vuln: 0.9 + (V_score / 100) × 0.2

    ## 9개 Physical Risks
    1. extreme_heat (극한 고온)
    2. extreme_cold (극한 한파)
    3. wildfire (산불)
    4. drought (가뭄)
    5. water_stress (물 부족)
    6. sea_level_rise (해수면 상승)
    7. river_flood (하천 홍수)
    8. urban_flood (도시 홍수)
    9. typhoon (태풍)

    ## API Endpoints
    ### Site Assessment (사업장 리스크 평가)
    - POST `/api/site-assessment/calculate`: 사업장 리스크 계산
    - POST `/api/site-assessment/recommend-locations`: 이전 후보지 추천
    - GET `/api/site-assessment/task-status/{task_id}`: 작업 상태 조회
    - GET `/api/site-assessment/tasks`: 모든 작업 조회
    - DELETE `/api/site-assessment/task/{task_id}`: 작업 삭제

    ### Batch Trigger (배치 작업 관리)
    - GET `/api/batch-trigger/scheduled-jobs`: 스케줄된 작업 조회

    ### Health Check
    - GET `/api/health`: 서버 상태 확인
    - GET `/api/health/db`: 데이터베이스 연결 확인
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(site_assessment.router)
app.include_router(health.router)
app.include_router(batch_trigger.router)


@app.on_event("startup")
async def startup_event():
    """서버 시작 시 실행"""
    global scheduler

    logger.info("=" * 60)
    logger.info("ModelOps Site Assessment API 시작")
    logger.info("=" * 60)
    logger.info("API 문서: http://localhost:8001/docs")
    logger.info("Health Check: http://localhost:8001/api/health")
    logger.info("=" * 60)

    # BackgroundScheduler 시작
    try:
        scheduler = BackgroundScheduler()

        # P(H) 배치 스케줄 등록: 매년 1월 1일 02:00
        scheduler.add_job(
            probability_batch_job,
            trigger=CronTrigger(month=1, day=1, hour=2, minute=0),  # 1월  # 1일  # 02:00
            id="probability_batch",
            name="P(H) Timeseries Batch",
            replace_existing=True,
        )

        # H 배치 스케줄 등록: 매년 1월 1일 04:00
        scheduler.add_job(
            hazard_batch_job,
            trigger=CronTrigger(month=1, day=1, hour=4, minute=0),  # 1월  # 1일  # 04:00
            id="hazard_batch",
            name="Hazard Score Timeseries Batch",
            replace_existing=True,
        )

        # 재난안전데이터 ETL 배치 스케줄 등록: 매일 09:00
        scheduler.add_job(
            emergency_messages_batch_job,
            trigger=CronTrigger(hour=9, minute=0),  # 09:00
            id="emergency_messages_etl",
            name="Emergency Messages ETL Batch",
            replace_existing=True,
        )

        scheduler.start()
        logger.info("✓ Background 배치 스케줄러 시작 및 작업 등록 완료")
        logger.info("  - P(H) 배치: 매년 1월 1일 02:00")
        logger.info("  - H 배치: 매년 1월 1일 04:00")
        logger.info("  - 재난안전데이터 ETL: 매일 09:00")

    except Exception as e:
        logger.error(f"✗ 배치 스케줄러 시작 실패: {e}", exc_info=True)
        logger.warning("스케줄러 없이 API 서버를 계속 실행합니다.")


@app.on_event("shutdown")
async def shutdown_event():
    """서버 종료 시 실행"""
    global scheduler

    # 스케줄러 종료
    if scheduler:
        scheduler.shutdown()
        logger.info("Background 배치 스케줄러 종료")

    logger.info("ModelOps Site Assessment API 종료")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "ModelOps Site Assessment API",
        "version": "2.0.0",
        "description": "사업장 리스크 평가 및 이전 후보지 추천 API",
        "docs": "/docs",
        "health": "/api/health",
        "features": [
            "사업장 리스크 계산 (건물 정보 기반 H × E × V)",
            "이전 후보지 추천 (~1000개 격자 평가)",
            "AAL 기반 의사결정 (base_aal × F_vuln)",
            "자동 배치 처리 (Hazard, Probability 스케줄러)",
        ],
        "calculation_process": {
            "1_hazard": "DB 조회 (스케줄러가 미리 계산)",
            "2_exposure": "건물 정보 기반 노출도 계산",
            "3_vulnerability": "건물 특성 기반 취약성 계산",
            "4_integrated_risk": "H × E × V / 10000",
            "5_aal": "base_aal × F_vuln × (1 - insurance_rate)",
        },
        "endpoints": {
            "site_assessment": {
                "calculate": "POST /api/site-assessment/calculate",
                "recommend_locations": "POST /api/site-assessment/recommend-locations",
                "task_status": "GET /api/site-assessment/task-status/{task_id}",
                "tasks": "GET /api/site-assessment/tasks",
                "delete_task": "DELETE /api/site-assessment/task/{task_id}",
            },
            "batch_trigger": {
                "scheduled_jobs": "GET /api/batch-trigger/scheduled-jobs",
            },
            "health": {"check": "GET /api/health", "database": "GET /api/health/db"},
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
