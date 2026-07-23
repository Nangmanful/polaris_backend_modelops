"""
SKALA Physical Risk AI System - 건축물대장 변수 제공 파일

이 파일에서 조회할 대상 변수를 정의하고 03_load_buildings.py를 호출합니다.

사용법:
    VWORLD_API_KEY=xxx PUBLICDATA_API_KEY=xxx python 03.1_example.py

최종 수정일: 2025-12-12
"""

from importlib import import_module

# 03_load_buildings 모듈 import
load_buildings = import_module("03_load_buildings")
fetch_buildings = load_buildings.fetch_buildings


# =============================================================================
# 변수 정의 (여기만 수정하면 됨)
# =============================================================================

# 방식 1: 좌표 기반 (lat, lon) - SK 사업장 9개
COORD_TARGETS = [
    {"name": "SK u-타워", "lat": 37.3825, "lon": 127.1220},
    {"name": "판교 캠퍼스", "lat": 37.405879, "lon": 127.099877},
    {"name": "수내 오피스", "lat": 37.3820, "lon": 127.1250},
    {"name": "서린 사옥", "lat": 37.570708, "lon": 126.983577},
    {"name": "대덕 데이터 센터", "lat": 36.3728, "lon": 127.3590},
    {"name": "판교 데이터 센터", "lat": 37.405879, "lon": 127.099877},
    {"name": "보라매 데이터 센터", "lat": 37.4858, "lon": 126.9302},
    {"name": "애커튼 파트너스", "lat": 37.5712, "lon": 126.9837},
    {"name": "애커튼 테크놀로지", "lat": 37.405879, "lon": 127.099877},
]

# 방식 2: 행정코드 기반 (sigungu_cd, bjdong_cd)
CODE_TARGETS = [
    {"name": "성남시 분당구 서현동", "sigungu_cd": "41135", "bjdong_cd": "10500"},
    {"name": "이천시 모가면 신갈리", "sigungu_cd": "41500", "bjdong_cd": "36029"},
    # 추가 가능...
]


# =============================================================================
# 실행 (변수 읽어서 03_load_buildings 호출)
# =============================================================================


def main():
    """변수 기반 건축물대장 조회"""

    results = []

    # 좌표 기반 조회
    if COORD_TARGETS:
        print("\n" + "=" * 60)
        print("[좌표 기반 조회]")
        print("=" * 60)
        for target in COORD_TARGETS:
            print(f"\n처리 중: {target['name']}")
            result = fetch_buildings(
                lat=target["lat"], lon=target["lon"], site_name=target["name"], save_to_db=True
            )
            results.append(
                {
                    "type": "좌표",
                    "name": target["name"],
                    "success": result["success"],
                    "buildings": result["total_buildings"],
                    "lots": result["total_lots"],
                }
            )

    # 행정코드 기반 조회
    if CODE_TARGETS:
        print("\n" + "=" * 60)
        print("[행정코드 기반 조회]")
        print("=" * 60)
        for target in CODE_TARGETS:
            print(f"\n처리 중: {target['name']}")
            result = fetch_buildings(
                sigungu_cd=target["sigungu_cd"],
                bjdong_cd=target["bjdong_cd"],
                site_name=target["name"],
                save_to_db=True,
            )
            results.append(
                {
                    "type": "행정코드",
                    "name": target["name"],
                    "success": result["success"],
                    "buildings": result["total_buildings"],
                    "lots": result["total_lots"],
                }
            )

    # 결과 요약
    print("\n" + "=" * 60)
    print("전체 결과 요약")
    print("=" * 60)
    for r in results:
        status = "O" if r["success"] else "X"
        print(
            f"  [{status}] [{r['type']}] {r['name']} → 건물 {r['buildings']}개, 번지 {r['lots']}개"
        )

    success_count = sum(1 for r in results if r["success"])
    print(f"\n총 {len(results)}개 중 {success_count}개 성공")
    print("=" * 60)


if __name__ == "__main__":
    main()
