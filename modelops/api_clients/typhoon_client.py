"""
태풍 API 클라이언트

태풍 Best Track API를 통해 태풍 경로 및 강도 데이터를 조회합니다.

기능:
1. 태풍 목록 조회 (api_typhoon_list)
2. 태풍 경로 조회 (api_typhoon_tracks)
3. 격자별 태풍 영향도 계산
"""

from typing import List, Dict, Any, Optional
import logging
import math

logger = logging.getLogger(__name__)


class TyphoonClient:
    """태풍 API 클라이언트"""

    # 태풍 강도 분류 (KMA 기준)
    INTENSITY_TROPICAL_DEPRESSION = "TD"  # 열대저압부 (< 17 m/s)
    INTENSITY_TROPICAL_STORM = "TS"  # 열대폭풍 (17-24 m/s)
    INTENSITY_SEVERE_TROPICAL_STORM = "STS"  # 강한열대폭풍 (25-32 m/s)
    INTENSITY_TYPHOON = "TY"  # 태풍 (33-43 m/s)
    INTENSITY_VERY_STRONG_TYPHOON = "STY"  # 강한태풍 (44-53 m/s)
    INTENSITY_SUPER_TYPHOON = "VSTY"  # 초강력태풍 (≥ 54 m/s)

    def __init__(self, conn=None, cursor=None):
        """
        Args:
            conn: DB 커넥션 (선택)
            cursor: DB 커서 (선택)
        """
        self.conn = conn
        self.cursor = cursor

    def get_typhoon_list(self, year: int = None, min_intensity: str = None) -> List[Dict[str, Any]]:
        """
        태풍 목록 조회

        Args:
            year: 발생 연도 (선택)
            min_intensity: 최소 강도 ('TS', 'TY' 등, 선택)

        Returns:
            [
                {
                    'typhoon_id': str,
                    'name_kr': str,
                    'name_en': str,
                    'year': int,
                    'max_wind_speed': float,
                    'max_pressure': float,
                    'intensity': str
                },
                ...
            ]
        """
        if self.conn is None or self.cursor is None:
            from ..database.connection import DatabaseConnection

            with DatabaseConnection.get_connection() as temp_conn:
                with temp_conn.cursor() as temp_cursor:
                    return self._get_typhoon_list_impl(year, min_intensity, temp_cursor)
        else:
            return self._get_typhoon_list_impl(year, min_intensity, self.cursor)

    def _get_typhoon_list_impl(self, year: int, min_intensity: str, cursor) -> List[Dict[str, Any]]:
        """태풍 목록 조회 구현"""

        # WHERE 조건 구성
        where_clauses = []
        params = []

        if year:
            where_clauses.append("year = %s")
            params.append(year)

        # min_intensity 필터링은 현재 DB 스키마에 grade 컬럼이 api_typhoon_info에 없으므로
        # 일단 목록을 가져온 뒤 애플리케이션 레벨에서 처리하거나,
        # 트랙 정보를 조인해야 하지만 여기서는 단순화를 위해 기본 정보만 조회합니다.
        # 필요하다면 api_typhoon_track과 조인하여 등급을 확인해야 합니다.

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # 쿼리 실행 (테이블명: api_typhoon_list -> api_typhoon_info)
        # 컬럼 매핑:
        # name_kr -> typ_name
        # name_en -> typ_en
        # max_wind_speed -> max_ws
        # max_pressure -> max_ps
        # intensity -> 없음 (필요 시 트랙 테이블 조인 필요)
        query = f"""
            SELECT
                typ_seq,
                typ_name,
                typ_en,
                year,
                max_ws,
                max_ps
            FROM api_typhoon_info
            {where_sql}
            ORDER BY year DESC, typ_seq DESC
        """

        cursor.execute(query, params)
        rows = cursor.fetchall()

        typhoons = []
        for row in rows:
            # 태풍 ID 생성 (YYYY-NNN 형식 또는 단순 SEQ)
            # 여기서는 typ_seq 사용
            typ_seq = row[0]
            year_val = row[3]
            typhoon_id = f"{year_val}-{typ_seq:03d}"

            typhoons.append(
                {
                    "typhoon_id": typhoon_id,
                    "typ_seq": typ_seq,
                    "name_kr": row[1],
                    "name_en": row[2],
                    "year": year_val,
                    "max_wind_speed": row[4],
                    "max_pressure": row[5],
                    "intensity": "",  # api_typhoon_info에는 등급 정보가 없음
                }
            )

        logger.info(
            f"태풍 목록 조회: {len(typhoons)}개 " f"(year={year}, min_intensity={min_intensity})"
        )

        return typhoons

    def get_typhoon_tracks(self, typhoon_id: str) -> List[Dict[str, Any]]:
        """
        태풍 경로 조회

        Args:
            typhoon_id: 태풍 ID (YYYY-NNN 형식 또는 dict에서 추출한 ID)
                        내부적으로는 typ_seq와 year를 분리해서 사용해야 함.
                        단순화를 위해 typhoon_id가 'YYYY-SEQ' 형식이라고 가정하거나
                        인자를 (year, typ_seq)로 받는 것이 좋으나 기존 시그니처 유지.

        Returns:
            track info list
        """
        # typhoon_id 파싱 (YYYY-NNN)
        try:
            year_str, seq_str = typhoon_id.split("-")
            year = int(year_str)
            typ_seq = int(seq_str)
        except ValueError:
            logger.error(f"잘못된 태풍 ID 형식: {typhoon_id} (Expected: YYYY-NNN)")
            return []

        if self.conn is None or self.cursor is None:
            from ..database.connection import DatabaseConnection

            with DatabaseConnection.get_connection() as temp_conn:
                with temp_conn.cursor() as temp_cursor:
                    return self._get_typhoon_tracks_impl(year, typ_seq, temp_cursor)
        else:
            return self._get_typhoon_tracks_impl(year, typ_seq, self.cursor)

    def _get_typhoon_tracks_impl(self, year: int, typ_seq: int, cursor) -> List[Dict[str, Any]]:
        """태풍 경로 조회 구현"""

        # 테이블명: api_typhoon_tracks -> api_typhoon_track
        # 컬럼 매핑:
        # track_time -> typ_tm (분석시각)
        # wind_speed -> wind_speed_ms
        # pressure -> pressure_hpa
        # radius_strong_wind -> rad15_km (강풍반경 15m/s)
        # intensity -> grade
        query = """
            SELECT
                typ_seq,
                typ_tm,
                latitude,
                longitude,
                wind_speed_ms,
                pressure_hpa,
                rad15_km,
                grade
            FROM api_typhoon_track
            WHERE year = %s AND typ_seq = %s
            ORDER BY typ_tm
        """

        cursor.execute(query, (year, typ_seq))
        rows = cursor.fetchall()

        tracks = []
        for row in rows:
            tracks.append(
                {
                    "typhoon_id": f"{year}-{row[0]:03d}",
                    "track_time": row[1],
                    "latitude": row[2],
                    "longitude": row[3],
                    "wind_speed": row[4],
                    "pressure": row[5],
                    "radius_strong_wind": row[6],
                    "intensity": row[7],
                }
            )

        logger.info(f"태풍 경로 조회: {len(tracks)}개 지점 (year={year}, seq={typ_seq})")

        return tracks

    def find_nearest_track_point(
        self, typhoon_id: str, grid_lat: float, grid_lon: float
    ) -> Optional[Dict[str, Any]]:
        """
        격자에서 가장 가까운 태풍 경로 지점 찾기

        Args:
            typhoon_id: 태풍 ID
            grid_lat: 격자 위도
            grid_lon: 격자 경도

        Returns:
            {
                'track_time': datetime,
                'latitude': float,
                'longitude': float,
                'wind_speed': float,
                'distance_km': float
            } 또는 None
        """
        tracks = self.get_typhoon_tracks(typhoon_id)

        if not tracks:
            return None

        # 각 경로 지점과의 거리 계산
        min_distance = float("inf")
        nearest_point = None

        for track in tracks:
            distance_km = self._haversine_distance(
                grid_lat, grid_lon, track["latitude"], track["longitude"]
            )

            if distance_km < min_distance:
                min_distance = distance_km
                nearest_point = {
                    "track_time": track["track_time"],
                    "latitude": track["latitude"],
                    "longitude": track["longitude"],
                    "wind_speed": track["wind_speed"],
                    "pressure": track["pressure"],
                    "radius_strong_wind": track["radius_strong_wind"],
                    "intensity": track["intensity"],
                    "distance_km": distance_km,
                }

        return nearest_point

    def calculate_grid_typhoon_impact(
        self, grid_lat: float, grid_lon: float, typhoon_id: str
    ) -> Dict[str, Any]:
        """
        격자별 태풍 영향도 계산

        Args:
            grid_lat: 격자 위도
            grid_lon: 격자 경도
            typhoon_id: 태풍 ID

        Returns:
            {
                'is_affected': bool,         # 영향권 여부
                'nearest_distance_km': float, # 최근접 거리
                'max_wind_speed': float,     # 최대 풍속 (m/s)
                'max_intensity': str,        # 최대 강도
                'impact_duration_hours': float  # 영향 지속 시간 (시간)
            }
        """
        tracks = self.get_typhoon_tracks(typhoon_id)

        if not tracks:
            return self._default_impact()

        # 영향권 판정: 강풍 반경 이내 또는 200km 이내
        affected_tracks = []
        min_distance = float("inf")
        max_wind_speed = 0.0
        max_intensity = "TD"

        intensity_scores = {"TD": 1, "TS": 2, "STS": 3, "TY": 4, "STY": 5, "VSTY": 6}

        for track in tracks:
            distance_km = self._haversine_distance(
                grid_lat, grid_lon, track["latitude"], track["longitude"]
            )

            # 최근접 거리 업데이트
            if distance_km < min_distance:
                min_distance = distance_km

            # 영향권 판정
            radius = track.get("radius_strong_wind", 200.0)
            if distance_km <= radius:
                affected_tracks.append(track)

                # 최대 풍속 업데이트
                if track["wind_speed"] > max_wind_speed:
                    max_wind_speed = track["wind_speed"]

                # 최대 강도 업데이트
                current_intensity = track.get("intensity", "TD")
                if intensity_scores.get(current_intensity, 0) > intensity_scores.get(
                    max_intensity, 0
                ):
                    max_intensity = current_intensity

        # 영향 지속 시간 계산 (3시간 간격 가정)
        impact_duration_hours = len(affected_tracks) * 3.0 if affected_tracks else 0.0

        return {
            "is_affected": len(affected_tracks) > 0,
            "nearest_distance_km": min_distance,
            "max_wind_speed": max_wind_speed,
            "max_intensity": max_intensity,
            "impact_duration_hours": impact_duration_hours,
        }

    def get_typhoons_affecting_grid(
        self,
        grid_lat: float,
        grid_lon: float,
        year_start: int = 2021,
        year_end: int = 2100,
        max_distance_km: float = 200.0,
    ) -> List[Dict[str, Any]]:
        """
        격자에 영향을 준 태풍 목록 조회

        Args:
            grid_lat: 격자 위도
            grid_lon: 격자 경도
            year_start: 시작 연도
            year_end: 종료 연도
            max_distance_km: 최대 영향 거리 (km, 기본: 200km)

        Returns:
            [
                {
                    'typhoon_id': str,
                    'name_kr': str,
                    'year': int,
                    'nearest_distance_km': float,
                    'max_wind_speed': float,
                    'max_intensity': str
                },
                ...
            ]
        """
        affecting_typhoons = []

        # 연도별 태풍 조회
        for year in range(year_start, year_end + 1):
            typhoons = self.get_typhoon_list(year=year)

            for typhoon in typhoons:
                impact = self.calculate_grid_typhoon_impact(
                    grid_lat, grid_lon, typhoon["typhoon_id"]
                )

                # 영향권 판정
                if impact["nearest_distance_km"] <= max_distance_km:
                    affecting_typhoons.append(
                        {
                            "typhoon_id": typhoon["typhoon_id"],
                            "name_kr": typhoon["name_kr"],
                            "year": typhoon["year"],
                            "nearest_distance_km": impact["nearest_distance_km"],
                            "max_wind_speed": impact["max_wind_speed"],
                            "max_intensity": impact["max_intensity"],
                        }
                    )

        logger.info(
            f"격자 영향 태풍 조회: {len(affecting_typhoons)}개 "
            f"(위치=({grid_lat}, {grid_lon}), {year_start}~{year_end})"
        )

        return affecting_typhoons

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Haversine 공식을 이용한 두 좌표 간 거리 계산 (km)

        Args:
            lat1, lon1: 첫 번째 좌표
            lat2, lon2: 두 번째 좌표

        Returns:
            거리 (km)
        """
        R = 6371.0  # 지구 반경 (km)

        # 라디안 변환
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        # Haversine 공식
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))

        distance = R * c
        return distance

    def _default_impact(self) -> Dict[str, Any]:
        """기본 영향도 (영향 없음)"""
        return {
            "is_affected": False,
            "nearest_distance_km": float("inf"),
            "max_wind_speed": 0.0,
            "max_intensity": "TD",
            "impact_duration_hours": 0.0,
        }
