"""
격자 매핑 유틸리티

사업장 좌표(latitude, longitude)를 기후 데이터 격자(grid_id)로 매핑합니다.

기능:
1. 좌표 → 최근접 격자 찾기
2. 0.01° 해상도 기반 격자 검색
3. PostGIS ST_Distance 기반 최근접 검색
"""

from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class GridMapper:
    """격자 매핑 클래스"""

    GRID_RESOLUTION = 0.01  # 격자 해상도 (°)

    @staticmethod
    def find_nearest_grid(
        latitude: float, longitude: float, conn=None, cursor=None
    ) -> Optional[Tuple[int, float, float]]:
        """
        사업장 좌표 → 최근접 격자 찾기

        Args:
            latitude: 위도
            longitude: 경도
            conn: DB 커넥션 (선택)
            cursor: DB 커서 (선택)

        Returns:
            (grid_id, grid_latitude, grid_longitude) 또는 None

        Raises:
            Exception: DB 조회 실패 시
        """
        if conn is None or cursor is None:
            from ..database.connection import DatabaseConnection

            with DatabaseConnection.get_connection() as temp_conn:
                with temp_conn.cursor() as temp_cursor:
                    return GridMapper._find_nearest_grid_impl(latitude, longitude, temp_cursor)
        else:
            return GridMapper._find_nearest_grid_impl(latitude, longitude, cursor)

    @staticmethod
    def _find_nearest_grid_impl(
        latitude: float, longitude: float, cursor
    ) -> Optional[Tuple[int, float, float]]:
        """최근접 격자 찾기 구현"""

        # 1단계: 0.01° 단위로 반올림하여 직접 검색
        rounded_lat = GridMapper._round_to_grid(latitude)
        rounded_lon = GridMapper._round_to_grid(longitude)

        cursor.execute(
            """
            SELECT grid_id, latitude, longitude
            FROM location_grid
            WHERE latitude = %s AND longitude = %s
            LIMIT 1
        """,
            (rounded_lat, rounded_lon),
        )

        result = cursor.fetchone()
        if result:
            logger.debug(f"직접 매칭: ({latitude}, {longitude}) → grid_id={result[0]}")
            return (result[0], result[1], result[2])

        # 2단계: 직접 매칭 실패 시 ST_Distance로 최근접 격자 찾기
        logger.warning(f"직접 매칭 실패, ST_Distance 검색: ({latitude}, {longitude})")

        cursor.execute(
            """
            SELECT
                grid_id,
                latitude,
                longitude,
                ST_Distance(
                    ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) AS distance_m
            FROM location_grid
            ORDER BY distance_m
            LIMIT 1
        """,
            (longitude, latitude),
        )

        result = cursor.fetchone()
        if result:
            logger.info(
                f"최근접 격자 매칭: ({latitude}, {longitude}) → "
                f"grid_id={result[0]} (거리: {result[3]:.2f}m)"
            )
            return (result[0], result[1], result[2])

        logger.error(f"격자 매칭 실패: ({latitude}, {longitude})")
        return None

    @staticmethod
    def _round_to_grid(value: float) -> float:
        """
        0.01° 단위로 반올림

        Args:
            value: 좌표값 (위도 또는 경도)

        Returns:
            반올림된 값
        """
        return round(value / GridMapper.GRID_RESOLUTION) * GridMapper.GRID_RESOLUTION

    @staticmethod
    def validate_coordinates(latitude: float, longitude: float) -> bool:
        """
        좌표 유효성 검증

        Args:
            latitude: 위도 (-90 ~ 90)
            longitude: 경도 (-180 ~ 180)

        Returns:
            유효하면 True
        """
        if not (-90 <= latitude <= 90):
            logger.error(f"위도 범위 오류: {latitude} (유효 범위: -90 ~ 90)")
            return False

        if not (-180 <= longitude <= 180):
            logger.error(f"경도 범위 오류: {longitude} (유효 범위: -180 ~ 180)")
            return False

        return True

    @staticmethod
    def get_grid_bounds(grid_latitude: float, grid_longitude: float) -> dict:
        """
        격자의 경계 좌표 계산

        Args:
            grid_latitude: 격자 중심 위도
            grid_longitude: 격자 중심 경도

        Returns:
            {
                'min_lat': float,
                'max_lat': float,
                'min_lon': float,
                'max_lon': float
            }
        """
        half_res = GridMapper.GRID_RESOLUTION / 2.0

        return {
            "min_lat": grid_latitude - half_res,
            "max_lat": grid_latitude + half_res,
            "min_lon": grid_longitude - half_res,
            "max_lon": grid_longitude + half_res,
        }

    @staticmethod
    def find_grids_in_radius(
        latitude: float, longitude: float, radius_km: float, conn=None, cursor=None
    ) -> list:
        """
        반경 내 격자 목록 조회

        Args:
            latitude: 중심 위도
            longitude: 중심 경도
            radius_km: 반경 (km)
            conn: DB 커넥션
            cursor: DB 커서

        Returns:
            [(grid_id, latitude, longitude, distance_m), ...]
        """
        if conn is None or cursor is None:
            from ..database.connection import DatabaseConnection

            with DatabaseConnection.get_connection() as temp_conn:
                with temp_conn.cursor() as temp_cursor:
                    return GridMapper._find_grids_in_radius_impl(
                        latitude, longitude, radius_km, temp_cursor
                    )
        else:
            return GridMapper._find_grids_in_radius_impl(latitude, longitude, radius_km, cursor)

    @staticmethod
    def _find_grids_in_radius_impl(
        latitude: float, longitude: float, radius_km: float, cursor
    ) -> list:
        """반경 내 격자 목록 조회 구현"""

        radius_m = radius_km * 1000.0

        cursor.execute(
            """
            SELECT
                grid_id,
                latitude,
                longitude,
                ST_Distance(
                    ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) AS distance_m
            FROM location_grid
            WHERE ST_DWithin(
                ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s
            )
            ORDER BY distance_m
        """,
            (longitude, latitude, longitude, latitude, radius_m),
        )

        results = cursor.fetchall()
        logger.info(
            f"반경 {radius_km}km 내 격자 {len(results)}개 조회: " f"({latitude}, {longitude})"
        )

        return [(r[0], r[1], r[2], r[3]) for r in results]
