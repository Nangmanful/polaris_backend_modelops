#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Spatial Data Loader (DB 기반)
공간 데이터 로드: 토지피복도, DEM, 하천정보, 해안선 등

변경 이력:
    - 2025-12-14: 파일 기반 → DB 기반으로 전환
"""

import logging
from typing import Dict

try:
    from ..database.connection import DatabaseConnection

    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

logger = logging.getLogger(__name__)


class SpatialDataLoader:
    """
    공간 데이터 로더 (DB 기반)

    데이터 소스: PostgreSQL DB
    테이블: raw_dem, raw_landcover, api_river_info, sea_level_grid 등
    """

    # 토지피복 코드 → 유형 매핑 (환경부 토지피복분류)
    LANDCOVER_MAP = {
        1: {"type": "water", "impervious": 0.0, "vegetation": 0.0, "urban": "none"},
        2: {"type": "urban", "impervious": 0.9, "vegetation": 0.1, "urban": "high"},
        3: {"type": "agricultural", "impervious": 0.2, "vegetation": 0.6, "urban": "low"},
        4: {"type": "forest", "impervious": 0.05, "vegetation": 0.95, "urban": "none"},
        5: {"type": "grassland", "impervious": 0.1, "vegetation": 0.8, "urban": "low"},
        6: {"type": "wetland", "impervious": 0.1, "vegetation": 0.7, "urban": "none"},
        7: {"type": "barren", "impervious": 0.3, "vegetation": 0.1, "urban": "low"},
    }

    def __init__(self, base_dir: str = None):
        """
        Args:
            base_dir: (레거시, 무시됨) 데이터 기본 경로
        """
        self._cache = {}

        if not DB_AVAILABLE:
            logger.warning("DatabaseConnection not available")

    def get_landcover_data(self, lat: float, lon: float) -> Dict:
        """
        토지피복도 데이터 추출

        Args:
            lat: 위도 (WGS84)
            lon: 경도 (WGS84)

        Returns:
            {
                'landcover_type': str,
                'landcover_code': int,
                'impervious_ratio': float,
                'vegetation_ratio': float,
                'urban_intensity': str,
                'data_source': str
            }
        """
        if not DB_AVAILABLE:
            return self._fallback_landcover()

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                # WGS84 좌표로 래스터 값 조회
                cursor.execute(
                    """
                    SELECT ST_Value(
                        rast,
                        ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), ST_SRID(rast))
                    ) AS landcover_code
                    FROM raw_landcover
                    WHERE ST_Intersects(
                        rast,
                        ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), ST_SRID(rast))
                    )
                    LIMIT 1
                """,
                    (lon, lat, lon, lat),
                )

                result = cursor.fetchone()

                if result and result["landcover_code"] is not None:
                    code = int(result["landcover_code"])
                    landcover_info = self.LANDCOVER_MAP.get(
                        code,
                        {
                            "type": "unknown",
                            "impervious": 0.5,
                            "vegetation": 0.3,
                            "urban": "medium",
                        },
                    )

                    return {
                        "landcover_type": landcover_info["type"],
                        "landcover_code": code,
                        "impervious_ratio": landcover_info["impervious"],
                        "vegetation_ratio": landcover_info["vegetation"],
                        "urban_intensity": landcover_info["urban"],
                        "data_source": "DB",
                    }

                return self._fallback_landcover()

        except Exception as e:
            logger.error(f"Failed to get landcover data: {e}")
            return self._fallback_landcover()

    def get_dem_data(self, lat: float, lon: float) -> Dict:
        """
        DEM 고도 데이터 추출

        Args:
            lat: 위도 (WGS84)
            lon: 경도 (WGS84)

        Returns:
            {
                'elevation_m': float,
                'slope_degree': float,
                'aspect': str,
                'region': str,
                'data_source': str
            }
        """
        if not DB_AVAILABLE:
            return self._fallback_dem()

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                # WGS84 좌표를 EPSG:5186으로 변환 후 가장 가까운 DEM 포인트 찾기
                cursor.execute(
                    """
                    WITH target_point AS (
                        SELECT ST_Transform(
                            ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                            5186
                        ) AS geom
                    )
                    SELECT
                        d.elevation,
                        d.region,
                        ST_Distance(d.geom, t.geom) AS distance_m
                    FROM raw_dem d, target_point t
                    ORDER BY d.geom <-> t.geom
                    LIMIT 1
                """,
                    (lon, lat),
                )

                result = cursor.fetchone()

                if result and result["distance_m"] < 1000:  # 1km 이내
                    return {
                        "elevation_m": float(result["elevation"]),
                        "slope_degree": 0.0,  # 별도 계산 필요
                        "aspect": "flat",  # 별도 계산 필요
                        "region": result["region"],
                        "data_source": "DB",
                    }

                return self._fallback_dem()

        except Exception as e:
            logger.error(f"Failed to get DEM data: {e}")
            return self._fallback_dem()

    def get_river_data(self, lat: float, lon: float) -> Dict:
        """
        하천 정보 추출

        Args:
            lat: 위도 (WGS84)
            lon: 경도 (WGS84)

        Returns:
            {
                'river_name': str,
                'river_grade': int,
                'distance_to_river_m': float,
                'watershed_area_km2': float,
                'stream_order': int,
                'flood_capacity': float,
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
                            WHEN river_grade = 0 THEN 5  -- 국가하천
                            WHEN river_grade = 1 THEN 4  -- 지방1급
                            WHEN river_grade = 2 THEN 3  -- 지방2급
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
            logger.error(f"Failed to get river data: {e}")
            return self._fallback_river()

    def get_coast_data(self, lat: float, lon: float) -> Dict:
        """
        해안선 관련 데이터 추출

        Args:
            lat: 위도 (WGS84)
            lon: 경도 (WGS84)

        Returns:
            {
                'distance_to_coast_m': float,
                'is_coastal': bool,
                'data_source': str
            }
        """
        if not DB_AVAILABLE:
            return self._fallback_coast()

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                # sea_level_grid에서 가장 가까운 격자와의 거리 계산
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
                    distance_m = float(result["distance_m"])
                    # 해안 격자까지의 거리를 해안선 거리로 근사
                    return {
                        "distance_to_coast_m": distance_m,
                        "is_coastal": distance_m < 10000,  # 10km 이내면 해안지역
                        "data_source": "DB",
                    }

                return self._fallback_coast()

        except Exception as e:
            logger.error(f"Failed to get coast data: {e}")
            return self._fallback_coast()

    def get_spatial_data(self, lat: float, lon: float) -> Dict:
        """
        모든 공간 데이터를 통합 조회

        Args:
            lat: 위도 (WGS84)
            lon: 경도 (WGS84)

        Returns:
            통합된 공간 데이터 딕셔너리
        """
        # 각 데이터 조회
        landcover = self.get_landcover_data(lat, lon)
        dem = self.get_dem_data(lat, lon)
        river = self.get_river_data(lat, lon)
        coast = self.get_coast_data(lat, lon)

        return {
            # 토지피복
            "landcover_type": landcover.get("landcover_type", "urban"),
            "landcover_code": landcover.get("landcover_code"),
            "impervious_ratio": landcover.get("impervious_ratio", 0.6),
            "imperviousness_ratio": landcover.get("impervious_ratio", 0.6),  # alias
            "vegetation_ratio": landcover.get("vegetation_ratio", 0.2),
            "urban_intensity": landcover.get("urban_intensity", "medium"),
            # 고도
            "elevation_m": dem.get("elevation_m", 50.0),
            "slope_degree": dem.get("slope_degree", 0.0),
            "region": dem.get("region"),
            # 하천
            "river_name": river.get("river_name"),
            "river_grade": river.get("river_grade"),
            "distance_to_river_m": river.get("distance_to_river_m", 10000.0),
            "watershed_area_km2": river.get("watershed_area_km2", 100.0),
            "stream_order": river.get("stream_order", 2),
            "flood_capacity": river.get("flood_capacity"),
            "basin_name": river.get("basin_name"),
            # 해안
            "distance_to_coast_m": coast.get("distance_to_coast_m", 50000.0),
            "is_coastal": coast.get("is_coastal", False),
            "data_source": "DB",
        }

    def get_ndvi_data(self, lat: float, lon: float) -> Dict:
        """
        NDVI 데이터 추출 (현재 DB에 없음, fallback 사용)

        Returns:
            {
                'ndvi': float,
                'vegetation_health': str,
                'data_source': str
            }
        """
        # TODO: NDVI 데이터가 DB에 적재되면 구현
        return self._fallback_ndvi()

    def get_soil_moisture_data(self, lat: float, lon: float) -> Dict:
        """
        토양 수분 데이터 추출

        Returns:
            {
                'soil_moisture': float,
                'moisture_level': str,
                'data_source': str
            }
        """
        # TODO: raw_drought 테이블에 soil_moisture 컬럼이 없음
        # 래스터 데이터만 있는 구조이므로 추후 구현 필요
        # DBML 참조: raw_drought는 rid, rast, filename 컬럼만 보유
        return self._fallback_soil_moisture()

    def get_administrative_area(self, lat: float, lon: float) -> Dict:
        """
        행정구역 정보 추출

        Returns:
            {
                'sido': str,
                'sigungu': str,
                'dong': str,
                'full_address': str,
                'data_source': str
            }
        """
        if not DB_AVAILABLE:
            return self._fallback_admin()

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                # location_grid에서 행정구역 정보 조회
                cursor.execute(
                    """
                    SELECT sido, sigungu, dong, full_address
                    FROM location_grid
                    ORDER BY SQRT(POWER(longitude - %s, 2) + POWER(latitude - %s, 2))
                    LIMIT 1
                """,
                    (lon, lat),
                )

                result = cursor.fetchone()

                if result:
                    return {
                        "sido": result["sido"],
                        "sigungu": result["sigungu"],
                        "dong": result["dong"],
                        "full_address": result["full_address"],
                        "data_source": "DB",
                    }

                return self._fallback_admin()

        except Exception as e:
            logger.error(f"Failed to get administrative area: {e}")
            return self._fallback_admin()

    # ==================== Fallback 메서드 ====================

    def _fallback_landcover(self) -> Dict:
        """토지피복 기본값"""
        return {
            "landcover_type": "urban",
            "landcover_code": 2,
            "impervious_ratio": 0.6,
            "vegetation_ratio": 0.2,
            "urban_intensity": "medium",
            "data_source": "fallback",
        }

    def _fallback_dem(self) -> Dict:
        """DEM 기본값"""
        return {
            "elevation_m": 50.0,
            "slope_degree": 5.0,
            "aspect": "flat",
            "region": None,
            "data_source": "fallback",
        }

    def _fallback_river(self) -> Dict:
        """하천 기본값"""
        return {
            "river_name": None,
            "river_grade": None,
            "distance_to_river_m": 10000.0,
            "watershed_area_km2": 100.0,
            "stream_order": 2,
            "flood_capacity": None,
            "basin_name": None,
            "data_source": "fallback",
        }

    def _fallback_coast(self) -> Dict:
        """해안 기본값"""
        return {"distance_to_coast_m": 50000.0, "is_coastal": False, "data_source": "fallback"}

    def _fallback_ndvi(self) -> Dict:
        """NDVI 기본값"""
        return {"ndvi": 0.5, "vegetation_health": "moderate", "data_source": "fallback"}

    def _fallback_soil_moisture(self) -> Dict:
        """토양수분 기본값"""
        return {"soil_moisture": 0.5, "moisture_level": "moderate", "data_source": "fallback"}

    def _fallback_admin(self) -> Dict:
        """행정구역 기본값"""
        return {
            "sido": None,
            "sigungu": None,
            "dong": None,
            "full_address": None,
            "data_source": "fallback",
        }
