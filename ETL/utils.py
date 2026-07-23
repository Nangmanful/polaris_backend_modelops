"""
SKALA Physical Risk AI System - New ETL 통합 유틸리티
Local + API 공통 함수, DB 연결, API 클라이언트 관리

최종 수정일: 2025-12-12
버전: v01
"""

import os
import sys
import json
import time
import logging
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

import psycopg2
from psycopg2.extensions import connection as Connection
from psycopg2.extras import Json
from dotenv import load_dotenv

# .env 파일 로드 (현재 폴더 우선, 없으면 상위 폴더)
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)


# =============================================================================
# 로깅 설정
# =============================================================================


def setup_logging(name: str) -> logging.Logger:
    """
    로깅 설정

    Args:
        name: 로거 이름 (보통 스크립트 이름)

    Returns:
        설정된 Logger 인스턴스
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        # 콘솔 핸들러
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # 포맷 설정
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 파일 핸들러 (logs 디렉토리에 저장)
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# =============================================================================
# 데이터베이스 연결
# =============================================================================


def get_db_connection() -> Connection:
    """
    Datawarehouse 데이터베이스 연결

    Returns:
        psycopg2 connection 객체

    Raises:
        psycopg2.Error: 연결 실패 시
    """
    return psycopg2.connect(
        host=os.getenv("DW_DB_HOST", "localhost"),
        port=os.getenv("DW_DB_PORT", "5555"),
        dbname=os.getenv("DW_DB_NAME", "datawarehouse"),
        user=os.getenv("DW_DB_USER", "skala"),
        password=os.getenv("DW_DB_PASSWORD", "skala1234"),
    )


def get_data_dir() -> Path:
    """
    데이터 디렉토리 경로 반환

    환경변수 DATA_DIR이 설정되어 있으면 해당 경로 사용,
    아니면 기본 경로 사용

    Returns:
        데이터 디렉토리 Path 객체
    """
    data_dir = os.getenv("DATA_DIR")
    if data_dir:
        return Path(data_dir)

    # 기본 경로: etl_base/local/data
    return Path(__file__).parent / "etl_base" / "local" / "data"


# =============================================================================
# 테이블 유틸리티
# =============================================================================


def table_exists(conn: Connection, table_name: str) -> bool:
    """
    테이블 존재 여부 확인

    Args:
        conn: 데이터베이스 연결
        table_name: 테이블 이름

    Returns:
        테이블이 존재하면 True
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = %s
        )
    """,
        (table_name,),
    )
    exists = cursor.fetchone()[0]
    cursor.close()
    return exists


def get_row_count(conn: Connection, table_name: str) -> int:
    """
    테이블 행 수 조회

    Args:
        conn: 데이터베이스 연결
        table_name: 테이블 이름

    Returns:
        행 수 (테이블이 없으면 0)
    """
    if not table_exists(conn, table_name):
        return 0

    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    cursor.close()
    return count


# Alias for API compatibility
get_table_count = get_row_count


def truncate_table(conn: Connection, table_name: str, cascade: bool = False) -> None:
    """
    테이블 데이터 삭제 (TRUNCATE)

    Args:
        conn: 데이터베이스 연결
        table_name: 테이블 이름
        cascade: CASCADE 옵션 사용 여부
    """
    cursor = conn.cursor()
    sql = f"TRUNCATE TABLE {table_name}"
    if cascade:
        sql += " CASCADE"
    cursor.execute(sql)
    conn.commit()
    cursor.close()


# =============================================================================
# 배치 INSERT / UPSERT
# =============================================================================


def batch_insert(
    conn: Connection, table_name: str, columns: list, data: list, batch_size: int = 1000
) -> int:
    """
    배치 삽입

    Args:
        conn: 데이터베이스 연결
        table_name: 테이블 이름
        columns: 컬럼 이름 리스트
        data: 삽입할 데이터 리스트 (튜플의 리스트)
        batch_size: 배치 크기

    Returns:
        삽입된 행 수
    """
    if not data:
        return 0

    cursor = conn.cursor()
    cols = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"

    insert_count = 0
    for i in range(0, len(data), batch_size):
        batch = data[i : i + batch_size]
        cursor.executemany(sql, batch)
        insert_count += len(batch)
        conn.commit()

    cursor.close()
    return insert_count


def upsert_api_data(
    conn: Connection,
    table_name: str,
    data: Dict,
    unique_columns: List[str],
    update_columns: List[str] = None,
) -> bool:
    """
    API 데이터 UPSERT (INSERT ON CONFLICT UPDATE)

    Args:
        conn: 데이터베이스 연결
        table_name: 테이블 이름
        data: 삽입할 데이터 (컬럼명: 값)
        unique_columns: 고유 키 컬럼들
        update_columns: 업데이트할 컬럼들 (None이면 전체)

    Returns:
        성공 여부
    """
    if not data:
        return False

    cursor = conn.cursor()

    try:
        columns = list(data.keys())
        values = list(data.values())

        # JSON 타입 처리
        values = [Json(v) if isinstance(v, dict) else v for v in values]

        # INSERT 구문 생성
        cols_str = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))

        # CONFLICT 처리
        unique_str = ", ".join(unique_columns)

        # UPDATE 구문
        if update_columns is None:
            update_columns = [c for c in columns if c not in unique_columns]

        if update_columns:
            update_str = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_columns])
            if "cached_at" in columns:
                update_str += ", cached_at = CURRENT_TIMESTAMP"
            elif "updated_at" in columns:
                update_str += ", updated_at = CURRENT_TIMESTAMP"
        else:
            if "cached_at" in columns:
                update_str = "cached_at = CURRENT_TIMESTAMP"
            elif "updated_at" in columns:
                update_str = "updated_at = CURRENT_TIMESTAMP"
            else:
                sql = f"""
                    INSERT INTO {table_name} ({cols_str})
                    VALUES ({placeholders})
                    ON CONFLICT ({unique_str})
                    DO NOTHING
                """
                cursor.execute(sql, values)
                conn.commit()
                return True

        sql = f"""
            INSERT INTO {table_name} ({cols_str})
            VALUES ({placeholders})
            ON CONFLICT ({unique_str})
            DO UPDATE SET {update_str}
        """

        cursor.execute(sql, values)
        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        logging.error(f"UPSERT 실패 ({table_name}): {e}")
        return False

    finally:
        cursor.close()


def batch_upsert(
    conn: Connection,
    table_name: str,
    data_list: List[Dict],
    unique_columns: List[str],
    batch_size: int = 100,
) -> int:
    """
    배치 UPSERT

    Args:
        conn: 데이터베이스 연결
        table_name: 테이블 이름
        data_list: 삽입할 데이터 리스트
        unique_columns: 고유 키 컬럼들
        batch_size: 배치 크기

    Returns:
        성공한 레코드 수
    """
    success_count = 0

    for i in range(0, len(data_list), batch_size):
        batch = data_list[i : i + batch_size]
        for data in batch:
            if upsert_api_data(conn, table_name, data, unique_columns):
                success_count += 1

    return success_count


# =============================================================================
# API 클라이언트
# =============================================================================


class APIClient:
    """
    공통 API 클라이언트
    - 재시도 로직
    - 에러 핸들링
    - 레이트 리미팅
    """

    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "SKALA-ETL/1.0"})

    def get(
        self, url: str, params: Dict = None, retries: int = 3, timeout: int = 30, delay: float = 1.0
    ) -> Optional[Dict]:
        """
        GET 요청 (재시도 포함)

        Args:
            url: API URL
            params: 요청 파라미터
            retries: 재시도 횟수
            timeout: 타임아웃 (초)
            delay: 재시도 간 대기 시간 (초)

        Returns:
            JSON 응답 또는 None
        """
        for attempt in range(retries):
            try:
                response = self.session.get(url, params=params, timeout=timeout)
                response.raise_for_status()

                # JSON 파싱 시도
                try:
                    return response.json()
                except json.JSONDecodeError:
                    # XML 등 다른 형식일 수 있음
                    return {"raw_text": response.text, "status_code": response.status_code}

            except requests.exceptions.RequestException as e:
                self.logger.warning(f"API 요청 실패 (시도 {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(delay * (attempt + 1))
                continue

        self.logger.error(f"API 요청 최종 실패: {url}")
        return None


def get_api_key(key_name: str) -> Optional[str]:
    """
    환경변수에서 API 키 가져오기

    Args:
        key_name: 환경변수 이름 (예: 'BUILDING_API_KEY')

    Returns:
        API 키 또는 None
    """
    key = os.getenv(key_name)
    if not key:
        logging.warning(f"API 키 없음: {key_name}")
    return key


# =============================================================================
# API 엔드포인트 정의
# =============================================================================

API_ENDPOINTS = {
    # 재난안전데이터공유플랫폼 (safetydata.go.kr)
    "river_info": "https://www.safetydata.go.kr/V2/api/DSSP-IF-10720",
    "emergency_messages": "https://www.safetydata.go.kr/V2/api/DSSP-IF-00247",
    # WAMIS (인증키 불필요 - 오픈 API)
    "wamis_water_usage": "http://www.wamis.go.kr:8080/wamis/openapi/wks/wks_wiawtaa_lst",
    "wamis_stations": "http://www.wamis.go.kr:8080/wamis/openapi/wkw/flw_dubobsif",
    "wamis_daily_flow": "http://www.wamis.go.kr:8080/wamis/openapi/wkw/flw_dtdata",
    # 기상청 태풍 (TYPHOON_API_KEY 사용)
    "typhoon_list": "https://apihub.kma.go.kr/api/typ01/url/typ_lst.php",
    "typhoon_data": "https://apihub.kma.go.kr/api/typ01/url/typ_data.php",
    "typhoon_besttrack": "https://apihub.kma.go.kr/api/typ01/url/typ_besttrack.php",
    # 기상청 TD (열대저압부)
    "td_list": "https://apihub.kma.go.kr/api/typ01/url/td_lst.php",
    # 재해연보 (행정안전부)
    "disaster_yearbook": "https://apis.data.go.kr/1741000/NaturalDisasterDamageByYear/getNaturalDisasterDamageByYear",
    # 건축물대장 (국토교통부)
    "buildings": "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo",
    # VWorld 역지오코딩
    "vworld_geocode": "https://api.vworld.kr/req/address",
}

# API 키 매핑
API_KEY_MAP = {
    "river_info": "RIVER_API_KEY",
    "emergency_messages": "EMERGENCYMESSAGE_API_KEY",
    "typhoon_list": "TYPHOON_API_KEY",
    "typhoon_data": "TYPHOON_API_KEY",
    "typhoon_besttrack": "TYPHOON_API_KEY",
    "td_list": "TYPHOON_API_KEY",
    "disaster_yearbook": "PUBLICDATA_API_KEY",
    "buildings": "PUBLICDATA_API_KEY",
    "vworld_geocode": "VWORLD_API_KEY",
}


# =============================================================================
# 테스트
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("SKALA New ETL - Utils 테스트")
    print("=" * 60)

    # DB 연결 테스트
    print("\n[1] Database Connection Test")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"    Connected: {version[:50]}...")
        cursor.close()
        conn.close()
        print("    Status: OK")
    except Exception as e:
        print(f"    Status: FAILED - {e}")

    # 데이터 디렉토리 확인
    print(f"\n[2] Data Directory")
    data_dir = get_data_dir()
    print(f"    Path: {data_dir}")
    print(f"    Exists: {data_dir.exists()}")

    # API 키 확인
    print("\n[3] API Keys")
    for key_name in [
        "RIVER_API_KEY",
        "EMERGENCYMESSAGE_API_KEY",
        "TYPHOON_API_KEY",
        "VWORLD_API_KEY",
        "PUBLICDATA_API_KEY",
    ]:
        key = os.getenv(key_name)
        status = f"OK ({key[:10]}...)" if key else "MISSING"
        print(f"    {key_name}: {status}")

    print("\n" + "=" * 60)
