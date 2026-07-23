"""
SKALA Physical Risk AI System - API ETL 유틸리티
외부 API 호출 및 데이터베이스 연결 관리

최종 수정일: 2025-12-03
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

# .env 파일 로드 (여러 위치 시도)
env_candidates = [
    Path(__file__).parent.parent.parent.parent / "new_etl" / ".env",  # modelops/new_etl/.env
    Path(__file__).parent.parent.parent / ".env",  # modelops/etl/.env (기존)
    Path(__file__).parent / ".env",  # scripts/.env
]
for env_path in env_candidates:
    if env_path.exists():
        load_dotenv(env_path)
        break


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
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


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
        port=os.getenv("DW_DB_PORT", "5434"),
        dbname=os.getenv("DW_DB_NAME", "skala_datawarehouse"),
        user=os.getenv("DW_DB_USER", "skala_dw_user"),
        password=os.getenv("DW_DB_PASSWORD", "skala_dw_2025"),
    )


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
                    time.sleep(delay * (attempt + 1))  # 점진적 대기
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

        # update_columns가 비어있으면 (모든 컬럼이 unique인 경우) 타임스탬프만 업데이트
        if update_columns:
            update_str = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_columns])
            # 테이블별 타임스탬프 컬럼 확인 (cached_at 또는 updated_at)
            if "cached_at" in columns:
                update_str += ", cached_at = CURRENT_TIMESTAMP"
            elif "updated_at" in columns:
                update_str += ", updated_at = CURRENT_TIMESTAMP"
        else:
            # 업데이트할 데이터 컬럼이 없는 경우 (모든 컬럼이 unique)
            # 타임스탬프만 업데이트하거나 DO NOTHING
            if "cached_at" in columns:
                update_str = "cached_at = CURRENT_TIMESTAMP"
            elif "updated_at" in columns:
                update_str = "updated_at = CURRENT_TIMESTAMP"
            else:
                # 타임스탬프 컬럼도 없으면 충돌 시 아무것도 하지 않음
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


def get_table_count(conn: Connection, table_name: str) -> int:
    """
    테이블 레코드 수 조회

    Args:
        conn: 데이터베이스 연결
        table_name: 테이블 이름

    Returns:
        레코드 수
    """
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    cursor.close()
    return count


# API 엔드포인트 정의
API_ENDPOINTS = {
    # SGIS (통계지리정보서비스 - 2025.11.20 도메인 변경)
    "sgis_auth": "https://sgisapi.mods.go.kr/OpenAPI3/auth/authentication.json",
    "sgis_population": "https://sgisapi.mods.go.kr/OpenAPI3/stats/searchpopulation.json",
    "sgis_addr_stage": "https://sgisapi.mods.go.kr/OpenAPI3/addr/stage.json",
    # 재난안전데이터공유플랫폼 (safetydata.go.kr)
    "river_info": "https://www.safetydata.go.kr/V2/api/DSSP-IF-10720",
    "emergency_messages": "https://www.safetydata.go.kr/V2/api/DSSP-IF-00247",
    # WAMIS (인증키 불필요 - 오픈 API)
    "wamis_water_usage": "http://www.wamis.go.kr:8080/wamis/openapi/wks/wks_wiawtaa_lst",
    "wamis_stations": "http://www.wamis.go.kr:8080/wamis/openapi/wkw/flw_dubobsif",
    "wamis_daily_flow": "http://www.wamis.go.kr:8080/wamis/openapi/wkw/flw_dtdata",
    # K-water 댐 저수율 (공공데이터포털)
    "dam_storage": "http://apis.data.go.kr/B500001/rwis/waterLevel/list",
    # 기상청 태풍 (TYPHOON_API_KEY 사용)
    "typhoon_list": "https://apihub.kma.go.kr/api/typ01/url/typ_lst.php",
    "typhoon_data": "https://apihub.kma.go.kr/api/typ01/url/typ_data.php",  # typ_inf.php(X) -> typ_data.php(O)
    "typhoon_now": "https://apihub.kma.go.kr/api/typ01/url/typ_now.php",
    "typhoon_affected": "https://apis.data.go.kr/1360000/TyphoonInfoService/getTyphoonInfo",
    # 기상청 TD (열대저압부)
    "td_list": "https://apihub.kma.go.kr/api/typ01/url/td_lst.php",
    "td_data": "https://apihub.kma.go.kr/api/typ01/url/td_data.php",
    "td_now": "https://apihub.kma.go.kr/api/typ01/url/td_now.php",
    # 기상청 태풍 베스트트랙 (사후 재분석)
    "typhoon_besttrack": "https://apihub.kma.go.kr/api/typ01/url/typ_besttrack.php",
    # 재해연보 (행정안전부)
    "disaster_yearbook": "https://apis.data.go.kr/1741000/NaturalDisasterDamageByYear/getNaturalDisasterDamageByYear",
    # 공공데이터포털 (PUBLICDATA_API_KEY 사용)
    "hospitals": "https://apis.data.go.kr/B552657/HsptlAsembySearchService/getHsptlMdcncListInfoInqire",
    "buildings": "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo",
    "firestations": "https://apis.data.go.kr/1741000/FacInfoService/getFacInfo",
    "shelters": "https://apis.data.go.kr/1741000/SheltInfoService/getSheltInfo",
    "watertanks": "https://apis.data.go.kr/1480523/ReservoirInfoService/getReservoirInfo",
    "groundwater": "https://apis.data.go.kr/B500001/groundwater/getGroundwaterInfo",
    "wildfire": "https://apis.data.go.kr/1400377/forestPoint/forestPointListSearch",
    "heating": "https://apis.data.go.kr/B552584/RealTimeHeatingIndex/getRealTimeHeatingIndex",
    "coastal_infra": "https://apis.data.go.kr/1192000/CoastProtectionInfoService/getCoastProtectionList",
}

# API 키 매핑
API_KEY_MAP = {
    # SGIS (2개 키 필요: SERVICE_ID + SECURITY_KEY)
    "sgis_auth": "SGIS_SERVICE_ID",
    "sgis_population": "SGIS_SERVICE_ID",
    "river_info": "RIVER_API_KEY",
    "emergency_messages": "EMERGENCYMESSAGE_API_KEY",
    "dam_storage": "PUBLICDATA_API_KEY",
    # 태풍 API (TYPHOON_API_KEY 사용)
    "typhoon_list": "TYPHOON_API_KEY",
    "typhoon_data": "TYPHOON_API_KEY",
    "typhoon_now": "TYPHOON_API_KEY",
    "typhoon_affected": "PUBLICDATA_API_KEY",
    # TD API (TYPHOON_API_KEY 사용)
    "td_list": "TYPHOON_API_KEY",
    "td_data": "TYPHOON_API_KEY",
    "td_now": "TYPHOON_API_KEY",
    # 베스트트랙
    "typhoon_besttrack": "TYPHOON_API_KEY",
    # 재해연보
    "disaster_yearbook": "PUBLICDATA_API_KEY",
    # 기타 공공데이터
    "hospitals": "PUBLICDATA_API_KEY",
    "buildings": "PUBLICDATA_API_KEY",
    "firestations": "PUBLICDATA_API_KEY",
    "shelters": "PUBLICDATA_API_KEY",
    "watertanks": "PUBLICDATA_API_KEY",
    "groundwater": "PUBLICDATA_API_KEY",
    "wildfire": "PUBLICDATA_API_KEY",
    "heating": "PUBLICDATA_API_KEY",
    "coastal_infra": "PUBLICDATA_API_KEY",
    # WAMIS는 키 불필요
}


if __name__ == "__main__":
    # 테스트
    print("Testing database connection...")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"Connected: {version}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Connection failed: {e}")

    print("\nAPI Keys loaded:")
    for key_name in [
        "BUILDING_API_KEY",
        "RIVER_API_KEY",
        "EMERGENCYMESSAGE_API_KEY",
        "KMA_API_KEY",
    ]:
        key = get_api_key(key_name)
        print(f"  {key_name}: {'OK' if key else 'MISSING'}")
