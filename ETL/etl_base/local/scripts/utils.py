"""
SKALA Physical Risk AI System - ETL 유틸리티
공통 함수 및 데이터베이스 연결 관리

최종 수정일: 2025-12-03
버전: v01
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

import psycopg2
from psycopg2.extensions import connection as Connection
from dotenv import load_dotenv

# .env 파일 로드 (프로젝트 루트에서)
env_path = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(env_path)


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
        host=os.getenv("DW_HOST", "localhost"),
        port=os.getenv("DW_PORT", "5555"),
        dbname=os.getenv("DW_NAME", "datawarehouse"),
        user=os.getenv("DW_USER", "skala"),
        password=os.getenv("DW_PASSWORD", "skala1234"),
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

    # 기본 경로: db_final_1202/etl/local/data
    return Path(__file__).parent.parent / "data"


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

    print(f"\nData directory: {get_data_dir()}")
