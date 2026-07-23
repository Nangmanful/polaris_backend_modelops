"""
SKALA Physical Risk AI System - 태풍 정보 API ETL

API: 기상청 API 허브 태풍정보
URL: https://apihub.kma.go.kr/api/typ01/
용도: 태풍 위험 평가 (경로 추적, 강도 분석, 영향 지역)

최종 수정일: 2025-12-03
버전: v01
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# 상위 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    setup_logging,
    get_db_connection,
    get_api_key,
    APIClient,
    batch_upsert,
    get_table_count,
)

# 태풍 등급 분류 기준 (최대풍속 m/s)
TYPHOON_GRADES = {
    "TD": (0, 17.1),  # 열대저압부
    "TS": (17.2, 24.4),  # 열대폭풍
    "STS": (24.5, 32.6),  # 강한 열대폭풍
    "TY": (32.7, 999),  # 태풍
}


def classify_typhoon_grade(wind_speed_ms: float) -> str:
    """
    풍속 기준 태풍 등급 분류

    Args:
        wind_speed_ms: 최대풍속 (m/s)

    Returns:
        등급 (TD, TS, STS, TY)
    """
    for grade, (min_ws, max_ws) in TYPHOON_GRADES.items():
        if min_ws <= wind_speed_ms < max_ws:
            return grade
    return "TY" if wind_speed_ms >= 32.7 else "TD"


def fetch_typhoon_list(client: APIClient, api_key: str, logger, year: int = None):
    """
    태풍 목록 API 호출

    Args:
        client: API 클라이언트
        api_key: API 키
        logger: 로거
        year: 연도 (없으면 현재 연도)

    Returns:
        API 응답 데이터
    """
    if year is None:
        year = datetime.now().year

    url = "https://apihub.kma.go.kr/api/typ01/url/typ_lst.php"
    params = {"authKey": api_key, "yy": str(year), "disp": "1", "help": "0"}  # 콤마 구분

    logger.info(f"태풍 목록 API 호출: {year}년")
    return client.get(url, params=params, timeout=30)


def fetch_typhoon_data(client: APIClient, api_key: str, logger, year: int, typ: int, mode: int = 0):
    """
    태풍 상세정보 API 호출

    Args:
        client: API 클라이언트
        api_key: API 키
        logger: 로거
        year: 연도
        typ: 태풍 번호
        mode: 표출범위 (0:분석만, 1:분석+최신예측, 2:최신분석+예측, 3:전체)

    Returns:
        API 응답 데이터
    """
    # typ_inf.php (X) -> typ_data.php (O) 수정됨
    url = "https://apihub.kma.go.kr/api/typ01/url/typ_data.php"
    params = {
        "authKey": api_key,
        "YY": str(year),  # 대문자 YY 사용
        "typ": str(typ),
        "mode": str(mode),
        "disp": "1",
        "help": "0",
    }

    logger.info(f"태풍 상세 API 호출: {year}년 {typ}호")
    return client.get(url, params=params, timeout=30)


def fetch_affected_typhoons(client: APIClient, api_key: str, logger, year: int = None):
    """
    한반도 영향 태풍 API 호출

    Args:
        client: API 클라이언트
        api_key: API 키
        logger: 로거
        year: 연도

    Returns:
        API 응답 데이터
    """
    if year is None:
        year = datetime.now().year

    url = "https://apis.data.go.kr/1360000/TyphoonInfoService/getTyphoonInfo"
    params = {
        "serviceKey": api_key,
        "numOfRows": "1000",  # API 최대 허용
        "pageNo": "1",
        "dataType": "JSON",
        "year": str(year),
    }

    logger.info(f"한반도 영향 태풍 API 호출: {year}년")
    return client.get(url, params=params, timeout=30)


def parse_typhoon_list(raw_text: str, year: int, logger) -> list:
    """
    태풍 목록 파싱 (CSV 형식)

    Args:
        raw_text: API 응답 텍스트
        year: 연도
        logger: 로거

    Returns:
        태풍 기본정보 리스트
    """
    parsed = []

    if not raw_text:
        return parsed

    lines = raw_text.strip().split("\n")

    for line in lines:
        if line.startswith("#") or not line.strip():
            continue

        try:
            parts = line.split(",")
            if len(parts) < 8:
                continue

            # YY, SEQ, NOW, EFF, TM_ST, TM_ED, TYP_NAME, TYP_EN
            record = {
                "year": int(parts[0].strip()) if parts[0].strip().isdigit() else year,
                "typ_seq": int(parts[1].strip()) if parts[1].strip().isdigit() else 0,
                "now_status": parts[2].strip() == "1",
                "eff_korea": parts[3].strip() == "1",
                "typ_name": parts[6].strip() if len(parts) > 6 else "",
                "typ_en": parts[7].strip() if len(parts) > 7 else "",
            }

            # 시각 파싱
            if len(parts) > 4 and parts[4].strip():
                try:
                    record["tm_st"] = datetime.strptime(parts[4].strip(), "%Y%m%d%H%M")
                except:
                    record["tm_st"] = None

            if len(parts) > 5 and parts[5].strip():
                try:
                    record["tm_ed"] = datetime.strptime(parts[5].strip(), "%Y%m%d%H%M")
                except:
                    record["tm_ed"] = None

            if record["typ_seq"] > 0:
                parsed.append(record)

        except Exception as e:
            logger.warning(f"태풍 목록 파싱 실패: {e}")
            continue

    return parsed


def parse_typhoon_track(raw_text: str, year: int, typ_seq: int, logger) -> list:
    """
    태풍 경로 파싱 (CSV 형식)

    Args:
        raw_text: API 응답 텍스트
        year: 연도
        typ_seq: 태풍 번호
        logger: 로거

    Returns:
        태풍 경로 리스트
    """
    parsed = []

    if not raw_text:
        return parsed

    lines = raw_text.strip().split("\n")

    for line in lines:
        if line.startswith("#") or not line.strip():
            continue

        try:
            parts = line.split(",")
            if len(parts) < 15:
                continue

            # FT, YY, TYP, SEQ, TMD, TYP_TM, FT_TM, LAT, LON, DIR, SP, PS, WS, RAD15, RAD25, ...
            wind_speed = float(parts[12].strip()) if parts[12].strip() else 0

            record = {
                "year": year,
                "typ_seq": typ_seq,
                "ft_type": int(parts[0].strip()) if parts[0].strip().isdigit() else 0,
                "seq": int(parts[3].strip()) if parts[3].strip().isdigit() else 0,
                "tmd": int(parts[4].strip()) if parts[4].strip().isdigit() else 0,
                "latitude": float(parts[7].strip()) if parts[7].strip() else None,
                "longitude": float(parts[8].strip()) if parts[8].strip() else None,
                "direction": parts[9].strip() if len(parts) > 9 else "",
                "speed_kmh": float(parts[10].strip()) if parts[10].strip() else None,
                "pressure_hpa": int(float(parts[11].strip())) if parts[11].strip() else None,
                "wind_speed_ms": wind_speed,
                "rad15_km": float(parts[13].strip()) if parts[13].strip() else None,
                "rad25_km": float(parts[14].strip()) if parts[14].strip() else None,
                "grade": classify_typhoon_grade(wind_speed),
            }

            # 시각 파싱
            if len(parts) > 5 and parts[5].strip():
                try:
                    record["typ_tm"] = datetime.strptime(parts[5].strip(), "%Y%m%d%H%M")
                except:
                    record["typ_tm"] = None

            if len(parts) > 6 and parts[6].strip():
                try:
                    record["ft_tm"] = datetime.strptime(parts[6].strip(), "%Y%m%d%H%M")
                except:
                    record["ft_tm"] = None

            parsed.append(record)

        except Exception as e:
            logger.warning(f"태풍 경로 파싱 실패: {e}")
            continue

    return parsed


def parse_affected_typhoons(raw_data: dict, logger) -> list:
    """
    한반도 영향 태풍 파싱

    Args:
        raw_data: API 응답
        logger: 로거

    Returns:
        영향 태풍 리스트
    """
    parsed = []

    if not raw_data:
        return parsed

    response = raw_data.get("response", {})
    body = response.get("body", {})
    items = body.get("items", {}).get("item", [])

    if isinstance(items, dict):
        items = [items]

    for item in items:
        try:
            record = {
                "year": int(item.get("year", 0)),
                "typ_seq": int(item.get("typ_seq", 0)),
                "typ_name": item.get("typ_name", ""),
                "typ_en": item.get("typ_en", ""),
                "min_pressure": int(item.get("typ_ps", 0)) if item.get("typ_ps") else None,
                "max_wind_speed": float(item.get("typ_ws", 0)) if item.get("typ_ws") else None,
                "eff": item.get("eff", ""),
                "api_response": item,
            }

            # 날짜 파싱
            tm_st = item.get("tm_st", "")
            tm_ed = item.get("tm_ed", "")

            try:
                record["tm_st"] = datetime.strptime(tm_st, "%Y%m%d").date() if tm_st else None
            except:
                record["tm_st"] = None

            try:
                record["tm_ed"] = datetime.strptime(tm_ed, "%Y%m%d").date() if tm_ed else None
            except:
                record["tm_ed"] = None

            if record["year"] > 0 and record["typ_seq"] > 0:
                parsed.append(record)

        except Exception as e:
            logger.warning(f"영향 태풍 파싱 실패: {e}")
            continue

    return parsed


def fetch_td_list(client: APIClient, api_key: str, logger, year: int = None):
    """
    TD(열대저압부) 목록 API 호출

    Args:
        client: API 클라이언트
        api_key: API 키
        logger: 로거
        year: 연도 (없으면 현재 연도)

    Returns:
        API 응답 데이터
    """
    if year is None:
        year = datetime.now().year

    url = "https://apihub.kma.go.kr/api/typ01/url/td_lst.php"
    params = {"authKey": api_key, "YY": str(year), "disp": "1", "help": "0"}

    logger.info(f"TD 목록 API 호출: {year}년")
    return client.get(url, params=params, timeout=30)


def parse_td_list(raw_text: str, year: int, logger) -> list:
    """
    TD 목록 파싱 (CSV 형식)

    Args:
        raw_text: API 응답 텍스트
        year: 연도
        logger: 로거

    Returns:
        TD 기본정보 리스트
    """
    parsed = []

    if not raw_text:
        return parsed

    lines = raw_text.strip().split("\n")

    for line in lines:
        if line.startswith("#") or not line.strip():
            continue

        try:
            parts = line.split(",")
            if len(parts) < 6:
                continue

            # YY, TD, TYP, TM_ST, TM_ED, REM
            record = {
                "year": int(parts[0].strip()) if parts[0].strip().isdigit() else year,
                "td_num": int(parts[1].strip()) if parts[1].strip().isdigit() else 0,
                "typhoon_typ_seq": int(parts[2].strip()) if parts[2].strip().isdigit() else None,
            }

            # 연결 태풍 번호가 있으면 태풍으로 발달
            record["upgraded_to_typhoon"] = (
                record["typhoon_typ_seq"] is not None and record["typhoon_typ_seq"] > 0
            )

            # 시각 파싱
            if len(parts) > 3 and parts[3].strip():
                try:
                    record["tm_st"] = datetime.strptime(parts[3].strip(), "%Y%m%d%H%M")
                except:
                    record["tm_st"] = None

            if len(parts) > 4 and parts[4].strip():
                try:
                    record["tm_ed"] = datetime.strptime(parts[4].strip(), "%Y%m%d%H%M")
                except:
                    record["tm_ed"] = None

            if record["td_num"] > 0:
                parsed.append(record)

        except Exception as e:
            logger.warning(f"TD 목록 파싱 실패: {e}")
            continue

    return parsed


def load_typhoon_data(sample_limit: int = None, years_back: int = 5):
    """
    태풍 데이터 적재

    Args:
        sample_limit: 샘플 제한 (테스트용)
        years_back: 과거 몇 년치 데이터 수집
    """
    logger = setup_logging("load_typhoon")
    logger.info("=" * 60)
    logger.info("태풍 정보 API ETL 시작")
    logger.info("=" * 60)

    # API 키 확인
    typhoon_api_key = get_api_key("TYPHOON_API_KEY")
    kma_api_key = get_api_key("KMALARGE_API_KEY")  # 기상청 대용량 API
    data_api_key = get_api_key("PUBLICDATA_API_KEY")

    if not typhoon_api_key and not kma_api_key and not data_api_key:
        logger.error("TYPHOON_API_KEY 또는 KMALARGE_API_KEY 환경변수 필요")
        return

    # 태풍 API 키 우선 사용
    kma_api_key = typhoon_api_key or kma_api_key

    # DB 연결
    conn = get_db_connection()
    logger.info("DB 연결 완료")

    # API 클라이언트
    client = APIClient(logger)

    current_year = datetime.now().year
    all_info = []
    all_track = []
    all_affected = []
    all_td = []  # TD (열대저압부) 데이터

    # 연도별 수집
    for year in range(current_year, current_year - years_back, -1):
        logger.info(f"\n=== {year}년 태풍 데이터 수집 ===")

        # 1. 태풍 목록 조회
        if kma_api_key:
            raw_list = fetch_typhoon_list(client, kma_api_key, logger, year)
            if raw_list and "raw_text" in raw_list:
                typhoon_list = parse_typhoon_list(raw_list["raw_text"], year, logger)
                logger.info(f"  태풍 목록: {len(typhoon_list)}개")

                for typhoon in typhoon_list:
                    typhoon["api_response"] = raw_list
                    all_info.append(typhoon)

                    # 2. 태풍별 상세 경로 조회
                    raw_track = fetch_typhoon_data(
                        client, kma_api_key, logger, year, typhoon["typ_seq"]
                    )
                    if raw_track and "raw_text" in raw_track:
                        tracks = parse_typhoon_track(
                            raw_track["raw_text"], year, typhoon["typ_seq"], logger
                        )
                        for track in tracks:
                            track["api_response"] = raw_track
                        all_track.extend(tracks)
                        logger.info(f"    {typhoon['typ_name']}: {len(tracks)}개 경로점")

            # 3. TD (열대저압부) 목록 조회
            raw_td = fetch_td_list(client, kma_api_key, logger, year)
            if raw_td and "raw_text" in raw_td:
                td_list = parse_td_list(raw_td["raw_text"], year, logger)
                for td in td_list:
                    td["api_response"] = raw_td
                all_td.extend(td_list)
                logger.info(f"  TD 목록: {len(td_list)}개")

        # 4. 한반도 영향 태풍 조회
        if data_api_key:
            raw_affected = fetch_affected_typhoons(client, data_api_key, logger, year)
            if raw_affected:
                affected = parse_affected_typhoons(raw_affected, logger)
                all_affected.extend(affected)
                logger.info(f"  한반도 영향 태풍: {len(affected)}개")

        # 샘플 제한
        if sample_limit:
            if len(all_info) >= sample_limit:
                break

    # DB 적재
    logger.info("\n=== DB 적재 시작 ===")

    # 태풍 기본정보
    if all_info:
        success = batch_upsert(
            conn, "api_typhoon_info", all_info, unique_columns=["year", "typ_seq"], batch_size=50
        )
        logger.info(f"api_typhoon_info: {success}건 적재")

    # 태풍 경로
    if all_track:
        success = batch_upsert(
            conn,
            "api_typhoon_track",
            all_track,
            unique_columns=["year", "typ_seq", "seq", "ft_type", "tmd"],
            batch_size=100,
        )
        logger.info(f"api_typhoon_track: {success}건 적재")

    # TD (열대저압부)
    if all_td:
        success = batch_upsert(
            conn, "api_typhoon_td", all_td, unique_columns=["year", "td_num"], batch_size=50
        )
        logger.info(f"api_typhoon_td: {success}건 적재")

    # 결과 확인
    logger.info("\n=== 적재 결과 ===")
    for table in ["api_typhoon_info", "api_typhoon_track", "api_typhoon_td"]:
        count = get_table_count(conn, table)
        logger.info(f"  {table}: {count}건")

    conn.close()
    logger.info("\n태풍 정보 API ETL 완료")


if __name__ == "__main__":
    sample_limit = int(os.getenv("SAMPLE_LIMIT", 0)) or None
    load_typhoon_data(sample_limit=sample_limit)
