"""
SKALA Physical Risk AI System - VWorld Geocoder API ETL

API: VWorld 역지오코딩
URL: https://api.vworld.kr/req/address
용도: 좌표 → 주소 변환 (건축물대장 조회를 위한 시군구코드/법정동코드 획득)

최종 수정일: 2025-12-03
버전: v01
"""

import os
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import setup_logging, get_db_connection, get_api_key, batch_upsert, get_table_count


def geocode_reverse(api_key: str, lat: float, lon: float, logger) -> dict:
    """
    VWorld 역지오코딩 API 호출

    Args:
        api_key: VWorld API 키
        lat: 위도
        lon: 경도
        logger: 로거

    Returns:
        주소 정보 딕셔너리
    """
    url = "https://api.vworld.kr/req/address"
    params = {
        "service": "address",
        "request": "getAddress",
        "version": "2.0",
        "crs": "EPSG:4326",
        "point": f"{lon},{lat}",
        "format": "json",
        "type": "BOTH",
        "zipcode": "true",
        "simple": "false",
        "key": api_key,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("response", {}).get("status") != "OK":
            logger.warning(f"VWorld API 응답 실패: {data.get('response', {}).get('status')}")
            return None

        results = data.get("response", {}).get("result", [])
        if not results:
            logger.warning(f"해당 좌표의 주소 정보 없음: ({lat}, {lon})")
            return None

        # 지번 주소와 도로명 주소 분리
        parcel_result = None
        road_result = None

        for item in results:
            if item.get("type") == "parcel":
                parcel_result = item
            elif item.get("type") == "road":
                road_result = item

        if not parcel_result:
            logger.warning("지번 주소 없음")
            return None

        structure = parcel_result.get("structure", {})

        # 번지 파싱
        bun = structure.get("number1", "")
        ji = structure.get("number2", "")

        if not bun:
            level5 = structure.get("level5", "")
            if level5 and "-" in level5:
                parts = level5.split("-")
                bun = parts[0]
                ji = parts[1] if len(parts) > 1 else ""
            elif level5:
                bun = level5
                ji = ""

        # 법정동코드에서 시군구/법정동 코드 추출
        dong_code = structure.get("level4LC", "")  # 10자리
        sigungu_cd = dong_code[:5] if len(dong_code) >= 5 else ""
        bjdong_cd = dong_code[5:10] if len(dong_code) >= 10 else ""

        return {
            "latitude": lat,
            "longitude": lon,
            "sido": structure.get("level1", ""),
            "sigungu": structure.get("level2", ""),
            "sigungu_cd": sigungu_cd,
            "dong": structure.get("level4L", ""),
            "bjdong_cd": bjdong_cd,
            "dong_code": dong_code,
            "bun": bun,
            "ji": ji,
            "zipcode": parcel_result.get("zipcode", ""),
            "full_address": parcel_result.get("text", ""),
            "parcel_address": parcel_result.get("text", ""),
            "road_address": road_result.get("text", "") if road_result else "",
            "api_response": data,
        }

    except Exception as e:
        logger.error(f"VWorld API 요청 오류: {e}")
        return None


def load_vworld_geocode(sample_limit: int = None):
    """
    VWorld 역지오코딩 데이터 적재 (테스트용 샘플 좌표)

    Args:
        sample_limit: 샘플 제한 (테스트용)
    """
    logger = setup_logging("load_vworld_geocode")
    logger.info("=" * 60)
    logger.info("VWorld Geocoder API ETL 시작")
    logger.info("=" * 60)

    # API 키 확인
    api_key = get_api_key("VWORLD_API_KEY")
    if not api_key:
        logger.error("VWORLD_API_KEY 환경변수 필요")
        return

    logger.info(f"API Key 확인: {api_key[:10]}...")

    # DB 연결
    conn = get_db_connection()
    logger.info("DB 연결 완료")

    # 테스트용 주요 좌표 (시청 및 주요 건물)
    test_locations = [
        (37.5665, 126.9780, "서울시청"),
        (37.5172, 127.0473, "강남역"),
        (35.1796, 129.0756, "부산시청"),
        (35.8714, 128.6014, "대구시청"),
        (37.4563, 126.7052, "인천시청"),
        (35.1595, 126.8526, "광주시청"),
        (36.3504, 127.3845, "대전시청"),
        (35.5384, 129.3114, "울산시청"),
        (36.4800, 127.2890, "세종시청"),
        (37.2750, 127.0094, "수원시청"),
        (37.8813, 127.7298, "춘천시청"),
        (36.6424, 127.4890, "청주시청"),
        (36.8065, 127.1467, "천안시청"),
        (35.8242, 127.1480, "전주시청"),
        (34.8118, 126.3922, "목포시청"),
        (35.8683, 128.5986, "경주시청"),
        (35.2285, 128.6811, "창원시청"),
        (33.4996, 126.5312, "제주시청"),
    ]

    all_data = []
    limit = sample_limit or len(test_locations)

    for lat, lon, name in test_locations[:limit]:
        logger.info(f"  역지오코딩: {name} ({lat}, {lon})")
        result = geocode_reverse(api_key, lat, lon, logger)

        if result:
            all_data.append(result)
            logger.info(f"    -> {result['full_address']}")
        else:
            logger.warning(f"    -> 실패")

    # DB 적재
    if all_data:
        logger.info(f"\n총 {len(all_data)}건 DB 적재 시작")
        success_count = batch_upsert(
            conn,
            "api_vworld_geocode",
            all_data,
            unique_columns=["latitude", "longitude"],
            batch_size=50,
        )
        logger.info(f"DB 적재 완료: {success_count}건")
    else:
        logger.warning("적재할 데이터 없음")

    # 결과 확인
    total_count = get_table_count(conn, "api_vworld_geocode")
    logger.info(f"api_vworld_geocode 테이블 총 레코드: {total_count}건")

    conn.close()
    logger.info("VWorld Geocoder API ETL 완료")


if __name__ == "__main__":
    sample_limit = int(os.getenv("SAMPLE_LIMIT", 0)) or None
    load_vworld_geocode(sample_limit=sample_limit)
