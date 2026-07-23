"""
Health Check API
서버 및 데이터베이스 상태 확인

경로·응답 형식은 공통 규약(docs/CONVENTIONS.md §2)을 따른다:
GET /api/health → { "status": "ok", "service": "modelops", "version": "<버전>" }
"""

from fastapi import APIRouter, HTTPException
from ..schemas.risk_models import HealthResponse
from ...database.connection import DatabaseConnection
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])

SERVICE_NAME = "modelops"
SERVICE_VERSION = "2.0.0"


@router.get(
    "",
    response_model=HealthResponse,
    responses={
        200: {"description": "서버 정상 작동 중"},
    },
)
async def health_check():
    """서버 상태 확인"""
    return HealthResponse(status="ok", service=SERVICE_NAME, version=SERVICE_VERSION)


@router.get(
    "/db",
    response_model=HealthResponse,
    responses={
        200: {"description": "데이터베이스 연결 정상"},
        500: {
            "description": "데이터베이스 연결 실패",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "status": "unhealthy",
                            "database": "disconnected",
                            "error": "Connection failed",
                        }
                    }
                }
            },
        },
    },
)
async def database_health():
    """데이터베이스 연결 확인"""
    try:
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

            if result:
                return HealthResponse(
                    status="ok",
                    service=SERVICE_NAME,
                    version=SERVICE_VERSION,
                    database="connected",
                )
            else:
                raise Exception("Database query returned no result")

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={"status": "unhealthy", "database": "disconnected", "error": str(e)},
        )
