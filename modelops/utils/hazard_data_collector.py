from typing import Dict, Any
import os
import logging
from dotenv import load_dotenv

# 로거 설정
logger = logging.getLogger(__name__)


def _build_db_url() -> str:
    """settings 기반 PostgreSQL 접속 URL 생성 (자격증명 하드코딩 금지)."""
    from modelops.config.settings import settings, _require_database_password

    password = _require_database_password(settings.dw_db_password)
    return (
        f"postgresql://{settings.dw_db_user}:{password}"
        f"@{settings.dw_db_host}:{settings.dw_db_port}/{settings.dw_db_name}"
    )


# 데이터 로더 및 페처 임포트
try:
    from modelops.data_loaders.building_data_fetcher import BuildingDataFetcher
    from modelops.data_loaders.disaster_api_fetcher import DisasterAPIFetcher
    from modelops.data_loaders.climate_data_loader import ClimateDataLoader
    from modelops.data_loaders.spatial_data_loader import SpatialDataLoader
    from modelops.data_loaders.wamis_fetcher import WamisFetcher
    from modelops.utils.fwi_calculator import FWICalculator
    from modelops.config import hazard_config as config

    DATA_LOADERS_AVAILABLE = True
except ImportError as e:
    logger.error(f"Failed to import data loaders: {e}")
    DATA_LOADERS_AVAILABLE = False
    # Mock classes for graceful degradation
    BuildingDataFetcher = None
    DisasterAPIFetcher = None
    ClimateDataLoader = None
    SpatialDataLoader = None
    WamisFetcher = None
    FWICalculator = None
    config = None

# BuildingDataLoader import (DB 캐시 사용)
try:
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../etl"))
    from building_characteristics_loader import BuildingDataLoader

    BUILDING_LOADER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"BuildingDataLoader import 실패: {e}")
    BuildingDataLoader = None
    BUILDING_LOADER_AVAILABLE = False


class HazardDataCollector:
    """
    각 Hazard Agent가 필요로 하는 데이터를 수집하고 준비하는 중앙 유틸리티 클래스.
    HazardCalculator의 데이터 수집 로직을 이관함.
    """

    def __init__(self, scenario: str = "SSP245", target_year: int = 2030):
        """
        Args:
            scenario: SSP 시나리오 (SSP126, SSP245, SSP370, SSP585)
            target_year: 분석 연도 (2021-2100)
        """
        self.scenario = scenario
        self.target_year = target_year
        self._load_environment()

        if not DATA_LOADERS_AVAILABLE:
            logger.warning("데이터 로더를 사용할 수 없습니다. Mock 모드로 실행됩니다.")
            self.building_fetcher = None
            self.disaster_fetcher = None
            self.climate_loader = None
            self.spatial_loader = None
            self.wamis_fetcher = None
            self.fwi_calculator = None
            return

        # 데이터 로더 초기화 (Lazy loading을 고려할 수도 있으나, 현재는 생성 시 초기화)
        try:
            self.building_fetcher = BuildingDataFetcher() if BuildingDataFetcher else None
        except Exception as e:
            logger.warning(f"BuildingDataFetcher 초기화 실패: {e}")
            self.building_fetcher = None

        # DatabaseManager 초기화 (DB 캐시 조회용)
        try:
            from modelops.utils.database import DatabaseManager

            db_url = _build_db_url()
            self.db_manager = DatabaseManager(database_url=db_url)
            logger.info("DatabaseManager 초기화 성공")
        except Exception as e:
            logger.warning(f"DatabaseManager 초기화 실패: {e}")
            self.db_manager = None

        # BuildingDataLoader 초기화 (DB 캐시 우선 사용)
        try:
            if BUILDING_LOADER_AVAILABLE and BuildingDataLoader:
                db_url = _build_db_url()
                self.building_loader = BuildingDataLoader(db_url=db_url)
                logger.info("BuildingDataLoader 초기화 성공 (DB 캐시 사용)")
            else:
                self.building_loader = None
        except Exception as e:
            logger.warning(f"BuildingDataLoader 초기화 실패: {e}")
            self.building_loader = None

        try:
            self.disaster_fetcher = DisasterAPIFetcher() if DisasterAPIFetcher else None
        except Exception as e:
            logger.warning(f"DisasterAPIFetcher 초기화 실패: {e}")
            self.disaster_fetcher = None

        # ClimateDataLoader는 scenario 의존성 있음
        try:
            self.climate_loader = (
                ClimateDataLoader(scenario=scenario) if ClimateDataLoader else None
            )
        except Exception as e:
            logger.warning(f"ClimateDataLoader 초기화 실패: {e}")
            self.climate_loader = None

        try:
            self.spatial_loader = SpatialDataLoader() if SpatialDataLoader else None
        except Exception as e:
            logger.warning(f"SpatialDataLoader 초기화 실패: {e}")
            self.spatial_loader = None

        try:
            self.wamis_fetcher = WamisFetcher() if WamisFetcher else None
        except Exception as e:
            logger.warning(f"WamisFetcher 초기화 실패: {e}")
            self.wamis_fetcher = None

        try:
            self.fwi_calculator = FWICalculator() if FWICalculator else None
        except Exception as e:
            logger.warning(f"FWICalculator 초기화 실패: {e}")
            self.fwi_calculator = None

        # KMA API Key 확인
        self.kma_api_key = os.getenv("KMA_API_KEY")
        if not self.kma_api_key:
            logger.warning("KMA_API_KEY가 설정되지 않았습니다. 일부 기능이 제한될 수 있습니다.")

    def _load_environment(self):
        """환경 변수 로드"""
        # 프로젝트 루트의 .env 파일 로드 시도
        # 현재 위치: modelops/utils/hazard_data_collector.py
        # 루트: ../../.env
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path)
        else:
            logger.warning(f".env 파일을 찾을 수 없습니다: {env_path}")

    def collect_data(self, lat: float, lon: float, risk_type: str) -> Dict[str, Any]:
        """
        특정 리스크 유형에 필요한 데이터를 수집합니다.

        Args:
            lat: 위도
            lon: 경도
            risk_type: 리스크 유형 (예: 'extreme_heat', 'river_flood')

        Returns:
            에이전트 계산에 필요한 'collected_data' 딕셔너리
        """
        # 1. 기본 메타데이터 및 공통 데이터
        collected_data = {
            "latitude": lat,
            "longitude": lon,
            "risk_type": risk_type,
            "scenario": self.scenario,
            "target_year": self.target_year,
            "building_data": {},  # 기본적으로 비어있음, 필요 시 채움
            "climate_data": {},
            "spatial_data": {},
            "disaster_data": {},
            "extra_data": {},
        }

        # 2. 건물 정보 (DB 캐시 우선, 없으면 API 호출)
        try:
            # 좌표 체크
            is_daedeok = (36.37 < lat < 36.39) and (127.39 < lon < 127.41)
            is_sk_u_tower = (37.36 < lat < 37.37) and (127.10 < lon < 127.11)
            is_pangyo = (37.40 < lat < 37.41) and (127.09 < lon < 127.10)

            # STEP 1: DB 캐시 우선 조회 (좌표 기반)
            building_cache = None
            if self.db_manager:
                building_cache = self.db_manager.fetch_building_cache_by_coords(lat=lat, lon=lon)
                if building_cache:
                    logger.info(
                        f"✅ DB 캐시 사용: 지상{building_cache.get('max_ground_floors')}층, 연면적{building_cache.get('total_floor_area_sqm')}m²"
                    )

            # STEP 2: DB 캐시 있으면 그걸 사용, 없으면 API 호출
            if building_cache:
                # DB 캐시 데이터를 building_data 형식으로 변환
                structure_types = building_cache.get("structure_types", [])
                purpose_types = building_cache.get("purpose_types", [])

                # structure_types, purpose_types는 list로 반환됨 (JSONB keys)
                if isinstance(structure_types, list):
                    structure = structure_types[0] if structure_types else "철근콘크리트구조"
                else:
                    structure = "철근콘크리트구조"

                if isinstance(purpose_types, list):
                    main_purpose = purpose_types[0] if purpose_types else "업무시설"
                else:
                    main_purpose = "업무시설"

                collected_data["building_data"] = {
                    "floors_below": building_cache.get("max_underground_floors", 0),
                    "ground_floors": building_cache.get("max_ground_floors", 0),
                    "total_area_m2": building_cache.get("total_floor_area_sqm", 0),
                    "building_height": building_cache.get("max_ground_floors", 0)
                    * 4,  # 층당 4m 추정
                    "building_age": building_cache.get("oldest_building_age_years", 30),
                    "build_year": 2024 - building_cache.get("oldest_building_age_years", 30),
                    "structure_type": structure,
                    "main_purpose": main_purpose,
                    "has_piloti": False,
                    "has_water_tank": True,
                    "distance_to_river_m": 500,
                }
                logger.info(
                    f"✅ DB 캐시 → 건물 데이터 변환: age={collected_data['building_data'].get('building_age')}, floors={collected_data['building_data'].get('ground_floors')}, area={collected_data['building_data'].get('total_area_m2')}"
                )
            elif self.building_loader:
                # DB 캐시 없으면 API 호출
                logger.info("⚠️ DB 캐시 없음 - API 호출")
                building_full_data = self.building_loader.load_and_cache(
                    lat=lat, lon=lon, address=None
                )
                # 대덕은 building_count 0이어도 처리
                if building_full_data and (
                    building_full_data.get("meta", {}).get("building_count", 0) > 0 or is_daedeok
                ):
                    # BuildingDataLoader 형식을 fetch_all_building_data 형식으로 변환
                    phys = building_full_data.get("physical_specs", {})
                    floors = phys.get("floors", {})
                    meta = building_full_data.get("meta", {})

                    # API 데이터 구조 대응 (max_ground, max_underground 등)
                    transition_specs = building_full_data.get("transition_specs", {})
                    structure_types = phys.get("structure_types", [])
                    purpose_types = phys.get("purpose_types", [])
                    age_info = phys.get("age", {})

                    # 대덕 데이터센터 특별 처리 (좌표 기반)
                    # 대덕: 36.38012284, 127.39798889 → 지상4층, 지하1층
                    # is_daedeok는 이미 위에서 정의됨

                    if is_daedeok:
                        collected_data["building_data"] = {
                            "basement_floors": 1,
                            "ground_floors": 4,
                            "total_area_m2": 5000,  # 기본값 (실제 면적 없음)
                            "building_height": 16,  # 4층 x 4m
                            "building_age": age_info.get("years", 15),
                            "build_year": 2010,
                            "structure": "철근콘크리트구조",
                            "main_purpose": "데이터센터",
                            "has_piloti": False,
                            "has_water_tank": True,
                            "distance_to_river_m": 500,
                        }
                        logger.info(f"✅ 대덕 데이터센터 고정 데이터 사용: 지상4층, 지하1층")
                    else:
                        collected_data["building_data"] = {
                            "basement_floors": floors.get("underground", 0)
                            or floors.get("max_underground", 0),
                            "ground_floors": floors.get("ground", 0) or floors.get("max_ground", 0),
                            "total_area_m2": (
                                transition_specs.get("total_area", 0)
                                or transition_specs.get("total_area_sum", 0)
                                or phys.get("area", {}).get("total_floor_area", 0)
                            ),
                            "building_height": floors.get("height", 0),
                            "building_age": age_info.get("years", 0),
                            "build_year": int(
                                age_info.get("approval_date", "0000")[:4]
                                or age_info.get("oldest_approval_date", "0000")[:4]
                                or 0
                            ),
                            "structure": phys.get("structure", "")
                            or (structure_types[0] if structure_types else ""),
                            "main_purpose": phys.get("main_purpose", "")
                            or (purpose_types[0] if purpose_types else ""),
                            "has_piloti": False,
                            "has_water_tank": any(
                                "저수조" in f.get("usage_etc", "")
                                for f in building_full_data.get("floor_details", [])
                            ),
                            "distance_to_river_m": (
                                building_full_data.get("geo_risks", {})
                                .get("river", {})
                                .get("distance_m", 9999)
                                if building_full_data.get("geo_risks", {}).get("river")
                                else 9999
                            ),
                        }
                        logger.info(
                            f"✅ 건물 데이터 변환 완료: age={collected_data['building_data'].get('building_age')}, floors={collected_data['building_data'].get('ground_floors')}, area={collected_data['building_data'].get('total_area_m2')}"
                        )
                else:
                    # DB 캐시에 없으면 BuildingDataFetcher로 API 호출
                    # 대덕 좌표일 때는 API 호출 (유사 건물 자동 선택)
                    if self.building_fetcher:
                        collected_data["building_data"] = (
                            self.building_fetcher.fetch_all_building_data(lat, lon)
                        )
                        logger.info("⚠️ DB 캐시 없음 - API에서 건물 데이터 조회")
            else:
                # BuildingDataLoader 없으면 기존 방식
                if self.building_fetcher:
                    collected_data["building_data"] = self.building_fetcher.fetch_all_building_data(
                        lat, lon
                    )
        except Exception as e:
            logger.warning(f"건물 데이터 수집 실패: {e}")

        # 2-1. 공간 데이터 (Exposure 계산에 필요 - 모든 리스크 타입에 공통)
        try:
            if self.spatial_loader:
                # 토지피복 데이터
                landcover_data = self.spatial_loader.get_landcover_data(lat, lon)
                collected_data["spatial_data"].update(landcover_data)
                logger.debug(
                    f"토지피복 데이터 수집 완료: {landcover_data.get('landcover_type', 'unknown')}"
                )
        except Exception as e:
            logger.warning(f"공간 데이터 수집 실패: {e}")

        # 3. 리스크 유형별 특화 데이터 수집
        if risk_type == "extreme_heat":
            self._collect_heat_data(lat, lon, collected_data)
        elif risk_type == "extreme_cold":
            self._collect_cold_data(lat, lon, collected_data)
        elif risk_type == "drought":
            self._collect_drought_data(lat, lon, collected_data)
        elif risk_type == "river_flood":
            self._collect_river_flood_data(lat, lon, collected_data)
        elif risk_type == "urban_flood":
            self._collect_urban_flood_data(lat, lon, collected_data)
        elif risk_type == "sea_level_rise":
            self._collect_slr_data(lat, lon, collected_data)
        elif risk_type == "typhoon":
            self._collect_typhoon_data(lat, lon, collected_data)
        elif risk_type == "wildfire":
            self._collect_wildfire_data(lat, lon, collected_data)
        elif risk_type == "water_stress":
            self._collect_water_stress_data(lat, lon, collected_data)
        elif risk_type == "exposure":
            self._collect_exposure_data(lat, lon, collected_data)

        return collected_data

    # --- 리스크별 데이터 수집 헬퍼 메서드 ---

    def _collect_exposure_data(self, lat: float, lon: float, data: Dict):
        """Exposure 계산에 필요한 데이터 수집 (Landcover 등)"""
        if self.spatial_loader:
            data["spatial_data"].update(self.spatial_loader.get_landcover_data(lat, lon))
            # NDVI 등 추가 데이터가 필요할 수 있음
            data["spatial_data"].update(self.spatial_loader.get_ndvi_data(lat, lon))

    def _collect_heat_data(self, lat: float, lon: float, data: Dict):
        if self.climate_loader:
            # hazard_calculate용 (단일 연도 데이터)
            single_year_data = self.climate_loader.get_extreme_heat_data(lat, lon, self.target_year)

            # probability_calculate용 (시계열 데이터)
            timeseries_data = self.climate_loader.get_extreme_heat_timeseries(lat, lon, 2021, 2100)
            baseline_data = self.climate_loader.get_extreme_heat_timeseries(lat, lon, 1991, 2020)

            # 병합: 기존 단일값 + 시계열 배열
            data["climate_data"] = {
                **single_year_data,  # heat_wave_duration, heatwave_days_per_year 등
                **timeseries_data,  # wsdi, su25, tr25 배열 등
            }
            data["baseline_wsdi"] = baseline_data.get("wsdi", [])

    def _collect_cold_data(self, lat: float, lon: float, data: Dict):
        if self.climate_loader:
            # hazard_calculate용 (단일 연도 데이터)
            single_year_data = self.climate_loader.get_extreme_cold_data(lat, lon, self.target_year)

            # probability_calculate용 (시계열 데이터)
            timeseries_data = self.climate_loader.get_extreme_cold_timeseries(lat, lon, 2021, 2100)
            baseline_data = self.climate_loader.get_extreme_cold_timeseries(lat, lon, 1991, 2020)

            # 병합
            data["climate_data"] = {**single_year_data, **timeseries_data}
            data["baseline_csdi"] = baseline_data.get("csdi", [])

    def _collect_drought_data(self, lat: float, lon: float, data: Dict):
        if self.climate_loader:
            # hazard_calculate용 (단일 연도 데이터)
            single_year_data = self.climate_loader.get_drought_data(lat, lon, self.target_year)

            # probability_calculate용 (월별 시계열 데이터)
            timeseries_data = self.climate_loader.get_drought_timeseries(lat, lon, 2021, 2100)

            # 병합
            data["climate_data"] = {**single_year_data, **timeseries_data}

        if self.spatial_loader:
            data["spatial_data"] = self.spatial_loader.get_soil_moisture_data(lat, lon)

    def _collect_river_flood_data(self, lat: float, lon: float, data: Dict):
        # TWI 계산을 위한 데이터 등 (Spatial Loader 기능 확인 필요)
        if self.spatial_loader:
            data["spatial_data"] = self.spatial_loader.get_landcover_data(lat, lon)

        if self.disaster_fetcher:
            try:
                data["disaster_data"] = self.disaster_fetcher.get_nearest_river_info(lat, lon)
            except Exception as e:
                logger.warning(f"하천정보 API 조회 실패 (무시하고 계속): {e}")

        if self.climate_loader:
            # hazard_calculate용 (단일 연도 데이터)
            single_year_data = self.climate_loader.get_flood_data(lat, lon, self.target_year)

            # probability_calculate용 (시계열 데이터)
            timeseries_data = self.climate_loader.get_flood_timeseries(lat, lon, 2021, 2100)
            baseline_data = self.climate_loader.get_flood_timeseries(lat, lon, 1991, 2020)

            # 병합
            data["climate_data"] = {**single_year_data, **timeseries_data}
            data["baseline_rx1day"] = baseline_data.get("rx1day", [])

    def _collect_urban_flood_data(self, lat: float, lon: float, data: Dict):
        if self.spatial_loader:
            data["spatial_data"] = self.spatial_loader.get_landcover_data(lat, lon)

        if self.climate_loader:
            # hazard_calculate용 (단일 연도 데이터)
            single_year_data = self.climate_loader.get_flood_data(lat, lon, self.target_year)

            # probability_calculate용 (시계열 데이터)
            timeseries_data = self.climate_loader.get_flood_timeseries(lat, lon, 2021, 2100)
            baseline_data = self.climate_loader.get_flood_timeseries(lat, lon, 1991, 2020)

            # 병합
            data["climate_data"] = {**single_year_data, **timeseries_data}
            data["baseline_rx1day"] = baseline_data.get("rx1day", [])

        # 건물 밀도 등을 위한 building_count는 이미 building_data에 포함되어 있다고 가정
        # data['building_data']['building_count'] 확인 필요

    def _collect_slr_data(self, lat: float, lon: float, data: Dict):
        # 해안 거리 계산 등은 별도 로직이 필요할 수 있음 (HazardCalculator에서는 distance_to_coast_m을 data에서 가져옴)
        # SpatialLoader가 이를 제공하는지 확인 필요. 없다면 BuildingFetcher나 외부 API 사용해야 함.
        # 여기서는 일단 ClimateLoader 호출
        if self.climate_loader:
            # hazard_calculate용 (단일 연도 데이터)
            single_year_data = self.climate_loader.get_sea_level_rise_data(
                lat, lon, self.target_year
            )

            # probability_calculate용 (시계열 데이터)
            timeseries_data = self.climate_loader.get_sea_level_rise_timeseries(
                lat, lon, 2021, 2100
            )

            # 병합
            data["climate_data"] = {**single_year_data, **timeseries_data}

        # 해안 거리 정보가 building_data나 spatial_data에 있어야 함.
        # 예시: data['extra_data']['distance_to_coast_m'] = ...

    def _collect_typhoon_data(self, lat: float, lon: float, data: Dict):
        """
        태풍 데이터 수집 (DB 우선, API fallback)
        """
        # 1. DB에서 태풍 데이터 로드 (climate_loader 사용)
        if self.climate_loader:
            typhoon_db_data = self.climate_loader.get_typhoon_data(lat, lon, self.target_year)

            data["typhoon_data"] = {
                "typhoons": typhoon_db_data.get("typhoons", []),
                "typhoon_frequency": typhoon_db_data.get("typhoon_frequency", 0),
                "max_wind_speed_ms": typhoon_db_data.get("max_wind_speed_ms", 30.0),
                "data_source": typhoon_db_data.get("data_source", "fallback"),
            }

            data["climate_data"]["rx1day"] = typhoon_db_data.get("rx1day")
            data["climate_data"]["max_1day_precipitation"] = typhoon_db_data.get("rx1day")
            data["spatial_data"]["distance_to_coast_m"] = typhoon_db_data.get("distance_to_coast_m")

            return

        # 2. API fallback (disaster_fetcher 사용)
        if self.disaster_fetcher:
            typhoons_all = []

            # 분석 기간 설정 (config 사용)
            end_year = 2022
            num_years = 10

            if config and hasattr(config, "TYPHOON_HAZARD_PARAMS"):
                period_params = config.TYPHOON_HAZARD_PARAMS.get("typhoon_analysis_period", {})
                end_year = period_params.get("end_year", 2022)
                num_years = period_params.get("num_years", 10)

            years_to_check = range(end_year, end_year - num_years, -1)

            for year in years_to_check:
                if hasattr(self.disaster_fetcher, "fetch_typhoon_besttrack"):
                    result = self.disaster_fetcher.fetch_typhoon_besttrack(year)
                    if result.get("typhoons"):
                        typhoons_all.extend(result["typhoons"])

            data["typhoon_data"] = {
                "typhoons": typhoons_all,
                "analysis_period_years": num_years,
                "end_year": end_year,
                "data_source": "api",
            }

    def _collect_wildfire_data(self, lat: float, lon: float, data: Dict):
        if self.spatial_loader:
            data["spatial_data"].update(self.spatial_loader.get_ndvi_data(lat, lon))
            data["spatial_data"].update(self.spatial_loader.get_landcover_data(lat, lon))

        if self.climate_loader:
            # hazard_calculate용 (단일 연도 데이터)
            single_year_fwi = self.climate_loader.get_fwi_input_data(lat, lon, self.target_year)
            single_year_drought = self.climate_loader.get_drought_data(lat, lon, self.target_year)

            # probability_calculate용 (월별 시계열 데이터) - 별도 키로 저장
            timeseries_data = self.climate_loader.get_wildfire_timeseries(lat, lon, 2021, 2100)

            # 단일값 우선 (hazard 계산용), timeseries는 별도 키로
            data["climate_data"] = {**single_year_fwi, **single_year_drought}
            # timeseries 배열은 별도 키로 저장 (probability 계산용)
            data["wildfire_timeseries"] = timeseries_data

    def _collect_water_stress_data(self, lat: float, lon: float, data: Dict):
        if self.wamis_fetcher:
            try:
                watershed_info = self.wamis_fetcher.get_watershed_from_coords(lat, lon)
                data["wamis_data"]["watershed_info"] = watershed_info

                # 용수 사용량
                major_watershed = watershed_info.get("major_watershed")
                if major_watershed:
                    data["wamis_data"]["water_usage"] = self.wamis_fetcher.get_water_usage(
                        major_watershed, year=self.target_year
                    )
            except Exception as e:
                logger.warning(f"WAMIS 데이터 수집 실패: {e}")

        if self.climate_loader:
            data["climate_data"] = self.climate_loader.get_drought_data(lat, lon, self.target_year)
