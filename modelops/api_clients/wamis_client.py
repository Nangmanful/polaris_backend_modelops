"""
WAMIS API 클라이언트

물관리정보시스템(WAMIS) API를 통해 수문 데이터를 조회합니다.

기능:
1. 관측소 목록 조회 (api_wamis_stations)
2. 수위 데이터 조회 (api_wamis_cache)
3. 유량 데이터 조회 (api_wamis_cache)
4. 강수량 데이터 조회 (api_wamis_cache)
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class WamisClient:
    """WAMIS API 클라이언트"""

    # 데이터 타입
    DATA_TYPE_WATER_LEVEL = "water_level"  # 수위 (m)
    DATA_TYPE_FLOW_RATE = "flow_rate"  # 유량 (m³/s)
    DATA_TYPE_RAINFALL = "rainfall"  # 강수량 (mm)

    def __init__(self, conn=None, cursor=None):
        """
        Args:
            conn: DB 커넥션 (선택)
            cursor: DB 커서 (선택)
        """
        self.conn = conn
        self.cursor = cursor

    def get_stations(self, data_type: str = None, region: str = None) -> List[Dict[str, Any]]:
        """
        WAMIS 관측소 목록 조회

        Args:
            data_type: 데이터 타입 ('water_level', 'flow_rate', 'rainfall')
            region: 지역 필터 (예: '서울', '경기')

        Returns:
            [
                {
                    'station_id': str,
                    'station_name': str,
                    'latitude': float,
                    'longitude': float,
                    'region': str,
                    'data_types': List[str]
                },
                ...
            ]
        """
        if self.conn is None or self.cursor is None:
            from ..database.connection import DatabaseConnection

            with DatabaseConnection.get_connection() as temp_conn:
                with temp_conn.cursor() as temp_cursor:
                    return self._get_stations_impl(data_type, region, temp_cursor)
        else:
            return self._get_stations_impl(data_type, region, self.cursor)

    def _get_stations_impl(self, data_type: str, region: str, cursor) -> List[Dict[str, Any]]:
        """관측소 목록 조회 구현"""

        # WHERE 조건 구성
        where_clauses = []
        params = []

        if data_type:
            where_clauses.append(f"data_types @> ARRAY[%s]::text[]")
            params.append(data_type)

        if region:
            where_clauses.append("region = %s")
            params.append(region)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # 쿼리 실행
        query = f"""
            SELECT
                station_id,
                station_name,
                latitude,
                longitude,
                region,
                data_types
            FROM api_wamis_stations
            {where_sql}
            ORDER BY station_id
        """

        cursor.execute(query, params)
        rows = cursor.fetchall()

        stations = []
        for row in rows:
            stations.append(
                {
                    "station_id": row[0],
                    "station_name": row[1],
                    "latitude": row[2],
                    "longitude": row[3],
                    "region": row[4],
                    "data_types": row[5],
                }
            )

        logger.info(
            f"WAMIS 관측소 조회: {len(stations)}개 " f"(data_type={data_type}, region={region})"
        )

        return stations

    def get_data(
        self,
        station_id: str,
        data_type: str,
        start_date: datetime = None,
        end_date: datetime = None,
    ) -> List[Dict[str, Any]]:
        """
        WAMIS 데이터 조회

        Args:
            station_id: 관측소 ID
            data_type: 데이터 타입 ('water_level', 'flow_rate', 'rainfall')
            start_date: 시작 일시 (기본: 7일 전)
            end_date: 종료 일시 (기본: 현재)

        Returns:
            [
                {
                    'station_id': str,
                    'data_type': str,
                    'observed_at': datetime,
                    'value': float
                },
                ...
            ]
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.now()

        if self.conn is None or self.cursor is None:
            from ..database.connection import DatabaseConnection

            with DatabaseConnection.get_connection() as temp_conn:
                with temp_conn.cursor() as temp_cursor:
                    return self._get_data_impl(
                        station_id, data_type, start_date, end_date, temp_cursor
                    )
        else:
            return self._get_data_impl(station_id, data_type, start_date, end_date, self.cursor)

    def _get_data_impl(
        self, station_id: str, data_type: str, start_date: datetime, end_date: datetime, cursor
    ) -> List[Dict[str, Any]]:
        """데이터 조회 구현"""

        query = """
            SELECT
                station_id,
                data_type,
                observed_at,
                value
            FROM api_wamis_cache
            WHERE station_id = %s
              AND data_type = %s
              AND observed_at BETWEEN %s AND %s
            ORDER BY observed_at
        """

        cursor.execute(query, (station_id, data_type, start_date, end_date))
        rows = cursor.fetchall()

        data = []
        for row in rows:
            data.append(
                {"station_id": row[0], "data_type": row[1], "observed_at": row[2], "value": row[3]}
            )

        logger.info(
            f"WAMIS 데이터 조회: {len(data)}건 "
            f"(station={station_id}, type={data_type}, "
            f"{start_date.date()} ~ {end_date.date()})"
        )

        return data

    def get_latest_value(self, station_id: str, data_type: str) -> Optional[float]:
        """
        최신 관측값 조회

        Args:
            station_id: 관측소 ID
            data_type: 데이터 타입

        Returns:
            최신 관측값 또는 None
        """
        if self.conn is None or self.cursor is None:
            from ..database.connection import DatabaseConnection

            with DatabaseConnection.get_connection() as temp_conn:
                with temp_conn.cursor() as temp_cursor:
                    return self._get_latest_value_impl(station_id, data_type, temp_cursor)
        else:
            return self._get_latest_value_impl(station_id, data_type, self.cursor)

    def _get_latest_value_impl(self, station_id: str, data_type: str, cursor) -> Optional[float]:
        """최신 관측값 조회 구현"""

        query = """
            SELECT value
            FROM api_wamis_cache
            WHERE station_id = %s
              AND data_type = %s
            ORDER BY observed_at DESC
            LIMIT 1
        """

        cursor.execute(query, (station_id, data_type))
        row = cursor.fetchone()

        if row:
            return row[0]
        return None

    def get_stations_near_grid(
        self,
        grid_lat: float,
        grid_lon: float,
        data_type: str = None,
        radius_km: float = 50.0,
        max_stations: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        격자 주변 관측소 조회

        Args:
            grid_lat: 격자 위도
            grid_lon: 격자 경도
            data_type: 데이터 타입 (선택)
            radius_km: 검색 반경 (km, 기본: 50km)
            max_stations: 최대 관측소 수 (기본: 10)

        Returns:
            [
                {
                    'station_id': str,
                    'station_name': str,
                    'latitude': float,
                    'longitude': float,
                    'distance_km': float,
                    'data_types': List[str]
                },
                ...
            ]
        """
        if self.conn is None or self.cursor is None:
            from ..database.connection import DatabaseConnection

            with DatabaseConnection.get_connection() as temp_conn:
                with temp_conn.cursor() as temp_cursor:
                    return self._get_stations_near_grid_impl(
                        grid_lat, grid_lon, data_type, radius_km, max_stations, temp_cursor
                    )
        else:
            return self._get_stations_near_grid_impl(
                grid_lat, grid_lon, data_type, radius_km, max_stations, self.cursor
            )

    def _get_stations_near_grid_impl(
        self,
        grid_lat: float,
        grid_lon: float,
        data_type: str,
        radius_km: float,
        max_stations: int,
        cursor,
    ) -> List[Dict[str, Any]]:
        """격자 주변 관측소 조회 구현"""

        radius_m = radius_km * 1000.0

        # WHERE 조건 구성
        where_clause = ""
        params = [grid_lon, grid_lat, grid_lon, grid_lat, radius_m]

        if data_type:
            where_clause = "AND data_types @> ARRAY[%s]::text[]"
            params.append(data_type)

        query = f"""
            SELECT
                station_id,
                station_name,
                latitude,
                longitude,
                data_types,
                ST_Distance(
                    ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) AS distance_m
            FROM api_wamis_stations
            WHERE ST_DWithin(
                ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s
            )
            {where_clause}
            ORDER BY distance_m
            LIMIT %s
        """

        params.append(max_stations)
        cursor.execute(query, params)
        rows = cursor.fetchall()

        stations = []
        for row in rows:
            stations.append(
                {
                    "station_id": row[0],
                    "station_name": row[1],
                    "latitude": row[2],
                    "longitude": row[3],
                    "data_types": row[4],
                    "distance_km": row[5] / 1000.0,
                }
            )

        logger.info(
            f"격자 주변 WAMIS 관측소 조회: {len(stations)}개 "
            f"(위치=({grid_lat}, {grid_lon}), 반경={radius_km}km)"
        )

        return stations

    def calculate_grid_value(
        self,
        grid_lat: float,
        grid_lon: float,
        data_type: str,
        start_date: datetime = None,
        end_date: datetime = None,
        radius_km: float = 50.0,
    ) -> Optional[float]:
        """
        격자별 관측값 계산 (IDW 보간)

        Args:
            grid_lat: 격자 위도
            grid_lon: 격자 경도
            data_type: 데이터 타입
            start_date: 시작 일시
            end_date: 종료 일시
            radius_km: 검색 반경 (km)

        Returns:
            격자별 평균 관측값 또는 None
        """
        # 1. 주변 관측소 조회
        stations = self.get_stations_near_grid(grid_lat, grid_lon, data_type, radius_km)

        if not stations:
            logger.warning(
                f"격자 주변 관측소 없음: ({grid_lat}, {grid_lon}), "
                f"type={data_type}, radius={radius_km}km"
            )
            return None

        # 2. 각 관측소의 평균 데이터 조회
        station_data = []
        for station in stations:
            data = self.get_data(station["station_id"], data_type, start_date, end_date)

            if data:
                # 기간 내 평균값 계산
                values = [d["value"] for d in data]
                avg_value = sum(values) / len(values)

                station_data.append(
                    {
                        "latitude": station["latitude"],
                        "longitude": station["longitude"],
                        "value": avg_value,
                    }
                )

        if not station_data:
            logger.warning(f"격자 주변 관측소 데이터 없음: ({grid_lat}, {grid_lon})")
            return None

        # 3. IDW 보간
        from ..utils.station_mapper import StationMapper

        try:
            interpolated_value = StationMapper.interpolate_to_grid(
                grid_lat, grid_lon, station_data, value_key="value", max_distance_km=radius_km
            )
            return interpolated_value
        except ValueError as e:
            logger.error(f"IDW 보간 실패: {e}")
            return None
