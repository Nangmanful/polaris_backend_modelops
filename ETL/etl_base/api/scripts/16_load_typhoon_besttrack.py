"""
SKALA Physical Risk AI System - 태풍 베스트트랙 API ETL

API: 기상청 API허브 태풍 베스트트랙
URL: https://apihub.kma.go.kr/api/typ01/url/typ_besttrack.php
용도: AAL 분석용 과거 태풍 정밀 재분석 데이터 (2015~2022)

최종 수정일: 2025-12-03
버전: v01
"""

import os
import sys
import requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    setup_logging,
    get_db_connection,
    get_api_key,
    batch_upsert,
    get_table_count,
    API_ENDPOINTS,
)


def fetch_besttrack_data(api_key: str, year: int, logger) -> list:
    """
    특정 연도의 베스트트랙 데이터 조회

    Args:
        api_key: API 키
        year: 조회 연도
        logger: 로거

    Returns:
        파싱된 데이터 리스트
    """
    url = API_ENDPOINTS.get(
        "typhoon_besttrack", "https://apihub.kma.go.kr/api/typ01/url/typ_besttrack.php"
    )

    params = {"year": year, "authKey": api_key, "help": 0}  # 값만 표시

    try:
        response = requests.get(url, params=params, timeout=60)

        if response.status_code == 200:
            return parse_besttrack_response(response.text, logger)
        else:
            logger.warning(f"[{year}] API 응답 실패: {response.status_code}")
            return []

    except Exception as e:
        logger.error(f"[{year}] API 요청 오류: {e}")
        return []


def parse_besttrack_response(text: str, logger) -> list:
    """
    베스트트랙 API 응답 파싱

    형식: GRADE TCID YEAR MONTH DAY HOUR LON LAT MAX_WS PS GALE_LONG GALE_SHORT GALE_DIR STORM_LONG STORM_SHORT STORM_DIR NAME
    """
    parsed = []

    def safe_float(val):
        try:
            v = val.strip()
            if v in ["-", "-999", "-999.9", ""]:
                return None
            return float(v)
        except:
            return None

    def safe_int(val):
        try:
            v = val.strip()
            if v in ["-", ""]:
                return None
            return int(float(v))
        except:
            return None

    for line in text.split("\n"):
        line = line.strip()

        # 주석/빈줄/마커 건너뛰기
        if not line or line.startswith("#"):
            continue

        # 공백 기준 분리
        parts = line.split()

        if len(parts) < 10:
            continue

        try:
            grade = parts[0] if parts[0] not in ["-", ""] else None
            tcid = parts[1]
            year = safe_int(parts[2])
            month = safe_int(parts[3])
            day = safe_int(parts[4])
            hour = safe_int(parts[5])

            obs_datetime = None
            if year and month and day and hour is not None:
                try:
                    obs_datetime = datetime(year, month, day, hour)
                except:
                    pass

            lon = safe_float(parts[6])
            lat = safe_float(parts[7])
            max_wind_speed = safe_float(parts[8])
            central_pressure = safe_float(parts[9])

            gale_long = safe_float(parts[10]) if len(parts) > 10 else None
            gale_short = safe_float(parts[11]) if len(parts) > 11 else None
            gale_dir = parts[12] if len(parts) > 12 and parts[12] not in ["-", "-999.9"] else None
            storm_long = safe_float(parts[13]) if len(parts) > 13 else None
            storm_short = safe_float(parts[14]) if len(parts) > 14 else None
            storm_dir = parts[15] if len(parts) > 15 and parts[15] not in ["-", "-999.9"] else None
            typhoon_name = parts[16] if len(parts) > 16 else None

            # 필터링: -999 값 정리
            if gale_long == -999:
                gale_long = None
            if gale_short == -999:
                gale_short = None
            if storm_long == -999:
                storm_long = None
            if storm_short == -999:
                storm_short = None

            record = {
                "grade": grade,
                "tcid": tcid,
                "year": year,
                "month": month,
                "day": day,
                "hour": hour,
                "obs_datetime": obs_datetime,
                "lon": lon,
                "lat": lat,
                "max_wind_speed": max_wind_speed,
                "central_pressure": central_pressure,
                "gale_long": gale_long,
                "gale_short": gale_short,
                "gale_dir": gale_dir,
                "storm_long": storm_long,
                "storm_short": storm_short,
                "storm_dir": storm_dir,
                "typhoon_name": typhoon_name,
            }

            if tcid and year:
                parsed.append(record)

        except Exception as e:
            continue

    return parsed


def load_typhoon_besttrack(sample_limit: int = None):
    """
    태풍 베스트트랙 데이터 적재 (2015~2022)
    """
    logger = setup_logging("load_typhoon_besttrack")
    logger.info("=" * 60)
    logger.info("태풍 베스트트랙 API ETL 시작")
    logger.info("=" * 60)

    api_key = get_api_key("TYPHOON_API_KEY")
    if not api_key:
        logger.error("TYPHOON_API_KEY 환경변수 필요")
        return

    conn = get_db_connection()
    logger.info("DB 연결 완료")

    all_data = []

    # 2015~2022년 데이터 수집 (베스트트랙 보유기간)
    for year in range(2015, 2023):
        logger.info(f"[{year}년] 데이터 조회...")
        data = fetch_besttrack_data(api_key, year, logger)

        if data:
            all_data.extend(data)
            logger.info(f"  -> {len(data)}건 수집")
        else:
            logger.warning(f"  -> 데이터 없음")

    logger.info(f"총 {len(all_data)}건 수집 완료")

    # 샘플 제한
    if sample_limit and len(all_data) > sample_limit:
        all_data = all_data[:sample_limit]
        logger.info(f"샘플 제한 적용: {sample_limit}건")

    # DB 적재
    if all_data:
        logger.info(f"DB 적재 시작...")
        success_count = batch_upsert(
            conn,
            "api_typhoon_besttrack",
            all_data,
            unique_columns=["tcid", "year", "month", "day", "hour"],
            batch_size=100,
        )
        logger.info(f"DB 적재 완료: {success_count}건")

        # 통계
        grades = {}
        for d in all_data:
            g = d.get("grade", "UNKNOWN")
            grades[g] = grades.get(g, 0) + 1
        logger.info(f"등급별: {grades}")

        # 태풍별 통계
        typhoons = set(d.get("typhoon_name") for d in all_data if d.get("typhoon_name"))
        logger.info(f"총 태풍 수: {len(typhoons)}개")
    else:
        logger.warning("적재할 데이터 없음")

    total_count = get_table_count(conn, "api_typhoon_besttrack")
    logger.info(f"api_typhoon_besttrack 테이블 총 레코드: {total_count}건")

    conn.close()
    logger.info("태풍 베스트트랙 API ETL 완료")


if __name__ == "__main__":
    sample_limit = int(os.getenv("SAMPLE_LIMIT", 0)) or None
    load_typhoon_besttrack(sample_limit=sample_limit)
