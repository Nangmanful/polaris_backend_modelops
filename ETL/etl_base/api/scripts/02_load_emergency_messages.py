"""
SKALA Physical Risk AI System - 긴급재난문자 API ETL

API: 재난안전데이터공유플랫폼 긴급재난문자
URL: https://www.safetydata.go.kr/V2/api/DSSP-IF-00247
용도: 재난 이력 추적 (9종 재난 유형별 발생 이력)

재난 유형 (9종): 강풍, 풍랑, 호우, 대설, 건조, 지진해일, 한파, 태풍, 황사, 폭염
강도: 주의보, 경보 (내용에서 키워드 검색)

최종 수정일: 2025-12-11
버전: v02
"""

import os
import sys
import requests
import urllib3
from pathlib import Path
from datetime import datetime, timedelta

# SSL 경고 비활성화 (재난안전데이터 API 인증서 이슈)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 상위 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    setup_logging,
    get_db_connection,
    get_api_key,
    batch_upsert,
    get_table_count,
    API_ENDPOINTS,
)

# 재난 유형 9종 키워드 (우선순위 순서)
DISASTER_TYPES = {
    "지진해일": ["지진해일", "쓰나미"],
    "태풍": ["태풍"],
    "호우": ["호우", "집중호우", "폭우", "강우", "폭풍우"],
    "대설": ["대설", "폭설", "눈"],
    "강풍": ["강풍", "폭풍"],
    "풍랑": ["풍랑", "파도", "해상"],
    "한파": ["한파", "혹한", "저온"],
    "황사": ["황사", "미세먼지"],
    "건조": ["건조", "화재주의보"],
    "폭염": ["폭염", "고온", "무더위"],
}

# 강도 키워드
SEVERITY_KEYWORDS = {
    "경보": ["경보"],
    "주의보": ["주의보", "주의"],
}


def extract_disaster_type(message_content: str) -> str:
    """
    메시지 내용에서 재난 유형 추출 (9종 중 1개, 우선순위 적용)

    Args:
        message_content: 재난문자 내용

    Returns:
        재난 유형 문자열 또는 None
    """
    if not message_content:
        return None

    # 우선순위 순서로 검색 (지진해일 > 태풍 > 호우 > ...)
    for disaster_type, keywords in DISASTER_TYPES.items():
        for keyword in keywords:
            if keyword in message_content:
                return disaster_type

    return None


def extract_severity(message_content: str) -> str:
    """
    메시지 내용에서 강도 추출 (경보 우선, 주의보 다음)

    Args:
        message_content: 재난문자 내용

    Returns:
        강도 문자열 ('경보' 또는 '주의보') 또는 None
    """
    if not message_content:
        return None

    # 경보 우선 검색
    for keyword in SEVERITY_KEYWORDS["경보"]:
        if keyword in message_content:
            return "경보"

    # 주의보 검색
    for keyword in SEVERITY_KEYWORDS["주의보"]:
        if keyword in message_content:
            return "주의보"

    return None


def fetch_emergency_messages(
    api_key: str,
    logger,
    region: str = None,
    start_date: str = None,
    page_no: int = 1,
    num_of_rows: int = 100,
):
    """
    긴급재난문자 API 호출 (SSL verify=False 필요)

    Args:
        api_key: API 키
        logger: 로거
        region: 지역명 (예: "서울특별시")
        start_date: 조회 시작일 (YYYYMMDD)
        page_no: 페이지 번호
        num_of_rows: 페이지당 결과 수

    Returns:
        API 응답 데이터
    """
    url = API_ENDPOINTS["emergency_messages"]
    params = {
        "serviceKey": api_key,
        "returnType": "json",
        "pageNo": str(page_no),
        "numOfRows": str(num_of_rows),
    }

    if region:
        params["rgnNm"] = region
    if start_date:
        params["crtDt"] = start_date

    logger.info(f"긴급재난문자 API 호출: 페이지 {page_no}, 지역={region or '전체'}")

    try:
        response = requests.get(url, params=params, verify=False, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"API 응답 실패: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"API 요청 오류: {e}")
        return None


def parse_emergency_data(raw_data: dict, logger) -> list:
    """
    API 응답 파싱 (필터링 적용)

    Args:
        raw_data: API 응답
        logger: 로거

    Returns:
        파싱된 데이터 리스트 (필터링 통과한 것만)
    """
    parsed = []

    if not raw_data:
        logger.warning("API 응답 없음")
        return parsed

    # 본문 데이터 추출 (body는 리스트 형태)
    body = raw_data.get("body", [])
    if not body:
        logger.warning("API 응답 body 없음")
        return parsed

    # body가 리스트인지 확인
    if isinstance(body, list):
        items = body
    else:
        items = [body]

    for item in items:
        try:
            # 메시지 내용
            msg_content = item.get("MSG_CN", "")
            if not msg_content:
                continue

            # 재난 유형 추출 (9종 중 1개)
            disaster_type = extract_disaster_type(msg_content)
            if not disaster_type:
                # 재난 유형을 찾을 수 없으면 스킵
                continue

            # 강도 추출 (주의보/경보)
            severity = extract_severity(msg_content)
            if not severity:
                # 강도를 찾을 수 없으면 스킵
                continue

            # 발령 일자 파싱 (YYYY-MM-DD만, 시간 제거)
            crt_dt_str = item.get("CRT_DT", "")
            alert_date = None
            if crt_dt_str:
                try:
                    # API 응답 형식: YYYY/MM/DD HH:MM:SS 또는 YYYYMMDDHHMMSS
                    if "/" in crt_dt_str:
                        # YYYY/MM/DD HH:MM:SS -> YYYY-MM-DD
                        alert_date = datetime.strptime(crt_dt_str.split()[0], "%Y/%m/%d").date()
                    else:
                        # YYYYMMDDHHMMSS -> YYYY-MM-DD
                        alert_date = datetime.strptime(crt_dt_str[:8], "%Y%m%d").date()
                except Exception as e:
                    logger.warning(f"날짜 파싱 실패: {crt_dt_str} - {e}")
                    continue
            else:
                continue

            # 지역명
            region = item.get("RCPTN_RGN_NM", "") or item.get("RGN_NM", "")
            if not region:
                continue

            record = {
                "alert_date": alert_date,
                "disaster_type": disaster_type,
                "severity": severity,
                "region": region,
            }

            parsed.append(record)

        except Exception as e:
            logger.warning(f"레코드 파싱 실패: {e}")
            continue

    return parsed


def load_emergency_messages(sample_limit: int = None, years: int = 5):
    """
    긴급재난문자 데이터 적재

    Args:
        sample_limit: 샘플 제한 (테스트용)
        years: 조회 기간 (년)
    """
    logger = setup_logging("load_emergency_messages")
    logger.info("=" * 60)
    logger.info("긴급재난문자 API ETL 시작 (v02)")
    logger.info("=" * 60)

    # API 키 확인
    api_key = get_api_key("EMERGENCYMESSAGE_API_KEY")
    if not api_key:
        logger.error("EMERGENCYMESSAGE_API_KEY 환경변수 필요")
        return

    # DB 연결
    conn = get_db_connection()
    logger.info("DB 연결 완료")

    # 조회 시작일 (N년 전)
    start_date = (datetime.now() - timedelta(days=365 * years)).strftime("%Y%m%d")
    logger.info(f"조회 기간: {start_date} ~ 현재")
    logger.info(f"재난 유형: {', '.join(DISASTER_TYPES.keys())}")
    logger.info(f"강도 필터: {', '.join(SEVERITY_KEYWORDS.keys())}")

    # 주요 지역별 수집
    regions = [
        "서울특별시",
        "부산광역시",
        "대구광역시",
        "인천광역시",
        "광주광역시",
        "대전광역시",
        "울산광역시",
        "세종특별자치시",
        "경기도",
        "강원특별자치도",
        "충청북도",
        "충청남도",
        "전북특별자치도",
        "전라남도",
        "경상북도",
        "경상남도",
        "제주특별자치도",
    ]

    all_data = []
    total_fetched = 0
    total_filtered = 0
    api_call_count = 0

    # SAMPLE_LIMIT가 있으면 API 호출 횟수 제한
    max_api_calls = None
    if sample_limit:
        max_api_calls = 20
        logger.info(f"샘플 모드: 최대 {max_api_calls}회 API 호출 제한")

    for region in regions:
        page_no = 1
        num_of_rows = 1000  # API 최대 허용
        region_count = 0
        region_filtered = 0

        while True:
            # API 호출 제한 체크
            if max_api_calls and api_call_count >= max_api_calls:
                logger.info(f"API 호출 제한 도달: {api_call_count}회")
                break

            raw_data = fetch_emergency_messages(
                api_key,
                logger,
                region=region,
                start_date=start_date,
                page_no=page_no,
                num_of_rows=num_of_rows,
            )
            api_call_count += 1

            if not raw_data:
                break

            # 파싱 전 데이터 개수
            body = raw_data.get("body", [])
            if isinstance(body, list):
                fetched = len(body)
            elif body:
                fetched = 1
            else:
                fetched = 0

            total_fetched += fetched

            # 파싱 및 필터링
            parsed = parse_emergency_data(raw_data, logger)
            if not parsed:
                logger.info(f"  {region} 페이지 {page_no}: {fetched}건 조회 → 0건 필터링 통과")
                if fetched < num_of_rows:
                    break
                page_no += 1
                continue

            filtered_count = len(parsed)
            total_filtered += filtered_count

            all_data.extend(parsed)
            region_count += filtered_count
            region_filtered += filtered_count

            logger.info(
                f"  {region} 페이지 {page_no}: {fetched}건 조회 → {filtered_count}건 필터링 통과"
            )

            # 샘플 제한 확인
            if sample_limit and len(all_data) >= sample_limit:
                all_data = all_data[:sample_limit]
                logger.info(f"샘플 제한 적용: {sample_limit}건")
                break

            if fetched < num_of_rows:
                break

            page_no += 1

        logger.info(f"{region}: 총 {region_filtered}건 필터링 통과")

        # API 호출 또는 샘플 제한 도달 시 종료
        if max_api_calls and api_call_count >= max_api_calls:
            break
        if sample_limit and len(all_data) >= sample_limit:
            break

    # DB 적재
    if all_data:
        logger.info(f"\n총 API 호출: {api_call_count}회")
        logger.info(f"총 조회: {total_fetched}건")
        logger.info(f"필터링 통과: {total_filtered}건")
        logger.info(f"DB 적재 시작: {len(all_data)}건")

        success_count = batch_upsert(
            conn,
            "api_emergency_messages",
            all_data,
            unique_columns=["alert_date", "disaster_type", "severity", "region"],
            batch_size=100,
        )
        logger.info(f"DB 적재 완료: {success_count}건")

        # 재난 유형별 통계
        type_stats = {}
        for d in all_data:
            dtype = d.get("disaster_type")
            type_stats[dtype] = type_stats.get(dtype, 0) + 1

        logger.info("\n재난 유형별 통계:")
        for dtype, count in sorted(type_stats.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  {dtype}: {count}건")

        # 강도별 통계
        severity_stats = {}
        for d in all_data:
            sev = d.get("severity")
            severity_stats[sev] = severity_stats.get(sev, 0) + 1

        logger.info("\n강도별 통계:")
        for sev, count in severity_stats.items():
            logger.info(f"  {sev}: {count}건")

    else:
        logger.warning("적재할 데이터 없음")

    # 결과 확인
    total_count = get_table_count(conn, "api_emergency_messages")
    logger.info(f"\napi_emergency_messages 테이블 총 레코드: {total_count}건")

    conn.close()
    logger.info("\n긴급재난문자 API ETL 완료")


if __name__ == "__main__":
    sample_limit = int(os.getenv("SAMPLE_LIMIT", 0)) or None
    load_emergency_messages(sample_limit=sample_limit)
