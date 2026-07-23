#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Climate Data Loader (DB 기반)
KMA SSP 시나리오 기후 데이터를 PostgreSQL DB에서 로드

변경 이력:
    - 2025-12-14: NetCDF 파일 기반 → DB 기반으로 전환
"""

import logging
from typing import Dict, Optional

try:
    from ..database.connection import DatabaseConnection

    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

logger = logging.getLogger(__name__)


class ClimateDataLoader:
    """
    KMA SSP 시나리오 기후 데이터 로더 (DB 기반)

    데이터 소스: PostgreSQL DB
    테이블: wsdi_data, csdi_data, cdd_data, rx1day_data, rx5day_data 등
    시나리오: SSP126, SSP245, SSP370, SSP585
    기간: 2021-2100
    """

    # SSP 시나리오 → DB 컬럼 매핑
    SSP_COLUMN_MAP = {
        "SSP126": "ssp1",
        "SSP245": "ssp2",
        "SSP370": "ssp3",
        "SSP585": "ssp5",
        "ssp1": "ssp1",
        "ssp2": "ssp2",
        "ssp3": "ssp3",
        "ssp5": "ssp5",
    }

    # 변수명 → DB 테이블 매핑 (연간 데이터 - year 컬럼 있음)
    YEARLY_TABLE_MAP = {
        # 극한 고온 (year 컬럼)
        "WSDIx": "wsdi_data",
        "WSDI": "wsdi_data",
        # 극한 한파 (year 컬럼)
        "CSDIx": "csdi_data",
        "CSDI": "csdi_data",
        # 강수/홍수 (year 컬럼)
        "RX1DAY": "rx1day_data",
        "RX5DAY": "rx5day_data",
        "RAIN80": "rain80_data",
        "CDD": "cdd_data",
        "SDII": "sdii_data",
    }

    # 월간/일간 데이터 테이블 (observation_date 컬럼 있음)
    OBSERVATION_DATE_TABLE_MAP = {
        # 기온
        "TXx": "tamax_data",  # 일 최고기온
        "SU25": "tamax_data",  # 폭염일 (최고기온 25도 이상)
        "ID0": "tamax_data",  # 결빙일 (최고기온 0도 이하)
        "TNn": "tamin_data",  # 일 최저기온
        "TR25": "tamin_data",  # 열대야 (최저기온 25도 이상)
        "FD0": "tamin_data",  # 서리일 (최저기온 0도 이하)
        "TA": "ta_data",  # 평균기온
        # 강수량
        "RN": "rn_data",  # 강수량
        # 기타
        "RHM": "rhm_data",  # 상대습도
        "WS": "ws_data",  # 풍속
        "SI": "si_data",  # 일사량
        "SPEI12": "spei12_data",  # SPEI12
    }

    def __init__(self, base_dir: str = None, scenario: str = "SSP245"):
        """
        Args:
            base_dir: (레거시, 무시됨) 데이터 기본 경로
            scenario: SSP 시나리오 (SSP126, SSP245, SSP370, SSP585)
        """
        self.scenario = scenario
        self.ssp_column = self.SSP_COLUMN_MAP.get(scenario, "ssp2")
        self._grid_cache = {}  # grid_id 캐시

        if not DB_AVAILABLE:
            logger.warning("DatabaseConnection not available")

    def _get_grid_id(self, lat: float, lon: float) -> Optional[int]:
        """
        위경도에서 가장 가까운 grid_id 조회

        Args:
            lat: 위도
            lon: 경도

        Returns:
            grid_id 또는 None
        """
        cache_key = f"{lat:.6f}_{lon:.6f}"
        if cache_key in self._grid_cache:
            return self._grid_cache[cache_key]

        if not DB_AVAILABLE:
            return None

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT grid_id
                    FROM location_grid
                    ORDER BY SQRT(POWER(longitude - %s, 2) + POWER(latitude - %s, 2))
                    LIMIT 1
                """,
                    (lon, lat),
                )

                result = cursor.fetchone()
                if result:
                    grid_id = result["grid_id"]
                    self._grid_cache[cache_key] = grid_id
                    return grid_id
                return None
        except Exception as e:
            logger.error(f"Failed to get grid_id: {e}")
            return None

    def _parse_year(self, year) -> tuple:
        """
        year를 파싱하여 정수 연도와 decadal 여부 반환

        Args:
            year: 연도 (2030 또는 "2030s")

        Returns:
            (int_year, is_decadal): (정수 연도, decadal 여부)
            예: 2030 → (2030, False)
                "2030s" → (2030, True)
                "2050s" → (2050, True)
        """
        if isinstance(year, str):
            if year.endswith("s"):
                # Decadal year: "2030s" → (2030, True)
                try:
                    int_year = int(year.replace("s", ""))
                    return (int_year, True)
                except ValueError:
                    logger.warning(f"Invalid decadal year format: {year}, using 2030")
                    return (2030, False)
            else:
                # 문자열 숫자: "2030" → (2030, False)
                try:
                    return (int(year), False)
                except ValueError:
                    logger.warning(f"Invalid year format: {year}, using 2030")
                    return (2030, False)
        else:
            # 정수: 2030 → (2030, False)
            return (int(year), False)

    def _extract_value(self, variable: str, lat: float, lon: float, year: int) -> Optional[float]:
        """
        DB에서 특정 위치/연도의 값 추출

        Args:
            variable: 변수명 (WSDIx, CDD, RX1DAY 등)
            lat: 위도
            lon: 경도
            year: 연도 (2021-2100)

        Returns:
            추출된 값 또는 None
        """
        if not DB_AVAILABLE:
            return None

        # 1. year 컬럼 기반 테이블 (YEARLY_TABLE_MAP)
        table_name = self.YEARLY_TABLE_MAP.get(variable)
        if table_name:
            return self._extract_yearly_value(variable, lat, lon, year, table_name)

        # 2. observation_date 컬럼 기반 테이블 (OBSERVATION_DATE_TABLE_MAP)
        table_name = self.OBSERVATION_DATE_TABLE_MAP.get(variable)
        if table_name:
            return self._extract_observation_date_value(variable, lat, lon, year, table_name)

        logger.warning(f"Unknown variable: {variable}")
        return None

    def _extract_yearly_value(
        self, variable: str, lat: float, lon: float, year: int, table_name: str
    ) -> Optional[float]:
        """
        year 컬럼 기반 테이블에서 값 추출

        Decadal year (예: "2030s") 지원:
        - "2030s" → 2030-2039년의 평균값 반환
        """
        grid_id = self._get_grid_id(lat, lon)
        if grid_id is None:
            return None

        try:
            # year 파싱 (decadal 여부 확인)
            int_year, is_decadal = self._parse_year(year)

            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                if is_decadal:
                    # Decadal year: 10년 평균 계산 (예: "2030s" → 2030-2039)
                    start_year = int_year
                    end_year = int_year + 9
                    query = f"""
                        SELECT AVG({self.ssp_column}) as value
                        FROM {table_name}
                        WHERE grid_id = %s AND year >= %s AND year <= %s
                    """
                    cursor.execute(query, (grid_id, start_year, end_year))
                else:
                    # 개별 연도
                    query = f"""
                        SELECT {self.ssp_column} as value
                        FROM {table_name}
                        WHERE grid_id = %s AND year = %s
                    """
                    cursor.execute(query, (grid_id, int_year))

                result = cursor.fetchone()
                if result and result["value"] is not None:
                    return float(result["value"])
                return None
        except Exception as e:
            logger.error(f"Failed to extract {variable} from DB: {e}")
            return None

    def _extract_observation_date_value(
        self, variable: str, lat: float, lon: float, year: int, table_name: str
    ) -> Optional[float]:
        """
        observation_date 컬럼 기반 테이블에서 연간 집계값 추출

        집계 방식:
        - TXx: 연간 최고기온 (MAX)
        - TNn: 연간 최저기온 (MIN)
        - SU25: 폭염일수 (최고기온 > 25도 COUNT)
        - TR25: 열대야일수 (최저기온 > 25도 COUNT)
        - FD0: 서리일수 (최저기온 < 0도 COUNT)
        - ID0: 결빙일수 (최고기온 < 0도 COUNT)
        - RHM, WS, SI, TA: 연평균 (AVG)
        - RN: 연강수량 (SUM)

        Decadal year (예: "2030s") 지원:
        - "2030s" → 2030-2039년의 평균값 반환
        """
        grid_id = self._get_grid_id(lat, lon)
        if grid_id is None:
            return None

        # year 파싱 (decadal 여부 확인)
        int_year, is_decadal = self._parse_year(year)

        # 변수별 집계 쿼리 매핑
        if is_decadal:
            # Decadal year: 10년 범위 (예: 2030-2039)
            start_year = int_year
            end_year = int_year + 9
            agg_queries = {
                "TXx": f"SELECT MAX({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) >= %s AND EXTRACT(YEAR FROM observation_date) <= %s",
                "TNn": f"SELECT MIN({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) >= %s AND EXTRACT(YEAR FROM observation_date) <= %s",
                "SU25": f"SELECT AVG(cnt) as value FROM (SELECT EXTRACT(YEAR FROM observation_date) as yr, COUNT(*) as cnt FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) >= %s AND EXTRACT(YEAR FROM observation_date) <= %s AND {self.ssp_column} > 25 GROUP BY yr) sub",
                "TR25": f"SELECT AVG(cnt) as value FROM (SELECT EXTRACT(YEAR FROM observation_date) as yr, COUNT(*) as cnt FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) >= %s AND EXTRACT(YEAR FROM observation_date) <= %s AND {self.ssp_column} > 25 GROUP BY yr) sub",
                "FD0": f"SELECT AVG(cnt) as value FROM (SELECT EXTRACT(YEAR FROM observation_date) as yr, COUNT(*) as cnt FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) >= %s AND EXTRACT(YEAR FROM observation_date) <= %s AND {self.ssp_column} < 0 GROUP BY yr) sub",
                "ID0": f"SELECT AVG(cnt) as value FROM (SELECT EXTRACT(YEAR FROM observation_date) as yr, COUNT(*) as cnt FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) >= %s AND EXTRACT(YEAR FROM observation_date) <= %s AND {self.ssp_column} < 0 GROUP BY yr) sub",
                "RN": f"SELECT AVG(sm) as value FROM (SELECT EXTRACT(YEAR FROM observation_date) as yr, SUM({self.ssp_column}) as sm FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) >= %s AND EXTRACT(YEAR FROM observation_date) <= %s GROUP BY yr) sub",
                "RHM": f"SELECT AVG({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) >= %s AND EXTRACT(YEAR FROM observation_date) <= %s",
                "WS": f"SELECT AVG({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) >= %s AND EXTRACT(YEAR FROM observation_date) <= %s",
                "SI": f"SELECT AVG({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) >= %s AND EXTRACT(YEAR FROM observation_date) <= %s",
                "TA": f"SELECT AVG({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) >= %s AND EXTRACT(YEAR FROM observation_date) <= %s",
                "SPEI12": f"SELECT AVG({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) >= %s AND EXTRACT(YEAR FROM observation_date) <= %s",
            }
            params = (grid_id, start_year, end_year)
        else:
            # 개별 연도
            agg_queries = {
                "TXx": f"SELECT MAX({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) = %s",
                "TNn": f"SELECT MIN({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) = %s",
                "SU25": f"SELECT COUNT(*) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) = %s AND {self.ssp_column} > 25",
                "TR25": f"SELECT COUNT(*) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) = %s AND {self.ssp_column} > 25",
                "FD0": f"SELECT COUNT(*) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) = %s AND {self.ssp_column} < 0",
                "ID0": f"SELECT COUNT(*) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) = %s AND {self.ssp_column} < 0",
                "RN": f"SELECT SUM({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) = %s",
                "RHM": f"SELECT AVG({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) = %s",
                "WS": f"SELECT AVG({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) = %s",
                "SI": f"SELECT AVG({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) = %s",
                "TA": f"SELECT AVG({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) = %s",
                "SPEI12": f"SELECT AVG({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) = %s",
            }
            params = (grid_id, int_year)

        query = agg_queries.get(variable)
        if not query:
            # 기본값: 평균
            if is_decadal:
                start_year = int_year
                end_year = int_year + 9
                query = f"SELECT AVG({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) >= %s AND EXTRACT(YEAR FROM observation_date) <= %s"
                params = (grid_id, start_year, end_year)
            else:
                query = f"SELECT AVG({self.ssp_column}) as value FROM {table_name} WHERE grid_id = %s AND EXTRACT(YEAR FROM observation_date) = %s"
                params = (grid_id, int_year)

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)

                result = cursor.fetchone()
                if result and result["value"] is not None:
                    return float(result["value"])
                return None
        except Exception as e:
            logger.error(f"Failed to extract {variable} from DB (observation_date): {e}")
            return None

    def _extract_monthly_value(
        self, variable: str, lat: float, lon: float, year: int, month: int = 6
    ) -> Optional[float]:
        """
        DB에서 월간 데이터 추출

        Args:
            variable: 변수명 (SPEI12, TA, RN 등)
            lat: 위도
            lon: 경도
            year: 연도
            month: 월 (1-12)

        Returns:
            추출된 값 또는 None
        """
        if not DB_AVAILABLE:
            return None

        # OBSERVATION_DATE_TABLE_MAP 사용
        table_name = self.OBSERVATION_DATE_TABLE_MAP.get(variable)
        if not table_name:
            logger.warning(f"Unknown monthly variable: {variable}")
            return None

        grid_id = self._get_grid_id(lat, lon)
        if grid_id is None:
            return None

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()
                # 월간 데이터는 observation_date 컬럼 사용
                query = f"""
                    SELECT {self.ssp_column} as value
                    FROM {table_name}
                    WHERE grid_id = %s
                      AND EXTRACT(YEAR FROM observation_date) = %s
                      AND EXTRACT(MONTH FROM observation_date) = %s
                """
                cursor.execute(query, (grid_id, year, month))

                result = cursor.fetchone()
                if result and result["value"] is not None:
                    return float(result["value"])
                return None
        except Exception as e:
            logger.error(f"Failed to extract monthly {variable} from DB: {e}")
            return None

    def get_extreme_heat_data(self, lat: float, lon: float, year: int = 2030) -> Dict:
        """
        극심한 고온 데이터 추출

        Args:
            lat: 위도
            lon: 경도
            year: 분석 연도 (2021-2100)

        Returns:
            {
                'annual_max_temp_celsius': float,
                'heatwave_days_per_year': int,
                'tropical_nights': int,
                'heat_wave_duration': float,
                'data_source': str
            }
        """
        try:
            # WSDI: 온난일 지속지수
            wsdix = self._extract_value("WSDIx", lat, lon, year)

            # TXx: 연간 최고기온
            txx = self._extract_value("TXx", lat, lon, year)

            # SU25, TR25는 별도 계산 필요 (현재는 기본값 사용)
            su25 = self._extract_value("SU25", lat, lon, year)
            tr25 = self._extract_value("TR25", lat, lon, year)

            data_source = "DB" if wsdix is not None else "fallback"

            return {
                "annual_max_temp_celsius": float(txx) if txx is not None else 38.5,
                "heatwave_days_per_year": int(su25) if su25 is not None else 25,
                "tropical_nights": int(tr25) if tr25 is not None else 15,
                "heat_wave_duration": float(wsdix) if wsdix is not None else 10,
                "wsdi": float(wsdix) if wsdix is not None else 10,  # 추가
                "climate_scenario": self.scenario,
                "year": year,
                "data_source": data_source,
            }
        except Exception as e:
            logger.error(f"극심한 고온 데이터 로드 실패: {e}")
            return {
                "annual_max_temp_celsius": 38.5,
                "heatwave_days_per_year": 25,
                "tropical_nights": 15,
                "heat_wave_duration": 10,
                "wsdi": 10,
                "climate_scenario": self.scenario,
                "year": year,
                "data_source": "fallback",
            }

    def get_extreme_cold_data(self, lat: float, lon: float, year: int = 2030) -> Dict:
        """
        극심한 한파 데이터 추출

        Returns:
            {
                'annual_min_temp_celsius': float,
                'coldwave_days_per_year': int,
                'ice_days': int,
                'cold_wave_duration': float,
                'data_source': str
            }
        """
        try:
            # CSDI: 한랭일 지속지수
            csdix = self._extract_value("CSDIx", lat, lon, year)

            # TNn: 연간 최저기온
            tnn = self._extract_value("TNn", lat, lon, year)

            # FD0, ID0는 별도 계산 필요
            fd0 = self._extract_value("FD0", lat, lon, year)
            id0 = self._extract_value("ID0", lat, lon, year)

            data_source = "DB" if csdix is not None else "fallback"

            return {
                "annual_min_temp_celsius": float(tnn) if tnn is not None else -15.0,
                "coldwave_days_per_year": int(fd0) if fd0 is not None else 10,
                "ice_days": int(id0) if id0 is not None else 5,
                "cold_wave_duration": float(csdix) if csdix is not None else 8,
                "csdi": float(csdix) if csdix is not None else 8,  # 추가
                "climate_scenario": self.scenario,
                "year": year,
                "data_source": data_source,
            }
        except Exception as e:
            logger.error(f"극심한 한파 데이터 로드 실패: {e}")
            return {
                "annual_min_temp_celsius": -15.0,
                "coldwave_days_per_year": 10,
                "ice_days": 5,
                "cold_wave_duration": 8,
                "csdi": 8,
                "climate_scenario": self.scenario,
                "year": year,
                "data_source": "fallback",
            }

    def get_drought_data(self, lat: float, lon: float, year: int = 2030) -> Dict:
        """
        가뭄 데이터 추출

        Returns:
            {
                'spei12_index': float,
                'annual_rainfall_mm': float,
                'consecutive_dry_days': int,
                'rainfall_intensity': float,
                'data_source': str
            }
        """
        try:
            # SPEI-12: 12개월 표준화 강수증발산지수 (6월 기준)
            spei12 = self._extract_monthly_value("SPEI12", lat, lon, year, month=6)

            # CDD: 최대 연속 무강수일수
            cdd = self._extract_value("CDD", lat, lon, year)

            # SDII: 강수일 평균 강수강도
            sdii = self._extract_value("SDII", lat, lon, year)

            # RAIN80: 80mm 이상 강수일수
            rain80 = self._extract_value("RAIN80", lat, lon, year)

            # RN: 연간 총 강수량 (월간 합계)
            annual_rainfall = self._get_annual_rainfall(lat, lon, year)

            data_source = "DB" if spei12 is not None or cdd is not None else "fallback"

            return {
                "spei12_index": float(spei12) if spei12 is not None else None,
                "annual_rainfall_mm": float(annual_rainfall) if annual_rainfall else 1200.0,
                "consecutive_dry_days": int(cdd) if cdd is not None else 15,
                "cdd": int(cdd) if cdd is not None else 15,
                "rainfall_intensity": float(sdii) if sdii is not None else 10.0,
                "sdii": float(sdii) if sdii is not None else 10.0,
                "rain80_days": int(rain80) if rain80 is not None else 5,
                "rain80": int(rain80) if rain80 is not None else 5,
                "climate_scenario": self.scenario,
                "year": year,
                "data_source": data_source,
            }
        except Exception as e:
            logger.error(f"가뭄 데이터 로드 실패: {e}")
            return {
                "spei12_index": None,
                "annual_rainfall_mm": 1200.0,
                "consecutive_dry_days": 15,
                "cdd": 15,
                "rainfall_intensity": 10.0,
                "sdii": 10.0,
                "rain80_days": 5,
                "rain80": 5,
                "climate_scenario": self.scenario,
                "year": year,
                "data_source": "fallback",
            }

    def _get_annual_rainfall(self, lat: float, lon: float, year: int) -> Optional[float]:
        """연간 총 강수량 계산 (월별 합계)"""
        if not DB_AVAILABLE:
            return None

        grid_id = self._get_grid_id(lat, lon)
        if grid_id is None:
            return None

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()
                query = f"""
                    SELECT SUM({self.ssp_column}) as total
                    FROM rn_data
                    WHERE grid_id = %s
                      AND EXTRACT(YEAR FROM observation_date) = %s
                """
                cursor.execute(query, (grid_id, year))
                result = cursor.fetchone()
                if result and result["total"]:
                    return float(result["total"])
                return None
        except Exception as e:
            logger.error(f"Failed to get annual rainfall: {e}")
            return None

    def get_flood_data(self, lat: float, lon: float, year: int = 2030) -> Dict:
        """
        홍수 데이터 추출

        Returns:
            {
                'max_1day_rainfall_mm': float,
                'max_5day_rainfall_mm': float,
                'heavy_rain_days': int,
                'extreme_rain_95p': float,
                'data_source': str
            }
        """
        try:
            # RX1DAY: 1일 최대 강수량
            rx1day = self._extract_value("RX1DAY", lat, lon, year)

            # RX5DAY: 5일 최대 강수량
            rx5day = self._extract_value("RX5DAY", lat, lon, year)

            # RAIN80: 강수량 80mm 이상 일수
            rain80 = self._extract_value("RAIN80", lat, lon, year)

            # SDII: 강수강도
            sdii = self._extract_value("SDII", lat, lon, year)

            data_source = "DB" if rx1day is not None else "fallback"

            return {
                "max_1day_rainfall_mm": float(rx1day) if rx1day is not None else 250.0,
                "rx1day": float(rx1day) if rx1day is not None else 250.0,  # 추가
                "max_5day_rainfall_mm": float(rx5day) if rx5day is not None else 400.0,
                "rx5day": float(rx5day) if rx5day is not None else 400.0,  # 추가
                "heavy_rain_days": int(rain80) if rain80 is not None else 5,
                "rain80": int(rain80) if rain80 is not None else 5,  # 추가
                "extreme_rain_95p": float(sdii) if sdii is not None else 200.0,
                "sdii": float(sdii) if sdii is not None else 10.0,  # 추가
                "climate_scenario": self.scenario,
                "year": year,
                "data_source": data_source,
            }
        except Exception as e:
            logger.error(f"홍수 데이터 로드 실패: {e}")
            return {
                "max_1day_rainfall_mm": 250.0,
                "rx1day": 250.0,
                "max_5day_rainfall_mm": 400.0,
                "rx5day": 400.0,
                "heavy_rain_days": 5,
                "rain80": 5,
                "extreme_rain_95p": 200.0,
                "sdii": 10.0,
                "climate_scenario": self.scenario,
                "year": year,
                "data_source": "fallback",
            }

    def get_fwi_input_data(self, lat: float, lon: float, year: int = 2030) -> Dict:
        """
        산불위험지수(FWI) 계산용 입력 데이터

        Returns:
            {
                'relative_humidity': float,
                'wind_speed_ms': float,
                'annual_rainfall_mm': float,
                'data_source': str
            }
        """
        try:
            # TA: 기온
            ta = self._extract_value("TA", lat, lon, year)

            # RHM: 상대습도
            rhm = self._extract_value("RHM", lat, lon, year)

            # WS: 풍속
            ws = self._extract_value("WS", lat, lon, year)

            # 연간 강수량
            annual_rainfall = self._get_annual_rainfall(lat, lon, year)

            data_source = "DB" if rhm is not None else "fallback"

            return {
                "temperature": float(ta) if ta is not None else 25.0,
                "ta": float(ta) if ta is not None else 25.0,  # 추가
                "avg_temperature": float(ta) if ta is not None else 25.0,  # 추가
                "relative_humidity": float(rhm) if rhm is not None else 65.0,
                "rhm": float(rhm) if rhm is not None else 65.0,  # 추가
                "wind_speed_ms": float(ws) if ws is not None else 3.5,
                "ws": float(ws) if ws is not None else 3.5,  # 추가
                "annual_rainfall_mm": float(annual_rainfall) if annual_rainfall else 1200.0,
                "rn": float(annual_rainfall) if annual_rainfall else 1200.0,  # 추가
                "climate_scenario": self.scenario,
                "year": year,
                "data_source": data_source,
            }
        except Exception as e:
            logger.error(f"FWI 입력 데이터 로드 실패: {e}")
            return {
                "temperature": 25.0,
                "ta": 25.0,
                "avg_temperature": 25.0,
                "relative_humidity": 65.0,
                "rhm": 65.0,
                "wind_speed_ms": 3.5,
                "ws": 3.5,
                "annual_rainfall_mm": 1200.0,
                "rn": 1200.0,
                "climate_scenario": self.scenario,
                "year": year,
                "data_source": "fallback",
            }

    def get_typhoon_data(self, lat: float, lon: float, year: int = 2030) -> Dict:
        """
        태풍 관련 데이터 추출 (DB에서 직접 조회)

        Returns:
            {
                'typhoon_frequency': int,
                'max_wind_speed_ms': float,
                'distance_to_coast_m': float,
                'rx1day': float,
                'data_source': str
            }
        """
        result = {
            "typhoon_frequency": 0,
            "max_wind_speed_ms": 30.0,
            "distance_to_coast_m": 50000.0,
            "typhoons": [],
            "data_source": "fallback",
        }

        if not DB_AVAILABLE:
            return result

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                # 1. 해안선 거리 조회 (sea_level_grid에서)
                try:
                    cursor.execute(
                        """
                        SELECT ST_Distance(
                            geom::geography,
                            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                        ) AS distance_m
                        FROM sea_level_grid
                        WHERE geom IS NOT NULL
                        ORDER BY geom::geography <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                        LIMIT 1
                    """,
                        (lon, lat, lon, lat),
                    )
                    dist_result = cursor.fetchone()
                    if dist_result:
                        result["distance_to_coast_m"] = float(dist_result["distance_m"])
                except Exception as e:
                    logger.debug(f"Failed to get distance to coast: {e}")
                    # 트랜잭션 에러 시 롤백
                    conn.rollback()

                # 2. 태풍 이력 조회 - api_typhoon_track 우선, 없으면 besttrack fallback
                # 미래 예측 데이터가 없으므로 과거 전체 데이터 통계 사용
                cursor.execute("""
                    SELECT COUNT(DISTINCT year || '_' || typ_seq) as typhoon_count,
                           MAX(wind_speed_ms) as max_wind
                    FROM api_typhoon_track
                """)
                typhoon_result = cursor.fetchone()

                # api_typhoon_track에 데이터가 없으면 besttrack에서 조회
                if not typhoon_result or typhoon_result["typhoon_count"] == 0:
                    cursor.execute("""
                        SELECT COUNT(DISTINCT year || '-' || tcid) as typhoon_count,
                               MAX(max_wind_speed) as max_wind
                        FROM api_typhoon_besttrack
                    """)
                    typhoon_result = cursor.fetchone()

                if typhoon_result:
                    result["typhoon_frequency"] = int(typhoon_result["typhoon_count"] or 0)
                    result["max_wind_speed_ms"] = float(typhoon_result["max_wind"] or 30.0)

                # 2-2. 태풍 상세 레코드 조회 - api_typhoon_track 우선 (반경 데이터 있음)
                # 거리순으로 정렬하여 최근접 태풍 데이터 조회
                cursor.execute(
                    """
                    SELECT CONCAT(year, '_', typ_seq) as tcid, year,
                           EXTRACT(MONTH FROM typ_tm)::int as month,
                           EXTRACT(DAY FROM typ_tm)::int as day,
                           EXTRACT(HOUR FROM typ_tm)::int as hour,
                           longitude as lon, latitude as lat,
                           grade, wind_speed_ms as max_wind_speed, pressure_hpa as central_pressure,
                           rad15_km as gale_long, rad15_km as gale_short, direction as gale_dir,
                           rad25_km as storm_long, rad25_km as storm_short, direction as storm_dir,
                           CONCAT('TYP_', typ_seq) as typhoon_name
                    FROM api_typhoon_track
                    ORDER BY location::geography <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                             year DESC, typ_tm DESC
                    LIMIT 100
                """,
                    (lon, lat),
                )
                typhoon_records = cursor.fetchall()

                # api_typhoon_track에 데이터가 없으면 api_typhoon_besttrack에서 조회
                if not typhoon_records:
                    cursor.execute(
                        """
                        SELECT tcid, year, month, day, hour,
                               longitude as lon, latitude as lat,
                               grade, max_wind_speed, central_pressure,
                               gale_long, gale_short, gale_dir,
                               storm_long, storm_short, storm_dir,
                               typhoon_name
                        FROM api_typhoon_besttrack
                        ORDER BY ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                                 year DESC, month DESC, day DESC
                        LIMIT 100
                    """,
                        (lon, lat),
                    )
                    typhoon_records = cursor.fetchall()

                if typhoon_records:
                    result["typhoons"] = [dict(rec) for rec in typhoon_records]

                # 3. RX1DAY 조회
                rx1day = self._extract_value("RX1DAY", lat, lon, year)
                result["rx1day"] = float(rx1day) if rx1day is not None else 250.0
                result["max_1day_rainfall_mm"] = result["rx1day"]

                result["data_source"] = "DB"

        except Exception as e:
            logger.error(f"태풍 데이터 로드 실패: {e}")

        return result

    def get_sea_level_rise_data(self, lat: float, lon: float, year: int = 2050) -> Dict:
        """
        해수면 상승 데이터 추출 (DB에서 직접 조회)

        Returns:
            {
                'sea_level_rise_cm': float,
                'distance_to_coast_m': float,
                'data_source': str
            }
        """
        result = {
            "sea_level_rise_cm": 20.0,
            "sea_level_rise_mm": 200.0,
            "slr": 20.0,
            "distance_to_coast_m": 50000.0,
            "climate_scenario": self.scenario,
            "year": year,
            "data_source": "fallback",
        }

        if not DB_AVAILABLE:
            return result

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                # 1. 데이터가 있는 가장 가까운 해수면 격자 + 해안선 거리
                query = f"""
                    SELECT g.grid_id, g.longitude, g.latitude,
                           ST_Distance(
                               g.geom::geography,
                               ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                           ) AS distance_m,
                           d.{self.ssp_column} as slr_cm
                    FROM sea_level_grid g
                    INNER JOIN sea_level_data d ON g.grid_id = d.grid_id
                    WHERE g.geom IS NOT NULL
                      AND d.year = %s
                      AND d.{self.ssp_column} IS NOT NULL
                    ORDER BY g.geom::geography <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    LIMIT 1
                """
                cursor.execute(query, (lon, lat, year, lon, lat))

                grid_result = cursor.fetchone()
                if grid_result:
                    result["distance_to_coast_m"] = float(grid_result["distance_m"])
                    result["sea_level_rise_cm"] = float(grid_result["slr_cm"])
                    result["sea_level_rise_mm"] = float(grid_result["slr_cm"]) * 10
                    result["slr"] = float(grid_result["slr_cm"])
                    result["data_source"] = "DB"

                    # 2050, 2100 데이터도 조회
                    grid_id = grid_result["grid_id"]
                    cursor.execute(
                        f"""
                        SELECT year, {self.ssp_column} as slr_cm
                        FROM sea_level_data
                        WHERE grid_id = %s AND year IN (2050, 2100)
                    """,
                        (grid_id,),
                    )
                    slr_data = {row["year"]: row["slr_cm"] for row in cursor.fetchall()}
                    result["sea_level_rise_2050_cm"] = float(slr_data.get(2050) or 10.0)
                    result["sea_level_rise_2100_cm"] = float(slr_data.get(2100) or 30.0)
                else:
                    # 해안선 거리만 조회 (데이터가 없는 경우)
                    cursor.execute(
                        """
                        SELECT ST_Distance(
                            geom::geography,
                            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                        ) AS distance_m
                        FROM sea_level_grid
                        WHERE geom IS NOT NULL
                        ORDER BY geom::geography <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                        LIMIT 1
                    """,
                        (lon, lat, lon, lat),
                    )
                    dist_result = cursor.fetchone()
                    if dist_result:
                        result["distance_to_coast_m"] = float(dist_result["distance_m"])

        except Exception as e:
            logger.error(f"해수면 상승 데이터 로드 실패: {e}")

        return result

    def get_water_stress_data(self, lat: float, lon: float, year: int = 2030) -> Dict:
        """
        물 스트레스 관련 데이터 추출

        Returns:
            {
                'annual_rainfall_mm': float,
                'consecutive_dry_days': int,
                'data_source': str
            }
        """
        try:
            cdd = self._extract_value("CDD", lat, lon, year)
            annual_rainfall = self._get_annual_rainfall(lat, lon, year)

            data_source = "DB" if cdd is not None else "fallback"

            return {
                "annual_rainfall_mm": float(annual_rainfall) if annual_rainfall else 1200.0,
                "consecutive_dry_days": int(cdd) if cdd is not None else 15,
                "cdd": int(cdd) if cdd is not None else 15,
                "climate_scenario": self.scenario,
                "year": year,
                "data_source": data_source,
            }
        except Exception as e:
            logger.error(f"물 스트레스 데이터 로드 실패: {e}")
            return {
                "annual_rainfall_mm": 1200.0,
                "consecutive_dry_days": 15,
                "cdd": 15,
                "climate_scenario": self.scenario,
                "year": year,
                "data_source": "fallback",
            }

    # ==================== Timeseries 메서드 ====================

    def get_extreme_heat_timeseries(
        self, lat: float, lon: float, start_year: int = 2021, end_year: int = 2100
    ) -> Dict:
        """극심한 고온 시계열 데이터"""
        years = list(range(start_year, end_year + 1))
        data = {"years": years, "wsdi": [], "txx": [], "climate_scenario": self.scenario}

        for year in years:
            heat_data = self.get_extreme_heat_data(lat, lon, year)
            data["wsdi"].append(heat_data.get("wsdi", 10))
            data["txx"].append(heat_data.get("annual_max_temp_celsius", 38.5))

        return data

    def get_extreme_cold_timeseries(
        self, lat: float, lon: float, start_year: int = 2021, end_year: int = 2100
    ) -> Dict:
        """극심한 한파 시계열 데이터"""
        years = list(range(start_year, end_year + 1))
        data = {"years": years, "csdi": [], "tnn": [], "climate_scenario": self.scenario}

        for year in years:
            cold_data = self.get_extreme_cold_data(lat, lon, year)
            data["csdi"].append(cold_data.get("csdi", 8))
            data["tnn"].append(cold_data.get("annual_min_temp_celsius", -15.0))

        return data

    def get_drought_timeseries(
        self, lat: float, lon: float, start_year: int = 2021, end_year: int = 2100
    ) -> Dict:
        """가뭄 시계열 데이터"""
        years = list(range(start_year, end_year + 1))
        data = {"years": years, "cdd": [], "spei12": [], "climate_scenario": self.scenario}

        for year in years:
            drought_data = self.get_drought_data(lat, lon, year)
            data["cdd"].append(drought_data.get("cdd", 15))
            data["spei12"].append(drought_data.get("spei12_index"))

        return data

    def get_flood_timeseries(
        self, lat: float, lon: float, start_year: int = 2021, end_year: int = 2100
    ) -> Dict:
        """홍수 시계열 데이터"""
        years = list(range(start_year, end_year + 1))
        data = {
            "years": years,
            "rx1day": [],
            "rx5day": [],
            "rain80": [],
            "climate_scenario": self.scenario,
        }

        for year in years:
            flood_data = self.get_flood_data(lat, lon, year)
            data["rx1day"].append(flood_data.get("rx1day", 250.0))
            data["rx5day"].append(flood_data.get("rx5day", 400.0))
            data["rain80"].append(flood_data.get("rain80", 5))

        return data

    def get_wildfire_timeseries(
        self, lat: float, lon: float, start_year: int = 2021, end_year: int = 2100
    ) -> Dict:
        """
        산불 시계열 데이터 (FWI 계산용)

        Returns:
            {
                'years': list,
                'ta': list (평균기온),
                'rhm': list (상대습도),
                'ws': list (풍속),
                'rn': list (강수량),
                'cdd': list (연속무강수일),
                'climate_scenario': str
            }
        """
        years = list(range(start_year, end_year + 1))
        data = {
            "years": years,
            "ta": [],
            "rhm": [],
            "ws": [],
            "rn": [],
            "cdd": [],
            "climate_scenario": self.scenario,
        }

        for year in years:
            # 평균기온 (TA)
            ta = self._extract_value("TA", lat, lon, year)
            data["ta"].append(float(ta) if ta is not None else 15.0)

            # 상대습도 (RHM)
            rhm = self._extract_value("RHM", lat, lon, year)
            data["rhm"].append(float(rhm) if rhm is not None else 65.0)

            # 풍속 (WS)
            ws = self._extract_value("WS", lat, lon, year)
            data["ws"].append(float(ws) if ws is not None else 3.5)

            # 강수량 (RN) - 연간 합계
            rn = self._get_annual_rainfall(lat, lon, year)
            data["rn"].append(float(rn) if rn is not None else 1200.0)

            # 연속무강수일 (CDD)
            cdd = self._extract_value("CDD", lat, lon, year)
            data["cdd"].append(int(cdd) if cdd is not None else 15)

        return data

    def get_sea_level_rise_timeseries(
        self, lat: float, lon: float, start_year: int = 2021, end_year: int = 2100
    ) -> Dict:
        """해수면 상승 시계열 데이터"""
        years = list(range(start_year, end_year + 1))
        data = {"years": years, "slr": [], "climate_scenario": self.scenario}

        for year in years:
            slr_data = self.get_sea_level_rise_data(lat, lon, year)
            data["slr"].append(slr_data.get("sea_level_rise_cm", 20.0))

        return data


# 이전 버전 호환성을 위한 alias
KMAClimateDataLoader = ClimateDataLoader
