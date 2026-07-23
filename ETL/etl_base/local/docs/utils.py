"""
SKALA Physical Risk AI System - 공통 유틸리티
데이터 로딩 스크립트를 위한 데이터베이스 연결 및 로깅 유틸리티

최종 수정일: 2025-11-19
버전: v01

사용처: 모든 load_*.py 스크립트
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional
import psycopg2
from psycopg2.extensions import connection
from dotenv import load_dotenv


def setup_logging(log_name: str) -> logging.Logger:
    """
    로깅 설정 구성

    Args:
        log_name: 로거 이름

    Returns:
        설정된 로거 인스턴스
    """
    # logs 디렉토리가 없으면 생성
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # 로깅 설정
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_file = log_dir / f"{log_name}.log"

    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    logger = logging.getLogger(log_name)
    return logger


def get_db_connection() -> connection:
    """
    PostgreSQL 데이터베이스 연결 가져오기

    Returns:
        psycopg2 연결 객체

    Raises:
        Exception: 연결 실패 시
    """
    # 환경 변수 로드
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)

    # 연결 파라미터 가져오기 (Datawarehouse)
    db_params = {
        "host": os.getenv("DW_HOST", "localhost"),
        "port": os.getenv("DW_PORT", "5433"),
        "database": os.getenv("DW_NAME", "skala_datawarehouse"),
        "user": os.getenv("DW_USER", "skala_dw_user"),
        "password": os.getenv("DW_PASSWORD"),
    }

    # 필수 파라미터 검증
    if not db_params["password"]:
        raise ValueError("DW_PASSWORD not set in .env file")

    try:
        conn = psycopg2.connect(**db_params)
        return conn
    except Exception as e:
        raise Exception(f"Failed to connect to database: {e}")


def get_data_dir() -> Path:
    """
    환경 변수 또는 기본값에서 데이터 디렉토리 경로 가져오기

    Returns:
        데이터 디렉토리 경로
    """
    # 환경 변수 로드
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)

    # 환경 변수에서 데이터 디렉토리 가져오기 또는 기본값 사용
    data_dir_str = os.getenv("DATA_DIR", "../data")

    # ETL 디렉토리 기준 상대 경로 해석
    if data_dir_str.startswith(".."):
        data_dir = (Path(__file__).parent.parent / data_dir_str).resolve()
    else:
        data_dir = Path(data_dir_str)

    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")
    return data_dir


def execute_sql(conn: connection, sql: str, params: Optional[tuple] = None) -> None:
    """
    SQL 문 실행

    Args:
        conn: 데이터베이스 연결
        sql: 실행할 SQL 문
        params: 파라미터화된 쿼리를 위한 선택적 파라미터
    """
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


def table_exists(conn: connection, table_name: str) -> bool:
    """
    데이터베이스에 테이블이 존재하는지 확인

    Args:
        conn: 데이터베이스 연결
        table_name: 확인할 테이블 이름

    Returns:
        테이블이 존재하면 True, 그렇지 않으면 False
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
            (table_name,),
        )
        result = cursor.fetchone()[0]
        return result
    finally:
        cursor.close()


def get_row_count(conn: connection, table_name: str) -> int:
    """
    테이블의 행 수 가져오기

    Args:
        conn: 데이터베이스 연결
        table_name: 테이블 이름

    Returns:
        테이블의 행 수
    """
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        return count
    finally:
        cursor.close()
