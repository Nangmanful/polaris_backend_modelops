"""
SKALA Physical Risk AI System - WAMIS API ETL

API: WAMIS 국가수자원관리종합정보시스템 (오픈 API - 키 불필요)
URL: http://www.wamis.go.kr:8080/wamis/openapi/
용도: 용수이용량, 유량관측소, 실시간 일유량

최종 수정일: 2025-12-03
버전: v01
"""

import os
import sys
from pathlib import Path

# 상위 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from psycopg2.extras import Json
from utils import (
    setup_logging,
    get_db_connection,
    APIClient,
    batch_upsert,
    get_table_count,
    API_ENDPOINTS,
)


def fetch_wamis_stations(client: APIClient, logger):
    """
    WAMIS 유량 관측소 목록 조회 (인증키 불필요)

    Returns:
        API 응답 데이터
    """
    url = API_ENDPOINTS["wamis_stations"]
    params = {"output": "json"}

    logger.info("WAMIS 유량 관측소 API 호출")
    return client.get(url, params=params, timeout=30)


def fetch_wamis_water_usage(client: APIClient, logger, basin: str = None):
    """
    WAMIS 용수이용량 조회 (인증키 불필요)

    Args:
        basin: 권역코드 (1:한강, 2:낙동강, 3:금강, 4:섬진강, 5:영산강, 6:제주도)

    Returns:
        API 응답 데이터
    """
    url = API_ENDPOINTS["wamis_water_usage"]
    params = {"output": "json"}

    if basin:
        params["basin"] = basin

    logger.info(f"WAMIS 용수이용량 API 호출: 권역={basin or '전체'}")
    return client.get(url, params=params, timeout=30)


def parse_wamis_stations(raw_data: dict, logger) -> list:
    """
    유량 관측소 응답 파싱

    Args:
        raw_data: API 응답
        logger: 로거

    Returns:
        파싱된 데이터 리스트
    """
    parsed = []

    if not raw_data:
        logger.warning("API 응답 없음")
        return parsed

    # 응답 구조 확인
    result = raw_data.get("result", {})
    if result.get("code") != "success":
        logger.error(f"API 오류: {result.get('msg')}")
        return parsed

    items = raw_data.get("list", [])
    if not items:
        logger.warning("API 응답 list 없음")
        return parsed

    for item in items:
        try:
            # 위경도 파싱
            lat = None
            lon = None
            try:
                lat = float(item.get("lat", 0)) if item.get("lat") else None
                lon = float(item.get("lon", 0)) if item.get("lon") else None
            except:
                pass

            record = {
                "obs_code": item.get("obscd", ""),
                "obs_name": item.get("obsnm", ""),
                "river_name": item.get("rvnm", ""),
                "basin_code": item.get("wlobscd", ""),
                "basin_name": item.get("bbsnm", ""),
                "sido_name": item.get("addr", "").split()[0] if item.get("addr") else "",
                "address": item.get("addr", ""),
                "latitude": lat,
                "longitude": lon,
                "is_active": True,  # 목록에 있으면 운영중
                "api_response": item,
            }

            if record["obs_code"]:
                parsed.append(record)

        except Exception as e:
            logger.warning(f"레코드 파싱 실패: {e}")
            continue

    return parsed


def parse_wamis_water_usage(raw_data: dict, logger) -> list:
    """
    용수이용량 응답 파싱 -> api_wamis 테이블용

    Args:
        raw_data: API 응답
        logger: 로거

    Returns:
        파싱된 데이터 리스트
    """
    parsed = []

    if not raw_data:
        logger.warning("API 응답 없음")
        return parsed

    result = raw_data.get("result", {})
    if result.get("code") != "success":
        logger.error(f"API 오류: {result.get('msg')}")
        return parsed

    items = raw_data.get("list", [])
    if not items:
        logger.warning("API 응답 list 없음")
        return parsed

    for item in items:
        try:
            record = {
                "api_type": "water_usage",
                "api_endpoint": API_ENDPOINTS["wamis_water_usage"],
                "admcd": item.get("admcd", ""),
                "basin": item.get("basin", ""),
                "year": item.get("year", ""),
                "output_format": "json",
                "response_data": item,
                "http_status": 200,
            }
            parsed.append(record)

        except Exception as e:
            logger.warning(f"레코드 파싱 실패: {e}")
            continue

    return parsed


def load_wamis_data(sample_limit: int = None):
    """
    WAMIS 데이터 적재 (인증키 불필요)

    Args:
        sample_limit: 샘플 제한 (테스트용)
    """
    logger = setup_logging("load_wamis")
    logger.info("=" * 60)
    logger.info("WAMIS API ETL 시작 (오픈 API - 키 불필요)")
    logger.info("=" * 60)

    # DB 연결
    conn = get_db_connection()
    logger.info("DB 연결 완료")

    # API 클라이언트
    client = APIClient(logger)

    # 1. 유량 관측소 목록 수집
    logger.info("\n=== 유량 관측소 목록 수집 ===")
    raw_stations = fetch_wamis_stations(client, logger)

    stations_data = []
    if raw_stations:
        stations_data = parse_wamis_stations(raw_stations, logger)
        logger.info(f"유량 관측소: {len(stations_data)}개 파싱 완료")

        if sample_limit:
            stations_data = stations_data[:sample_limit]

    # 2. 용수이용량 수집 (권역별)
    logger.info("\n=== 용수이용량 수집 ===")
    basins = ["1", "2", "3", "4", "5", "6"]  # 한강, 낙동강, 금강, 섬진강, 영산강, 제주도
    basin_names = ["한강", "낙동강", "금강", "섬진강", "영산강", "제주도"]

    water_usage_data = []
    for basin, name in zip(basins, basin_names):
        raw_usage = fetch_wamis_water_usage(client, logger, basin)
        if raw_usage:
            usage_parsed = parse_wamis_water_usage(raw_usage, logger)
            water_usage_data.extend(usage_parsed)
            logger.info(f"  {name}: {len(usage_parsed)}건")

    # DB 적재
    logger.info("\n=== DB 적재 ===")

    # 유량 관측소
    if stations_data:
        success = batch_upsert(
            conn, "api_wamis_stations", stations_data, unique_columns=["obs_code"], batch_size=100
        )
        logger.info(f"api_wamis_stations: {success}건 적재")

    # 용수이용량 (api_wamis 테이블)
    if water_usage_data:
        # api_wamis는 unique 제약이 다름
        cursor = conn.cursor()
        for data in water_usage_data:
            try:
                cursor.execute(
                    """
                    INSERT INTO api_wamis (api_type, api_endpoint, basin, year, output_format, response_data, http_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        data["api_type"],
                        data["api_endpoint"],
                        data["basin"],
                        data["year"],
                        data["output_format"],
                        Json(data["response_data"]),
                        data["http_status"],
                    ),
                )
            except Exception as e:
                logger.warning(f"용수이용량 삽입 실패: {e}")
        conn.commit()
        cursor.close()
        logger.info(f"api_wamis (water_usage): {len(water_usage_data)}건 적재")

    # 결과 확인
    logger.info("\n=== 적재 결과 ===")
    for table in ["api_wamis_stations", "api_wamis"]:
        count = get_table_count(conn, table)
        logger.info(f"  {table}: {count}건")

    conn.close()
    logger.info("\nWAMIS API ETL 완료")


if __name__ == "__main__":
    sample_limit = int(os.getenv("SAMPLE_LIMIT", 0)) or None
    load_wamis_data(sample_limit=sample_limit)
