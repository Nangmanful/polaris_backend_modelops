#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
수자원 권역 매핑
좌표 → 대권역/중권역 매핑
"""

from typing import Dict


class WatershedMapper:
    """
    수자원 권역 매핑 클래스

    대권역 (4개): 한강, 낙동강, 금강, 영산강/섬진강
    중권역: 각 대권역 내 세부 권역
    """

    def __init__(self):
        # 대권역별 대표 중심 좌표와 범위 (간단한 경계 박스)
        self.major_watersheds = {
            "한강": {
                "id": 1001,
                "center": (37.5, 127.5),
                "bounds": {  # 대략적인 경계
                    "lat_min": 36.5,
                    "lat_max": 38.5,
                    "lon_min": 126.5,
                    "lon_max": 129.0,
                },
                "major_rivers": ["한강", "북한강", "남한강", "안양천"],
                "region": "수도권, 강원도",
            },
            "낙동강": {
                "id": 1002,
                "center": (35.5, 128.5),
                "bounds": {"lat_min": 34.5, "lat_max": 36.5, "lon_min": 127.5, "lon_max": 129.5},
                "major_rivers": ["낙동강", "황강", "남강", "밀양강"],
                "region": "부산, 경남, 경북",
            },
            "금강": {
                "id": 1003,
                "center": (36.3, 127.3),
                "bounds": {"lat_min": 35.5, "lat_max": 37.0, "lon_min": 126.5, "lon_max": 128.0},
                "major_rivers": ["금강", "갑천", "미호천", "유등천"],
                "region": "대전, 충남, 충북",
            },
            "영산강섬진강": {
                "id": 1004,
                "center": (35.0, 127.0),
                "bounds": {"lat_min": 34.0, "lat_max": 36.0, "lon_min": 126.0, "lon_max": 128.0},
                "major_rivers": ["영산강", "섬진강", "황룡강", "지석천"],
                "region": "광주, 전남, 전북",
            },
        }

        # 시도별 주요 하천 매핑
        self.city_river_mapping = {
            "서울특별시": {
                "watershed": "한강",
                "major_river": "한강",
                "tributaries": ["중랑천", "안양천", "탄천"],
            },
            "부산광역시": {
                "watershed": "낙동강",
                "major_river": "낙동강",
                "tributaries": ["수영강", "온천천"],
            },
            "대구광역시": {
                "watershed": "낙동강",
                "major_river": "낙동강",
                "tributaries": ["금호강", "신천"],
            },
            "인천광역시": {
                "watershed": "한강",
                "major_river": "한강",
                "tributaries": ["굴포천", "공촌천"],
            },
            "광주광역시": {
                "watershed": "영산강섬진강",
                "major_river": "영산강",
                "tributaries": ["광주천", "황룡강"],
            },
            "대전광역시": {
                "watershed": "금강",
                "major_river": "금강",
                "tributaries": ["갑천", "유등천", "대전천"],
            },
            "울산광역시": {
                "watershed": "낙동강",
                "major_river": "태화강",
                "tributaries": ["동천", "외황강"],
            },
            "세종특별자치시": {
                "watershed": "금강",
                "major_river": "금강",
                "tributaries": ["미호천"],
            },
            "경기도": {
                "watershed": "한강",
                "major_river": "한강",
                "tributaries": ["안양천", "탄천", "왕숙천"],
            },
            "강원도": {
                "watershed": "한강",
                "major_river": "북한강",
                "tributaries": ["소양강", "홍천강"],
            },
            "충청북도": {
                "watershed": "금강",
                "major_river": "금강",
                "tributaries": ["미호천", "보청천"],
            },
            "충청남도": {
                "watershed": "금강",
                "major_river": "금강",
                "tributaries": ["논산천", "석성천"],
            },
            "전라북도": {
                "watershed": "영산강섬진강",
                "major_river": "섬진강",
                "tributaries": ["만경강", "동진강"],
            },
            "전라남도": {
                "watershed": "영산강섬진강",
                "major_river": "영산강",
                "tributaries": ["지석천", "황룡강"],
            },
            "경상북도": {
                "watershed": "낙동강",
                "major_river": "낙동강",
                "tributaries": ["반변천", "내성천"],
            },
            "경상남도": {
                "watershed": "낙동강",
                "major_river": "낙동강",
                "tributaries": ["남강", "황강"],
            },
            "제주특별자치도": {
                "watershed": "제주",
                "major_river": "한천",
                "tributaries": ["산지천", "병문천"],
            },
        }

    def get_watershed_from_coords(self, lat: float, lon: float) -> Dict:
        """
        좌표로부터 권역 정보 추출

        Args:
            lat: 위도
            lon: 경도

        Returns:
            {
                'major_watershed': str,  # 대권역명
                'watershed_id': int,     # 권역ID
                'major_river': str,      # 주요 하천
                'region': str,           # 해당 지역
                'data_source': str
            }
        """
        # 1. 좌표 기반으로 대권역 찾기
        for watershed_name, info in self.major_watersheds.items():
            bounds = info["bounds"]
            if (
                bounds["lat_min"] <= lat <= bounds["lat_max"]
                and bounds["lon_min"] <= lon <= bounds["lon_max"]
            ):
                return {
                    "major_watershed": watershed_name,
                    "watershed_id": info["id"],
                    "major_rivers": info["major_rivers"],
                    "region": info["region"],
                    "data_source": "watershed_mapping",
                }

        # 2. 범위 밖이면 가장 가까운 권역 찾기
        min_distance = float("inf")
        closest_watershed = None

        for watershed_name, info in self.major_watersheds.items():
            center_lat, center_lon = info["center"]
            distance = ((lat - center_lat) ** 2 + (lon - center_lon) ** 2) ** 0.5

            if distance < min_distance:
                min_distance = distance
                closest_watershed = watershed_name

        if closest_watershed:
            info = self.major_watersheds[closest_watershed]
            return {
                "major_watershed": closest_watershed,
                "watershed_id": info["id"],
                "major_rivers": info["major_rivers"],
                "region": info["region"],
                "data_source": "watershed_mapping_nearest",
            }

        return {
            "major_watershed": "unknown",
            "watershed_id": 0,
            "major_rivers": [],
            "region": "unknown",
            "data_source": "fallback",
        }

    def get_watershed_from_region(self, sido: str) -> Dict:
        """
        시도명으로부터 권역 정보 추출

        Args:
            sido: 시도명 (예: '대전광역시')

        Returns:
            권역 정보 딕셔너리
        """
        if sido in self.city_river_mapping:
            mapping = self.city_river_mapping[sido]
            watershed_name = mapping["watershed"]

            if watershed_name in self.major_watersheds:
                info = self.major_watersheds[watershed_name]
                return {
                    "major_watershed": watershed_name,
                    "watershed_id": info["id"],
                    "major_river": mapping["major_river"],
                    "tributaries": mapping["tributaries"],
                    "region": sido,
                    "data_source": "city_river_mapping",
                }

        return {
            "major_watershed": "unknown",
            "watershed_id": 0,
            "major_river": "unknown",
            "tributaries": [],
            "region": sido,
            "data_source": "fallback",
        }


# 테스트 코드
if __name__ == "__main__":
    mapper = WatershedMapper()

    print("\n" + "=" * 80)
    print("수자원 권역 매핑 테스트")
    print("=" * 80)

    # 테스트 1: 좌표로 권역 찾기
    print("\n[테스트 1] 좌표 → 권역")
    test_coords = [
        (36.383, 127.395, "대전 유성구"),
        (37.5172, 127.0473, "서울 강남"),
        (35.1796, 129.0756, "부산 해운대"),
        (35.1595, 126.8526, "광주 서구"),
    ]

    for lat, lon, name in test_coords:
        result = mapper.get_watershed_from_coords(lat, lon)
        print(f"\n{name} ({lat}, {lon}):")
        print(f"  대권역: {result['major_watershed']}")
        print(f"  주요하천: {', '.join(result['major_rivers'])}")
        print(f"  지역: {result['region']}")

    # 테스트 2: 시도명으로 권역 찾기
    print("\n[테스트 2] 시도명 → 권역")
    test_cities = ["대전광역시", "서울특별시", "부산광역시"]

    for city in test_cities:
        result = mapper.get_watershed_from_region(city)
        print(f"\n{city}:")
        print(f"  대권역: {result['major_watershed']}")
        print(f"  주요하천: {result['major_river']}")
        print(f"  지류: {', '.join(result.get('tributaries', []))}")
