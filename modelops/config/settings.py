"""전역 설정.

환경변수 이름은 공통 규약(docs/CONVENTIONS.md §4)의 정식 명칭을 따른다:
- Datawarehouse: DW_DB_HOST/PORT/NAME/USER/PASSWORD (기본 포트 5433)
- FastAPI 콜백: FASTAPI_BASE_URL
- 서비스 간 인증: INTERNAL_API_KEY

DB 자격증명은 환경변수(.env)로만 주입한다. 코드에 비밀번호 기본값을 두지 않으며,
비밀번호가 비어 있으면 DB 연결 시점에 명확한 에러를 발생시킨다
(modelops.database.connection 참고). 기본 포트는 .env.example의
DW_DB_PORT(5433)와 일치시킨다.
"""

import os


def _require_database_password(password: str) -> str:
    """DB 비밀번호가 설정되어 있는지 검증하고 반환한다."""
    if not password:
        raise RuntimeError(
            "DW_DB_PASSWORD 환경변수가 설정되지 않았습니다. "
            ".env 파일을 생성하거나 (예: .env.example 참고) "
            "환경변수 DW_DB_PASSWORD를 설정한 뒤 다시 실행하세요."
        )
    return password


try:
    from pydantic_settings import BaseSettings

    class Settings(BaseSettings):
        # Datawarehouse (기후 격자·계산 결과 — CONVENTIONS §4)
        dw_db_host: str = "localhost"
        dw_db_port: int = 5433
        dw_db_name: str = "skala_datawarehouse"
        dw_db_user: str = "skala_dw_user"
        dw_db_password: str = ""

        # FastAPI Application (콜백 API)
        fastapi_base_url: str = "http://localhost:8000"
        internal_api_key: str = ""

        hazard_schedule_month: int = 1
        hazard_schedule_day: int = 1
        hazard_schedule_hour: int = 4
        hazard_schedule_minute: int = 0

        # Batch Processing
        parallel_workers: int = 4
        batch_size: int = 1000

        # NOTIFY
        notify_channel: str = "aiops_trigger"

        class Config:
            env_file = ".env"
            case_sensitive = False
            extra = "ignore"  # 정의되지 않은 환경변수 무시

    settings = Settings()

except ImportError:
    # pydantic_settings가 없으면 간단한 클래스 사용
    class Settings:
        dw_db_host: str = os.getenv("DW_DB_HOST", "localhost")
        dw_db_port: int = int(os.getenv("DW_DB_PORT", "5433"))
        dw_db_name: str = os.getenv("DW_DB_NAME", "skala_datawarehouse")
        dw_db_user: str = os.getenv("DW_DB_USER", "skala_dw_user")
        dw_db_password: str = os.getenv("DW_DB_PASSWORD", "")

        # FastAPI Application (콜백 API)
        fastapi_base_url: str = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")
        internal_api_key: str = os.getenv("INTERNAL_API_KEY", "")

        probability_schedule_month: int = 1
        probability_schedule_day: int = 1
        probability_schedule_hour: int = 2
        probability_schedule_minute: int = 0

        hazard_schedule_month: int = 1
        hazard_schedule_day: int = 1
        hazard_schedule_hour: int = 4
        hazard_schedule_minute: int = 0

        parallel_workers: int = 4
        batch_size: int = 1000

        notify_channel: str = "aiops_trigger"

    settings = Settings()
