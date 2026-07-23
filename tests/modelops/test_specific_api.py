import sys
import os

# 프로젝트 루트 경로 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, "..", "..")
sys.path.append(project_root)

from modelops.data_loaders.building_db_fetcher import BuildingDataFetcher


def test_specific():
    fetcher = BuildingDataFetcher()

    print("=== 1. 건축물대장 직접 조회 (대전 유성구 원촌동 140-1) ===")
    # 시군구: 30200 (대전 유성구), 법정동: 14200 (원촌동)
    # 번: 0140, 지: 0001
    # 주의: BuildingDataFetcher 내부에서 bun/ji를 4자리로 패딩함 ('0140', '0001')
    res = fetcher.get_building_title_info(
        sigungu_cd="30200", bjdong_cd="14200", bun="0140", ji="0001"
    )
    print(f"결과: {res}")

    print("\n=== 2. 좌표 -> 주소/코드 변환 테스트 ===")
    # 대전 유성구 원촌동 140-1의 좌표
    lat, lon = 36.382967, 127.395442
    addr_info = fetcher.get_building_code_from_coords(lat, lon)
    print(f"입력 좌표: {lat}, {lon}")
    if addr_info:
        print(f"주소: {addr_info.get('full_address')}")
        print(f"법정동코드(VWorld): {addr_info.get('dong_code')}")
        print(f"번/지: {addr_info.get('bun')}-{addr_info.get('ji')}")
    else:
        print("주소 변환 실패")

    print("\n=== 3. 하천 조회 테스트 (V-World WFS) ===")
    try:
        # BuildingDataFetcher.get_river_info는 V-World WFS를 사용함
        river = fetcher.get_river_info(lat, lon)
        print(f"V-World WFS 하천 정보: {river}")
    except Exception as e:
        print(f"V-World WFS 실패: {e}")


if __name__ == "__main__":
    test_specific()
