from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
import uuid
import json
import logging
from ..config.settings import settings, _require_database_password

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """PostgreSQL 데이터베이스 연결 관리"""

    # Connection Pool (스레드 안전)
    _connection_pool = None
    _pool_lock = None

    @classmethod
    def _init_pool(cls):
        """Connection Pool 초기화 (Lazy Initialization)"""
        import threading

        if cls._pool_lock is None:
            cls._pool_lock = threading.Lock()

        with cls._pool_lock:
            if cls._connection_pool is None:
                try:
                    cls._connection_pool = pool.ThreadedConnectionPool(
                        minconn=2,  # 최소 연결 수
                        maxconn=20,  # 최대 연결 수 (MAX_WORKERS=8 * 2 여유)
                        host=settings.dw_db_host,
                        port=settings.dw_db_port,
                        dbname=settings.dw_db_name,
                        user=settings.dw_db_user,
                        password=_require_database_password(settings.dw_db_password),
                    )

                    # Connection Pool 연결 검증 (초기화 후 바로 연결 테스트)
                    test_conn = cls._connection_pool.getconn()
                    try:
                        with test_conn.cursor() as cursor:
                            cursor.execute("SELECT 1")
                        cls._connection_pool.putconn(test_conn)
                        logger.info(
                            "Database connection pool initialized and verified (minconn=2, maxconn=20)"
                        )
                    except Exception as e:
                        cls._connection_pool.putconn(test_conn)
                        raise Exception(f"Connection pool verification failed: {e}")

                except Exception as e:
                    logger.error(f"Failed to initialize connection pool: {e}")
                    cls._connection_pool = None  # 실패 시 None으로 재설정
                    raise

    @staticmethod
    def get_connection_string() -> str:
        """데이터베이스 연결 문자열 생성"""
        return (
            f"host={settings.dw_db_host} "
            f"port={settings.dw_db_port} "
            f"dbname={settings.dw_db_name} "
            f"user={settings.dw_db_user} "
            f"password={_require_database_password(settings.dw_db_password)}"
        )

    @classmethod
    @contextmanager
    def get_connection(cls):
        """데이터베이스 연결 컨텍스트 매니저 (Connection Pool 사용)"""
        # Pool 초기화 (처음 호출 시에만)
        if cls._connection_pool is None:
            cls._init_pool()

        conn = None
        try:
            # Pool에서 연결 가져오기
            conn = cls._connection_pool.getconn()
            conn.cursor_factory = RealDictCursor
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            # Pool에 연결 반환
            if conn:
                cls._connection_pool.putconn(conn)

    @staticmethod
    def fetch_grid_coordinates() -> List[Dict[str, float]]:
        """모든 격자 좌표 조회 (Decimal -> float 변환)"""
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT latitude, longitude
                FROM climate_data
                ORDER BY latitude, longitude
            """)
            return [
                {"latitude": float(row["latitude"]), "longitude": float(row["longitude"])}
                for row in cursor.fetchall()
            ]

    def fetch_all_grid_points(self) -> List[tuple]:
        """
        모든 격자점 좌표 조회 (배치 처리용)

        Returns:
            [(latitude, longitude), ...] 튜플 리스트 (float 타입)
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            # location_grid 테이블에서 격자점 조회
            cursor.execute("""
                SELECT DISTINCT latitude, longitude
                FROM location_grid
                ORDER BY latitude, longitude
            """)
            rows = cursor.fetchall()
            if rows:
                return [(float(row["latitude"]), float(row["longitude"])) for row in rows]

            # location_grid가 비어있으면 기후 데이터 테이블에서 조회
            cursor.execute("""
                SELECT DISTINCT latitude, longitude
                FROM wsdi_data
                ORDER BY latitude, longitude
                LIMIT 100
            """)
            rows = cursor.fetchall()
            return [(float(row["latitude"]), float(row["longitude"])) for row in rows]

    @staticmethod
    def fetch_climate_data(
        latitude: float, longitude: float, risk_type: str = None, ssp_scenario: str = "ssp2"
    ) -> Dict[str, Any]:
        """
        특정 격자의 기후 데이터 조회 (전처리 레이어 적용)

        Args:
            latitude: 격자 위도
            longitude: 격자 경도
            risk_type: 리스크 타입 (extreme_heat, extreme_cold 등)
            ssp_scenario: SSP 시나리오 (ssp1, ssp2, ssp3, ssp5)

        Returns:
            리스크별 파생 지표 딕셔너리
        """
        # 1. 원시 데이터 조회
        raw_data = DatabaseConnection._fetch_raw_climate_data(latitude, longitude, ssp_scenario)

        # 2. 리스크 타입이 지정되지 않으면 원시 데이터 반환
        if not risk_type:
            return {"climate_data": raw_data}

        # 3. 전처리 레이어 호출
        from ..preprocessing.climate_indicators import ClimateIndicatorCalculator
        from ..preprocessing.baseline_splitter import BaselineSplitter

        calculator = ClimateIndicatorCalculator(raw_data)
        splitter = BaselineSplitter(start_year=2021, end_year=2100)

        # 4. 리스크별 필요 지표 계산
        result = {"climate_data": {}}

        if risk_type == "extreme_heat":
            result["climate_data"] = calculator.get_heatwave_indicators()

        elif risk_type == "extreme_cold":
            result["climate_data"] = calculator.get_coldwave_indicators()

        elif risk_type == "wildfire":
            result["climate_data"] = calculator.get_wildfire_indicators()

        elif risk_type == "river_flood":
            # rx5day 기준/미래 분리
            rx5day_split = splitter.split_rx5day(raw_data.get("rx5day", []))
            result["climate_data"] = rx5day_split
            result["climate_data"]["watershed_area_km2"] = 100.0  # TODO: 실제 유역면적 조회
            result["climate_data"]["stream_order"] = 2  # TODO: 실제 하천 차수 조회

        elif risk_type == "urban_flood":
            # rx1day, sdii, rain80 기준/미래 분리
            rx1day_split = splitter.split_rx1day(raw_data.get("rx1day", []))
            sdii_split = splitter.split_sdii(raw_data.get("sdii", []))
            rain80_split = splitter.split_rain80(raw_data.get("rain80", []))
            result["climate_data"] = {**rx1day_split, **sdii_split, **rain80_split}

        elif risk_type == "drought":
            result["climate_data"] = {
                "consecutive_dry_days": raw_data.get("cdd", []),
                "spi_index": raw_data.get("spei12", []),
                "soil_moisture": 0.5,  # TODO: 실제 토양수분 조회
                "drought_duration_months": 6,  # TODO: 계산 필요
            }

        elif risk_type == "typhoon":
            # 풍속 95분위수 기준/미래 분리
            wind_split = splitter.split_wind(raw_data.get("ws", []))
            result["climate_data"] = wind_split

        elif risk_type == "sea_level_rise":
            # 해수면 상승 데이터 (별도 조회 필요)
            sea_level_data = DatabaseConnection._fetch_sea_level_data(
                latitude, longitude, ssp_scenario
            )
            result["climate_data"] = {"slr_cm": sea_level_data}

        elif risk_type == "water_stress":
            # 강수량, 유역면적 등
            result["climate_data"] = {
                "precipitation_mm": raw_data.get("rn", []),
                "withdrawal_total": 0.0,  # TODO: WAMIS API 호출
                "basin_area_km2": 100.0,  # TODO: 유역면적 조회
                "runoff_coef": 0.6,  # TODO: 유출계수 조회
            }
        else:
            # 기본값: 원시 데이터 반환
            result["climate_data"] = raw_data

        return result

    @staticmethod
    def _fetch_raw_climate_data(
        latitude: float, longitude: float, ssp_scenario: str = "ssp2"
    ) -> Dict[str, List[float]]:
        """
        원시 기후 데이터 조회 (DB 테이블에서 직접 조회)

        Args:
            latitude: 격자 위도
            longitude: 격자 경도
            ssp_scenario: SSP 시나리오 (ssp1, ssp2, ssp3, ssp5)

        Returns:
            {
                'tamax': List[float],  # 일별 최고기온
                'tamin': List[float],  # 일별 최저기온
                'ta': List[float],     # 월별 평균기온
                'rn': List[float],     # 월별 강수량
                'ws': List[float],     # 월별 풍속
                'rhm': List[float],    # 월별 상대습도
                'si': List[float],     # 월별 일사량
                'wsdi': List[float],   # 연별 WSDI
                'csdi': List[float],   # 연별 CSDI
                'rx1day': List[float], # 연별 1일 최대강수
                'rx5day': List[float], # 연별 5일 최대강수
                'cdd': List[float],    # 연별 연속 무강수일
                'rain80': List[float], # 연별 80mm 이상 강수일수
                'sdii': List[float],   # 연별 강수강도
                'spei12': List[float]  # 월별 SPEI12
            }
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()

            # 1. location_grid에서 grid_id 조회
            cursor.execute(
                """
                SELECT grid_id
                FROM location_grid
                WHERE latitude = %s AND longitude = %s
                LIMIT 1
            """,
                (latitude, longitude),
            )

            grid_result = cursor.fetchone()
            if not grid_result:
                # 격자가 없으면 빈 데이터 반환
                return {}

            grid_id = grid_result["grid_id"]

            raw_data = {}

            # 2. 일별 데이터 조회 (tamax, tamin) - admin_id 기반
            # TODO: 좌표 → admin_id 매핑 필요
            # 현재는 스킵하고 월별/연별 데이터만 조회

            # 3. 월별 데이터 조회 (ta, rn, ws, rhm, si, spei12)
            monthly_tables = {
                "ta": "ta_data",
                "rn": "rn_data",
                "ws": "ws_data",
                "rhm": "rhm_data",
                "si": "si_data",
                "spei12": "spei12_data",
            }

            for key, table in monthly_tables.items():
                cursor.execute(
                    f"""
                    SELECT {ssp_scenario}
                    FROM {table}
                    WHERE grid_id = %s
                    ORDER BY observation_date
                """,
                    (grid_id,),
                )

                rows = cursor.fetchall()
                raw_data[key] = [row[ssp_scenario] for row in rows if row[ssp_scenario] is not None]

            # 4. 연별 데이터 조회 (wsdi, csdi, rx1day, rx5day, cdd, rain80, sdii)
            yearly_tables = {
                "wsdi": "wsdi_data",
                "csdi": "csdi_data",
                "rx1day": "rx1day_data",
                "rx5day": "rx5day_data",
                "cdd": "cdd_data",
                "rain80": "rain80_data",
                "sdii": "sdii_data",
            }

            for key, table in yearly_tables.items():
                cursor.execute(
                    f"""
                    SELECT {ssp_scenario}
                    FROM {table}
                    WHERE grid_id = %s
                    ORDER BY year
                """,
                    (grid_id,),
                )

                rows = cursor.fetchall()
                raw_data[key] = [row[ssp_scenario] for row in rows if row[ssp_scenario] is not None]

            return raw_data

    @staticmethod
    def _fetch_sea_level_data(
        latitude: float, longitude: float, ssp_scenario: str = "ssp2"
    ) -> List[float]:
        """
        해수면 상승 데이터 조회

        Args:
            latitude: 격자 위도
            longitude: 격자 경도
            ssp_scenario: SSP 시나리오

        Returns:
            연도별 해수면 상승값 (cm) 리스트
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()

            # 1. sea_level_grid에서 grid_id 조회
            cursor.execute(
                """
                SELECT grid_id
                FROM sea_level_grid
                WHERE latitude = %s AND longitude = %s
                LIMIT 1
            """,
                (latitude, longitude),
            )

            grid_result = cursor.fetchone()
            if not grid_result:
                return []

            grid_id = grid_result["grid_id"]

            # 2. sea_level_data 조회
            cursor.execute(
                f"""
                SELECT {ssp_scenario}
                FROM sea_level_data
                WHERE grid_id = %s
                ORDER BY year
            """,
                (grid_id,),
            )

            rows = cursor.fetchall()
            return [row[ssp_scenario] for row in rows if row[ssp_scenario] is not None]

    @staticmethod
    def save_probability_results(results: List[Dict[str, Any]]) -> None:
        """
        P(H) 계산 결과 저장

        테이블 스키마:
            - latitude, longitude, risk_type, target_year (PK)
            - ssp126_aal, ssp245_aal, ssp370_aal, ssp585_aal
            - ssp126_bin_probs, ssp245_bin_probs, ssp370_bin_probs, ssp585_bin_probs

        Args:
            results: 저장할 결과 리스트
                - latitude: 위도
                - longitude: 경도
                - scenario: SSP 시나리오 (SSP126, SSP245, SSP370, SSP585)
                - target_year: 분석 연도
                - risk_type: 리스크 타입
                - aal: AAL (Annual Average Loss)
                - bin_probabilities: bin별 발생확률 배열
        """
        import json

        # 시나리오 → 컬럼명 매핑
        scenario_to_aal_col = {
            "SSP126": "ssp126_aal",
            "SSP245": "ssp245_aal",
            "SSP370": "ssp370_aal",
            "SSP585": "ssp585_aal",
        }
        scenario_to_bin_col = {
            "SSP126": "ssp126_bin_probs",
            "SSP245": "ssp245_bin_probs",
            "SSP370": "ssp370_bin_probs",
            "SSP585": "ssp585_bin_probs",
        }

        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            for result in results:
                scenario = result.get("scenario", "SSP245")
                aal_col = scenario_to_aal_col.get(scenario)
                bin_col = scenario_to_bin_col.get(scenario)

                if not aal_col or not bin_col:
                    continue  # 알 수 없는 시나리오는 스킵

                bin_probs_json = json.dumps(result.get("bin_probabilities", []))

                # UPSERT: 해당 시나리오 컬럼만 업데이트
                cursor.execute(
                    f"""
                    INSERT INTO probability_results
                    (latitude, longitude, risk_type, target_year, {aal_col}, {bin_col})
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (latitude, longitude, risk_type, target_year)
                    DO UPDATE SET
                        {aal_col} = EXCLUDED.{aal_col},
                        {bin_col} = EXCLUDED.{bin_col}
                """,
                    (
                        result["latitude"],
                        result["longitude"],
                        result["risk_type"],
                        result["target_year"],
                        result.get("aal", 0.0),
                        bin_probs_json,
                    ),
                )

    @staticmethod
    def save_hazard_results(results: List[Dict[str, Any]]) -> None:
        """
        Hazard Score 계산 결과 저장

        테이블 스키마:
            - latitude, longitude, risk_type, target_year (PK)
            - ssp126_score_100, ssp245_score_100, ssp370_score_100, ssp585_score_100

        Args:
            results: 저장할 결과 리스트
                - latitude: 위도
                - longitude: 경도
                - scenario: SSP 시나리오 (SSP126, SSP245, SSP370, SSP585)
                - target_year: 분석 연도
                - risk_type: 리스크 타입
                - hazard_score_100: 0-100 점수
        """
        # 시나리오 → 컬럼명 매핑
        scenario_to_column = {
            "SSP126": "ssp126_score_100",
            "SSP245": "ssp245_score_100",
            "SSP370": "ssp370_score_100",
            "SSP585": "ssp585_score_100",
        }

        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            for result in results:
                scenario = result.get("scenario", "SSP245")
                column_name = scenario_to_column.get(scenario)

                if not column_name:
                    continue  # 알 수 없는 시나리오는 스킵

                # UPSERT: 해당 시나리오 컬럼만 업데이트
                cursor.execute(
                    f"""
                    INSERT INTO hazard_results
                    (latitude, longitude, risk_type, target_year, {column_name})
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (latitude, longitude, risk_type, target_year)
                    DO UPDATE SET
                        {column_name} = EXCLUDED.{column_name}
                """,
                    (
                        result["latitude"],
                        result["longitude"],
                        result["risk_type"],
                        result["target_year"],
                        result.get("hazard_score_100", 0.0),
                    ),
                )

    @staticmethod
    def fetch_building_info(latitude: float, longitude: float) -> Dict[str, Any]:
        """
        건물 정보 조회 (building_aggregate_cache 테이블 사용)

        Args:
            latitude: 격자 위도
            longitude: 격자 경도

        Returns:
            건물 정보 딕셔너리 (없으면 빈 딕셔너리)
        """
        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                # VWorld 역지오코딩으로 좌표 → 법정동코드 변환
                cursor.execute(
                    """
                    SELECT sigungu_cd, bjdong_cd, bun, ji
                    FROM api_vworld_geocode
                    WHERE ST_DWithin(
                        location::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        1000
                    )
                    ORDER BY ST_Distance(
                        location::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    )
                    LIMIT 1
                """,
                    (longitude, latitude, longitude, latitude),
                )

                geocode_result = cursor.fetchone()

                if not geocode_result:
                    return {}

                sigungu_cd = geocode_result["sigungu_cd"]
                bjdong_cd = geocode_result["bjdong_cd"]
                bun = geocode_result["bun"]
                ji = geocode_result["ji"]

                # building_aggregate_cache에서 건물 집계 정보 조회
                cursor.execute(
                    """
                    SELECT
                        oldest_building_age_years as building_age,
                        structure_types,
                        purpose_types,
                        max_underground_floors as floors_below,
                        max_ground_floors as floors_above,
                        total_floor_area_sqm as total_area,
                        total_building_area_sqm as arch_area
                    FROM building_aggregate_cache
                    WHERE sigungu_cd = %s AND bjdong_cd = %s AND bun = %s AND ji = %s
                    LIMIT 1
                """,
                    (sigungu_cd, bjdong_cd, bun, ji),
                )

                result = cursor.fetchone()

                if not result:
                    return {}

                # JSONB 배열에서 첫 번째 요소 추출
                structure_types = result.get("structure_types", [])
                purpose_types = result.get("purpose_types", [])

                return {
                    "building_age": result.get("building_age"),
                    "structure": structure_types[0] if structure_types else None,
                    "main_purpose": purpose_types[0] if purpose_types else None,
                    "floors_below": result.get("floors_below"),
                    "floors_above": result.get("floors_above"),
                    "total_area": result.get("total_area"),
                    "arch_area": result.get("arch_area"),
                }
        except Exception as e:
            logger.error(f"Failed to fetch building info: {e}")
            return {}

    @staticmethod
    def fetch_building_data_for_vulnerability(
        latitude: float, longitude: float
    ) -> Optional[Dict[str, Any]]:
        """
        Vulnerability 계산용 건물 데이터 조회 (building_aggregate_cache 테이블 사용)

        Args:
            latitude: 위도 (WGS84)
            longitude: 경도 (WGS84)

        Returns:
            {
                'building_age': int,
                'ground_floors': int,
                'floors_below': int,
                'has_piloti': bool,
                'structure_type': str,
                'total_area_m2': float,
                'main_purpose': str,
                'has_seismic_design': bool,
                'elevation_m': float,
                'flood_capacity': float,
                'data_source': str
            } 또는 None
        """
        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                # VWorld 역지오코딩으로 좌표 → 법정동코드 변환
                cursor.execute(
                    """
                    SELECT sigungu_cd, bjdong_cd, bun, ji
                    FROM api_vworld_geocode
                    WHERE ST_DWithin(
                        location::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        1000
                    )
                    ORDER BY ST_Distance(
                        location::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    )
                    LIMIT 1
                """,
                    (longitude, latitude, longitude, latitude),
                )

                geocode_result = cursor.fetchone()

                if not geocode_result:
                    logger.warning(f"No geocode found for ({latitude}, {longitude})")
                    return None

                sigungu_cd = geocode_result["sigungu_cd"]
                bjdong_cd = geocode_result["bjdong_cd"]
                bun = geocode_result["bun"]
                ji = geocode_result["ji"]

                # building_aggregate_cache에서 건물 집계 정보 조회
                cursor.execute(
                    """
                    SELECT
                        oldest_building_age_years as building_age,
                        max_ground_floors as ground_floors,
                        max_underground_floors as floors_below,
                        structure_types,
                        purpose_types,
                        total_floor_area_sqm as total_area_m2,
                        buildings_with_seismic,
                        buildings_without_seismic,
                        building_count
                    FROM building_aggregate_cache
                    WHERE sigungu_cd = %s AND bjdong_cd = %s AND bun = %s AND ji = %s
                    LIMIT 1
                """,
                    (sigungu_cd, bjdong_cd, bun, ji),
                )

                result = cursor.fetchone()

                if not result:
                    logger.warning(f"No building data for ({sigungu_cd}, {bjdong_cd}, {bun}, {ji})")
                    return None

                # JSONB 배열에서 첫 번째 요소 추출
                structure_types = result.get("structure_types", [])
                purpose_types = result.get("purpose_types", [])
                structure_type = structure_types[0] if structure_types else "RC"
                main_purpose = purpose_types[0] if purpose_types else "residential"

                # 필로티 여부 추정 (1층이 있고 지하층이 없는 경우)
                ground_floors = result.get("ground_floors", 3)
                floors_below = result.get("floors_below", 0)
                has_piloti = ground_floors >= 1 and floors_below == 0

                # 내진설계 여부 추정 (건물 수 기반)
                with_seismic = result.get("buildings_with_seismic", 0)
                without_seismic = result.get("buildings_without_seismic", 0)
                total_buildings = with_seismic + without_seismic
                has_seismic_design = (
                    with_seismic > without_seismic if total_buildings > 0 else False
                )

                building_age = result.get("building_age", 30)

                return {
                    "building_age": int(building_age) if building_age else 30,
                    "ground_floors": int(ground_floors) if ground_floors else 3,
                    "floors_below": int(floors_below) if floors_below else 0,
                    "has_piloti": has_piloti,
                    "structure_type": structure_type,
                    "total_area_m2": (
                        float(result.get("total_area_m2", 500.0))
                        if result.get("total_area_m2")
                        else 500.0
                    ),
                    "main_purpose": main_purpose,
                    "has_seismic_design": has_seismic_design,
                    "elevation_m": 50.0,  # TODO: DEM 데이터에서 조회
                    "flood_capacity": 0.0,  # TODO: 별도 계산 필요
                    "data_source": "building_aggregate_cache",
                }

        except Exception as e:
            logger.error(f"Failed to fetch building data for vulnerability: {e}")
            return None

    @staticmethod
    def fetch_base_aals(latitude: float, longitude: float) -> Dict[str, float]:
        """
        base_aal 조회 (probability_results.aal)

        Args:
            latitude: 위도
            longitude: 경도

        Returns:
            {risk_type: base_aal} 딕셔너리
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT risk_type, aal AS base_aal
                FROM probability_results
                WHERE latitude = %s AND longitude = %s
            """,
                (latitude, longitude),
            )

            return {row["risk_type"]: row["base_aal"] for row in cursor.fetchall()}

    @staticmethod
    def _get_or_create_site_id(cursor, latitude: float, longitude: float) -> str:
        """
        좌표 기반 deterministic site_id 생성 (UUID5)

        Args:
            cursor: DB cursor (unused, kept for interface compatibility)
            latitude: 위도
            longitude: 경도

        Returns:
            site_id (UUID string)
        """
        # 좌표 기반 deterministic UUID 생성 (uuid5)
        namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace
        name = f"site:{latitude:.6f}:{longitude:.6f}"
        return str(uuid.uuid5(namespace, name))

    @staticmethod
    def save_exposure_results(results: List[Dict[str, Any]]) -> None:
        """
        E (Exposure) 계산 결과 저장

        Args:
            results: 저장할 결과 리스트
                - site_id: 사업장 ID (선택, 없으면 좌표 기반 UUID 생성)
                - latitude: 위도
                - longitude: 경도
                - risk_type: 리스크 타입
                - exposure_score: 노출도 점수 (0-100)
                - target_year: 목표 연도 (선택, 기본 2050)
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            for result in results:
                lat, lon = result["latitude"], result["longitude"]
                risk_type = result["risk_type"]
                target_year = str(result.get("target_year", 2050))
                score = result.get("exposure_score", 0.0)

                # site_id: 전달받은 값 사용, 없으면 좌표 기반 UUID 생성
                site_id = result.get("site_id") or DatabaseConnection._get_or_create_site_id(
                    cursor, lat, lon
                )

                # 기존 데이터 삭제 후 삽입 (site_id, risk_type, target_year 기준)
                cursor.execute(
                    """
                    DELETE FROM exposure_results
                    WHERE site_id = %s AND risk_type = %s AND target_year = %s::text
                """,
                    (site_id, risk_type, str(target_year)),
                )

                cursor.execute(
                    """
                    INSERT INTO exposure_results
                    (site_id, latitude, longitude, risk_type, target_year, exposure_score)
                    VALUES (%s, %s, %s, %s, %s::text, %s)
                """,
                    (site_id, lat, lon, risk_type, str(target_year), score),
                )

    @staticmethod
    def save_vulnerability_results(results: List[Dict[str, Any]]) -> None:
        """
        V (Vulnerability) 계산 결과 저장

        Args:
            results: 저장할 결과 리스트
                - site_id: 사업장 ID (선택, 없으면 좌표 기반 UUID 생성)
                - latitude: 위도
                - longitude: 경도
                - risk_type: 리스크 타입
                - vulnerability_score: 취약성 점수 (0-100)
                - target_year: 목표 연도 (선택, 기본 2050)
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            for result in results:
                lat, lon = result["latitude"], result["longitude"]
                risk_type = result["risk_type"]
                target_year = str(result.get("target_year", 2050))
                score = result.get("vulnerability_score", 0.0)

                # site_id: 전달받은 값 사용, 없으면 좌표 기반 UUID 생성
                site_id = result.get("site_id") or DatabaseConnection._get_or_create_site_id(
                    cursor, lat, lon
                )

                # 기존 데이터 삭제 후 삽입
                cursor.execute(
                    """
                    DELETE FROM vulnerability_results
                    WHERE site_id = %s AND risk_type = %s AND target_year = %s::text
                """,
                    (site_id, risk_type, str(target_year)),
                )

                cursor.execute(
                    """
                    INSERT INTO vulnerability_results
                    (site_id, latitude, longitude, risk_type, target_year, vulnerability_score)
                    VALUES (%s, %s, %s, %s, %s::text, %s)
                """,
                    (site_id, lat, lon, risk_type, str(target_year), score),
                )

    @staticmethod
    def save_aal_scaled_results(results: List[Dict[str, Any]]) -> None:
        """
        AAL 스케일링 결과 저장

        Args:
            results: 저장할 결과 리스트
                - site_id: 사업장 ID (선택, 없으면 좌표 기반 UUID 생성)
                - latitude: 위도
                - longitude: 경도
                - risk_type: 리스크 타입
                - target_year: 목표 연도
                - scenario: SSP 시나리오 (SSP126, SSP245, SSP370, SSP585)
                - final_aal: 최종 AAL
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            for result in results:
                lat, lon = result["latitude"], result["longitude"]
                risk_type = result["risk_type"]
                target_year = str(result.get("target_year", 2050))
                scenario = result.get("scenario", "SSP245").lower()
                final_aal = result.get("final_aal", 0.0)
                aal_column = f"{scenario}_final_aal"

                # site_id: 전달받은 값 사용, 없으면 좌표 기반 UUID 생성
                site_id = result.get("site_id") or DatabaseConnection._get_or_create_site_id(
                    cursor, lat, lon
                )

                # 기존 데이터 삭제 후 삽입
                cursor.execute(
                    """
                    DELETE FROM aal_scaled_results
                    WHERE site_id = %s AND risk_type = %s AND target_year = %s::text
                """,
                    (site_id, risk_type, str(target_year)),
                )

                cursor.execute(
                    f"""
                    INSERT INTO aal_scaled_results
                    (site_id, latitude, longitude, risk_type, target_year, {aal_column})
                    VALUES (%s, %s, %s, %s, %s::text, %s)
                """,
                    (site_id, lat, lon, risk_type, str(target_year), final_aal),
                )

    # ==================== Batch Jobs 관리 메서드 ====================

    @staticmethod
    def create_batch_job(job_type: str, input_params: Dict[str, Any]) -> str:
        """
        배치 작업 생성

        Args:
            job_type: 작업 유형 ('ondemand_risk_calculation' 등)
            input_params: 입력 파라미터 (latitude, longitude, risk_types 등)

        Returns:
            batch_id (UUID string)
        """
        batch_id = str(uuid.uuid4())
        input_params_json = json.dumps(input_params)

        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO batch_jobs
                (batch_id, job_type, status, progress, total_items, completed_items,
                 failed_items, input_params, created_at)
                VALUES (%s, %s, 'queued', 0, 0, 0, 0, %s::jsonb, NOW())
                RETURNING batch_id
            """,
                (batch_id, job_type, input_params_json),
            )

            result = cursor.fetchone()
            return result["batch_id"]

    @staticmethod
    def update_batch_progress(
        batch_id: str,
        progress: int,
        current_step: str = None,
        completed_items: int = None,
        failed_items: int = None,
    ) -> None:
        """
        배치 진행률 업데이트

        Args:
            batch_id: 배치 ID
            progress: 진행률 (0-100)
            current_step: 현재 단계 설명 (선택)
            completed_items: 완료 항목 수 (선택)
            failed_items: 실패 항목 수 (선택)
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()

            # 동적 쿼리 생성
            update_fields = ["progress = %s"]
            params = [progress]

            if current_step is not None:
                update_fields.append("status = 'running'")

            if completed_items is not None:
                update_fields.append("completed_items = %s")
                params.append(completed_items)

            if failed_items is not None:
                update_fields.append("failed_items = %s")
                params.append(failed_items)

            # batch_id는 마지막 파라미터
            params.append(batch_id)

            query = f"""
                UPDATE batch_jobs
                SET {', '.join(update_fields)}
                WHERE batch_id = %s
            """

            cursor.execute(query, params)

    @staticmethod
    def complete_batch_job(batch_id: str, results: Dict[str, Any]) -> None:
        """
        배치 작업 완료 처리

        Args:
            batch_id: 배치 ID
            results: 최종 결과 (JSONB)
        """
        results_json = json.dumps(results)

        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE batch_jobs
                SET status = 'completed',
                    progress = 100,
                    results = %s::jsonb,
                    completed_at = NOW()
                WHERE batch_id = %s
            """,
                (results_json, batch_id),
            )

    @staticmethod
    def fail_batch_job(batch_id: str, error_message: str, error_stack_trace: str = None) -> None:
        """
        배치 작업 실패 처리

        Args:
            batch_id: 배치 ID
            error_message: 에러 메시지
            error_stack_trace: 스택 트레이스 (선택)
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE batch_jobs
                SET status = 'failed',
                    error_message = %s,
                    error_stack_trace = %s,
                    completed_at = NOW()
                WHERE batch_id = %s
            """,
                (error_message, error_stack_trace, batch_id),
            )

    @staticmethod
    def get_batch_status(batch_id: str) -> Optional[Dict[str, Any]]:
        """
        배치 상태 조회 (FastAPI에서 사용)

        Args:
            batch_id: 배치 ID

        Returns:
            {
                'batch_id': str,
                'job_type': str,
                'status': str,
                'progress': int,
                'results': dict,
                'error_message': str,
                'created_at': datetime,
                'completed_at': datetime
            } 또는 None
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    batch_id,
                    job_type,
                    status,
                    progress,
                    total_items,
                    completed_items,
                    failed_items,
                    input_params,
                    results,
                    error_message,
                    error_stack_trace,
                    created_at,
                    started_at,
                    completed_at
                FROM batch_jobs
                WHERE batch_id = %s
            """,
                (batch_id,),
            )

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    # ==================== 조회 메서드 ====================

    @staticmethod
    def fetch_hazard_results(
        latitude: float,
        longitude: float,
        risk_types: List[str] = None,
        target_year: int = None,
        scenario: str = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Hazard Score 조회

        테이블 스키마:
            - latitude, longitude, risk_type, target_year (PK)
            - ssp126_score_100, ssp245_score_100, ssp370_score_100, ssp585_score_100

        Args:
            latitude: 위도
            longitude: 경도
            risk_types: 조회할 리스크 타입 목록 (None이면 전체)
            target_year: 조회할 연도 (None이면 전체)
            scenario: 조회할 시나리오 (SSP126, SSP245, SSP370, SSP585, None이면 전체)

        Returns:
            {
                'extreme_heat': {
                    'target_year': 2050,
                    'ssp126_score_100': 45.0,
                    'ssp245_score_100': 55.0,
                    'ssp370_score_100': 65.0,
                    'ssp585_score_100': 75.0
                },
                ...
            }
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()

            # 기본 쿼리
            query = """
                SELECT risk_type, target_year,
                       ssp126_score_100, ssp245_score_100,
                       ssp370_score_100, ssp585_score_100
                FROM hazard_results
                WHERE latitude = %s AND longitude = %s
            """
            params = [latitude, longitude]

            if risk_types:
                query += " AND risk_type = ANY(%s)"
                params.append(risk_types)

            if target_year:
                query += " AND target_year = %s::text"
                params.append(str(target_year))

            query += " ORDER BY risk_type, target_year"

            cursor.execute(query, params)

            results = {}
            for row in cursor.fetchall():
                risk_type = row["risk_type"]
                year = row["target_year"]
                key = f"{risk_type}_{year}" if target_year is None else risk_type

                result_data = {
                    "target_year": year,
                    "ssp126_score_100": row["ssp126_score_100"],
                    "ssp245_score_100": row["ssp245_score_100"],
                    "ssp370_score_100": row["ssp370_score_100"],
                    "ssp585_score_100": row["ssp585_score_100"],
                }

                # 특정 시나리오만 요청한 경우
                if scenario:
                    scenario_col = f"{scenario.lower()}_score_100"
                    result_data["hazard_score_100"] = row.get(scenario_col, 0.0)

                results[key] = result_data

            return results

    @staticmethod
    def fetch_probability_results(
        latitude: float,
        longitude: float,
        risk_types: List[str] = None,
        target_year: int = None,
        scenario: str = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        P(H) 조회 (최근접 격자 기반)

        테이블 스키마:
            - latitude, longitude, risk_type, target_year (PK)
            - ssp126_aal, ssp245_aal, ssp370_aal, ssp585_aal
            - ssp126_bin_probs, ssp245_bin_probs, ssp370_bin_probs, ssp585_bin_probs

        Args:
            latitude: 위도
            longitude: 경도
            risk_types: 조회할 리스크 타입 목록 (None이면 전체)
            target_year: 조회할 연도 (None이면 최신)
            scenario: 조회할 시나리오 (SSP126, SSP245, SSP370, SSP585, None이면 전체)

        Returns:
            {
                'extreme_heat': {'aal': 0.025, 'bin_probabilities': [...], ...},
                ...
            }
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()

            # 최근접 격자 조회 쿼리 (거리 제한 없음)
            # DISTINCT ON을 사용하여 risk_type, target_year 조합당 가장 가까운 격자 1개만 선택
            query = """
                SELECT DISTINCT ON (risk_type, target_year)
                       risk_type, target_year,
                       ssp126_aal, ssp245_aal, ssp370_aal, ssp585_aal,
                       ssp126_bin_probs, ssp245_bin_probs, ssp370_bin_probs, ssp585_bin_probs,
                       SQRT(POWER(latitude - %s, 2) + POWER(longitude - %s, 2)) AS distance
                FROM probability_results
                WHERE 1=1
            """
            params = [latitude, longitude]

            if risk_types:
                query += " AND risk_type = ANY(%s)"
                params.append(risk_types)

            if target_year:
                query += " AND target_year = %s::text"
                params.append(str(target_year))

            # risk_type, target_year별로 거리순 정렬하여 가장 가까운 것 선택
            query += " ORDER BY risk_type, target_year, distance"

            cursor.execute(query, params)

            results = {}
            for row in cursor.fetchall():
                risk_type = row["risk_type"]
                year = row["target_year"]
                key = f"{risk_type}_{year}" if target_year is None else risk_type

                result_data = {
                    "target_year": year,
                    "ssp126_aal": row["ssp126_aal"],
                    "ssp245_aal": row["ssp245_aal"],
                    "ssp370_aal": row["ssp370_aal"],
                    "ssp585_aal": row["ssp585_aal"],
                    "ssp126_bin_probs": row["ssp126_bin_probs"],
                    "ssp245_bin_probs": row["ssp245_bin_probs"],
                    "ssp370_bin_probs": row["ssp370_bin_probs"],
                    "ssp585_bin_probs": row["ssp585_bin_probs"],
                }

                # 특정 시나리오만 요청한 경우, aal과 bin_probabilities 키 추가
                if scenario:
                    scenario_lower = scenario.lower()
                    result_data["aal"] = row.get(f"{scenario_lower}_aal", 0.0)
                    result_data["bin_probabilities"] = row.get(f"{scenario_lower}_bin_probs")

                results[key] = result_data

            return results

    @staticmethod
    def fetch_population_data(latitude: float, longitude: float) -> Dict[str, Any]:
        """
        행정구역 인구 데이터 조회 (location_admin)

        Args:
            latitude: 위도
            longitude: 경도

        Returns:
            {
                'admin_name': str,
                'population_2020': int,
                'population_2025': int,
                ...,
                'population_2050': int,
                'population_change_2020_2050': int,
                'population_change_rate_percent': float
            }
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
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
                    population_2050,
                    population_change_2020_2050,
                    population_change_rate_percent
                FROM location_admin
                WHERE ST_Contains(geom, ST_SetSRID(ST_Point(%s, %s), 5174))
                LIMIT 1
            """,
                (longitude, latitude),
            )

            row = cursor.fetchone()
            if row:
                return dict(row)

            # 행정구역을 찾지 못한 경우 기본값 반환
            return {
                "admin_name": "Unknown",
                "population_2020": 0,
                "population_2025": 0,
                "population_2030": 0,
                "population_2035": 0,
                "population_2040": 0,
                "population_2045": 0,
                "population_2050": 0,
                "population_change_2020_2050": 0,
                "population_change_rate_percent": 0.0,
            }

    @staticmethod
    def save_candidate_site(
        latitude: float,
        longitude: float,
        aal: float = None,
        aal_by_risk: Dict[str, float] = None,
        risk_score: int = None,
        risks: Dict[str, Any] = None,
        reference_site_id: str = None,
    ) -> str:
        """
        후보지 추천 결과 저장 (E, V, AAL 계산 결과 중심)

        Args:
            latitude: 위도
            longitude: 경도
            aal: 연평균 손실 평균 (9개 리스크 평균)
            aal_by_risk: 리스크별 개별 AAL {risk_type: final_aal}
            risk_score: 종합 리스크 점수 (0-100)
            risks: 개별 리스크 점수 (JSON)
            reference_site_id: 참조 사업장 ID (요청에서 전달된 site_id)

        Returns:
            생성된 후보지 ID (UUID string)
        """
        candidate_id = str(uuid.uuid4())
        # name 필드는 NOT NULL이므로 임시 값을 사용합니다.
        # 필요하다면 이 로직을 수정하여 실제 이름을 제공해야 합니다.
        generated_name = f"Candidate Site ({latitude:.4f}, {longitude:.4f})"

        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO candidate_sites (
                    id, name, latitude, longitude,
                    aal, aal_by_risk, risk_score, risks, site_id,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s::jsonb, %s, %s::jsonb, %s,
                    NOW(), NOW()
                )
                RETURNING id
            """,
                (
                    candidate_id,
                    generated_name,
                    latitude,
                    longitude,
                    aal,
                    json.dumps(aal_by_risk) if aal_by_risk else None,
                    risk_score,
                    json.dumps(risks) if risks else None,
                    reference_site_id,
                ),
            )

            return candidate_id

    @staticmethod
    def check_candidate_exists(
        latitude: float,
        longitude: float,
        scenario: str,
        target_year: int,
        tolerance: float = 0.0001,
    ) -> bool:
        """
        후보지가 이미 평가되었는지 확인

        Args:
            latitude: 위도
            longitude: 경도
            scenario: SSP 시나리오
            target_year: 목표 연도
            tolerance: 좌표 허용 오차 (기본 0.0001도 ≈ 11m)

        Returns:
            True if exists with complete data, False otherwise
        """
        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                # 1. candidate_sites 테이블에서 좌표 매칭
                cursor.execute(
                    """
                    SELECT id
                    FROM candidate_sites
                    WHERE ABS(latitude - %s) < %s
                      AND ABS(longitude - %s) < %s
                """,
                    (latitude, tolerance, longitude, tolerance),
                )

                if not cursor.fetchone():
                    return False

                # 2. site_id 생성 (deterministic UUID)
                site_id = DatabaseConnection._get_or_create_site_id(cursor, latitude, longitude)

                # 3. E, V, AAL 데이터 완전성 확인 (9개 리스크 타입 모두 존재해야 함)
                cursor.execute(
                    """
                    SELECT
                        (SELECT COUNT(DISTINCT risk_type) FROM exposure_results
                         WHERE site_id = %s AND target_year = %s::text) as e_count,
                        (SELECT COUNT(DISTINCT risk_type) FROM vulnerability_results
                         WHERE site_id = %s AND target_year = %s::text) as v_count,
                        (SELECT COUNT(DISTINCT risk_type) FROM aal_scaled_results
                         WHERE site_id = %s AND target_year = %s::text) as aal_count
                """,
                    (
                        site_id,
                        str(target_year),
                        site_id,
                        str(target_year),
                        site_id,
                        str(target_year),
                    ),
                )

                result = cursor.fetchone()
                return (
                    result["e_count"] == 9 and result["v_count"] == 9 and result["aal_count"] == 9
                )
        except Exception as e:
            logger.warning(f"중복 체크 실패 ({latitude}, {longitude}): {e}")
            return False  # 오류 시 중복 아님으로 간주하여 계산 진행
