"""
SKALA Physical Risk AI System - 건축물대장 ETL
좌표를 받아서 역지오코딩 → 건축물대장 API 호출 → DB 적재

API: 국토교통부 건축물대장정보 서비스
URL: https://apis.data.go.kr/1613000/BldRgstHubService

사용법:
    # 직접 실행 (테스트용 - SK u-타워)
    python 03_load_buildings.py

    # 외부에서 호출
    from 03_load_buildings import fetch_buildings_for_location
    result = fetch_buildings_for_location(37.3825, 127.1220, "SK u-타워")

최종 수정일: 2025-12-12
버전: v01
"""

import os
import json
import requests
from typing import Dict, List, Optional
from collections import defaultdict

from utils import setup_logging, get_db_connection, get_api_key, APIClient

# =============================================================================
# VWorld 역지오코딩 (좌표 → 행정구역코드)
# =============================================================================


def reverse_geocode_for_building(lat: float, lon: float, logger) -> Optional[Dict]:
    """
    좌표를 행정구역코드로 변환 (건축물대장 API용)

    Returns:
        {
            'sigungu_cd': '11680',      # 시군구코드
            'bjdong_cd': '10300',       # 법정동코드
            'full_address': '서울특별시 강남구 역삼동'
        }
    """
    api_key = os.getenv("VWORLD_API_KEY")
    if not api_key:
        logger.warning("VWORLD_API_KEY 없음")
        return None

    url = "https://api.vworld.kr/req/address"
    params = {
        "service": "address",
        "request": "getAddress",
        "version": "2.0",
        "crs": "epsg:4326",
        "point": f"{lon},{lat}",
        "format": "json",
        "type": "PARCEL",
        "key": api_key,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("response", {}).get("status") != "OK":
            logger.warning(f"VWorld 응답 오류: {data}")
            return None

        result = data["response"]["result"][0]
        structure = result.get("structure", {})

        # 시군구코드 + 법정동코드 추출
        # VWorld 응답은 단순 문자열로 옴 (level4LC = 법정동코드 10자리)
        level4lc = structure.get("level4LC", "")  # 법정동코드 전체 (10자리)

        # 시군구코드: 앞 5자리
        sigungu_cd = level4lc[:5] if len(level4lc) >= 5 else ""

        # 법정동코드: 뒤 5자리
        bjdong_cd = level4lc[5:10] if len(level4lc) >= 10 else "00000"

        full_address = result.get("text", "")

        logger.info(f"   역지오코딩: ({lat}, {lon}) → {full_address}")
        logger.info(f"   시군구코드: {sigungu_cd}, 법정동코드: {bjdong_cd}")

        return {"sigungu_cd": sigungu_cd, "bjdong_cd": bjdong_cd, "full_address": full_address}

    except Exception as e:
        logger.warning(f"역지오코딩 실패 ({lat}, {lon}): {e}")
        return None


# =============================================================================
# 건축물대장 API 호출
# =============================================================================


def fetch_building_info(
    client: APIClient, api_key: str, logger, sigungu_cd: str, bjdong_cd: str, bun: str = None
) -> Optional[Dict]:
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

    logger.info(f"   건축물대장 API 호출: {sigungu_cd}-{bjdong_cd}")
    return client.get(url, params=params, timeout=30)


def parse_building_data(raw_data: dict, logger) -> List[Dict]:
    """API 응답 파싱"""
    parsed = []

    if not raw_data:
        return parsed

    response = raw_data.get("response", {})
    body = response.get("body", {})
    items = body.get("items", {})

    if not items:
        logger.info("   건물 데이터 없음")
        return parsed

    item_list = items.get("item", [])
    if isinstance(item_list, dict):
        item_list = [item_list]

    for item in item_list:
        try:
            use_apr_day = item.get("useAprDay", "")

            record = {
                "sigungu_cd": item.get("sigunguCd", ""),
                "bjdong_cd": item.get("bjdongCd", ""),
                "bun": item.get("bun", ""),
                "ji": item.get("ji", ""),
                "plat_plc": item.get("platPlc", ""),  # 지번 주소
                "new_plat_plc": item.get("newPlatPlc", ""),  # 도로명 주소
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

    logger.info(f"   파싱 완료: {len(parsed)}개 건물")
    return parsed


def aggregate_buildings_by_lot(buildings: list, logger) -> List[Dict]:
    """건물 리스트를 번지 단위로 집계"""
    from datetime import datetime, date

    lot_groups = defaultdict(list)

    for building in buildings:
        sigungu = building.get("sigungu_cd", "")
        bjdong = building.get("bjdong_cd", "")
        bun = building.get("bun", "").zfill(4)
        ji = building.get("ji", "").zfill(4)

        key = (sigungu, bjdong, bun, ji)
        lot_groups[key].append(building)

    logger.info(f"   {len(lot_groups)}개 번지로 그룹화")

    aggregated_lots = []

    for (sigungu_cd, bjdong_cd, bun, ji), bldgs in lot_groups.items():
        building_count = len(bldgs)

        # 구조 종류 수집
        structure_types = list(
            set(
                [
                    b.get("strct_nm", "")
                    for b in bldgs
                    if b.get("strct_nm") and b.get("strct_nm").strip()
                ]
            )
        )

        # 용도 종류 수집
        purpose_types = list(
            set(
                [
                    b.get("main_purp_cd_nm", "")
                    for b in bldgs
                    if b.get("main_purp_cd_nm") and b.get("main_purp_cd_nm").strip()
                ]
            )
        )

        # 층수 집계 (지상)
        ground_floors = [b.get("grnd_flr_cnt", 0) or 0 for b in bldgs]
        max_ground_floors = max(ground_floors) if ground_floors else 0

        # 층수 집계 (지하)
        underground_floors = [b.get("ugrnd_flr_cnt", 0) or 0 for b in bldgs]
        max_underground_floors = max(underground_floors) if underground_floors else 0
        min_underground_floors = (
            min([f for f in underground_floors if f > 0])
            if any(f > 0 for f in underground_floors)
            else 0
        )

        # 면적 집계
        total_floor_area = sum([b.get("tot_area", 0) or 0 for b in bldgs])
        total_building_area = sum([b.get("arch_area", 0) or 0 for b in bldgs])

        # 사용승인일 집계
        approval_dates = []
        for b in bldgs:
            apr_day = b.get("use_apr_day")
            if apr_day and len(apr_day) >= 8:
                try:
                    dt = datetime.strptime(apr_day[:8], "%Y%m%d").date()
                    approval_dates.append(dt)
                except:
                    pass

        oldest_approval_date = min(approval_dates) if approval_dates else None
        newest_approval_date = max(approval_dates) if approval_dates else None

        # 건물 연식 계산
        oldest_building_age_years = None
        if oldest_approval_date:
            oldest_building_age_years = date.today().year - oldest_approval_date.year

        # 내진설계 (API에 해당 필드가 있다면)
        # 건축물대장 API에서 내진설계 정보는 etcStrct 필드 등에서 확인 가능
        buildings_with_seismic = 0
        buildings_without_seismic = building_count  # 기본값

        # 주소 정보 (API에서 platPlc=지번주소, newPlatPlc=도로명주소)
        first_bldg = bldgs[0]
        jibun_address = first_bldg.get("plat_plc", "") or f"{bun}-{ji}"
        road_address = first_bldg.get("new_plat_plc", "") or None

        # 층별 상세 정보 (최대 100개)
        floor_details = []
        for b in bldgs[:100]:
            floor_details.append(
                {
                    "strct": b.get("strct_nm", ""),
                    "purp": b.get("main_purp_cd_nm", ""),
                    "grnd": b.get("grnd_flr_cnt", 0),
                    "ugrnd": b.get("ugrnd_flr_cnt", 0),
                    "area": b.get("tot_area", 0),
                }
            )

        # 층별 용도 종류
        floor_purpose_types = purpose_types  # 동일

        # 데이터 품질 점수 계산
        filled_fields = sum(
            [
                1 if structure_types else 0,
                1 if purpose_types else 0,
                1 if max_ground_floors > 0 else 0,
                1 if total_floor_area > 0 else 0,
                1 if oldest_approval_date else 0,
                1 if road_address else 0,
            ]
        )
        data_quality_score = round(filled_fields / 6, 2)

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
            "max_underground_floors": (
                max_underground_floors if max_underground_floors > 0 else None
            ),
            "min_underground_floors": (
                min_underground_floors if min_underground_floors > 0 else None
            ),
            "buildings_with_seismic": buildings_with_seismic,
            "buildings_without_seismic": buildings_without_seismic,
            "oldest_approval_date": oldest_approval_date,
            "newest_approval_date": newest_approval_date,
            "oldest_building_age_years": oldest_building_age_years,
            "total_floor_area_sqm": round(total_floor_area, 2) if total_floor_area else None,
            "total_building_area_sqm": (
                round(total_building_area, 2) if total_building_area else None
            ),
            "floor_details": json.dumps(floor_details, ensure_ascii=False),
            "floor_purpose_types": json.dumps(floor_purpose_types, ensure_ascii=False),
            "data_quality_score": data_quality_score,
        }

        aggregated_lots.append(aggregated)

    return aggregated_lots


# =============================================================================
# 메인 함수: 좌표로 건축물대장 조회
# =============================================================================


def fetch_buildings(
    lat: float = None,
    lon: float = None,
    sigungu_cd: str = None,
    bjdong_cd: str = None,
    site_name: str = None,
    save_to_db: bool = True,
) -> Dict:
    """
    건축물대장 조회 (좌표 또는 행정코드로 조회 가능)

    입력 방식:
        1. 좌표 방식: lat, lon 입력 → 역지오코딩 후 조회
        2. 행정코드 방식: sigungu_cd, bjdong_cd 입력 → 바로 조회

    Args:
        lat: 위도 (좌표 방식)
        lon: 경도 (좌표 방식)
        sigungu_cd: 시군구코드 5자리 (행정코드 방식)
        bjdong_cd: 법정동코드 5자리 (행정코드 방식)
        site_name: 사업장명 (로깅용)
        save_to_db: DB 저장 여부

    Returns:
        {
            'success': bool,
            'site_name': str,
            'location': {'lat': float, 'lon': float} or None,
            'geocode': {'sigungu_cd': str, 'bjdong_cd': str, 'address': str},
            'buildings': [집계된 건물 목록],
            'total_buildings': int,
            'total_lots': int
        }
    """
    logger = setup_logging("load_buildings")

    # 입력 방식 판별
    use_coords = lat is not None and lon is not None
    use_codes = sigungu_cd is not None and bjdong_cd is not None

    if not use_coords and not use_codes:
        logger.error("좌표(lat, lon) 또는 행정코드(sigungu_cd, bjdong_cd) 필요")
        return {"success": False, "error": "입력값 없음"}

    # 라벨 설정
    if use_coords:
        site_label = site_name or f"({lat}, {lon})"
    else:
        site_label = site_name or f"행정코드 {sigungu_cd}-{bjdong_cd}"

    logger.info("=" * 60)
    logger.info(f"건축물대장 조회: {site_label}")
    logger.info("=" * 60)

    result = {
        "success": False,
        "site_name": site_name,
        "location": {"lat": lat, "lon": lon} if use_coords else None,
        "geocode": None,
        "buildings": [],
        "total_buildings": 0,
        "total_lots": 0,
    }

    # 1. API 키 확인
    api_key = get_api_key("PUBLICDATA_API_KEY")
    if not api_key:
        logger.error("PUBLICDATA_API_KEY 환경변수 필요")
        return result

    # 2. 행정코드 확보 (좌표면 역지오코딩, 코드면 바로 사용)
    if use_coords:
        logger.info("\n[1단계] 역지오코딩 (좌표 → 행정코드)")
        geocode = reverse_geocode_for_building(lat, lon, logger)
        if not geocode:
            logger.error("역지오코딩 실패")
            return result
        final_sigungu = geocode["sigungu_cd"]
        final_bjdong = geocode["bjdong_cd"]
        full_address = geocode["full_address"]
    else:
        logger.info("\n[1단계] 행정코드 직접 사용 (역지오코딩 생략)")
        logger.info(f"   시군구코드: {sigungu_cd}, 법정동코드: {bjdong_cd}")
        final_sigungu = sigungu_cd
        final_bjdong = bjdong_cd
        full_address = f"행정코드 {sigungu_cd}-{bjdong_cd}"

    result["geocode"] = {
        "sigungu_cd": final_sigungu,
        "bjdong_cd": final_bjdong,
        "address": full_address,
    }

    # 3. 건축물대장 API 호출
    logger.info("\n[2단계] 건축물대장 API 호출")
    client = APIClient(logger)
    raw_data = fetch_building_info(client, api_key, logger, final_sigungu, final_bjdong)

    if not raw_data:
        logger.warning("API 응답 없음")
        return result

    # 4. 데이터 파싱
    logger.info("\n[3단계] 데이터 파싱")
    buildings = parse_building_data(raw_data, logger)
    result["total_buildings"] = len(buildings)

    if not buildings:
        logger.info("해당 지역에 건물 없음")
        result["success"] = True
        return result

    # 5. 번지별 집계
    logger.info("\n[4단계] 번지별 집계")
    aggregated = aggregate_buildings_by_lot(buildings, logger)
    result["buildings"] = aggregated
    result["total_lots"] = len(aggregated)

    # 6. DB 저장 (선택)
    if save_to_db and aggregated:
        logger.info("\n[5단계] DB 저장")
        saved = save_to_database(aggregated, site_name, logger)
        logger.info(f"   {saved}건 저장 완료")

    result["success"] = True

    # 결과 요약
    logger.info("\n" + "=" * 60)
    logger.info(f"건축물대장 조회 완료: {site_label}")
    logger.info(f"   - 주소: {full_address}")
    logger.info(f"   - 행정코드: {final_sigungu}-{final_bjdong}")
    logger.info(f"   - 건물 수: {result['total_buildings']}개")
    logger.info(f"   - 번지 수: {result['total_lots']}개")
    logger.info("=" * 60)

    return result


# 기존 함수명 호환성 (alias)
def fetch_buildings_for_location(lat, lon, site_name=None, save_to_db=True):
    """좌표 기반 건축물대장 조회 (기존 함수명 호환)"""
    return fetch_buildings(lat=lat, lon=lon, site_name=site_name, save_to_db=save_to_db)


def fetch_buildings_by_code(sigungu_cd, bjdong_cd, site_name=None, save_to_db=True):
    """행정코드 기반 건축물대장 조회"""
    return fetch_buildings(
        sigungu_cd=sigungu_cd, bjdong_cd=bjdong_cd, site_name=site_name, save_to_db=save_to_db
    )


def save_to_database(aggregated_lots: List[Dict], site_name: str, logger) -> int:
    """집계 데이터를 building_aggregate_cache 테이블에 저장"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 테이블 존재 확인
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'building_aggregate_cache'
            )
        """)
        if not cursor.fetchone()[0]:
            logger.warning("building_aggregate_cache 테이블 없음 - 저장 건너뜀")
            cursor.close()
            conn.close()
            return 0

        insert_query = """
        INSERT INTO building_aggregate_cache (
            sigungu_cd, bjdong_cd, bun, ji,
            jibun_address, road_address,
            building_count, structure_types, purpose_types,
            max_ground_floors, max_underground_floors, min_underground_floors,
            buildings_with_seismic, buildings_without_seismic,
            oldest_approval_date, newest_approval_date, oldest_building_age_years,
            total_floor_area_sqm, total_building_area_sqm,
            floor_details, floor_purpose_types, data_quality_score
        ) VALUES (
            %(sigungu_cd)s, %(bjdong_cd)s, %(bun)s, %(ji)s,
            %(jibun_address)s, %(road_address)s,
            %(building_count)s, %(structure_types)s::jsonb, %(purpose_types)s::jsonb,
            %(max_ground_floors)s, %(max_underground_floors)s, %(min_underground_floors)s,
            %(buildings_with_seismic)s, %(buildings_without_seismic)s,
            %(oldest_approval_date)s, %(newest_approval_date)s, %(oldest_building_age_years)s,
            %(total_floor_area_sqm)s, %(total_building_area_sqm)s,
            %(floor_details)s::jsonb, %(floor_purpose_types)s::jsonb, %(data_quality_score)s
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
            floor_details = EXCLUDED.floor_details,
            floor_purpose_types = EXCLUDED.floor_purpose_types,
            data_quality_score = EXCLUDED.data_quality_score,
            updated_at = NOW()
        """

        success_count = 0
        for lot in aggregated_lots:
            try:
                cursor.execute(insert_query, lot)
                success_count += 1
            except Exception as e:
                logger.warning(f"저장 실패: {e}")
                conn.rollback()
                continue

        conn.commit()
        cursor.close()
        conn.close()

        return success_count

    except Exception as e:
        logger.error(f"DB 연결 실패: {e}")
        return 0


# =============================================================================
# 직접 실행 시 안내
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("건축물대장 ETL 모듈")
    print("=" * 60)
    print("\n사용법:")
    print("  1. 03.1_example.py에서 변수 정의 후 실행")
    print("  2. 또는 다른 파일에서 import하여 사용")
    print("\n예시:")
    print("  from 03_load_buildings import fetch_buildings")
    print("  # 좌표 방식")
    print("  result = fetch_buildings(lat=37.38, lon=127.12)")
    print("  # 행정코드 방식")
    print("  result = fetch_buildings(sigungu_cd='41135', bjdong_cd='10500')")
    print("=" * 60)
