"""
재난안전데이터 API 조회
- 하천정보 API
- 긴급재난문자 API
"""

import os
import requests
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Optional
from datetime import datetime, timedelta

# 환경변수 로드
BASE_DIR = Path(__file__).parent.parent.parent
load_dotenv(BASE_DIR / ".env")


class DisasterAPIFetcher:
    """재난안전데이터 API 조회 클래스"""

    def __init__(self):
        self.river_api_key = os.getenv("RIVER_API_KEY")  # 하천정보 API
        self.emergency_api_key = os.getenv("EMERGENCYMESSAGE_API_KEY")  # 긴급재난문자 API
        self.disaster_api_key = os.getenv("DISASTERAREA_API_KEY")  # 재난지역 API
        self.kma_api_key = os.getenv("KMA_API_KEY")
        self.typhoon_api_base_url = "https://apihub.kma.go.kr/api/typ01/url/typ_besttrack.php"

    def get_nearest_river_info(self, lat: float, lon: float) -> Optional[Dict]:
        """
        재난안전데이터 하천정보 API로 가장 가까운 하천 찾기
        """
        url = "https://www.safetydata.go.kr/V2/api/DSSP-IF-10720"

        params = {
            "serviceKey": self.river_api_key,
            "returnType": "json",
            "pageNo": "1",
            "numOfRows": "100",  # 100개 조회해서 가장 가까운 것 찾기
        }

        try:
            response = requests.get(url, params=params, timeout=15)
            data = response.json()

            if data.get("header", {}).get("resultCode") != "00":
                raise ValueError(f"하천정보 API 오류: {data.get('header', {}).get('resultMsg')}")

            rivers = data.get("body", [])
            if not rivers:
                raise ValueError("하천정보 API 응답 없음")

            # TODO: 실제로는 하천의 좌표 정보가 있어야 거리 계산 가능
            # 현재 API 응답에는 하천명, 등급, 유역면적만 있음
            # 임시로 첫 번째 하천 사용
            river = rivers[0]

            result = {
                "river_name": river.get("RVR_NM", "미상"),
                "river_grade": int(river.get("RVR_GRD_CD", 3)),  # 하천등급 (1급, 2급 등)
                "watershed_area_km2": float(river.get("DRAR", 0) or 0),  # 유역면적
                "river_length_km": float(river.get("RVR_PRLG_LEN", 0) or 0),  # 하천연장
                "distance_m": 1000,  # TODO: 실제 거리 계산 필요
            }

            print(
                f"   ✅ 하천정보 API: {result['river_name']}, 등급 {result['river_grade']}, 유역 {result['watershed_area_km2']}km²"
            )
            return result

        except Exception as e:
            print(f"   ⚠️  하천정보 API 실패: {e}")
            raise ValueError(f"[TCFD 경고] 하천정보 API 조회 실패: {e}")

    def get_flood_history(self, region: str, years: int = 5) -> int:
        """
        긴급재난문자 API로 침수 이력 조회

        Args:
            region: 지역명 (예: "서울특별시", "경기도 성남시")
            years: 조회 기간 (년)

        Returns:
            침수 관련 재난 발생 횟수
        """
        url = "https://www.safetydata.go.kr/V2/api/DSSP-IF-00247"

        # 조회 시작일 (years 년 전)
        start_date = (datetime.now() - timedelta(days=365 * years)).strftime("%Y%m%d")

        params = {
            "serviceKey": self.emergency_api_key,
            "returnType": "json",
            "pageNo": "1",
            "numOfRows": "1000",  # 최대한 많이 조회
            "crtDt": start_date,
            "rgnNm": region,
        }

        try:
            response = requests.get(url, params=params, timeout=15)
            data = response.json()

            if data.get("header", {}).get("resultCode") != "00":
                raise ValueError(
                    f"긴급재난문자 API 오류: {data.get('header', {}).get('resultMsg')}"
                )

            messages = data.get("body", [])

            # 침수 관련 키워드
            flood_keywords = ["침수", "홍수", "범람", "하천범람", "도로침수", "지하침수"]

            flood_count = 0
            for msg in messages:
                msg_content = msg.get("MSG_CN", "")
                if any(keyword in msg_content for keyword in flood_keywords):
                    flood_count += 1

            print(f"   ✅ 재난이력 API: 최근 {years}년간 침수 관련 재난 {flood_count}건")
            return flood_count

        except Exception as e:
            print(f"   ⚠️  긴급재난문자 API 실패: {e}")
            raise ValueError(f"[TCFD 경고] 재난이력 조회 실패: {e}")

    def fetch_typhoon_besttrack(self, year: int) -> Dict:
        """
        기상청 태풍 베스트트랙 API에서 특정 년도의 모든 태풍 데이터 조회

        Args:
            year: 조회 연도 (2015-2022)

        Returns:
            {'typhoons': [...], 'data_source': 'kma_besttrack' or 'fallback'}
        """
        try:
            if not self.kma_api_key:
                print("⚠️ [TCFD 경고] KMA_API_KEY가 설정되지 않았습니다.")
                return {"typhoons": [], "data_source": "fallback"}

            # 모든 태풍 등급 조회
            params = {"year": str(year), "help": "2", "authKey": self.kma_api_key}  # 값만 표시

            response = requests.get(self.typhoon_api_base_url, params=params, timeout=30)

            if response.status_code == 200:
                typhoons = []
                lines = response.text.strip().split("\\n")

                for line in lines:
                    if line and not line.startswith("#"):
                        fields = line.split()
                        if len(fields) >= 10:
                            typhoons.append(
                                {
                                    "grade": fields[0],
                                    "tcid": fields[1],
                                    "year": int(fields[2]),
                                    "month": int(fields[3]),
                                    "day": int(fields[4]),
                                    "hour": int(fields[5]),
                                    "lon": float(fields[6]),
                                    "lat": float(fields[7]),
                                    "max_wind_speed": int(fields[8]),
                                    "central_pressure": int(fields[9]),
                                }
                            )

                return {"typhoons": typhoons, "data_source": "kma_besttrack"}
            else:
                print(f"⚠️ [TCFD 경고] 태풍 API 조회 실패: HTTP {response.status_code}")
                return {"typhoons": [], "data_source": "fallback"}

        except Exception as e:
            print(f"⚠️ [TCFD 경고] 태풍 베스트트랙 API 조회 실패: {e}")
            return {"typhoons": [], "data_source": "fallback"}


if __name__ == "__main__":
    # 테스트
    fetcher = DisasterAPIFetcher()

    print("\n[테스트 1] 하천정보 조회")
    try:
        river = fetcher.get_nearest_river_info(37.5172, 127.0473)
        print(f"결과: {river}")
    except Exception as e:
        print(f"실패: {e}")

    print("\n[테스트 2] 침수 이력 조회 (서울특별시)")
    try:
        count = fetcher.get_flood_history("서울특별시", years=5)
        print(f"결과: 침수 이력 {count}건")
    except Exception as e:
        print(f"실패: {e}")

    print("\n[테스트 3] 침수 이력 조회 (경기도)")
    try:
        count = fetcher.get_flood_history("경기도", years=5)
        print(f"결과: 침수 이력 {count}건")
    except Exception as e:
        print(f"실패: {e}")
