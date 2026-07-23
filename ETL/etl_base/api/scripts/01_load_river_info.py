"""
SKALA Physical Risk AI System - 하천정보 API ETL

API: 재난안전데이터공유플랫폼 하천정보
URL: https://www.safetydata.go.kr/V2/api/DSSP-IF-10720
용도: 홍수 위험 평가를 위한 하천 정보

최종 수정일: 2025-12-13
버전: v02 - 추가 필드 + VWorld 지오코딩으로 geometry 생성
"""

import os
import sys
import time
import requests
from pathlib import Path

# 상위 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    setup_logging,
    get_db_connection,
    get_api_key,
    APIClient,
    get_table_count,
    API_ENDPOINTS,
)


def geocode_address(api_key: str, address: str, logger) -> dict:
    """
    VWorld 순방향 지오코딩 API (주소 → 좌표)
    행정구역명의 경우 시군구청을 검색하여 대표 좌표 획득

    Args:
        api_key: VWorld API 키
        address: 검색할 주소
        logger: 로거

    Returns:
        {'lat': float, 'lon': float} 또는 None
    """
    if not address or not address.strip():
        return None

    url = "https://api.vworld.kr/req/search"

    # 먼저 type=place로 시군구청 검색 시도
    # 주소에서 시군구 추출하여 "XX시청" 또는 "XX군청" 형태로 검색
    search_queries = []

    # 원본 주소도 시도
    search_queries.append(("address", address))

    # 시군구청 검색 쿼리 생성
    parts = address.replace("/", " ").split()
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # "시", "군", "구"로 끝나면 청사 검색
        if part.endswith("시"):
            search_queries.insert(0, ("place", f"{part}청"))
        elif part.endswith("군"):
            search_queries.insert(0, ("place", f"{part}청"))
        elif part.endswith("구"):
            # 구는 상위 시가 필요하므로 전체 주소로 검색
            search_queries.insert(0, ("place", f"{part}청"))

    for search_type, query in search_queries:
        try:
            params = {
                "service": "search",
                "request": "search",
                "version": "2.0",
                "crs": "EPSG:4326",
                "query": query,
                "type": search_type,
                "format": "json",
                "key": api_key,
            }

            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if data.get("response", {}).get("status") != "OK":
                continue

            items = data.get("response", {}).get("result", {}).get("items", [])
            if not items:
                continue

            # 첫 번째 결과 사용
            point = items[0].get("point", {})
            x = point.get("x")  # 경도
            y = point.get("y")  # 위도

            if x and y:
                return {"lat": float(y), "lon": float(x)}

        except Exception as e:
            continue

    logger.debug(f"지오코딩 실패: {address}")
    return None


def build_address_for_geocoding(sido: str, sigungu: str, emd: str) -> str:
    """
    시도/시군구/읍면동 정보로 지오코딩용 주소 생성
    시군구 약어를 정식 명칭으로 변환

    Args:
        sido: 시도명
        sigungu: 시군구명
        emd: 읍면동명

    Returns:
        검색용 주소 문자열
    """
    # 시도 약어 → 정식 명칭
    sido_map = {
        "서울": "서울특별시",
        "부산": "부산광역시",
        "대구": "대구광역시",
        "인천": "인천광역시",
        "광주": "광주광역시",
        "대전": "대전광역시",
        "울산": "울산광역시",
        "세종": "세종특별자치시",
        "경기": "경기도",
        "강원": "강원도",
        "충북": "충청북도",
        "충남": "충청남도",
        "전북": "전라북도",
        "전남": "전라남도",
        "경북": "경상북도",
        "경남": "경상남도",
        "제주": "제주특별자치도",
    }

    parts = []

    # 시도 처리
    if sido and sido.strip():
        sido = sido.strip()
        parts.append(sido_map.get(sido, sido))

    # 시군구 처리 - 접미사가 없으면 일반적인 패턴 추론
    if sigungu and sigungu.strip():
        sg = sigungu.strip()
        if not (sg.endswith("시") or sg.endswith("군") or sg.endswith("구")):
            # 접미사 추가 시도 (주로 군 지역이 많음)
            sg = f"{sg}군"
        parts.append(sg)

    # 읍면동은 포함하지 않음 (너무 구체적이면 검색 실패율 높음)
    # if emd and emd.strip():
    #     parts.append(emd.strip())

    return " ".join(parts) if parts else None


def fetch_river_info(
    client: APIClient, api_key: str, logger, page_no: int = 1, num_of_rows: int = 100
):
    """
    하천정보 API 호출

    Args:
        client: API 클라이언트
        api_key: API 키
        logger: 로거
        page_no: 페이지 번호
        num_of_rows: 페이지당 결과 수

    Returns:
        API 응답 데이터
    """
    url = API_ENDPOINTS["river_info"]
    params = {
        "serviceKey": api_key,
        "returnType": "json",
        "pageNo": str(page_no),
        "numOfRows": str(num_of_rows),
    }

    logger.info(f"하천정보 API 호출: 페이지 {page_no}")
    return client.get(url, params=params, timeout=30)


def parse_river_data(raw_data: dict, logger, vworld_api_key: str = None) -> list:
    """
    API 응답 파싱 + 지오코딩

    Args:
        raw_data: API 응답
        logger: 로거
        vworld_api_key: VWorld API 키 (지오코딩용)

    Returns:
        파싱된 데이터 리스트
    """
    parsed = []

    if not raw_data:
        logger.warning("API 응답 없음")
        return parsed

    # 헤더 확인
    header = raw_data.get("header", {})
    if header.get("resultCode") != "00":
        logger.error(f"API 오류: {header.get('resultMsg')}")
        return parsed

    # 본문 데이터 추출
    body = raw_data.get("body", [])
    if not body:
        logger.warning("API 응답 body 없음")
        return parsed

    geocode_success = 0
    geocode_fail = 0

    for item in body:
        try:
            # 기존 필드
            record = {
                "river_code": item.get("RVR_CD", ""),
                "river_name": item.get("RVR_NM", ""),
                "river_grade": int(item.get("RVR_GRD_CD", 0) or 0),
                "watershed_area_km2": float(item.get("DRAR", 0) or 0),
                "river_length_km": float(item.get("RVR_PRLG_LEN", 0) or 0),
                "start_point": item.get("ORG_PT", ""),
                "end_point": item.get("CNFLS_PT", ""),
                "management_org": item.get("MGMT_ORG", ""),
                "basin_name": item.get("WTRSHD_NM", ""),
                "sido_name": item.get("CTPV_NM", ""),
                "sigungu_name": item.get("SGG_NM", ""),
                # 추가 필드 (v02)
                "start_sido": item.get("RVR_CAPO_VL_1", ""),
                "start_sigungu": item.get("RVR_CAPO_VL_2", ""),
                "start_emd": item.get("RVR_CAPO_VL_3", ""),
                "end_sido": item.get("RVR_FNLST_NM_1", ""),
                "end_sigungu": item.get("RVR_FNLST_NM_2", ""),
                "end_emd": item.get("RVR_FNLST_NM_3", ""),
                "flood_capacity": float(item.get("FLOD_CPC", 0) or 0),
                "main_river": item.get("MAST", ""),
                "watershed_code": item.get("WASY_CD", ""),
                # 좌표 (초기값)
                "start_lat": None,
                "start_lon": None,
                "end_lat": None,
                "end_lon": None,
                "api_response": item,
            }

            # river_code가 없으면 river_name + grade로 생성
            if not record["river_code"]:
                record["river_code"] = f"{record['river_name']}_{record['river_grade']}"

            # 지오코딩 (VWorld API 키가 있는 경우만)
            if vworld_api_key:
                # 1. 기점 지오코딩: start_point 먼저 시도, 실패하면 구조화된 주소
                start_coord = None
                if record["start_point"]:
                    # '/' 구분자를 ' '로 변환
                    start_query = record["start_point"].replace("/", " ")
                    start_coord = geocode_address(vworld_api_key, start_query, logger)

                if not start_coord and (record["start_sido"] or record["start_sigungu"]):
                    # 폴백: 구조화된 주소로 시도
                    start_addr = build_address_for_geocoding(
                        record["start_sido"], record["start_sigungu"], record["start_emd"]
                    )
                    if start_addr:
                        start_coord = geocode_address(vworld_api_key, start_addr, logger)

                if start_coord:
                    record["start_lat"] = start_coord["lat"]
                    record["start_lon"] = start_coord["lon"]
                    geocode_success += 1
                else:
                    geocode_fail += 1

                # 2. 종점 지오코딩
                end_coord = None
                if record["end_point"]:
                    end_query = record["end_point"].replace("/", " ")
                    end_coord = geocode_address(vworld_api_key, end_query, logger)

                if not end_coord and (record["end_sido"] or record["end_sigungu"]):
                    end_addr = build_address_for_geocoding(
                        record["end_sido"], record["end_sigungu"], record["end_emd"]
                    )
                    if end_addr:
                        end_coord = geocode_address(vworld_api_key, end_addr, logger)

                if end_coord:
                    record["end_lat"] = end_coord["lat"]
                    record["end_lon"] = end_coord["lon"]

                # API 레이트 리밋 방지
                time.sleep(0.1)

            parsed.append(record)

        except Exception as e:
            logger.warning(f"레코드 파싱 실패: {e}")
            continue

    if vworld_api_key:
        logger.info(f"지오코딩 결과: 성공 {geocode_success}, 실패 {geocode_fail}")

    return parsed


def load_river_info(sample_limit: int = None):
    """
    하천정보 데이터 적재 + 지오코딩으로 geometry 생성

    Args:
        sample_limit: 샘플 제한 (테스트용)
    """
    logger = setup_logging("load_river_info")
    logger.info("=" * 60)
    logger.info("하천정보 API ETL 시작 (v02 - 지오코딩 포함)")
    logger.info("=" * 60)

    # API 키 확인
    api_key = get_api_key("RIVER_API_KEY")
    if not api_key:
        logger.error("RIVER_API_KEY 환경변수 필요")
        return

    # VWorld API 키 (지오코딩용, 선택적)
    vworld_api_key = get_api_key("VWORLD_API_KEY")
    if vworld_api_key:
        logger.info("VWorld API 키 확인됨 - 지오코딩 활성화")
    else:
        logger.warning("VWORLD_API_KEY 없음 - 지오코딩 건너뜀")

    # DB 연결
    conn = get_db_connection()
    logger.info("DB 연결 완료")

    # API 클라이언트
    client = APIClient(logger)

    # 데이터 수집
    all_data = []
    page_no = 1
    # 샘플 제한이 있으면 그만큼만 가져옴 (지오코딩 시간 절약)
    num_of_rows = sample_limit if sample_limit else 1000

    while True:
        raw_data = fetch_river_info(client, api_key, logger, page_no, num_of_rows)
        if not raw_data:
            break

        # 샘플 제한 적용 (지오코딩 전에 자르기)
        body = raw_data.get("body", [])
        if sample_limit and len(all_data) + len(body) > sample_limit:
            remaining = sample_limit - len(all_data)
            raw_data["body"] = body[:remaining]

        parsed = parse_river_data(raw_data, logger, vworld_api_key)
        if not parsed:
            break

        all_data.extend(parsed)
        logger.info(f"페이지 {page_no}: {len(parsed)}건 수집 (누적: {len(all_data)}건)")

        # 샘플 제한 확인
        if sample_limit and len(all_data) >= sample_limit:
            logger.info(f"샘플 제한 적용: {sample_limit}건")
            break

        # 더 이상 데이터가 없으면 종료
        if len(parsed) < num_of_rows:
            break

        page_no += 1

    # DB 적재 (geometry 생성 포함)
    if all_data:
        logger.info(f"총 {len(all_data)}건 DB 적재 시작")

        cursor = conn.cursor()
        success_count = 0
        error_count = 0

        for record in all_data:
            try:
                # geometry 생성 여부 결정
                start_geom_sql = "NULL"
                end_geom_sql = "NULL"

                if record.get("start_lat") and record.get("start_lon"):
                    start_geom_sql = f"ST_SetSRID(ST_MakePoint({record['start_lon']}, {record['start_lat']}), 4326)"

                if record.get("end_lat") and record.get("end_lon"):
                    end_geom_sql = (
                        f"ST_SetSRID(ST_MakePoint({record['end_lon']}, {record['end_lat']}), 4326)"
                    )

                # UPSERT SQL
                sql = f"""
                    INSERT INTO api_river_info (
                        river_code, river_name, river_grade, watershed_area_km2, river_length_km,
                        start_point, end_point, management_org, basin_name, sido_name, sigungu_name,
                        start_sido, start_sigungu, start_emd, end_sido, end_sigungu, end_emd,
                        flood_capacity, main_river, watershed_code,
                        start_lat, start_lon, end_lat, end_lon,
                        start_geom, end_geom, api_response
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        {start_geom_sql}, {end_geom_sql}, %s
                    )
                    ON CONFLICT (river_code) DO UPDATE SET
                        river_name = EXCLUDED.river_name,
                        river_grade = EXCLUDED.river_grade,
                        watershed_area_km2 = EXCLUDED.watershed_area_km2,
                        river_length_km = EXCLUDED.river_length_km,
                        start_point = EXCLUDED.start_point,
                        end_point = EXCLUDED.end_point,
                        management_org = EXCLUDED.management_org,
                        basin_name = EXCLUDED.basin_name,
                        sido_name = EXCLUDED.sido_name,
                        sigungu_name = EXCLUDED.sigungu_name,
                        start_sido = EXCLUDED.start_sido,
                        start_sigungu = EXCLUDED.start_sigungu,
                        start_emd = EXCLUDED.start_emd,
                        end_sido = EXCLUDED.end_sido,
                        end_sigungu = EXCLUDED.end_sigungu,
                        end_emd = EXCLUDED.end_emd,
                        flood_capacity = EXCLUDED.flood_capacity,
                        main_river = EXCLUDED.main_river,
                        watershed_code = EXCLUDED.watershed_code,
                        start_lat = EXCLUDED.start_lat,
                        start_lon = EXCLUDED.start_lon,
                        end_lat = EXCLUDED.end_lat,
                        end_lon = EXCLUDED.end_lon,
                        start_geom = EXCLUDED.start_geom,
                        end_geom = EXCLUDED.end_geom,
                        api_response = EXCLUDED.api_response,
                        cached_at = CURRENT_TIMESTAMP
                """

                import json

                cursor.execute(
                    sql,
                    (
                        record["river_code"],
                        record["river_name"],
                        record["river_grade"],
                        record["watershed_area_km2"],
                        record["river_length_km"],
                        record["start_point"],
                        record["end_point"],
                        record["management_org"],
                        record["basin_name"],
                        record["sido_name"],
                        record["sigungu_name"],
                        record["start_sido"],
                        record["start_sigungu"],
                        record["start_emd"],
                        record["end_sido"],
                        record["end_sigungu"],
                        record["end_emd"],
                        record["flood_capacity"],
                        record["main_river"],
                        record["watershed_code"],
                        record["start_lat"],
                        record["start_lon"],
                        record["end_lat"],
                        record["end_lon"],
                        json.dumps(record["api_response"], ensure_ascii=False),
                    ),
                )
                success_count += 1

            except Exception as e:
                error_count += 1
                if error_count <= 5:
                    logger.warning(f"레코드 적재 실패: {e}")
                continue

        conn.commit()
        cursor.close()

        logger.info(f"DB 적재 완료: 성공 {success_count}, 실패 {error_count}")

        # 지오코딩 통계
        with_geom = sum(1 for r in all_data if r.get("start_lat"))
        logger.info(f"geometry 생성: {with_geom}/{len(all_data)}건")

    else:
        logger.warning("적재할 데이터 없음")

    # 결과 확인
    total_count = get_table_count(conn, "api_river_info")
    logger.info(f"api_river_info 테이블 총 레코드: {total_count}건")

    conn.close()
    logger.info("하천정보 API ETL 완료")


if __name__ == "__main__":
    # 환경변수로 샘플 제한 설정 가능
    sample_limit = int(os.getenv("SAMPLE_LIMIT", 0)) or None
    load_river_info(sample_limit=sample_limit)
