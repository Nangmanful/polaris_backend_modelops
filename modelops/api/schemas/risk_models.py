"""
Pydantic 스키마 정의
Risk Assessment API 요청/응답 모델
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class RiskAssessmentRequest(BaseModel):
    """리스크 평가 계산 요청"""

    # Required fields
    latitude: float = Field(..., ge=-90, le=90, description="위도")
    longitude: float = Field(..., ge=-180, le=180, description="경도")

    # Optional fields
    site_id: Optional[str] = Field(None, max_length=255, description="사업장 ID (추적용)")

    building_info: Optional[Dict[str, Any]] = Field(
        None,
        description="""
        커스텀 건물 정보 (제공 시 API 호출 생략)
        - ground_floors: int (지상층수)
        - basement_floors: int (지하층수)
        - total_area_m2: float (연면적)
        - building_age: int (건축년수)
        - structure: str (구조: 철근콘크리트/철골 등)
        - main_purpose: str (주용도: 업무시설/공장 등)
        - has_piloti: bool (필로티 여부)
        - has_water_tank: bool (물탱크 여부)
        - distance_to_river_m: float (하천거리)
        - distance_to_coast_m: float (해안거리)
    """,
    )

    asset_info: Optional[Dict[str, Any]] = Field(
        None,
        description="""
        커스텀 자산 정보
        - total_asset_value: float (총 자산가치, 원)
        - insurance_coverage_rate: float (보험 보전율, 0~1)
        - floor_area: float (전용면적, ㎡)
    """,
    )

    class Config:
        json_schema_extra = {
            "example": {
                "latitude": 37.5665,
                "longitude": 126.9780,
                "site_id": "SITE-2025-001",
                "building_info": {
                    "ground_floors": 10,
                    "basement_floors": 2,
                    "total_area_m2": 5000.0,
                    "building_age": 15,
                    "structure": "철근콘크리트",
                    "main_purpose": "업무시설",
                },
                "asset_info": {"total_asset_value": 50000000000, "insurance_coverage_rate": 0.7},
            }
        }


class RiskAssessmentResponse(BaseModel):
    """리스크 평가 계산 응답"""

    request_id: str = Field(..., description="요청 ID")
    status: str = Field(..., description="상태 (queued, processing, completed, failed)")
    websocket_url: Optional[str] = Field(None, description="WebSocket URL")
    message: Optional[str] = Field(None, description="메시지")
    site_id: Optional[str] = Field(None, description="사업장 ID (요청 시 제공된 경우)")

    class Config:
        json_schema_extra = {
            "example": {
                "request_id": "req-12345-67890",
                "status": "queued",
                "websocket_url": "ws://localhost:8001/api/v1/risk-assessment/ws/req-12345-67890",
                "message": "계산이 큐에 등록되었습니다",
                "site_id": "SITE-2025-001",
            }
        }


class ProgressUpdate(BaseModel):
    """진행상황 업데이트"""

    status: str = Field(..., description="상태")
    current: int = Field(..., description="현재 진행")
    total: int = Field(..., description="전체 작업")
    current_risk: Optional[str] = Field(None, description="현재 계산 중인 리스크")
    results: Optional[Dict[str, Any]] = Field(None, description="계산 결과")
    error: Optional[str] = Field(None, description="에러 메시지")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "processing",
                "current": 3,
                "total": 9,
                "current_risk": "wildfire",
                "results": None,
                "error": None,
            }
        }


class RiskResultsResponse(BaseModel):
    """저장된 리스크 결과 조회 응답"""

    latitude: float
    longitude: float
    exposure: Dict[str, Any] = Field(..., description="노출도 결과")
    vulnerability: Dict[str, Any] = Field(..., description="취약성 결과")
    aal_scaled: Dict[str, Any] = Field(..., description="AAL 스케일링 결과")
    summary: Optional[Dict[str, Any]] = Field(None, description="요약 통계")
    calculated_at: Optional[datetime] = Field(None, description="계산 일시")

    class Config:
        json_schema_extra = {
            "example": {
                "latitude": 37.5665,
                "longitude": 126.9780,
                "exposure": {"extreme_heat": {"exposure_score": 0.75, "proximity_factor": 0.9}},
                "vulnerability": {
                    "extreme_heat": {"vulnerability_score": 65.0, "vulnerability_level": "high"}
                },
                "aal_scaled": {
                    "extreme_heat": {
                        "base_aal": 0.012,
                        "vulnerability_scale": 1.03,
                        "final_aal": 0.01236,
                    }
                },
                "summary": {"total_final_aal": 0.0987, "average_vulnerability": 62.5},
            }
        }


class HealthResponse(BaseModel):
    """Health Check 응답 (공통 규약 CONVENTIONS §2: status·service·version)"""

    status: str = Field(..., description="서버 상태 (ok)")
    service: str = Field(..., description="서비스 이름 (modelops)")
    version: str = Field(..., description="서비스 버전")
    database: Optional[str] = Field(None, description="데이터베이스 상태 (/api/health/db 전용)")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "ok",
                "service": "modelops",
                "version": "2.0.0",
            }
        }
