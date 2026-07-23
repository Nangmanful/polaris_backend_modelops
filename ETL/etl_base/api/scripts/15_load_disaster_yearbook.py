"""
SKALA Physical Risk AI System - 재해연보 API ETL

API: 행정안전부 연도별 자연재해 피해 통계
URL: https://apis.data.go.kr/1741000/NaturalDisasterDamageByYear/getNaturalDisasterDamageByYear
용도: 과거 자연재해 피해 통계 (태풍, 호우, 대설 등)

최종 수정일: 2025-12-03
버전: v01
"""

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# 상위 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    setup_logging,
    get_db_connection,
    get_api_key,
    APIClient,
    batch_upsert,
    get_table_count,
    API_ENDPOINTS,
)


def classify_damage_level(total_damage: float) -> str:
    """
    총 피해액 기준 피해 등급 분류

    Args:
        total_damage: 총 피해액 (억원)

    Returns:
        피해 등급 (경미/보통/심각/대재해)
    """
    if total_damage is None:
        return None
    if total_damage < 100:
        return "경미"
    elif total_damage < 1000:
        return "보통"
    elif total_damage < 5000:
        return "심각"
    else:
        return "대재해"


def get_major_disaster_type(record: dict) -> str:
    """
    최대 피해 유형 결정

    Args:
        record: 연도별 피해 기록

    Returns:
        주요 재해 유형
    """
    damages = {
        "태풍": record.get("typhoon_damage", 0) or 0,
        "호우": record.get("heavy_rain_damage", 0) or 0,
        "대설": record.get("heavy_snow_damage", 0) or 0,
        "강풍": record.get("strong_wind_damage", 0) or 0,
        "풍랑": record.get("wind_wave_damage", 0) or 0,
        "지진": record.get("earthquake_damage", 0) or 0,
    }

    if max(damages.values()) == 0:
        return None

    return max(damages, key=damages.get)


def fetch_disaster_yearbook(
    client: APIClient, api_key: str, logger, page_no: int = 1, num_of_rows: int = 100
):
    """
    재해연보 API 호출

    Args:
        client: API 클라이언트
        api_key: API 키
        logger: 로거
        page_no: 페이지 번호
        num_of_rows: 페이지당 결과 수

    Returns:
        API 응답 데이터 (XML)
    """
    url = API_ENDPOINTS["disaster_yearbook"]
    params = {
        "ServiceKey": api_key,  # 대문자 S
        "pageNo": str(page_no),
        "numOfRows": str(num_of_rows),
    }

    logger.info(f"재해연보 API 호출: 페이지 {page_no}")
    return client.get(url, params=params, timeout=30)


def parse_disaster_yearbook(raw_data: dict, logger) -> list:
    """
    XML 응답 파싱

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

    # raw_text에서 XML 파싱
    raw_text = raw_data.get("raw_text", "")
    if not raw_text:
        logger.warning("응답 텍스트 없음")
        return parsed

    try:
        root = ET.fromstring(raw_text)

        # head 정보 확인
        head = root.find(".//head")
        if head is not None:
            result_msg = head.find(".//RESULT/resultMsg")
            if result_msg is not None:
                if "NOMAL" not in result_msg.text and "SUCCESS" not in result_msg.text.upper():
                    logger.error(f"API 오류: {result_msg.text}")
                    return parsed

        # row 데이터 파싱
        rows = root.findall(".//row")
        logger.info(f"파싱할 row 수: {len(rows)}")

        for row in rows:
            try:
                # 연도 파싱
                year_elem = row.find("wrttimeid")
                if year_elem is None or not year_elem.text:
                    continue

                year = int(year_elem.text)

                # 피해 금액 파싱 (억원)
                def get_float(elem_name):
                    elem = row.find(elem_name)
                    if elem is not None and elem.text:
                        try:
                            return float(elem.text)
                        except:
                            return None
                    return None

                record = {
                    "year": year,
                    "typhoon_damage": get_float("typhoon"),
                    "heavy_rain_damage": get_float("heavy_rain"),
                    "heavy_snow_damage": get_float("heavy_snow"),
                    "strong_wind_damage": get_float("strong_wind"),
                    "wind_wave_damage": get_float("wind_wave"),
                    "earthquake_damage": get_float("earthquake"),
                    "other_damage": get_float("etc"),
                    "total_damage": get_float("tot"),
                    "api_response": raw_data,
                }

                # 피해 등급 및 주요 재해 유형 계산
                record["damage_level"] = classify_damage_level(record["total_damage"])
                record["major_disaster_type"] = get_major_disaster_type(record)

                parsed.append(record)

            except Exception as e:
                logger.warning(f"row 파싱 실패: {e}")
                continue

    except ET.ParseError as e:
        logger.error(f"XML 파싱 실패: {e}")
        return parsed

    return parsed


def load_disaster_yearbook(sample_limit: int = None):
    """
    재해연보 데이터 적재

    Args:
        sample_limit: 샘플 제한 (테스트용)
    """
    logger = setup_logging("load_disaster_yearbook")
    logger.info("=" * 60)
    logger.info("재해연보 API ETL 시작")
    logger.info("=" * 60)

    # API 키 확인
    api_key = get_api_key("PUBLICDATA_API_KEY")
    if not api_key:
        logger.error("PUBLICDATA_API_KEY 환경변수 필요")
        return

    # DB 연결
    conn = get_db_connection()
    logger.info("DB 연결 완료")

    # API 클라이언트
    client = APIClient(logger)

    all_data = []
    page_no = 1
    num_of_rows = 100

    while True:
        raw_data = fetch_disaster_yearbook(client, api_key, logger, page_no, num_of_rows)

        if not raw_data:
            break

        parsed = parse_disaster_yearbook(raw_data, logger)
        if not parsed:
            break

        all_data.extend(parsed)
        logger.info(f"페이지 {page_no}: {len(parsed)}건 파싱")

        # 샘플 제한 확인
        if sample_limit and len(all_data) >= sample_limit:
            all_data = all_data[:sample_limit]
            logger.info(f"샘플 제한 적용: {sample_limit}건")
            break

        if len(parsed) < num_of_rows:
            break

        page_no += 1

    # DB 적재
    if all_data:
        logger.info(f"총 {len(all_data)}건 DB 적재 시작")
        success_count = batch_upsert(
            conn,
            "api_disaster_yearbook",
            all_data,
            unique_columns=[
                "year",
                "admin_code",
                "disaster_type",
            ],  # 스키마 UNIQUE(year, admin_code, disaster_type) 제약조건
            batch_size=50,
        )
        logger.info(f"DB 적재 완료: {success_count}건")

        # 통계 출력
        typhoon_total = sum(d.get("typhoon_damage", 0) or 0 for d in all_data)
        rain_total = sum(d.get("heavy_rain_damage", 0) or 0 for d in all_data)
        total_total = sum(d.get("total_damage", 0) or 0 for d in all_data)

        logger.info(
            f"피해 통계: 태풍 {typhoon_total:.0f}억원, 호우 {rain_total:.0f}억원, 총계 {total_total:.0f}억원"
        )
    else:
        logger.warning("적재할 데이터 없음")

    # 결과 확인
    total_count = get_table_count(conn, "api_disaster_yearbook")
    logger.info(f"api_disaster_yearbook 테이블 총 레코드: {total_count}건")

    conn.close()
    logger.info("재해연보 API ETL 완료")


if __name__ == "__main__":
    sample_limit = int(os.getenv("SAMPLE_LIMIT", 0)) or None
    load_disaster_yearbook(sample_limit=sample_limit)
