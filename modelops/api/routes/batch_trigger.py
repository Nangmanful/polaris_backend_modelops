"""
Batch Trigger API
배치 스케줄 조회 API

과거의 배치 강제 실행 POST 라우트 11개는 소비처 없이 전부 주석 처리되어 있어
API_CONTRACT(§1-B) 기준 삭제 대상으로 제거했다. 스케줄 조회만 유지한다
(운영자 수동 조회용 — 존치 여부는 API_CONTRACT §3-5 미해결 항목).
"""

from fastapi import APIRouter, HTTPException
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batch-trigger", tags=["batch-trigger"])


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
