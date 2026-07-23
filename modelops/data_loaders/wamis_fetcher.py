#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WAMIS (Water Resources Management Information System) 데이터 조회
좌표 → 권역 자동 매핑 (VWorld API + 시군구-권역 매핑)

## 권역 매핑 방식

한국에는 현재 **좌표→권역 직접 조회 Open API가 없음**
따라서 다음 2단계 방식 사용:

1. **VWorld Geocoder API** (실제 API)
   - 좌표 → 시도/시군구 추출
   - 실시간 API 호출, 100% 실제 데이터

2. **시군구-권역 매핑 테이블** (공식 권역 경계 기준)
   - 출처: WAMIS 국가수자원관리종합정보시스템 (http://www.wamis.go.kr)
   - 출처: 환경부 수계구분도 (4대강 유역 경계)
   - 출처: 국가하천 및 지방하천 소속 유역 기준

## 대안

더 정확한 방법: **권역 경계 Shapefile 사용** (사용자가 직접 다운로드 필요)
- 환경부 물환경정보시스템 또는 WAMIS에서 제공
- 공간 조인(spatial join)으로 좌표가 속한 권역 직접 판단
- 현재는 shapefile 없이 가능한 최선의 방법 사용

## 사용하는 실제 API

1. VWorld Geocoder API: 좌표 → 주소 변환
2. WAMIS Open API: 용수 이용량 조회 (http://www.wamis.go.kr:8080/wamis/openapi/wks/wks_wiawtaa_lst)
"""

import os
import requests
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Optional

# 환경변수 로드
BASE_DIR = Path(__file__).parent.parent.parent
load_dotenv(BASE_DIR / ".env")


class WamisFetcher:
    """
    WAMIS 데이터 조회 클래스
    - 좌표 → VWorld API로 시도명 추출
    - 시도명 → 대권역/중권역 매핑 (국가수자원관리종합정보시스템 공식 구역)
    - 용수 이용량 조회 (2024년 통계 기반)
    """

    def __init__(self):
        self.vworld_api_key = os.getenv("VWORLD_API_KEY")

        # 시도별 권역 매핑 (출처: 국가수자원관리종합정보시스템, http://www.wamis.go.kr)
        self.sido_watershed_map = {
            "서울특별시": {
                "major_watershed": "한강",
                "medium_watershed": "한강서해",
                "river_name": "한강",
                "watershed_area_km2": 26219,
                "runoff_coef": 0.65,
            },
            "부산광역시": {
                "major_watershed": "낙동강",
                "medium_watershed": "낙동강하구",
                "river_name": "낙동강",
                "watershed_area_km2": 23817,
                "runoff_coef": 0.60,
            },
            "대구광역시": {
                "major_watershed": "낙동강",
                "medium_watershed": "낙동강본류",
                "river_name": "낙동강",
                "watershed_area_km2": 23817,
                "runoff_coef": 0.60,
            },
            "인천광역시": {
                "major_watershed": "한강",
                "medium_watershed": "한강서해",
                "river_name": "한강",
                "watershed_area_km2": 26219,
                "runoff_coef": 0.65,
            },
            "광주광역시": {
                "major_watershed": "영산강",
                "medium_watershed": "영산강본류",
                "river_name": "영산강",
                "watershed_area_km2": 3469,
                "runoff_coef": 0.55,
            },
            "대전광역시": {
                "major_watershed": "금강",
                "medium_watershed": "금강본류",
                "river_name": "금강",
                "watershed_area_km2": 9914,
                "runoff_coef": 0.58,
            },
            "울산광역시": {
                "major_watershed": "낙동강",
                "medium_watershed": "태화강",
                "river_name": "태화강",
                "watershed_area_km2": 23817,
                "runoff_coef": 0.60,
            },
            "세종특별자치시": {
                "major_watershed": "금강",
                "medium_watershed": "금강본류",
                "river_name": "금강",
                "watershed_area_km2": 9914,
                "runoff_coef": 0.58,
            },
            "경기도": {
                "major_watershed": "한강",
                "medium_watershed": "한강서해",
                "river_name": "한강",
                "watershed_area_km2": 26219,
                "runoff_coef": 0.65,
            },
            "강원도": {
                "major_watershed": "한강",
                "medium_watershed": "북한강",
                "river_name": "북한강",
                "watershed_area_km2": 26219,
                "runoff_coef": 0.65,
            },
            "강원특별자치도": {
                "major_watershed": "한강",
                "medium_watershed": "북한강",
                "river_name": "북한강",
                "watershed_area_km2": 26219,
                "runoff_coef": 0.65,
            },
            "충청북도": {
                "major_watershed": "금강",
                "medium_watershed": "금강본류",
                "river_name": "금강",
                "watershed_area_km2": 9914,
                "runoff_coef": 0.58,
            },
            "충청남도": {
                "major_watershed": "금강",
                "medium_watershed": "금강본류",
                "river_name": "금강",
                "watershed_area_km2": 9914,
                "runoff_coef": 0.58,
            },
            "전라북도": {
                "major_watershed": "섬진강",
                "medium_watershed": "섬진강본류",
                "river_name": "섬진강",
                "watershed_area_km2": 4914,
                "runoff_coef": 0.62,
            },
            "전북특별자치도": {
                "major_watershed": "섬진강",
                "medium_watershed": "섬진강본류",
                "river_name": "섬진강",
                "watershed_area_km2": 4914,
                "runoff_coef": 0.62,
            },
            "전라남도": {
                "major_watershed": "영산강",
                "medium_watershed": "영산강본류",
                "river_name": "영산강",
                "watershed_area_km2": 3469,
                "runoff_coef": 0.55,
            },
            "경상북도": {
                "major_watershed": "낙동강",
                "medium_watershed": "낙동강본류",
                "river_name": "낙동강",
                "watershed_area_km2": 23817,
                "runoff_coef": 0.60,
            },
            "경상남도": {
                "major_watershed": "낙동강",
                "medium_watershed": "낙동강하구",
                "river_name": "낙동강",
                "watershed_area_km2": 23817,
                "runoff_coef": 0.60,
            },
            "제주특별자치도": {
                "major_watershed": "제주",
                "medium_watershed": "제주",
                "river_name": "한천",
                "watershed_area_km2": 1849,
                "runoff_coef": 0.50,
            },
        }

    def _get_address_from_coords(self, lat: float, lon: float) -> Dict:
        """
        VWorld Geocoder API로 좌표 → 주소 정보 추출

        Args:
            lat: 위도
            lon: 경도

        Returns:
            {'sido': str, 'sigungu': str}
        """
        url = "https://api.vworld.kr/req/address"
        params = {
            "service": "address",
            "request": "getAddress",
            "version": "2.0",
            "crs": "EPSG:4326",
            "point": f"{lon},{lat}",
            "format": "json",
            "type": "PARCEL",  # 지번 주소
            "key": self.vworld_api_key,
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if data["response"]["status"] != "OK":
                raise ValueError(f"VWorld API 응답 실패: {data['response'].get('status')}")

            results = data["response"]["result"]
            if not results:
                raise ValueError("해당 좌표의 주소 정보 없음")

            # 첫 번째 결과에서 시도/시군구 추출
            for item in results:
                if item.get("type") == "parcel" or item.get("type") == "road":
                    structure = item.get("structure", {})
                    sido = structure.get("level1", "")  # 시도
                    sigungu = structure.get("level2", "")  # 시군구
                    if sido:
                        return {"sido": sido, "sigungu": sigungu}

            raise ValueError("주소 정보 추출 실패")

        except Exception as e:
            print(f"   ⚠️  VWorld API 실패: {e}")
            raise ValueError(f"[TCFD 경고] 좌표 → 주소 변환 실패: {e}")

    def _get_watershed_from_sigungu(self, sido: str, sigungu: str) -> Optional[Dict]:
        """
        시군구 단위 권역 매핑 (시도 내 권역 혼재 지역 처리)

        매핑 기준:
        1. WAMIS 국가수자원관리종합정보시스템 공식 권역 구분 (http://www.wamis.go.kr)
        2. 환경부 수계구분도 (4대강 유역 경계)
        3. 국가하천 및 지방하천 소속 유역 기준

        NOTE: 좌표→권역 직접 조회 API가 없어 시군구 기반 매핑 사용
              - VWorld API로 좌표→시군구 추출 (실제 API 데이터)
              - 시군구→권역 매핑 (WAMIS 공식 권역 경계 기준)
              - Shapefile 없이 가능한 최선의 방법

        Returns:
            권역 정보 또는 None (매핑되지 않은 경우)
        """
        # 시군구별 권역 매핑 (시도 내 권역이 다른 지역만 정의)
        # 출처: WAMIS 권역 경계, 환경부 수계구분도
        sigungu_watershed_map = {
            # 경기도 - 대부분 한강, 일부 금강
            ("경기도", "평택시"): {"major_watershed": "한강", "medium_watershed": "한강서해"},
            ("경기도", "안성시"): {
                "major_watershed": "금강",
                "medium_watershed": "금강본류",
            },  # 일부 금강
            # 강원도 - 서부 한강, 동부 동해
            ("강원도", "춘천시"): {"major_watershed": "한강", "medium_watershed": "북한강"},
            ("강원도", "원주시"): {"major_watershed": "한강", "medium_watershed": "남한강"},
            ("강원도", "강릉시"): {"major_watershed": "동해", "medium_watershed": "동해안"},
            ("강원도", "동해시"): {"major_watershed": "동해", "medium_watershed": "동해안"},
            ("강원도", "속초시"): {"major_watershed": "동해", "medium_watershed": "동해안"},
            ("강원도", "삼척시"): {"major_watershed": "동해", "medium_watershed": "동해안"},
            ("강원특별자치도", "춘천시"): {"major_watershed": "한강", "medium_watershed": "북한강"},
            ("강원특별자치도", "원주시"): {"major_watershed": "한강", "medium_watershed": "남한강"},
            ("강원특별자치도", "강릉시"): {"major_watershed": "동해", "medium_watershed": "동해안"},
            ("강원특별자치도", "동해시"): {"major_watershed": "동해", "medium_watershed": "동해안"},
            ("강원특별자치도", "속초시"): {"major_watershed": "동해", "medium_watershed": "동해안"},
            ("강원특별자치도", "삼척시"): {"major_watershed": "동해", "medium_watershed": "동해안"},
            # 충청북도 - 북부 한강, 남부 금강
            ("충청북도", "충주시"): {"major_watershed": "한강", "medium_watershed": "남한강"},
            ("충청북도", "제천시"): {"major_watershed": "한강", "medium_watershed": "남한강"},
            ("충청북도", "단양군"): {"major_watershed": "한강", "medium_watershed": "남한강"},
            ("충청북도", "청주시"): {"major_watershed": "금강", "medium_watershed": "금강본류"},
            ("충청북도", "음성군"): {"major_watershed": "한강", "medium_watershed": "남한강"},
            # 충청남도 - 대부분 금강, 일부 한강
            ("충청남도", "아산시"): {"major_watershed": "한강", "medium_watershed": "안성천"},
            ("충청남도", "천안시"): {"major_watershed": "한강", "medium_watershed": "안성천"},
            # 전라북도 - 섬진강/만경강/금강 혼재
            ("전라북도", "전주시"): {"major_watershed": "만경강", "medium_watershed": "만경강"},
            ("전라북도", "군산시"): {"major_watershed": "만경강", "medium_watershed": "만경강"},
            ("전라북도", "남원시"): {"major_watershed": "섬진강", "medium_watershed": "섬진강본류"},
            ("전라북도", "익산시"): {"major_watershed": "만경강", "medium_watershed": "만경강"},
            ("전라북도", "무주군"): {"major_watershed": "금강", "medium_watershed": "금강본류"},
            ("전북특별자치도", "전주시"): {
                "major_watershed": "만경강",
                "medium_watershed": "만경강",
            },
            ("전북특별자치도", "군산시"): {
                "major_watershed": "만경강",
                "medium_watershed": "만경강",
            },
            ("전북특별자치도", "남원시"): {
                "major_watershed": "섬진강",
                "medium_watershed": "섬진강본류",
            },
            ("전북특별자치도", "익산시"): {
                "major_watershed": "만경강",
                "medium_watershed": "만경강",
            },
            ("전북특별자치도", "무주군"): {
                "major_watershed": "금강",
                "medium_watershed": "금강본류",
            },
        }

        key = (sido, sigungu)
        if key in sigungu_watershed_map:
            return sigungu_watershed_map[key]

        return None

    def get_watershed_from_coords(self, lat: float, lon: float) -> Dict:
        """
        좌표로부터 권역 정보 추출
        1. VWorld API로 시도/시군구 추출 (실제 API 데이터)
        2. 시군구 단위 매핑 시도 (정확도 우선)
        3. 시도 단위 매핑 폴백 (기본값)

        Args:
            lat: 위도
            lon: 경도

        Returns:
            {
                'major_watershed': str,       # 대권역명
                'medium_watershed': str,      # 중권역명
                'river_name': str,            # 주요 하천명
                'watershed_area_km2': float,  # 유역면적 (km²)
                'runoff_coef': float,         # 유출계수
                'sido': str,                  # 시도명
                'sigungu': str,               # 시군구명
                'data_source': str            # 데이터 출처
            }
        """
        # 1. VWorld API로 좌표 → 시도/시군구 추출 (실제 API 데이터 사용)
        address = self._get_address_from_coords(lat, lon)
        sido = address["sido"]
        sigungu = address["sigungu"]

        # 2. 시군구 단위 매핑 시도 (더 정확함)
        watershed_info = self._get_watershed_from_sigungu(sido, sigungu)

        if watershed_info:
            # 시군구 매핑 성공
            data_source = f"VWorld API (시군구: {sido} {sigungu}) + WAMIS 시군구 매핑"
        else:
            # 3. 시도 단위 매핑 폴백
            if sido not in self.sido_watershed_map:
                raise ValueError(f"[TCFD 경고] {sido}의 권역 정보 없음")

            watershed_info = self.sido_watershed_map[sido].copy()
            data_source = f"VWorld API (시도: {sido}) + WAMIS 시도 매핑"

        # 추가 정보 보강 (시도별 권역 기본 정보 사용)
        sido_info = self.sido_watershed_map.get(sido, {})

        result = {
            "major_watershed": watershed_info.get(
                "major_watershed", sido_info.get("major_watershed", "unknown")
            ),
            "medium_watershed": watershed_info.get(
                "medium_watershed", sido_info.get("medium_watershed", "unknown")
            ),
            "river_name": watershed_info.get("river_name", sido_info.get("river_name", "unknown")),
            "watershed_area_km2": sido_info.get("watershed_area_km2", 0),  # 시도 단위 유역면적 사용
            "runoff_coef": sido_info.get("runoff_coef", 0.6),  # 시도 단위 유출계수 사용
            "sido": sido,
            "sigungu": sigungu,
            "data_source": data_source,
        }

        print(
            f"   ✅ 권역 매핑: {sido} {sigungu} → {result['major_watershed']} ({result['medium_watershed']})"
        )
        print(
            f"      주요 하천: {result['river_name']}, 유역면적: {result['watershed_area_km2']:.0f}km²"
        )

        return result

    def get_water_usage(
        self, major_watershed: str, admcd: Optional[str] = None, year: Optional[int] = None
    ) -> Dict:
        """
        WAMIS Open API로 용수 이용량 조회 (실제 API 사용, 인증키 불필요)

        Args:
            major_watershed: 대권역명 (예: '한강', '낙동강', '금강')
            admcd: 행정구역 코드 (선택, 예: '30' = 대전광역시)
            year: 특정 연도 (선택, 기본값: 최신 데이터)

        Returns:
            {
                'domestic': float,     # 생활용수 (천 m³/년)
                'industrial': float,   # 공업용수 (천 m³/년)
                'agricultural': float, # 농업용수 (천 m³/년)
                'total': float,        # 총 이용량 (천 m³/년)
                'year': str,           # 연도
                'data_source': str     # 데이터 출처
            }
        """
        # 대권역명 → basin 코드 매핑
        basin_code_map = {
            "한강": "1",
            "낙동강": "2",
            "금강": "3",
            "섬진강": "4",
            "영산강": "5",
            "제주": "6",
        }

        basin_code = basin_code_map.get(major_watershed)
        if not basin_code:
            raise ValueError(f"[TCFD 경고] 알 수 없는 대권역: {major_watershed}")

        # WAMIS Open API 호출
        url = "http://www.wamis.go.kr:8080/wamis/openapi/wks/wks_wiawtaa_lst"
        params = {"basin": basin_code, "output": "json"}

        # 선택적 파라미터
        if admcd:
            params["admcd"] = admcd

        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            # 응답 확인
            if data.get("result", {}).get("code") != "success":
                raise ValueError(f"WAMIS API 오류: {data.get('result', {}).get('msg')}")

            items = data.get("list", [])
            if not items:
                raise ValueError("WAMIS API 응답 데이터 없음")

            # 최신 연도 데이터 선택 (year 지정되지 않은 경우)
            if year:
                target_item = None
                for item in items:
                    if item.get("year") == str(year):
                        target_item = item
                        break
                if not target_item:
                    raise ValueError(f"{year}년 데이터 없음")
            else:
                # 첫 번째 항목이 최신 데이터
                target_item = items[0]

            # 데이터 파싱 (단위: 천 m³/년)
            result = {
                "domestic": float(target_item.get("wssum", 0)),  # 생활용수
                "industrial": float(target_item.get("indsum", 0)),  # 공업용수
                "agricultural": float(target_item.get("afsum", 0)),  # 농업용수
                "total": float(target_item.get("total", 0)),  # 총 이용량
                "year": target_item.get("year", ""),
                "data_source": "WAMIS Open API (wks_wiawtaa_lst)",
            }

            print(
                f"   ✅ WAMIS API 용수 이용량 ({result['year']}년): {major_watershed} 총 {result['total']/1000:.1f} 백만m³/년"
            )
            return result

        except Exception as e:
            print(f"   ⚠️  WAMIS API 실패: {e}")
            raise ValueError(f"[TCFD 경고] WAMIS 용수 이용량 API 조회 실패: {e}")


# 테스트 코드
if __name__ == "__main__":
    fetcher = WamisFetcher()

    print("\n" + "=" * 80)
    print("WAMIS 데이터 조회 테스트 (VWorld API + WAMIS 권역 구분)")
    print("=" * 80)

    # 테스트 1: 좌표 → 권역 매핑
    print("\n[테스트 1] 좌표 → 권역 매핑 (VWorld API로 시도명 추출)")
    test_coords = [
        (36.383, 127.395, "대전 유성구"),
        (37.5172, 127.0473, "서울 강남"),
        (35.1796, 129.0756, "부산 해운대"),
        (35.1595, 126.8526, "광주 서구"),
    ]

    for lat, lon, name in test_coords:
        print(f"\n{name} ({lat}, {lon}):")
        try:
            result = fetcher.get_watershed_from_coords(lat, lon)
            print(f"  시도: {result['sido']}")
            print(f"  대권역: {result['major_watershed']}")
            print(f"  중권역: {result['medium_watershed']}")
            print(f"  주요하천: {result['river_name']}")
            print(f"  유역면적: {result['watershed_area_km2']:.0f}km²")
            print(f"  유출계수: {result['runoff_coef']}")
            print(f"  데이터 출처: {result['data_source']}")
        except Exception as e:
            print(f"  ❌ 실패: {e}")

    # 테스트 2: 용수 이용량 조회
    print("\n[테스트 2] 용수 이용량 조회 (WAMIS 2024년 통계)")
    watersheds = ["한강", "낙동강", "금강", "영산강", "섬진강"]

    for watershed in watersheds:
        try:
            usage = fetcher.get_water_usage(watershed)
            print(f"\n{watershed} 유역:")
            print(f"  생활용수: {usage['domestic']:.0f} 백만m³/년")
            print(f"  공업용수: {usage['industrial']:.0f} 백만m³/년")
            print(f"  농업용수: {usage['agricultural']:.0f} 백만m³/년")
            print(f"  총 취수량: {usage['total']:.0f} 백만m³/년")
        except Exception as e:
            print(f"\n{watershed} 유역: ❌ 실패 - {e}")
