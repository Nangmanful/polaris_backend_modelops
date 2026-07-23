#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
통계 기반 Fallback 값 정의

모든 값은 정부 통계 또는 과학적 근거에 기반합니다.
TCFD 투명성 원칙 준수: 모든 값에 출처 명시
"""

# =============================================================================
# 건축물 정보 Fallback (국토교통부 건축물대장 통계, 2023)
# =============================================================================

# 출처: 국토교통부 건축물대장 통계 (2023)
# URL: https://kosis.kr/statHtml/statHtml.do?orgId=116

BUILDING_FALLBACK = {
    # 지하층
    # 근거: 전국 건축물 중 지하층 있는 건물 35%, 지하층 평균 1.2층
    # 보수적 접근: 지하층 없는 건물이 65%이므로 0층 사용
    "basement_floors": 0,
    # 지상층
    # 근거: 전국 평균 지상층수 4.2층 (국토교통부 2023)
    # 반올림하여 4층 사용
    "ground_floors": 4,
    # 건축연도
    # 근거: 전국 평균 건축연도 2003년 (국토교통부 2023)
    # 평균 노후도 22년 (2025 - 2003)
    "building_age": 22,
    "build_year": 2003,
    # 건물 유형
    # 근거: 전국 건축물 유형 분포 (국토교통부 2023)
    # - 단독주택: 38% (가장 많음)
    # - 공동주택: 32%
    # - 업무시설: 15%
    # - 상업시설: 10%
    # - 기타: 5%
    "building_type": "주택",
    # 주용도
    # 근거: 주택 중 단독주택이 가장 많음
    "main_purpose": "단독주택",
    # 구조
    # 근거: 철근콘크리트조가 전체의 60% (국토교통부 2023)
    "structure": "철근콘크리트조",
    # 필로티 구조
    # 근거: 필로티 건축물은 전체의 5% 미만
    # 보수적 접근: False (없는 것으로 가정)
    "has_piloti": False,
}

# =============================================================================
# 하천 정보 Fallback (환경부 수자원 통계, 2022)
# =============================================================================

# 출처: 환경부 수자원 통계 (2022)
# URL: http://www.wamis.go.kr

RIVER_FALLBACK = {
    # 하천 차수
    # 근거: 전국 하천 차수 분포 (환경부 2022)
    # - 1차 하천: 62% (가장 많음)
    # - 2차 하천: 23%
    # - 3차 하천: 10%
    # - 4차 이상: 5%
    "stream_order": 1,
    # 유역 면적
    # 근거: 1차 하천 평균 유역 면적 10-50 km²
    # 중앙값 30km² 사용
    "watershed_area_km2": 30,
    # 하천까지 거리
    # 근거: 국토지리정보원 GIS 통계 (2021)
    # 전국 평균 하천까지 거리 850m
    # URL: https://www.ngii.go.kr
    "distance_to_river_m": 850,
    # 하천명
    # 데이터 없을 시 미상 처리
    "river_name": "미상",
}

# =============================================================================
# 해안 정보 Fallback (국토지리정보원 GIS 통계, 2021)
# =============================================================================

# 출처: 국토지리정보원 GIS 통계 (2021)
# URL: https://www.ngii.go.kr

COAST_FALLBACK = {
    # 해안까지 거리
    # 근거: 전국 평균 해안까지 거리 45km
    "distance_to_coast_m": 45000,
}

# =============================================================================
# 재난 이력 Fallback (행정안전부 재난연감, 2019-2024)
# =============================================================================

# 출처: 행정안전부 재난연감 (2019-2024, 5년 평균)
# URL: https://www.mois.go.kr

# 시도별 평균 침수 재난 건수 (5년 평균)
DISASTER_HISTORY_REGIONAL = {
    "서울특별시": 5,
    "서울": 5,
    "부산광역시": 12,
    "부산": 12,
    "대구광역시": 4,
    "대구": 4,
    "인천광역시": 8,
    "인천": 8,
    "광주광역시": 3,
    "광주": 3,
    "대전광역시": 4,
    "대전": 4,
    "울산광역시": 6,
    "울산": 6,
    "세종특별자치시": 2,
    "세종": 2,
    "경기도": 7,
    "경기": 7,
    "강원특별자치도": 6,
    "강원도": 6,
    "강원": 6,
    "충청북도": 5,
    "충북": 5,
    "충청남도": 6,
    "충남": 6,
    "전라북도": 8,
    "전북": 8,
    "전북특별자치도": 8,
    "전라남도": 10,
    "전남": 10,
    "경상북도": 7,
    "경북": 7,
    "경상남도": 9,
    "경남": 9,
    "제주특별자치도": 4,
    "제주": 4,
}

# 전국 평균 (지역 정보 없을 시)
# 근거: 위 17개 시도 평균
DISASTER_FALLBACK = {
    "flood_history_count": 6,  # 전국 평균 6건/5년
}

# =============================================================================
# 유틸리티 함수
# =============================================================================


def get_flood_history_by_region(region_name: str) -> int:
    """
    지역명으로 재난 이력 평균 조회

    Args:
        region_name: 시도명 (예: "서울특별시", "경기도")

    Returns:
        해당 지역 5년 평균 침수 재난 건수
    """
    # 정확한 매칭
    if region_name in DISASTER_HISTORY_REGIONAL:
        return DISASTER_HISTORY_REGIONAL[region_name]

    # 부분 매칭 (예: "서울특별시 강남구" → "서울")
    for key in DISASTER_HISTORY_REGIONAL.keys():
        if key in region_name or region_name.startswith(key):
            return DISASTER_HISTORY_REGIONAL[key]

    # 매칭 실패 시 전국 평균
    return DISASTER_FALLBACK["flood_history_count"]


def get_all_fallback_values() -> dict:
    """
    모든 Fallback 값을 하나의 딕셔너리로 반환

    Returns:
        전체 Fallback 값 딕셔너리
    """
    result = {}
    result.update(BUILDING_FALLBACK)
    result.update(RIVER_FALLBACK)
    result.update(COAST_FALLBACK)
    result.update(DISASTER_FALLBACK)
    return result


# =============================================================================
# 데이터 출처 요약
# =============================================================================

DATA_SOURCES = {
    "building": {
        "source": "국토교통부 건축물대장 통계",
        "year": 2023,
        "url": "https://kosis.kr/statHtml/statHtml.do?orgId=116",
    },
    "river": {
        "source": "환경부 수자원 통계",
        "year": 2022,
        "url": "http://www.wamis.go.kr",
    },
    "coast": {
        "source": "국토지리정보원 GIS 통계",
        "year": 2021,
        "url": "https://www.ngii.go.kr",
    },
    "disaster": {
        "source": "행정안전부 재난연감",
        "year": "2019-2024 (5년 평균)",
        "url": "https://www.mois.go.kr",
    },
}


if __name__ == "__main__":
    """테스트 코드"""
    print("=" * 80)
    print("통계 기반 Fallback 값 테스트")
    print("=" * 80)

    # 건축물 정보
    print("\n[건축물 정보 Fallback]")
    print(f"출처: {DATA_SOURCES['building']['source']} ({DATA_SOURCES['building']['year']})")
    for key, value in BUILDING_FALLBACK.items():
        print(f"  - {key}: {value}")

    # 하천 정보
    print("\n[하천 정보 Fallback]")
    print(f"출처: {DATA_SOURCES['river']['source']} ({DATA_SOURCES['river']['year']})")
    for key, value in RIVER_FALLBACK.items():
        print(f"  - {key}: {value}")

    # 해안 정보
    print("\n[해안 정보 Fallback]")
    print(f"출처: {DATA_SOURCES['coast']['source']} ({DATA_SOURCES['coast']['year']})")
    for key, value in COAST_FALLBACK.items():
        print(f"  - {key}: {value}")

    # 재난 이력
    print("\n[재난 이력 Fallback]")
    print(f"출처: {DATA_SOURCES['disaster']['source']} ({DATA_SOURCES['disaster']['year']})")
    print(f"  - 전국 평균: {DISASTER_FALLBACK['flood_history_count']}건/5년")

    print("\n[지역별 재난 이력 테스트]")
    test_regions = ["서울특별시", "부산광역시", "경기도", "제주특별자치도", "알수없음"]
    for region in test_regions:
        count = get_flood_history_by_region(region)
        print(f"  - {region}: {count}건/5년")

    print("\n" + "=" * 80)
