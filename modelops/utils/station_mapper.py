"""
관측소 → 격자 보간 유틸리티

기상 관측소 데이터를 격자 데이터로 보간합니다.
IDW (Inverse Distance Weighting) 방식 사용.

사용 예시:
- 태풍 경로상 관측소 풍속 → 격자별 풍속 추정
- WAMIS 관측소 수위 → 격자별 수위 추정
"""

from typing import List, Dict, Tuple, Any
import logging
import math

logger = logging.getLogger(__name__)


class StationMapper:
    """관측소 → 격자 보간 클래스"""

    # IDW 파라미터
    DEFAULT_POWER = 2.0  # 거리 가중치 지수 (일반적으로 2 사용)
    DEFAULT_MAX_DISTANCE_KM = 50.0  # 최대 보간 거리 (km)
    MIN_STATIONS = 3  # 최소 필요 관측소 수

    @staticmethod
    def interpolate_to_grid(
        grid_lat: float,
        grid_lon: float,
        station_data: List[Dict[str, Any]],
        value_key: str = "value",
        power: float = DEFAULT_POWER,
        max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
    ) -> float:
        """
        IDW를 이용한 관측소 데이터 → 격자 보간

        Args:
            grid_lat: 격자 위도
            grid_lon: 격자 경도
            station_data: 관측소 데이터 리스트
                [
                    {'latitude': 37.5, 'longitude': 127.0, 'value': 25.3},
                    ...
                ]
            value_key: 보간할 값의 키 (기본: 'value')
            power: IDW 거리 가중치 지수 (기본: 2.0)
            max_distance_km: 최대 보간 거리 (기본: 50km)

        Returns:
            보간된 값

        Raises:
            ValueError: 관측소 수가 부족하거나 데이터가 없는 경우
        """
        if not station_data:
            raise ValueError("관측소 데이터가 없습니다")

        # 1. 각 관측소와의 거리 계산
        distances_and_values = []
        for station in station_data:
            if value_key not in station:
                continue

            s_lat = station.get("latitude")
            s_lon = station.get("longitude")
            if s_lat is None or s_lon is None:
                continue

            distance_km = StationMapper._haversine_distance(grid_lat, grid_lon, s_lat, s_lon)

            # 최대 거리 이내만 사용
            if distance_km <= max_distance_km:
                distances_and_values.append((distance_km, station[value_key]))

        if len(distances_and_values) < StationMapper.MIN_STATIONS:
            logger.warning(
                f"관측소 수 부족: {len(distances_and_values)}개 "
                f"(최소 {StationMapper.MIN_STATIONS}개 필요)"
            )
            # 관측소 수가 부족하면 가장 가까운 관측소 값 반환
            if distances_and_values:
                distances_and_values.sort(key=lambda x: x[0])
                return distances_and_values[0][1]
            else:
                raise ValueError(f"최대 거리 {max_distance_km}km 이내에 관측소가 없습니다")

        # 2. IDW 보간
        interpolated_value = StationMapper._idw_interpolation(distances_and_values, power)

        logger.debug(
            f"IDW 보간: ({grid_lat}, {grid_lon}) = {interpolated_value:.2f} "
            f"(관측소 {len(distances_and_values)}개)"
        )

        return interpolated_value

    @staticmethod
    def _idw_interpolation(distances_and_values: List[Tuple[float, float]], power: float) -> float:
        """
        IDW (Inverse Distance Weighting) 보간 계산

        공식: value = Σ(wi × vi) / Σ(wi)
        여기서 wi = 1 / (di^power)

        Args:
            distances_and_values: [(distance_km, value), ...]
            power: 거리 가중치 지수

        Returns:
            보간된 값
        """
        # 거리가 0인 경우 (정확히 관측소 위치) 해당 값 직접 반환
        for dist, value in distances_and_values:
            if dist < 0.001:  # 1m 이내
                return value

        # IDW 계산
        weight_sum = 0.0
        weighted_value_sum = 0.0

        for dist, value in distances_and_values:
            weight = 1.0 / (dist**power)
            weighted_value_sum += weight * value
            weight_sum += weight

        return weighted_value_sum / weight_sum if weight_sum > 0 else 0.0

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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

    @staticmethod
    def find_nearest_stations(
        grid_lat: float,
        grid_lon: float,
        station_list: List[Dict[str, Any]],
        n_nearest: int = 5,
        max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
    ) -> List[Dict[str, Any]]:
        """
        격자에서 가장 가까운 N개 관측소 찾기

        Args:
            grid_lat: 격자 위도
            grid_lon: 격자 경도
            station_list: 관측소 목록
                [
                    {'station_id': 'STN001', 'latitude': 37.5, 'longitude': 127.0, ...},
                    ...
                ]
            n_nearest: 찾을 관측소 수 (기본: 5)
            max_distance_km: 최대 거리 (기본: 50km)

        Returns:
            가까운 관측소 목록 (거리순 정렬)
            [
                {'station_id': 'STN001', ..., 'distance_km': 12.3},
                ...
            ]
        """
        stations_with_distance = []

        for station in station_list:
            s_lat = station.get("latitude")
            s_lon = station.get("longitude")
            if s_lat is None or s_lon is None:
                continue

            distance_km = StationMapper._haversine_distance(grid_lat, grid_lon, s_lat, s_lon)

            if distance_km <= max_distance_km:
                station_copy = station.copy()
                station_copy["distance_km"] = distance_km
                stations_with_distance.append(station_copy)

        # 거리순 정렬
        stations_with_distance.sort(key=lambda x: x["distance_km"])

        # N개만 반환
        return stations_with_distance[:n_nearest]

    @staticmethod
    def batch_interpolate(
        grid_coords: List[Tuple[float, float]],
        station_data: List[Dict[str, Any]],
        value_key: str = "value",
        power: float = DEFAULT_POWER,
        max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
    ) -> Dict[Tuple[float, float], float]:
        """
        여러 격자에 대한 일괄 보간

        Args:
            grid_coords: 격자 좌표 리스트 [(lat, lon), ...]
            station_data: 관측소 데이터 리스트
            value_key: 보간할 값의 키
            power: IDW 거리 가중치 지수
            max_distance_km: 최대 보간 거리

        Returns:
            {(lat, lon): interpolated_value, ...}
        """
        result = {}

        for grid_lat, grid_lon in grid_coords:
            try:
                interpolated = StationMapper.interpolate_to_grid(
                    grid_lat,
                    grid_lon,
                    station_data,
                    value_key=value_key,
                    power=power,
                    max_distance_km=max_distance_km,
                )
                result[(grid_lat, grid_lon)] = interpolated
            except ValueError as e:
                logger.warning(f"보간 실패: ({grid_lat}, {grid_lon}) - {e}")
                result[(grid_lat, grid_lon)] = None

        logger.info(
            f"일괄 보간 완료: {len(grid_coords)}개 격자, "
            f"{sum(1 for v in result.values() if v is not None)}개 성공"
        )

        return result

    @staticmethod
    def calculate_coverage(
        grid_lat: float,
        grid_lon: float,
        station_data: List[Dict[str, Any]],
        max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
    ) -> Dict[str, Any]:
        """
        격자의 관측소 커버리지 분석

        Args:
            grid_lat: 격자 위도
            grid_lon: 격자 경도
            station_data: 관측소 데이터
            max_distance_km: 최대 거리

        Returns:
            {
                'n_stations': int,           # 범위 내 관측소 수
                'nearest_distance_km': float,  # 최근접 관측소 거리
                'avg_distance_km': float,    # 평균 거리
                'coverage_quality': str      # 'excellent', 'good', 'fair', 'poor'
            }
        """
        distances = []
        for station in station_data:
            s_lat = station.get("latitude")
            s_lon = station.get("longitude")
            if s_lat is None or s_lon is None:
                continue

            distance_km = StationMapper._haversine_distance(grid_lat, grid_lon, s_lat, s_lon)

            if distance_km <= max_distance_km:
                distances.append(distance_km)

        if not distances:
            return {
                "n_stations": 0,
                "nearest_distance_km": None,
                "avg_distance_km": None,
                "coverage_quality": "poor",
            }

        distances.sort()
        n_stations = len(distances)
        nearest = distances[0]
        avg_distance = sum(distances) / n_stations

        # 품질 판정
        if n_stations >= 5 and nearest < 10:
            quality = "excellent"
        elif n_stations >= 3 and nearest < 20:
            quality = "good"
        elif n_stations >= 2 and nearest < 30:
            quality = "fair"
        else:
            quality = "poor"

        return {
            "n_stations": n_stations,
            "nearest_distance_km": nearest,
            "avg_distance_km": avg_distance,
            "coverage_quality": quality,
        }
