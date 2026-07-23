from typing import Dict, Any

BUILDING_FALLBACK: Dict[str, Any] = {
    "structure": "철근콘크리트구조",  # 통계청 2020년 건축물 총조사
    "floors": {"ground": 5, "underground": 1},  # 평균 층수
    "height": 15.0,  # 평균 높이
    "seismic": {"applied": "N", "ability": "내진설계 미적용"},  # 1988년 이전 건축물 다수
    "age": {"years": 30, "approval_date": "19950101"},  # 평균 건축 연한
    "main_purpose": "주거용",  # 가장 흔한 용도
    "total_area": 1000.0,  # 평균 연면적
    "arch_area": 200.0,  # 평균 건축면적
    "energy_grade": "4등급",  # 평균 에너지 효율 등급
    "green_grade": "일반",  # 평균 친환경 건축물 등급
    "total_parking": 10,  # 평균 주차 대수
    "household_count": 20,  # 공동주택 평균 세대수
    "integrated_building_grade": "일반",
    "energy_rating": "N/A",
    "epi_score": "N/A",
    "ride_use_elevator_count": 1,
    "etc_structure": "N/A",
    "main_purpose_cd": "20000",  # 주거용 코드 (예시)
}

RIVER_FALLBACK: Dict[str, Any] = {
    "distance_m": 5000,  # 평균 하천 거리 (5km)
    "river_name": "미상",
    "stream_order": 3,  # 평균 하천 차수
}

DATA_SOURCES: Dict[str, str] = {
    "BUILDING_REGISTER_API": "건축행정시스템 - 건축물대장 정보",
    "VWORLD_API": "V-World 공간정보 오픈플랫폼",
    "DISASTER_HISTORY_API": "재난안전데이터 포털 - 과거 재난 이력",
    "STATISTICS_KOREA": "통계청 - 건축물 총조사",
    "MINISTRY_OF_LAND": "국토교통부 - 주택가격동향조사",
}

DISASTER_FALLBACK: Dict[str, Any] = {
    "intensity": "보통",
    "damage_scale": "소규모",
    "frequency": "낮음",
    "affected_area_km2": 0.1,
    "economic_loss_million_krw": 10,
}


def get_flood_history_by_region(sigungu_cd: str) -> Dict[str, Any]:
    """
    지역별 침수 이력 데이터 (예시)
    실제로는 DB나 별도 API에서 조회
    """
    if sigungu_cd == "11680":  # 강남구
        return {
            "last_flood_year": 2022,
            "max_inundation_depth_m": 1.5,
            "flood_frequency_past_10_years": 3,
        }
    elif sigungu_cd == "11110":  # 종로구
        return {
            "last_flood_year": 2011,
            "max_inundation_depth_m": 0.8,
            "flood_frequency_past_10_years": 1,
        }
    else:
        return {
            "last_flood_year": None,
            "max_inundation_depth_m": None,
            "flood_frequency_past_10_years": 0,
        }
