"""전역 설정.

DB 자격증명은 환경변수(.env)로만 주입한다. 코드에 비밀번호 기본값을 두지 않으며,
비밀번호가 비어 있으면 DB 연결 시점에 명확한 에러를 발생시킨다
(modelops.database.connection 참고). 기본 포트는 .env.example의
DATABASE_PORT(5432)와 일치시킨다.
"""

import os


def _require_database_password(password: str) -> str:
    """DB 비밀번호가 설정되어 있는지 검증하고 반환한다."""
    if not password:
        raise RuntimeError(
            "DATABASE_PASSWORD 환경변수가 설정되지 않았습니다. "
            ".env 파일을 생성하거나 (예: .env.example 참고) "
            "환경변수 DATABASE_PASSWORD를 설정한 뒤 다시 실행하세요."
        )
    return password


try:
    from pydantic_settings import BaseSettings

    class Settings(BaseSettings):
        # Database (Data Warehouse - Primary DB for climate data)
        database_host: str = "localhost"
        database_port: int = 5432
        database_name: str = "datawarehouse"
        database_user: str = "skala"
        database_password: str = ""

        # FastAPI Application (콜백 API)
        fastapi_url: str = "http://localhost:8000"
        fastapi_api_key: str = ""

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
        database_host: str = os.getenv("DATABASE_HOST", "localhost")
        database_port: int = int(os.getenv("DATABASE_PORT", "5432"))
        database_name: str = os.getenv("DATABASE_NAME", "datawarehouse")
        database_user: str = os.getenv("DATABASE_USER", "skala")
        database_password: str = os.getenv("DATABASE_PASSWORD", "")

        # FastAPI Application (콜백 API)
        fastapi_url: str = os.getenv("FASTAPI_URL", "http://localhost:8000")
        fastapi_api_key: str = os.getenv("FASTAPI_API_KEY", "")

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
