"""
건물 정보 API 클라이언트

⚠️ DEPRECATED: 이 파일은 현재 사용되지 않습니다.
- 과거: api_buildings 테이블 사용
- 현재: building_aggregate_cache 테이블 사용 (connection.py 참조)

기능:
1. 격자별 건물 정보 조회
2. 건물 유형별 집계
3. 자산 가치 계산
"""

from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class BuildingClient:
    """건물 정보 클라이언트"""

    # 건물 용도 분류
    USAGE_RESIDENTIAL = "residential"  # 주거용
    USAGE_COMMERCIAL = "commercial"  # 상업용
    USAGE_INDUSTRIAL = "industrial"  # 산업용
    USAGE_PUBLIC = "public"  # 공공시설
    USAGE_AGRICULTURAL = "agricultural"  # 농업시설
    USAGE_OTHER = "other"  # 기타

    # 구조 유형
    STRUCTURE_REINFORCED_CONCRETE = "rc"  # 철근콘크리트
    STRUCTURE_STEEL = "steel"  # 철골조
    STRUCTURE_WOOD = "wood"  # 목조
    STRUCTURE_BRICK = "brick"  # 벽돌조
    STRUCTURE_OTHER = "other"  # 기타

    def __init__(self, conn=None, cursor=None):
        """
        Args:
            conn: DB 커넥션 (선택)
            cursor: DB 커서 (선택)
        """
        self.conn = conn
        self.cursor = cursor

    def get_buildings_in_grid(
        self, grid_lat: float, grid_lon: float, grid_resolution: float = 0.01
    ) -> List[Dict[str, Any]]:
        """
        격자 내 건물 조회

        Args:
            grid_lat: 격자 중심 위도
            grid_lon: 격자 중심 경도
            grid_resolution: 격자 해상도 (°, 기본: 0.01)

        Returns:
            [
                {
                    'building_id': str,
                    'latitude': float,
                    'longitude': float,
                    'usage_type': str,
                    'structure_type': str,
                    'floors': int,
                    'area_sqm': float,
                    'built_year': int,
                    'asset_value': float
                },
                ...
            ]
        """
        if self.conn is None or self.cursor is None:
            from ..database.connection import DatabaseConnection

            with DatabaseConnection.get_connection() as temp_conn:
                with temp_conn.cursor() as temp_cursor:
                    return self._get_buildings_in_grid_impl(
                        grid_lat, grid_lon, grid_resolution, temp_cursor
                    )
        else:
            return self._get_buildings_in_grid_impl(
                grid_lat, grid_lon, grid_resolution, self.cursor
            )

    def _get_buildings_in_grid_impl(
        self, grid_lat: float, grid_lon: float, grid_resolution: float, cursor
    ) -> List[Dict[str, Any]]:
        """격자 내 건물 조회 구현"""

        # 격자 경계 계산
        half_res = grid_resolution / 2.0
        min_lat = grid_lat - half_res
        max_lat = grid_lat + half_res
        min_lon = grid_lon - half_res
        max_lon = grid_lon + half_res

        query = """
            SELECT
                building_id,
                latitude,
                longitude,
                usage_type,
                structure_type,
                floors,
                area_sqm,
                built_year,
                asset_value
            FROM api_buildings
            WHERE latitude BETWEEN %s AND %s
              AND longitude BETWEEN %s AND %s
            ORDER BY asset_value DESC
        """

        cursor.execute(query, (min_lat, max_lat, min_lon, max_lon))
        rows = cursor.fetchall()

        buildings = []
        for row in rows:
            buildings.append(
                {
                    "building_id": row[0],
                    "latitude": row[1],
                    "longitude": row[2],
                    "usage_type": row[3],
                    "structure_type": row[4],
                    "floors": row[5],
                    "area_sqm": row[6],
                    "built_year": row[7],
                    "asset_value": row[8],
                }
            )

        logger.info(f"격자 내 건물 조회: {len(buildings)}개 " f"(위치=({grid_lat}, {grid_lon}))")

        return buildings

    def get_building_statistics(
        self, grid_lat: float, grid_lon: float, grid_resolution: float = 0.01
    ) -> Dict[str, Any]:
        """
        격자별 건물 통계 계산

        Args:
            grid_lat: 격자 중심 위도
            grid_lon: 격자 중심 경도
            grid_resolution: 격자 해상도 (°)

        Returns:
            {
                'total_buildings': int,
                'total_asset_value': float,
                'avg_asset_value': float,
                'by_usage': {
                    'residential': {'count': int, 'total_value': float},
                    ...
                },
                'by_structure': {
                    'rc': {'count': int, 'total_value': float},
                    ...
                },
                'avg_floors': float,
                'total_area_sqm': float
            }
        """
        buildings = self.get_buildings_in_grid(grid_lat, grid_lon, grid_resolution)

        if not buildings:
            return self._default_statistics()

        # 전체 통계
        total_buildings = len(buildings)
        total_asset_value = sum(b["asset_value"] for b in buildings)
        avg_asset_value = total_asset_value / total_buildings

        # 용도별 통계
        by_usage = {}
        for building in buildings:
            usage = building["usage_type"]
            if usage not in by_usage:
                by_usage[usage] = {"count": 0, "total_value": 0.0}
            by_usage[usage]["count"] += 1
            by_usage[usage]["total_value"] += building["asset_value"]

        # 구조별 통계
        by_structure = {}
        for building in buildings:
            structure = building["structure_type"]
            if structure not in by_structure:
                by_structure[structure] = {"count": 0, "total_value": 0.0}
            by_structure[structure]["count"] += 1
            by_structure[structure]["total_value"] += building["asset_value"]

        # 평균 층수, 총 면적
        avg_floors = sum(b["floors"] for b in buildings) / total_buildings
        total_area_sqm = sum(b["area_sqm"] for b in buildings)

        return {
            "total_buildings": total_buildings,
            "total_asset_value": total_asset_value,
            "avg_asset_value": avg_asset_value,
            "by_usage": by_usage,
            "by_structure": by_structure,
            "avg_floors": avg_floors,
            "total_area_sqm": total_area_sqm,
        }

    def find_high_value_buildings(
        self,
        grid_lat: float,
        grid_lon: float,
        min_value: float = 1000000000.0,
        grid_resolution: float = 0.01,
    ) -> List[Dict[str, Any]]:
        """
        고가 건물 조회

        Args:
            grid_lat: 격자 중심 위도
            grid_lon: 격자 중심 경도
            min_value: 최소 자산 가치 (원, 기본: 10억)
            grid_resolution: 격자 해상도 (°)

        Returns:
            고가 건물 목록 (자산 가치 내림차순)
        """
        buildings = self.get_buildings_in_grid(grid_lat, grid_lon, grid_resolution)

        high_value_buildings = [b for b in buildings if b["asset_value"] >= min_value]

        logger.info(
            f"고가 건물 조회: {len(high_value_buildings)}개 "
            f"(최소 가치={min_value:,.0f}원, 위치=({grid_lat}, {grid_lon}))"
        )

        return high_value_buildings

    def get_buildings_by_usage(
        self, grid_lat: float, grid_lon: float, usage_type: str, grid_resolution: float = 0.01
    ) -> List[Dict[str, Any]]:
        """
        용도별 건물 조회

        Args:
            grid_lat: 격자 중심 위도
            grid_lon: 격자 중심 경도
            usage_type: 용도 유형 (예: 'residential', 'commercial')
            grid_resolution: 격자 해상도 (°)

        Returns:
            해당 용도 건물 목록
        """
        buildings = self.get_buildings_in_grid(grid_lat, grid_lon, grid_resolution)

        filtered_buildings = [b for b in buildings if b["usage_type"] == usage_type]

        logger.info(
            f"용도별 건물 조회: {len(filtered_buildings)}개 "
            f"(용도={usage_type}, 위치=({grid_lat}, {grid_lon}))"
        )

        return filtered_buildings

    def calculate_exposure_score(
        self, grid_lat: float, grid_lon: float, grid_resolution: float = 0.01
    ) -> float:
        """
        격자별 노출도 점수 계산 (자산 가치 기반)

        Args:
            grid_lat: 격자 중심 위도
            grid_lon: 격자 중심 경도
            grid_resolution: 격자 해상도 (°)

        Returns:
            노출도 점수 (0.0 ~ 1.0)
        """
        stats = self.get_building_statistics(grid_lat, grid_lon, grid_resolution)

        if stats["total_buildings"] == 0:
            return 0.0

        # 자산 가치 정규화 (100억 기준)
        max_value = 10000000000.0  # 100억
        normalized_value = min(stats["total_asset_value"] / max_value, 1.0)

        # 건물 수 정규화 (100개 기준)
        max_buildings = 100.0
        normalized_count = min(stats["total_buildings"] / max_buildings, 1.0)

        # 노출도 점수 = 자산 가치 70% + 건물 수 30%
        exposure_score = normalized_value * 0.7 + normalized_count * 0.3

        logger.debug(
            f"노출도 점수 계산: {exposure_score:.3f} "
            f"(자산={stats['total_asset_value']:,.0f}원, "
            f"건물={stats['total_buildings']}개)"
        )

        return exposure_score

    def get_buildings_near_location(
        self, latitude: float, longitude: float, radius_km: float = 1.0, max_buildings: int = 100
    ) -> List[Dict[str, Any]]:
        """
        특정 위치 주변 건물 조회

        Args:
            latitude: 위도
            longitude: 경도
            radius_km: 검색 반경 (km, 기본: 1km)
            max_buildings: 최대 건물 수 (기본: 100)

        Returns:
            주변 건물 목록 (거리순 정렬)
        """
        if self.conn is None or self.cursor is None:
            from ..database.connection import DatabaseConnection

            with DatabaseConnection.get_connection() as temp_conn:
                with temp_conn.cursor() as temp_cursor:
                    return self._get_buildings_near_location_impl(
                        latitude, longitude, radius_km, max_buildings, temp_cursor
                    )
        else:
            return self._get_buildings_near_location_impl(
                latitude, longitude, radius_km, max_buildings, self.cursor
            )

    def _get_buildings_near_location_impl(
        self, latitude: float, longitude: float, radius_km: float, max_buildings: int, cursor
    ) -> List[Dict[str, Any]]:
        """특정 위치 주변 건물 조회 구현"""

        radius_m = radius_km * 1000.0

        query = """
            SELECT
                building_id,
                latitude,
                longitude,
                usage_type,
                structure_type,
                floors,
                area_sqm,
                built_year,
                asset_value,
                ST_Distance(
                    ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) AS distance_m
            FROM api_buildings
            WHERE ST_DWithin(
                ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s
            )
            ORDER BY distance_m
            LIMIT %s
        """

        cursor.execute(query, (longitude, latitude, longitude, latitude, radius_m, max_buildings))
        rows = cursor.fetchall()

        buildings = []
        for row in rows:
            buildings.append(
                {
                    "building_id": row[0],
                    "latitude": row[1],
                    "longitude": row[2],
                    "usage_type": row[3],
                    "structure_type": row[4],
                    "floors": row[5],
                    "area_sqm": row[6],
                    "built_year": row[7],
                    "asset_value": row[8],
                    "distance_km": row[9] / 1000.0,
                }
            )

        logger.info(
            f"위치 주변 건물 조회: {len(buildings)}개 "
            f"(위치=({latitude}, {longitude}), 반경={radius_km}km)"
        )

        return buildings

    def _default_statistics(self) -> Dict[str, Any]:
        """기본 통계 (건물 없음)"""
        return {
            "total_buildings": 0,
            "total_asset_value": 0.0,
            "avg_asset_value": 0.0,
            "by_usage": {},
            "by_structure": {},
            "avg_floors": 0.0,
            "total_area_sqm": 0.0,
        }
