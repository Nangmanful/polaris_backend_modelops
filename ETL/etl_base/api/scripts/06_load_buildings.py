"""
SKALA Physical Risk AI System - 건축물 집계 캐시 ETL

API: 국토교통부 건축물대장정보 서비스
URL: https://apis.data.go.kr/1613000/BldRgstHubService
용도: 번지 단위 건물 집계 데이터 (취약성 분석용)

최종 수정일: 2025-12-11
버전: v02 (집계 캐시 버전)
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))

from utils import setup_logging, get_db_connection, get_api_key, APIClient, get_table_count


def fetch_building_info(
    client: APIClient, api_key: str, logger, sigungu_cd: str, bjdong_cd: str, bun: str = None
):
    """건축물 표제부 조회"""
    url = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
    params = {
        "serviceKey": api_key,
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "numOfRows": "1000",
        "pageNo": "1",
        "_type": "json",
    }

    if bun:
        params["bun"] = bun

    logger.info(f"건축물대장 API 호출: {sigungu_cd}-{bjdong_cd}" + (f" 번:{bun}" if bun else ""))
    return client.get(url, params=params, timeout=30)


def aggregate_buildings_by_lot(buildings: list, logger) -> dict:
    """
    건물 리스트를 번지 단위로 집계

    Args:
        buildings: 개별 건물 데이터 리스트

    Returns:
        번지별 집계 데이터 딕셔너리
    """
    # 번지별로 그룹화
    lot_groups = defaultdict(list)

    for building in buildings:
        sigungu = building.get("sigungu_cd", "")
        bjdong = building.get("bjdong_cd", "")
        bun = building.get("bun", "").zfill(4)
        ji = building.get("ji", "").zfill(4)

        key = (sigungu, bjdong, bun, ji)
        lot_groups[key].append(building)

    logger.info(f"총 {len(lot_groups)}개 번지로 그룹화")

    # 각 번지별로 집계
    aggregated_lots = []

    for (sigungu_cd, bjdong_cd, bun, ji), bldgs in lot_groups.items():
        building_count = len(bldgs)

        # 구조 종류 수집 (중복 제거)
        structure_types = list(
            set(
                [
                    b.get("strct_nm", "")
                    for b in bldgs
                    if b.get("strct_nm") and b.get("strct_nm").strip()
                ]
            )
        )

        # 용도 종류 수집 (중복 제거)
        purpose_types = list(
            set(
                [
                    b.get("main_purp_cd_nm", "")
                    for b in bldgs
                    if b.get("main_purp_cd_nm") and b.get("main_purp_cd_nm").strip()
                ]
            )
        )

        # 층수 집계
        ground_floors = [b.get("grnd_flr_cnt", 0) or 0 for b in bldgs]
        underground_floors = [b.get("ugrnd_flr_cnt", 0) or 0 for b in bldgs]

        max_ground_floors = max(ground_floors) if ground_floors else 0
        max_underground_floors = max(underground_floors) if underground_floors else 0
        min_underground_floors = (
            min([f for f in underground_floors if f > 0]) if any(underground_floors) else 0
        )

        # 내진설계 집계 (추후 API로 확인 필요, 일단 0으로)
        buildings_with_seismic = 0
        buildings_without_seismic = building_count

        # 사용승인일 집계
        approval_dates = [
            datetime.strptime(b.get("use_apr_day"), "%Y-%m-%d").date()
            for b in bldgs
            if b.get("use_apr_day") and len(b.get("use_apr_day", "")) >= 10
        ]

        oldest_approval_date = min(approval_dates) if approval_dates else None
        newest_approval_date = max(approval_dates) if approval_dates else None

        # 연식 계산
        if oldest_approval_date:
            oldest_building_age_years = (datetime.now().date() - oldest_approval_date).days // 365
        else:
            oldest_building_age_years = None

        # 면적 집계
        total_floor_area = sum([b.get("tot_area", 0) or 0 for b in bldgs])
        total_building_area = sum([b.get("arch_area", 0) or 0 for b in bldgs])

        # 주소 정보 (첫 번째 건물에서 추출)
        first_bldg = bldgs[0]
        jibun_address = f"{first_bldg.get('na_bjdong_nm', '')} {bun}-{ji}".strip()
        road_address = first_bldg.get("na_road_nm", "") or None

        # 집계 데이터 생성
        aggregated = {
            "sigungu_cd": sigungu_cd,
            "bjdong_cd": bjdong_cd,
            "bun": bun,
            "ji": ji,
            "jibun_address": jibun_address,
            "road_address": road_address,
            "building_count": building_count,
            "structure_types": json.dumps(structure_types, ensure_ascii=False),
            "purpose_types": json.dumps(purpose_types, ensure_ascii=False),
            "max_ground_floors": max_ground_floors,
            "max_underground_floors": max_underground_floors,
            "min_underground_floors": min_underground_floors,
            "buildings_with_seismic": buildings_with_seismic,
            "buildings_without_seismic": buildings_without_seismic,
            "oldest_approval_date": oldest_approval_date,
            "newest_approval_date": newest_approval_date,
            "oldest_building_age_years": oldest_building_age_years,
            "total_floor_area_sqm": round(total_floor_area, 2) if total_floor_area else None,
            "total_building_area_sqm": (
                round(total_building_area, 2) if total_building_area else None
            ),
            "floor_details": None,  # 추후 층별 API 호출 시 추가
            "floor_purpose_types": None,
            "data_quality_score": 0.8,  # 기본 품질 점수
        }

        aggregated_lots.append(aggregated)

        logger.info(f"  {sigungu_cd}-{bjdong_cd} {bun}-{ji}: {building_count}개 건물 집계")

    return aggregated_lots


def parse_building_data(raw_data: dict, logger) -> list:
    """API 응답 파싱"""
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
            use_apr_day = item.get("useAprDay", "")

            record = {
                "sigungu_cd": item.get("sigunguCd", ""),
                "bjdong_cd": item.get("bjdongCd", ""),
                "bun": item.get("bun", ""),
                "ji": item.get("ji", ""),
                "na_bjdong_nm": item.get("naBjdongNm", ""),
                "na_road_nm": item.get("naRoadNm", ""),
                "strct_cd": item.get("strctCd", ""),
                "strct_nm": item.get("strctCdNm", ""),
                "main_purp_cd": item.get("mainPurpsCd", ""),
                "main_purp_cd_nm": item.get("mainPurpsCdNm", ""),
                "use_apr_day": use_apr_day[:10] if use_apr_day and len(use_apr_day) >= 8 else None,
                "grnd_flr_cnt": int(item.get("grndFlrCnt", 0) or 0),
                "ugrnd_flr_cnt": int(item.get("ugrndFlrCnt", 0) or 0),
                "tot_area": float(item.get("totArea", 0) or 0),
                "arch_area": float(item.get("archArea", 0) or 0),
            }

            parsed.append(record)

        except Exception as e:
            logger.warning(f"레코드 파싱 실패: {e}")
            continue

    return parsed


def save_aggregated_data(conn, aggregated_lots: list, logger):
    """집계 데이터를 building_aggregate_cache 테이블에 저장 (UPSERT)"""
    cursor = conn.cursor()

    insert_query = """
    INSERT INTO building_aggregate_cache (
        sigungu_cd, bjdong_cd, bun, ji,
        jibun_address, road_address,
        building_count, structure_types, purpose_types,
        max_ground_floors, max_underground_floors, min_underground_floors,
        buildings_with_seismic, buildings_without_seismic,
        oldest_approval_date, newest_approval_date, oldest_building_age_years,
        total_floor_area_sqm, total_building_area_sqm,
        floor_details, floor_purpose_types,
        data_quality_score, api_call_count
    ) VALUES (
        %(sigungu_cd)s, %(bjdong_cd)s, %(bun)s, %(ji)s,
        %(jibun_address)s, %(road_address)s,
        %(building_count)s, %(structure_types)s::jsonb, %(purpose_types)s::jsonb,
        %(max_ground_floors)s, %(max_underground_floors)s, %(min_underground_floors)s,
        %(buildings_with_seismic)s, %(buildings_without_seismic)s,
        %(oldest_approval_date)s, %(newest_approval_date)s, %(oldest_building_age_years)s,
        %(total_floor_area_sqm)s, %(total_building_area_sqm)s,
        %(floor_details)s, %(floor_purpose_types)s,
        %(data_quality_score)s, 1
    )
    ON CONFLICT (sigungu_cd, bjdong_cd, bun, ji)
    DO UPDATE SET
        building_count = EXCLUDED.building_count,
        structure_types = EXCLUDED.structure_types,
        purpose_types = EXCLUDED.purpose_types,
        max_ground_floors = EXCLUDED.max_ground_floors,
        max_underground_floors = EXCLUDED.max_underground_floors,
        min_underground_floors = EXCLUDED.min_underground_floors,
        buildings_with_seismic = EXCLUDED.buildings_with_seismic,
        buildings_without_seismic = EXCLUDED.buildings_without_seismic,
        oldest_approval_date = EXCLUDED.oldest_approval_date,
        newest_approval_date = EXCLUDED.newest_approval_date,
        oldest_building_age_years = EXCLUDED.oldest_building_age_years,
        total_floor_area_sqm = EXCLUDED.total_floor_area_sqm,
        total_building_area_sqm = EXCLUDED.total_building_area_sqm,
        data_quality_score = EXCLUDED.data_quality_score,
        updated_at = NOW(),
        api_call_count = building_aggregate_cache.api_call_count + 1
    """

    success_count = 0
    for lot in aggregated_lots:
        try:
            cursor.execute(insert_query, lot)
            success_count += 1
        except Exception as e:
            logger.error(
                f"저장 실패 ({lot['sigungu_cd']}-{lot['bjdong_cd']} {lot['bun']}-{lot['ji']}): {e}"
            )
            conn.rollback()
            continue

    conn.commit()
    cursor.close()

    logger.info(f"building_aggregate_cache: {success_count}건 저장 완료")
    return success_count


def load_building_aggregate_data(sample_limit: int = None):
    """건축물 집계 데이터 적재"""
    logger = setup_logging("load_building_aggregate")
    logger.info("=" * 60)
    logger.info("건축물 집계 캐시 ETL 시작")
    logger.info("=" * 60)

    api_key = get_api_key("PUBLICDATA_API_KEY")
    if not api_key:
        logger.error("PUBLICDATA_API_KEY 환경변수 필요")
        return

    conn = get_db_connection()
    logger.info("DB 연결 완료")

    client = APIClient(logger)

    # 테스트 지역 (서울, 부산, 대전 등)
    test_areas = [
        ("11110", "10100"),  # 서울 종로구 청운동
        ("11680", "10100"),  # 서울 강남구 역삼동
        ("26350", "10100"),  # 부산 해운대구 우동
        ("30200", "14200"),  # 대전 유성구 원촌동
    ]

    all_buildings = []
    for sigungu_cd, bjdong_cd in test_areas:
        raw_data = fetch_building_info(client, api_key, logger, sigungu_cd, bjdong_cd)
        if raw_data:
            parsed = parse_building_data(raw_data, logger)
            all_buildings.extend(parsed)
            logger.info(f"  {sigungu_cd}-{bjdong_cd}: {len(parsed)}개 건물 수집")

        if sample_limit and len(all_buildings) >= sample_limit:
            all_buildings = all_buildings[:sample_limit]
            break

    logger.info(f"총 {len(all_buildings)}개 건물 수집 완료")

    # 번지 단위로 집계
    if all_buildings:
        aggregated_lots = aggregate_buildings_by_lot(all_buildings, logger)

        # DB에 저장
        saved = save_aggregated_data(conn, aggregated_lots, logger)
        logger.info(f"{saved}개 번지 집계 데이터 저장 완료")

    total = get_table_count(conn, "building_aggregate_cache")
    logger.info(f"building_aggregate_cache 총 레코드: {total}건")

    conn.close()
    logger.info("건축물 집계 캐시 ETL 완료")


if __name__ == "__main__":
    sample_limit = int(os.getenv("SAMPLE_LIMIT", 0)) or None
    load_building_aggregate_data(sample_limit=sample_limit)
