"""
파일명: building_characteristics_loader.py
작성일: 2025-12-16
버전: v02
파일 개요: 건축물 데이터 ETL (API → DB 적재)

================================================================================
[ 입력 데이터 요구사항 ]
================================================================================

1. load_and_cache() - 단일 건물 데이터 로드
   입력:
       - lat: float (위도, 필수) - 예: 37.405879
       - lon: float (경도, 필수) - 예: 127.099877
       - address: str (도로명 주소, 선택) - 예: "경기도 성남시 분당구 판교로 255번길 38"

   출력:
       - Dict: BuildingDataFetcher 형식의 건축물 데이터
         {
           "meta": {"pk", "name", "road_address", "admin_codes", "bun", "ji", ...},
           "physical_specs": {"structure_types", "purpose_types", "floors", "seismic", "age"},
           "floor_details": [...],
           ...
         }

2. load_batch() - 다중 건물 배치 로드
   입력:
       - sites: List[Dict] - 사이트 정보 리스트
         [
           {"site_id": "uuid-...", "lat": 37.405879, "lon": 127.099877, "address": "..."},
           ...
         ]

   출력:
       - Dict[str, Dict]: site_id별 건축물 데이터

================================================================================
[ DB 테이블 ]
================================================================================

building_aggregate_cache (datawarehouse DB):
    - PK: (sigungu_cd, bjdong_cd, bun, ji)
    - 주요 컬럼: road_address, building_count, structure_types, purpose_types,
                oldest_building_age_years, total_floor_area_sqm, ...

================================================================================
[ 사용 예시 ]
================================================================================

# 1. 초기화
loader = BuildingDataLoader(db_url="postgresql://...")

# 2. 단일 건물 로드 (API 호출 → DB 캐시 저장)
data = loader.load_and_cache(
    lat=37.405879,
    lon=127.099877,
    address="경기도 성남시 분당구 판교로 255번길 38"
)

# 3. 배치 로드
results = await loader.load_batch([
    {"site_id": "uuid-1", "lat": 37.405879, "lon": 127.099877, "address": "..."},
    {"site_id": "uuid-2", "lat": 37.3825, "lon": 127.1220, "address": "..."},
])

================================================================================
"""

from typing import Dict, Any, List, Optional
import logging
import os

# BuildingDataFetcher 임포트
try:
    from modelops.utils.building_data_fetcher import BuildingDataFetcher
except ImportError:
    try:
        # 직접 실행 시
        import sys
        import os

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from modelops.utils.building_data_fetcher import BuildingDataFetcher
    except ImportError:
        BuildingDataFetcher = None
        print("⚠️ BuildingDataFetcher를 임포트할 수 없습니다.")

# DatabaseManager 임포트
try:
    from modelops.utils.database import DatabaseManager
except ImportError:
    try:
        from modelops.database.connection import DatabaseConnection as DatabaseManager
    except ImportError:
        DatabaseManager = None
        print("⚠️ DatabaseManager를 임포트할 수 없습니다.")

logger = logging.getLogger(__name__)


class BuildingDataLoader:
    """
    건축물 데이터 ETL 클래스

    역할:
        1. API를 통한 건축물 데이터 수집 (BuildingDataFetcher)
        2. DB 캐시 저장 (building_aggregate_cache)
        3. DB 캐시 조회

    사용 예시:
        loader = BuildingDataLoader()
        # 단일 사업장 데이터 로드 및 캐시
        data = loader.load_and_cache(lat=35.1234, lon=129.0567, address="부산시...")

        # 배치 로드 (다중 사업장)
        results = await loader.load_batch([
            {"site_id": 1, "lat": 35.1234, "lon": 129.0567, "address": "부산시..."},
            ...
        ])
    """

    def __init__(self, db_url: Optional[str] = None):
        """
        초기화

        Args:
            db_url: Datawarehouse DB URL (building_aggregate_cache 테이블 접근용)
        """
        self.logger = logger

        # BuildingDataFetcher 초기화
        if BuildingDataFetcher:
            try:
                self.fetcher = BuildingDataFetcher()
                self.logger.info("BuildingDataFetcher 초기화 성공")
            except Exception as e:
                self.logger.error(f"BuildingDataFetcher 초기화 실패: {e}")
                self.fetcher = None
        else:
            self.fetcher = None

        # DatabaseManager 초기화 (datawarehouse DB)
        self.db_manager = None
        if DatabaseManager:
            try:
                dw_db_url = (
                    db_url or os.getenv("DATAWAREHOUSE_DATABASE_URL") or os.getenv("DATABASE_URL")
                )
                if dw_db_url:
                    self.db_manager = DatabaseManager(dw_db_url)
                    self.logger.info("DatabaseManager 초기화 성공 (building_aggregate_cache)")
                else:
                    self.logger.warning("DB URL이 설정되지 않음 - DB 캐시 비활성화")
            except Exception as e:
                self.logger.error(f"DatabaseManager 초기화 실패: {e}")
                self.db_manager = None

    def load_and_cache(self, lat: float, lon: float, address: str = None) -> Dict[str, Any]:
        """
        건축물 데이터 로드 및 DB 캐시 저장

        플로우:
            1. API로 데이터 조회
            2. DB 캐시에 저장
            3. 데이터 반환

        Args:
            lat: 위도
            lon: 경도
            address: 도로명 주소 (선택)

        Returns:
            BuildingDataFetcher 형식의 건축물 데이터
        """
        if not self.fetcher:
            self.logger.warning("Fetcher 없음, 빈 데이터 반환")
            return {}

        try:
            # 1. API로 데이터 조회
            data = self.fetcher.fetch_full_tcfd_data(lat, lon, address)

            if not data:
                self.logger.warning(f"API에서 데이터 조회 실패: lat={lat}, lon={lon}")
                return {}

            # 2. 주소 코드 추출 (meta에서 - 중첩 구조 대응)
            meta = data.get("meta", {})
            admin_codes = meta.get("admin_codes", {})

            # admin_codes가 있으면 거기서, 없으면 meta에서 직접
            sigungu_cd = admin_codes.get("sigungu_cd", "") or meta.get("sigungu_cd", "")
            bjdong_cd = admin_codes.get("bjdong_cd", "") or meta.get("bjdong_cd", "")

            # bun/ji는 road_address에서 파싱하거나 meta에서
            bun = meta.get("bun", "")
            ji = meta.get("ji", "")

            # bun/ji가 없으면 road_address에서 파싱 시도
            if not (bun and ji):
                road_addr = meta.get("road_address", "") or meta.get("address", "")
                # 도로명주소에서 번지 추출 로직은 BuildingDataFetcher가 이미 처리함
                # 여기서는 sigungu_cd/bjdong_cd만 있어도 저장 시도
                pass

            # 3개 SK 사업장 특별 처리 (좌표 기반 식별)
            is_daedeok = (36.37 < lat < 36.39) and (127.39 < lon < 127.41)
            is_sk_u_tower = (37.36 < lat < 37.37) and (127.10 < lon < 127.11)
            is_pangyo = (37.40 < lat < 37.41) and (127.09 < lon < 127.10)

            # 3. DB 캐시에 저장 (주소 코드가 있는 경우만)
            if self.db_manager and sigungu_cd and bjdong_cd and bun and ji:
                try:
                    self.db_manager.save_building_aggregate_cache(
                        sigungu_cd=sigungu_cd,
                        bjdong_cd=bjdong_cd,
                        bun=bun,
                        ji=ji,
                        building_data=data,
                    )
                    self.logger.info(f"✅ DB 캐시 저장 완료: {sigungu_cd}-{bjdong_cd}-{bun}-{ji}")
                except Exception as cache_error:
                    self.logger.warning(f"DB 캐시 저장 실패 (계속 진행): {cache_error}")
            elif (is_daedeok or is_sk_u_tower or is_pangyo) and self.db_manager:
                # SK 3개 사업장 강제 저장 (주소 코드 없을 때)
                site_name = (
                    "대덕 데이터센터"
                    if is_daedeok
                    else ("SK u타워" if is_sk_u_tower else "판교 캠퍼스")
                )
                self.logger.info(
                    f"🔧 {site_name} 강제 저장 시도: sigungu={sigungu_cd}, bjdong={bjdong_cd}, bun={bun}, ji={ji}"
                )

                # 빈 값 채우기 (사업장별 하드코딩)
                if is_daedeok:
                    if not sigungu_cd:
                        sigungu_cd = "30200"
                    if not bjdong_cd:
                        bjdong_cd = "14200"
                    if not bun:
                        bun = "0140"
                    if not ji:
                        ji = "0009"
                elif is_sk_u_tower:
                    if not sigungu_cd:
                        sigungu_cd = "41135"
                    if not bjdong_cd:
                        bjdong_cd = "10300"
                    if not bun:
                        bun = "0025"
                    if not ji:
                        ji = "0001"
                elif is_pangyo:
                    if not sigungu_cd:
                        sigungu_cd = "41135"
                    if not bjdong_cd:
                        bjdong_cd = "10900"
                    if not bun:
                        bun = "0612"
                    if not ji:
                        ji = "0004"

                try:
                    self.db_manager.save_building_aggregate_cache(
                        sigungu_cd=sigungu_cd,
                        bjdong_cd=bjdong_cd,
                        bun=bun,
                        ji=ji,
                        building_data=data,
                    )
                    self.logger.info(
                        f"✅ {site_name} 강제 저장 완료: {sigungu_cd}-{bjdong_cd}-{bun}-{ji}"
                    )
                except Exception as cache_error:
                    self.logger.warning(f"{site_name} 강제 저장 실패: {cache_error}")

            return data

        except Exception as e:
            self.logger.error(f"TCFD 데이터 조회 중 오류: {e}")
            return {}

    def fetch_from_cache(
        self, sigungu_cd: str, bjdong_cd: str, bun: str, ji: str
    ) -> Optional[Dict[str, Any]]:
        """
        DB 캐시에서 건축물 데이터 조회

        Args:
            sigungu_cd: 시군구 코드
            bjdong_cd: 법정동 코드
            bun: 번
            ji: 지

        Returns:
            BuildingDataFetcher 형식의 데이터 또는 None
        """
        if not self.db_manager:
            return None

        try:
            cache_data = self.db_manager.fetch_building_aggregate_cache(
                sigungu_cd=sigungu_cd, bjdong_cd=bjdong_cd, bun=bun, ji=ji
            )

            if cache_data:
                self.logger.info(f"DB 캐시에서 데이터 로드: {sigungu_cd}-{bjdong_cd}-{bun}-{ji}")
                return self.db_manager.convert_cache_to_building_data(cache_data)

            return None

        except Exception as e:
            self.logger.error(f"DB 캐시 조회 실패: {e}")
            return None

    async def load_batch(self, sites: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        """
        다중 사업장 건축물 데이터 배치 로드 및 캐시

        Args:
            sites: 사업장 정보 리스트
                [
                    {"site_id": 1, "lat": 35.1234, "lon": 129.0567, "address": "..."},
                    ...
                ]

        Returns:
            사업장별 건축물 데이터
                {
                    1: {...building_data...},
                    2: {...building_data...},
                    ...
                }
        """
        import asyncio

        self.logger.info(f"🔄 배치 건축물 데이터 로드 시작: {len(sites)}개 사업장")

        results = {}

        # 순차 처리 (API rate limit 고려)
        for site in sites:
            site_id = site.get("site_id")
            lat = site.get("lat")
            lon = site.get("lon")
            address = site.get("address")

            try:
                data = self.load_and_cache(lat, lon, address)
                results[site_id] = data
                self.logger.info(f"  ✓ 사업장 {site_id} 데이터 로드 완료")
            except Exception as e:
                self.logger.error(f"  ✗ 사업장 {site_id} 데이터 로드 실패: {e}")
                results[site_id] = {}

            # API rate limit 대응
            await asyncio.sleep(0.5)

        self.logger.info(f"✅ 배치 건축물 데이터 로드 완료: {len(results)}개")
        return results

    def get_or_load(
        self,
        lat: float,
        lon: float,
        address: str = None,
        sigungu_cd: str = None,
        bjdong_cd: str = None,
        bun: str = None,
        ji: str = None,
    ) -> Dict[str, Any]:
        """
        캐시 우선 조회, 없으면 API 호출

        플로우:
            1. 주소 코드가 있으면 DB 캐시 조회
            2. 캐시에 없으면 API 호출 → DB 저장

        Args:
            lat: 위도
            lon: 경도
            address: 도로명 주소 (선택)
            sigungu_cd: 시군구 코드 (선택, 캐시 조회용)
            bjdong_cd: 법정동 코드 (선택, 캐시 조회용)
            bun: 번 (선택, 캐시 조회용)
            ji: 지 (선택, 캐시 조회용)

        Returns:
            BuildingDataFetcher 형식의 건축물 데이터
        """
        # 1. 주소 코드가 있으면 캐시 우선 조회
        if sigungu_cd and bjdong_cd and bun and ji:
            cached = self.fetch_from_cache(sigungu_cd, bjdong_cd, bun, ji)
            if cached:
                self.logger.info("캐시에서 데이터 반환")
                return cached

        # 2. 캐시에 없으면 API 호출 → DB 저장
        return self.load_and_cache(lat, lon, address)

    # ==========================================================================
    # DB 조회만 하는 메서드 (Agent가 사용 - API 호출 X)
    # ==========================================================================

    def fetch_from_db_only(
        self,
        sigungu_cd: str = None,
        bjdong_cd: str = None,
        bun: str = None,
        ji: str = None,
        road_address: str = None,
    ) -> Optional[Dict[str, Any]]:
        """
        DB 캐시에서만 건축물 데이터 조회 (API 호출 X)
        → Agent가 사용하는 메서드

        Args:
            sigungu_cd: 시군구 코드 (선택)
            bjdong_cd: 법정동 코드 (선택)
            bun: 번 (선택)
            ji: 지 (선택)
            road_address: 도로명 주소 (선택, 주소 코드 없을 때 사용)

        Returns:
            BuildingDataFetcher 형식의 데이터 또는 None
        """
        if not self.db_manager:
            self.logger.warning("DB 연결 없음 - 조회 불가")
            return None

        # 1. 주소 코드가 있으면 직접 조회
        if sigungu_cd and bjdong_cd and bun and ji:
            return self.fetch_from_cache(sigungu_cd, bjdong_cd, bun, ji)

        # 2. 주소 코드 없으면 road_address로 조회
        if road_address:
            return self._fetch_by_road_address(road_address)

        self.logger.warning("주소 코드 또는 도로명 주소가 필요합니다")
        return None

    def _fetch_by_road_address(self, road_address: str) -> Optional[Dict[str, Any]]:
        """
        도로명 주소로 building_aggregate_cache 조회

        주소 정규화:
            - 공백 제거 후 비교 (판교로 255번길 → 판교로255번길)
            - 핵심 주소 부분만 추출 (도로명 + 번지)

        Args:
            road_address: 도로명 주소

        Returns:
            BuildingDataFetcher 형식의 데이터 또는 None
        """
        if not self.db_manager:
            return None

        try:
            # 핵심 주소 추출 (시도 시군구 도로명+번지)
            # 예: "경기도 성남시 분당구 판교로 255번길 38 SK판교캠퍼스"
            #   → "판교로255번길 38" 또는 "성남대로343번길 9"
            core_address = self._extract_core_address(road_address)

            query = """
                SELECT
                    cache_id,
                    sigungu_cd,
                    bjdong_cd,
                    bun,
                    ji,
                    jibun_address,
                    road_address,
                    building_count,
                    structure_types,
                    purpose_types,
                    max_ground_floors,
                    max_underground_floors,
                    min_underground_floors,
                    buildings_with_seismic,
                    buildings_without_seismic,
                    oldest_building_age_years,
                    total_floor_area_sqm,
                    total_building_area_sqm,
                    -- floor_details 제외 (동 전체 건물 데이터라 너무 큼, 보고서에서 미사용)
                    floor_purpose_types
                FROM building_aggregate_cache
                WHERE REPLACE(road_address, ' ', '') LIKE %s
                ORDER BY cached_at DESC
                LIMIT 1
            """
            # 공백 제거 후 부분 일치 검색
            search_pattern = f"%{core_address}%"
            results = self.db_manager.execute_query(query, (search_pattern,))

            if results:
                self.logger.info(
                    f"DB 캐시에서 주소로 데이터 로드: {road_address} (검색: {core_address})"
                )
                return self.db_manager.convert_cache_to_building_data(results[0])

            self.logger.warning(f"DB 캐시에 데이터 없음: {road_address} (검색: {core_address})")
            return None

        except Exception as e:
            self.logger.error(f"DB 캐시 조회 실패: {e}")
            return None

    def _extract_core_address(self, road_address: str) -> str:
        """
        도로명 주소에서 핵심 부분 추출 (공백 제거 + 도로명/번지만)

        예시:
            "경기도 성남시 분당구 판교로 255번길 38 SK판교캠퍼스"
            → "판교로255번길38"

            "경기도 성남시 분당구 성남대로 343번길 9 에스케이유타워"
            → "성남대로343번길9"

        Args:
            road_address: 전체 도로명 주소

        Returns:
            공백 제거된 핵심 주소 (도로명 + 번지)
        """
        import re

        # 공백 제거
        addr_no_space = road_address.replace(" ", "")

        # 도로명 + 번길/로 + 번지 패턴 추출
        # 예: 판교로255번길38, 성남대로343번길9
        pattern = r"([가-힣]+(?:로|길)\d+(?:번길)?)\s*(\d+)"
        match = re.search(pattern, addr_no_space)

        if match:
            return f"{match.group(1)}{match.group(2)}"

        # 패턴 매칭 실패시 공백 제거한 전체 주소 반환
        return addr_no_space

    def fetch_by_site_id(self, site_id: str) -> Optional[Dict[str, Any]]:
        """
        site_id로 건축물 데이터 조회 (sites 테이블 → building_aggregate_cache)

        플로우:
            1. sites 테이블에서 site_id로 주소 정보 조회
            2. 주소로 building_aggregate_cache 조회

        Args:
            site_id: 사업장 UUID

        Returns:
            BuildingDataFetcher 형식의 데이터 또는 None
        """
        if not self.db_manager:
            self.logger.warning("DB 연결 없음 - 조회 불가")
            return None

        try:
            # 1. sites 테이블에서 주소 정보 조회
            site_query = """
                SELECT address, latitude, longitude
                FROM sites
                WHERE id = %s
            """
            site_results = self.db_manager.execute_query(site_query, (site_id,))

            if not site_results:
                self.logger.warning(f"사업장 정보 없음: {site_id}")
                return None

            site = site_results[0]
            address = site.get("address")

            # 2. 주소로 building_aggregate_cache 조회
            if address:
                return self._fetch_by_road_address(address)

            self.logger.warning(f"사업장 주소 정보 없음: {site_id}")
            return None

        except Exception as e:
            self.logger.error(f"site_id로 건축물 데이터 조회 실패: {e}")
            return None
