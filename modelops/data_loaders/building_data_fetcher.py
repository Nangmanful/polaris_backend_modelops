#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Building Data Fetcher (DB 기반)
건물 정보 및 주소 정보를 PostgreSQL DB에서 조회

변경 이력:
    - 2025-12-14: API 기반 → DB 기반으로 전환
"""

import logging
from typing import Dict, Optional
from datetime import datetime

try:
    from ..database.connection import DatabaseConnection

    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# 통계 기반 Fallback 상수
try:
    from modelops.config.fallback_constants import (
        BUILDING_FALLBACK,
        RIVER_FALLBACK,
        COAST_FALLBACK,
        DATA_SOURCES,
    )

    FALLBACK_AVAILABLE = True
except ImportError:
    FALLBACK_AVAILABLE = False
    BUILDING_FALLBACK = {
        "building_age": 25,
        "structure": "reinforced_concrete",
        "main_purpose": "residential",
        "floors_above": 5,
        "floors_below": 1,
        "total_area": 1000.0,
    }
    RIVER_FALLBACK = {
        "distance_to_river_m": 10000.0,
        "watershed_area_km2": 100.0,
        "stream_order": 2,
    }
    COAST_FALLBACK = {
        "distance_to_coast_m": 50000.0,
    }

logger = logging.getLogger(__name__)


class BuildingDataFetcher:
    """
    건물 정보 조회 클래스 (DB 기반)

    데이터 소스: PostgreSQL DB
    테이블: api_vworld_geocode, api_river_info, location_grid 등
    """

    def __init__(self):
        """초기화"""
        if not DB_AVAILABLE:
            logger.warning("DatabaseConnection not available")

    def get_building_code_from_coords(self, lat: float, lon: float) -> Optional[Dict]:
        """
        위/경도 → 시군구코드, 법정동코드 조회

        Args:
            lat: 위도 (WGS84)
            lon: 경도 (WGS84)

        Returns:
            {
                'sigungu_cd': str,
                'bjdong_cd': str,
                'dong_code': str,
                'sido': str,
                'sigungu': str,
                'dong': str,
                'full_address': str,
                'data_source': str
            }
        """
        if not DB_AVAILABLE:
            return self._fallback_geocode()

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                # api_vworld_geocode에서 가장 가까운 좌표 찾기
                cursor.execute(
                    """
                    SELECT
                        sigungu_cd,
                        bjdong_cd,
                        dong_code,
                        sido,
                        sigungu,
                        dong,
                        full_address,
                        ST_Distance(
                            location::geography,
                            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                        ) AS distance_m
                    FROM api_vworld_geocode
                    ORDER BY location <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                    LIMIT 1
                """,
                    (lon, lat, lon, lat),
                )

                result = cursor.fetchone()

                if result:
                    return {
                        "sigungu_cd": result["sigungu_cd"],
                        "bjdong_cd": result["bjdong_cd"],
                        "dong_code": result["dong_code"],
                        "sido": result["sido"],
                        "sigungu": result["sigungu"],
                        "dong": result["dong"],
                        "full_address": result["full_address"],
                        "data_source": "DB",
                    }

                # api_vworld_geocode에서 찾지 못한 경우 fallback 반환
                # location_grid는 좌표만 저장하고 행정구역 정보는 없음
                return self._fallback_geocode()

        except Exception as e:
            logger.error(f"Failed to get building code: {e}")
            return self._fallback_geocode()

    def get_building_info(self, lat: float, lon: float) -> Dict:
        """
        위/경도로 건물 정보 조회 (building_aggregate_cache 테이블)

        Args:
            lat: 위도
            lon: 경도

        Returns:
            {
                'building_age': int,
                'structure': str,
                'main_purpose': str,
                'floors_above': int,
                'floors_below': int,
                'total_area': float,
                'has_seismic_design': bool,
                'data_source': str
            }
        """
        if not DB_AVAILABLE:
            return self._fallback_building()

        try:
            # 1. 좌표로 bjdong_cd 조회 (sigungu_cd는 location_grid에 없을 수 있음)
            geocode = self.get_building_code_from_coords(lat, lon)
            if not geocode or not geocode.get("bjdong_cd"):
                logger.warning(f"No geocode found for ({lat}, {lon})")
                return self._fallback_building()

            bjdong_cd = geocode["bjdong_cd"]

            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                # 2. building_aggregate_cache에서 해당 지역 건물 정보 조회 (bjdong_cd로)
                cursor.execute(
                    """
                    SELECT
                        oldest_building_age_years,
                        structure_types,
                        purpose_types,
                        max_ground_floors,
                        max_underground_floors,
                        total_floor_area_sqm,
                        buildings_with_seismic,
                        buildings_without_seismic,
                        building_count
                    FROM building_aggregate_cache
                    WHERE bjdong_cd = %s
                    ORDER BY building_count DESC
                    LIMIT 1
                """,
                    (bjdong_cd,),
                )

                result = cursor.fetchone()

                if result:
                    # structure_types에서 가장 많은 구조 타입 추출
                    structure = "reinforced_concrete"
                    if result["structure_types"]:
                        struct_types = result["structure_types"]
                        if isinstance(struct_types, dict) and struct_types:
                            structure = max(struct_types, key=struct_types.get)

                    # purpose_types에서 가장 많은 용도 추출
                    main_purpose = "residential"
                    if result["purpose_types"]:
                        purpose_types = result["purpose_types"]
                        if isinstance(purpose_types, dict) and purpose_types:
                            main_purpose = max(purpose_types, key=purpose_types.get)

                    # 내진설계 여부
                    with_seismic = result["buildings_with_seismic"] or 0
                    without_seismic = result["buildings_without_seismic"] or 0
                    has_seismic = with_seismic > without_seismic

                    return {
                        "building_age": result["oldest_building_age_years"] or 25,
                        "structure": structure,
                        "main_purpose": main_purpose,
                        "floors_above": result["max_ground_floors"] or 5,
                        "floors_below": result["max_underground_floors"] or 1,
                        "total_area": float(result["total_floor_area_sqm"] or 1000.0),
                        "has_seismic_design": has_seismic,
                        "has_piloti": False,  # 필로티 정보는 별도 조회 필요
                        "elevation_m": 50.0,  # DEM 기반 조회 필요
                        "data_source": "DB",
                    }

                logger.warning(f"No building data in cache for bjdong_cd={bjdong_cd}")
                return self._fallback_building()

        except Exception as e:
            logger.error(f"Failed to get building info: {e}")
            return self._fallback_building()

    def get_river_info(self, lat: float, lon: float) -> Dict:
        """
        가장 가까운 하천 정보 조회

        Args:
            lat: 위도
            lon: 경도

        Returns:
            {
                'river_name': str,
                'river_grade': int,
                'distance_to_river_m': float,
                'watershed_area_km2': float,
                'stream_order': int,
                'basin_name': str,
                'data_source': str
            }
        """
        if not DB_AVAILABLE:
            return self._fallback_river()

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    WITH river_distances AS (
                        SELECT
                            river_name,
                            river_grade,
                            watershed_area_km2,
                            flood_capacity,
                            basin_name,
                            LEAST(
                                COALESCE(ST_Distance(
                                    start_geom::geography,
                                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                                ), 999999999),
                                COALESCE(ST_Distance(
                                    end_geom::geography,
                                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                                ), 999999999)
                            ) AS distance_m
                        FROM api_river_info
                        WHERE start_geom IS NOT NULL OR end_geom IS NOT NULL
                    )
                    SELECT
                        river_name,
                        river_grade,
                        distance_m AS distance_to_river_m,
                        COALESCE(watershed_area_km2, 100.0) AS watershed_area_km2,
                        flood_capacity,
                        basin_name,
                        CASE
                            WHEN river_grade = 0 THEN 5
                            WHEN river_grade = 1 THEN 4
                            WHEN river_grade = 2 THEN 3
                            ELSE 2
                        END AS stream_order
                    FROM river_distances
                    ORDER BY distance_m ASC
                    LIMIT 1
                """,
                    (lon, lat, lon, lat),
                )

                result = cursor.fetchone()

                if result:
                    return {
                        "river_name": result["river_name"],
                        "river_grade": result["river_grade"],
                        "distance_to_river_m": float(result["distance_to_river_m"]),
                        "watershed_area_km2": float(result["watershed_area_km2"]),
                        "stream_order": int(result["stream_order"]),
                        "flood_capacity": result["flood_capacity"],
                        "basin_name": result["basin_name"],
                        "data_source": "DB",
                    }

                return self._fallback_river()

        except Exception as e:
            logger.error(f"Failed to get river info: {e}")
            return self._fallback_river()

    def get_distance_to_coast(self, lat: float, lon: float) -> float:
        """
        해안선까지의 거리 조회

        Args:
            lat: 위도
            lon: 경도

        Returns:
            거리 (미터)
        """
        if not DB_AVAILABLE:
            return COAST_FALLBACK.get("distance_to_coast_m", 50000.0)

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT
                        ST_Distance(
                            ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                        ) AS distance_m
                    FROM sea_level_grid
                    ORDER BY distance_m
                    LIMIT 1
                """,
                    (lon, lat),
                )

                result = cursor.fetchone()

                if result:
                    return float(result["distance_m"])

                return COAST_FALLBACK.get("distance_to_coast_m", 50000.0)

        except Exception as e:
            logger.error(f"Failed to get coast distance: {e}")
            return COAST_FALLBACK.get("distance_to_coast_m", 50000.0)

    def get_population_data(self, lat: float, lon: float, years: list = None) -> Dict:
        """
        좌표 기반 인구 데이터 조회 (현재 + 미래)

        데이터 소스: location_admin 테이블
        - level=3 (읍면동): population_current (현재인구)
        - level=1 (시도): population_2020~2050 (장래인구추계)

        Args:
            lat: 위도 (WGS84)
            lon: 경도 (WGS84)
            years: 조회할 연도 리스트 (기본값: [2020, 2025, 2030, 2040, 2050])

        Returns:
            {
                'emd_code': str,          # 읍면동 코드
                'emd_name': str,          # 읍면동 이름
                'sido_code': str,         # 시도 코드
                'sido_name': str,         # 시도 이름
                'population_current': int, # 읍면동 현재인구
                'population_by_year': {2020: int, 2030: int, ...},  # 시도 미래인구
                'population_2020': int,
                'population_2030': int,
                'population_2050': int,
                'data_source': str
            }
        """
        if years is None:
            years = [2020, 2025, 2030, 2040, 2050]

        if not DB_AVAILABLE:
            return self._fallback_population(years)

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                # 1. 좌표 → 읍면동(level=3) 찾기
                # location_admin.centroid는 SRID 5174 (Korean TM), 입력은 WGS84 (4326)
                cursor.execute(
                    """
                    SELECT
                        admin_code,
                        admin_name,
                        sido_code,
                        sigungu_code,
                        population_current
                    FROM location_admin
                    WHERE level = 3
                      AND centroid IS NOT NULL
                    ORDER BY centroid <-> ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 5174)
                    LIMIT 1
                """,
                    (lon, lat),
                )

                emd_result = cursor.fetchone()

                if not emd_result:
                    logger.warning(f"No 읍면동 found for ({lat}, {lon})")
                    return self._fallback_population(years)

                emd_code = emd_result["admin_code"]
                emd_name = emd_result["admin_name"]
                sido_code = emd_result["sido_code"]
                sigungu_code = emd_result["sigungu_code"]
                population_current = emd_result["population_current"] or 0

                # population_current가 없으면 api_sgis_population에서 시군구 인구 조회 (매핑 테이블 사용)
                if population_current == 0 and sido_code and sigungu_code:
                    cursor.execute(
                        """
                        SELECT SUM(asp.population) as pop
                        FROM sido_code_mapping sido
                        JOIN sigungu_code_mapping scm
                            ON sido.admin_sido = scm.sido_code
                        JOIN api_sgis_population asp
                            ON sido.sgis_sido = asp.sido_code
                            AND scm.sgis_sigungu = asp.sigungu_code
                        WHERE scm.sido_code = %s
                          AND scm.admin_sigungu = %s
                          AND asp.gender = 'total'
                    """,
                        (sido_code, sigungu_code),
                    )
                    sgis_result = cursor.fetchone()
                    if sgis_result and sgis_result["pop"]:
                        population_current = sgis_result["pop"]

                # 2. 시도(level=1)에서 미래인구 조회 시도
                cursor.execute(
                    """
                    SELECT
                        admin_name,
                        population_2020,
                        population_2025,
                        population_2030,
                        population_2035,
                        population_2040,
                        population_2045,
                        population_2050
                    FROM location_admin
                    WHERE level = 1
                      AND sido_code = %s
                """,
                    (sido_code,),
                )

                sido_result = cursor.fetchone()

                if not sido_result:
                    # Level=1이 없으면 현재 인구로 미래 인구 추정
                    logger.info(
                        f"Level=1 시도 데이터 없음 (sido_code={sido_code}), 현재 인구 기반 추정 사용"
                    )

                    # 전국 평균 인구 증감률 (통계청 2023 기준)
                    # 2024 → 2030: -2.5%, 2024 → 2050: -10%
                    growth_rates = {
                        2020: 0.02,  # 2024 대비 +2% (역추정)
                        2025: -0.005,  # 2024 대비 -0.5%
                        2030: -0.025,  # 2024 대비 -2.5%
                        2035: -0.045,  # 2024 대비 -4.5%
                        2040: -0.070,  # 2024 대비 -7%
                        2045: -0.085,  # 2024 대비 -8.5%
                        2050: -0.100,  # 2024 대비 -10%
                    }

                    population_by_year = {
                        year: int(population_current * (1 + rate))
                        for year, rate in growth_rates.items()
                    }

                    # 시도명 추출 (읍면동 이름에서)
                    sido_name = emd_name.split()[0] if emd_name else "알수없음"
                else:
                    sido_name = sido_result["admin_name"]

                    # 연도별 인구 데이터 매핑
                    population_by_year = {
                        2020: sido_result["population_2020"] or 0,
                        2025: sido_result["population_2025"] or 0,
                        2030: sido_result["population_2030"] or 0,
                        2035: sido_result["population_2035"] or 0,
                        2040: sido_result["population_2040"] or 0,
                        2045: sido_result["population_2045"] or 0,
                        2050: sido_result["population_2050"] or 0,
                    }

                return {
                    "emd_code": emd_code,
                    "emd_name": emd_name,
                    "sido_code": sido_code,
                    "sido_name": sido_name,
                    "population_current": population_current,
                    "population_by_year": population_by_year,
                    "population_2020": population_by_year.get(2020, 0),
                    "population_2030": population_by_year.get(2030, 0),
                    "population_2050": population_by_year.get(2050, 0),
                    "data_source": "DB",
                }

        except Exception as e:
            logger.error(f"Failed to get population data: {e}")
            return self._fallback_population(years)

    def _interpolate_population(
        self, population_by_year: Dict[int, int], target_years: list
    ) -> Dict[int, int]:
        """
        누락된 연도의 인구 데이터 보간

        Args:
            population_by_year: 연도별 인구 데이터
            target_years: 목표 연도 리스트

        Returns:
            보간된 연도별 인구 데이터
        """
        if not population_by_year:
            return {year: 0 for year in target_years}

        # 있는 데이터 연도 정렬
        known_years = sorted(population_by_year.keys())
        result = dict(population_by_year)

        for year in target_years:
            if year in result:
                continue

            # 선형 보간
            lower_year = None
            upper_year = None

            for ky in known_years:
                if ky < year:
                    lower_year = ky
                elif ky > year and upper_year is None:
                    upper_year = ky
                    break

            if lower_year and upper_year:
                # 두 점 사이 선형 보간
                lower_pop = population_by_year[lower_year]
                upper_pop = population_by_year[upper_year]
                ratio = (year - lower_year) / (upper_year - lower_year)
                result[year] = int(lower_pop + (upper_pop - lower_pop) * ratio)
            elif lower_year:
                # 마지막 연도 이후: 동일값 유지 (또는 추세 외삽)
                result[year] = population_by_year[lower_year]
            elif upper_year:
                # 첫 연도 이전: 동일값 유지
                result[year] = population_by_year[upper_year]
            else:
                result[year] = 0

        return result

    def _fallback_population(self, years: list) -> Dict:
        """인구 데이터 기본값"""
        return {
            "emd_code": None,
            "emd_name": None,
            "sido_code": None,
            "sido_name": None,
            "population_current": 0,
            "population_by_year": {year: 0 for year in years},
            "population_2020": 0,
            "population_2030": 0,
            "population_2050": 0,
            "data_source": "fallback",
        }

    def fetch_all_building_data(self, lat: float, lon: float) -> Dict:
        """
        모든 건물/공간 관련 데이터 통합 조회

        Args:
            lat: 위도
            lon: 경도

        Returns:
            통합된 건물/공간 데이터 딕셔너리
        """
        # 각 데이터 조회
        geocode = self.get_building_code_from_coords(lat, lon)
        building = self.get_building_info(lat, lon)
        river = self.get_river_info(lat, lon)
        coast_distance = self.get_distance_to_coast(lat, lon)
        population = self.get_population_data(lat, lon)

        return {
            # 주소 정보
            "sigungu_cd": geocode.get("sigungu_cd") if geocode else None,
            "bjdong_cd": geocode.get("bjdong_cd") if geocode else None,
            "dong_code": geocode.get("dong_code") if geocode else None,
            "sido": geocode.get("sido") if geocode else None,
            "sigungu": geocode.get("sigungu") if geocode else None,
            "dong": geocode.get("dong") if geocode else None,
            "full_address": geocode.get("full_address") if geocode else None,
            # 건물 정보
            "building_age": building.get("building_age", 25),
            "structure": building.get("structure", "reinforced_concrete"),
            "structure_type": building.get(
                "structure", "reinforced_concrete"
            ),  # alias for vulnerability agents
            "main_purpose": building.get("main_purpose", "residential"),
            "floors_above": building.get("floors_above", 5),
            "ground_floors": building.get("floors_above", 5),  # alias for exposure agents
            "floors_below": building.get("floors_below", 1),
            "total_area": building.get("total_area", 1000.0),
            "total_area_m2": building.get("total_area", 1000.0),  # alias for vulnerability agents
            "has_piloti": building.get("has_piloti", False),  # 필로티 여부
            "has_seismic_design": building.get("has_seismic_design", False),  # 내진설계 여부
            "elevation_m": building.get("elevation_m", 50.0),  # 해발고도 (DEM 기반)
            # 저수조 여부 (법적 요건: 6층 이상 또는 연면적 3000m² 이상)
            "has_water_tank": building.get(
                "has_water_tank",
                building.get("floors_above", 5) >= 6 or building.get("total_area", 1000.0) >= 3000,
            ),
            # 하천 정보
            "river_name": river.get("river_name"),
            "river_grade": river.get("river_grade"),
            "distance_to_river_m": river.get("distance_to_river_m", 10000.0),
            "watershed_area_km2": river.get("watershed_area_km2", 100.0),
            "stream_order": river.get("stream_order", 2),
            "basin_name": river.get("basin_name"),
            "flood_capacity": river.get("flood_capacity"),  # 하천 홍수량
            # 해안 정보
            "distance_to_coast_m": coast_distance,
            # 인구 정보
            "emd_code": population.get("emd_code"),
            "emd_name": population.get("emd_name"),
            "sido_code": population.get("sido_code"),
            "sido_name": population.get("sido_name"),
            "population_current": population.get("population_current", 0),
            "population_2020": population.get("population_2020", 0),
            "population_2030": population.get("population_2030", 0),
            "population_2050": population.get("population_2050", 0),
            "population_by_year": population.get("population_by_year", {}),
            "data_source": "DB",
        }

    def get_building_age(self, use_apr_day: str) -> int:
        """사용승인일로부터 건물 연령 계산"""
        try:
            if not use_apr_day:
                return BUILDING_FALLBACK.get("building_age", 25)

            # YYYYMMDD 형식
            year = int(use_apr_day[:4])
            current_year = datetime.now().year
            return current_year - year

        except Exception:
            return BUILDING_FALLBACK.get("building_age", 25)

    def classify_building_type(self, main_purpose: str) -> str:
        """건물 용도 분류"""
        if not main_purpose:
            return "residential"

        purpose_lower = main_purpose.lower()

        if any(kw in purpose_lower for kw in ["주거", "아파트", "주택", "다세대", "연립"]):
            return "residential"
        elif any(kw in purpose_lower for kw in ["상업", "사무", "오피스", "업무"]):
            return "commercial"
        elif any(kw in purpose_lower for kw in ["공장", "산업", "제조", "창고"]):
            return "industrial"
        elif any(kw in purpose_lower for kw in ["공공", "관공서", "교육", "학교"]):
            return "public"
        else:
            return "mixed"

    # ==================== Fallback 메서드 ====================

    def _fallback_geocode(self) -> Dict:
        """지오코딩 기본값"""
        return {
            "sigungu_cd": None,
            "bjdong_cd": None,
            "dong_code": None,
            "sido": None,
            "sigungu": None,
            "dong": None,
            "full_address": None,
            "data_source": "fallback",
        }

    def _fallback_building(self) -> Dict:
        """건물 정보 기본값"""
        return {
            "building_age": BUILDING_FALLBACK.get("building_age", 25),
            "structure": BUILDING_FALLBACK.get("structure", "reinforced_concrete"),
            "main_purpose": BUILDING_FALLBACK.get("main_purpose", "residential"),
            "floors_above": BUILDING_FALLBACK.get("floors_above", 5),
            "floors_below": BUILDING_FALLBACK.get("floors_below", 1),
            "total_area": BUILDING_FALLBACK.get("total_area", 1000.0),
            "data_source": "fallback",
        }

    def _fallback_river(self) -> Dict:
        """하천 정보 기본값"""
        return {
            "river_name": None,
            "river_grade": None,
            "distance_to_river_m": RIVER_FALLBACK.get("distance_to_river_m", 10000.0),
            "watershed_area_km2": RIVER_FALLBACK.get("watershed_area_km2", 100.0),
            "stream_order": RIVER_FALLBACK.get("stream_order", 2),
            "flood_capacity": None,
            "basin_name": None,
            "data_source": "fallback",
        }


# 하위 호환성을 위한 alias
BuildingFetcher = BuildingDataFetcher
