"""
파일명: typhoon_probability_agent.py
최종 수정일: 2025-12-14
버전: v3.0
파일 개요: 열대성 태풍 리스크 확률 P(H) 계산 Agent
변경 이력:
        - 2025-12-14: v3.0 - Hazard/Exposure 패턴 적용
                * _build_collected_data() 메서드 추가
                * calculate(lat, lon, ssp_scenario) 지원
                * ClimateDataLoader 기반 데이터 fetch
        - 2025-11-23: v2.0 - SSP 시나리오 기반 미래 태풍 강도 추정 추가
                * Hybrid Approach: 과거 통계 + 기온 스케일링 + 확률적 시뮬레이션
                * IPCC AR6 기반 스케일링: 1°C당 4% 강도 증가
                * Gamma 분포 기반 확률적 S_tc 샘플링
                * 4개 SSP 시나리오 지원 (SSP126, SSP245, SSP370, SSP585)
        - 2025-11-22: v1.1 - 타원 영향권 계산 버그 수정
                * 위경도(도) → km 단위 변환 추가
                * 위도 1도 ≈ 111km, 경도 1도 ≈ 111km × cos(위도) 적용
        - 2025-11-21: v1 - AAL에서 확률 계산으로 분리
                * 강도지표: S_tc(t,j) = Σ w_tc[bin_inst(storm,τ,j)] (누적 노출 지수)
                * bin_year(t,j): S_tc → 연도 bin 변환
                * DR_intensity: [0.00, 0.02, 0.10, 0.30]
                * 취약성 스케일링 제거
"""

from typing import Dict, Any, List, Optional
import numpy as np
import math
from .base_probability_agent import BaseProbabilityAgent


class TyphoonProbabilityAgent(BaseProbabilityAgent):
    """
    열대성 태풍 리스크 확률 P(H) 계산 Agent

    사용 데이터:
            - KMA 태풍 Best Track API (과거)
            - KMA SSP 시나리오 기온 데이터 (미래 추정)

    강도지표: S_tc(t,j) = 연도별 누적 노출 지수
    - bin_inst(storm,τ,j): 시점별 태풍 영향 등급
    - w_tc: bin별 가중치 [0, 1, 3, 7]

    미래 태풍 강도 추정:
    - Hybrid Approach: 과거 통계 + 기온 스케일링 + Gamma 분포 샘플링
    - IPCC AR6 기반: 1°C 온난화 시 태풍 강도 4% 증가
    - SSP 시나리오: SSP126, SSP245, SSP370, SSP585
    """

    # SSP 시나리오 매핑
    SCENARIO_MAPPING = {
        "SSP1-2.6": "SSP126",
        "SSP2-4.5": "SSP245",
        "SSP3-7.0": "SSP370",
        "SSP5-8.5": "SSP585",
        "SSP126": "SSP126",
        "SSP245": "SSP245",
        "SSP370": "SSP370",
        "SSP585": "SSP585",
    }

    # IPCC AR6 기반 스케일링 계수 (1°C당 강도 증가율)
    INTENSITY_SCALE_PER_DEGREE = 0.04  # 4%/°C

    def __init__(self):
        """
        TyphoonProbabilityAgent 초기화

        bin 구간 (연도별 누적 노출 지수 S_tc):
                - bin1: S_tc = 0 (영향 없음)
                - bin2: 0 < S_tc <= 5 (약한 노출)
                - bin3: 5 < S_tc <= 15 (중간~강한 노출)
                - bin4: S_tc > 15 (매우 강한 노출)

        기본 손상률 (DR_intensity):
                - bin1: 0%
                - bin2: 2%
                - bin3: 10%
                - bin4: 30%
        """
        bins = [
            (0, 0),  # bin1: 영향 없음
            (0, 5),  # bin2: 약한 노출
            (5, 15),  # bin3: 중간~강한 노출
            (15, float("inf")),  # bin4: 매우 강한 노출
        ]

        dr_intensity = [0.00, 0.02, 0.10, 0.30]  # 0%  # 2%  # 10%  # 30%

        super().__init__(risk_type="typhoon", bins=bins, dr_intensity=dr_intensity)

        # 시점별 bin 가중치
        self.w_tc = [0, 1, 3, 7]  # [bin1, bin2(TS), bin3(STS), bin4(TY)]

        # Baseline 통계 (미래 시나리오용)
        self.baseline_stats: Optional[Dict[str, Any]] = None
        self.baseline_temp: Optional[float] = None

    def initialize_baseline(
        self,
        historical_tracks: List[Dict[str, Any]],
        site_location: Dict[str, float],
        baseline_temp: Optional[float] = None,
    ) -> None:
        """
        과거 Best Track 데이터로 baseline 초기화 (미래 시나리오 계산 전 필수)

        Args:
                historical_tracks: 과거 태풍 Best Track 데이터 (2015-2024)
                site_location: 사이트 위치 {'lon': float, 'lat': float}
                baseline_temp: 과거 평균 기온 (°C), None이면 기본값 14.2 사용
        """
        # 과거 S_tc 계산
        historical_S_tc = self._calculate_historical_S_tc(historical_tracks, site_location)

        # 통계 추출
        self.baseline_stats = self._extract_baseline_statistics(historical_S_tc)

        # 과거 평균 기온 (스케일링 기준)
        self.baseline_temp = baseline_temp if baseline_temp is not None else 14.2

        self.logger.info(
            f"Baseline 초기화 완료: mean={self.baseline_stats['mean']:.2f}, "
            f"std={self.baseline_stats['std']:.2f}, temp={self.baseline_temp}°C"
        )

    def _calculate_historical_S_tc(
        self, typhoon_tracks: List[Dict[str, Any]], site_location: Dict[str, float]
    ) -> Dict[int, float]:
        """
        과거 Best Track 데이터에서 연도별 S_tc 계산

        Args:
                typhoon_tracks: 태풍 Best Track 데이터
                site_location: 사이트 위치

        Returns:
                연도별 S_tc 딕셔너리 {year: S_tc}
        """
        site_lon = site_location.get("lon")
        site_lat = site_location.get("lat")

        yearly_exposure = {}

        for storm_data in typhoon_tracks:
            year = storm_data.get("year")
            tracks = storm_data.get("tracks", [])

            if year not in yearly_exposure:
                yearly_exposure[year] = 0.0

            for track_point in tracks:
                bin_inst = self._calculate_bin_inst(track_point, site_lon, site_lat)
                yearly_exposure[year] += self.w_tc[bin_inst]

        return yearly_exposure

    def _extract_baseline_statistics(self, historical_S_tc: Dict[int, float]) -> Dict[str, Any]:
        """
        과거 S_tc에서 통계적 특성 추출

        Args:
                historical_S_tc: 연도별 S_tc 딕셔너리

        Returns:
                통계 딕셔너리 {mean, std, distribution, fit_params}
        """
        values = list(historical_S_tc.values())

        if not values:
            return {
                "mean": 0.0,
                "std": 1.0,
                "distribution": "gamma",
                "fit_params": {"shape": 1.0, "scale": 1.0},
            }

        baseline_mean = np.mean(values)
        baseline_std = np.std(values)

        # Gamma 분포 피팅 (S_tc >= 0)
        # 0으로 나눔 방지
        if baseline_std > 0 and baseline_mean > 0:
            shape = (baseline_mean / baseline_std) ** 2
            scale = baseline_std**2 / baseline_mean
        else:
            shape = 1.0
            scale = max(baseline_mean, 1.0)

        return {
            "mean": baseline_mean,
            "std": baseline_std,
            "distribution": "gamma",
            "fit_params": {"shape": shape, "scale": scale},
        }

    def _calculate_intensity_scaling(self, year_temp: float) -> float:
        """
        기온 기반 태풍 강도 스케일링 계산

        IPCC AR6 근거: 2°C 온난화 시 태풍 강도 1-10% 증가
        본 구현: 1°C당 4% 증가 (보수적 중간값)

        Args:
                year_temp: 해당 연도 평균 기온 (°C)

        Returns:
                intensity_scale (1.0 = baseline, >1.0 = 강화)
        """
        if self.baseline_temp is None:
            return 1.0

        temp_increase = year_temp - self.baseline_temp
        intensity_scale = 1.0 + self.INTENSITY_SCALE_PER_DEGREE * temp_increase

        # 극단값 방지 (0.8 ~ 1.5 범위로 제한)
        return max(0.8, min(1.5, intensity_scale))

    def _generate_future_S_tc(
        self, target_years: List[int], yearly_temps: Dict[int, float], seed: Optional[int] = None
    ) -> np.ndarray:
        """
        미래 연도별 S_tc 시뮬레이션 (Gamma 분포 샘플링)

        Args:
                target_years: 계산할 연도 리스트
                yearly_temps: 연도별 평균 기온 딕셔너리
                seed: 재현성을 위한 랜덤 시드 (None이면 외부 상태 사용)

        Returns:
                미래 S_tc 배열
        """
        if self.baseline_stats is None:
            raise ValueError(
                "Baseline이 초기화되지 않았습니다. " "먼저 initialize_baseline()을 호출하세요."
            )

        if seed is not None:
            np.random.seed(seed)

        simulated_S_tc = []

        for year in target_years:
            # 해당 연도 기온 (없으면 baseline 사용)
            year_temp = yearly_temps.get(year, self.baseline_temp)

            # 강도 스케일링
            scale = self._calculate_intensity_scaling(year_temp)

            # 스케일링된 기대값
            expected_mean = self.baseline_stats["mean"] * scale

            # Gamma 분포에서 샘플링
            shape = self.baseline_stats["fit_params"]["shape"]
            if shape > 0 and expected_mean > 0:
                scale_param = expected_mean / shape
                sampled = np.random.gamma(shape, scale_param)
            else:
                sampled = expected_mean

            # 극단값 제한
            sampled = max(0, min(sampled, self.baseline_stats["mean"] * 3))

            simulated_S_tc.append(sampled)

        return np.array(simulated_S_tc)

    def calculate_intensity_indicator(
        self, collected_data: Dict[str, Any], seed: Optional[int] = None
    ) -> np.ndarray:
        """
        태풍 강도지표 S_tc(t,j) 계산
        S_tc(t,j) = Σ over all (storm,τ in year t) of w_tc[bin_inst(storm,τ,j)]

        Args:
                collected_data: 수집된 태풍 데이터 (2가지 모드)

                1) 과거 모드:
                {
                        'typhoon_data': {
                                'typhoon_tracks': [{'year': int, 'storm_id': str, 'tracks': [...]}],
                                'site_location': {'lon': float, 'lat': float}
                        }
                }

                2) 미래 시나리오 모드:
                {
                        'future_scenario': {
                                'scenario': 'SSP126' | 'SSP245' | 'SSP370' | 'SSP585',
                                'target_years': [2026, 2027, ...],
                                'yearly_temps': {2026: 15.2, 2027: 15.4, ...},
                                'site_location': {'lon': float, 'lat': float}
                        }
                }
                seed: 랜덤 시드 (None이면 내부에서 설정 안함, 외부 상태 사용)

        Returns:
                연도별 누적 노출 지수 배열
        """
        # 미래 시나리오 모드
        if "future_scenario" in collected_data:
            scenario_info = collected_data["future_scenario"]

            # Baseline 체크
            if self.baseline_stats is None:
                raise ValueError(
                    "Baseline이 초기화되지 않았습니다. " "먼저 initialize_baseline()을 호출하세요."
                )

            target_years = scenario_info.get("target_years", [])
            yearly_temps = scenario_info.get("yearly_temps", {})
            scenario = scenario_info.get("scenario", "SSP370")

            # 시나리오명 정규화
            scenario = self.SCENARIO_MAPPING.get(scenario, scenario)

            self.logger.info(f"미래 시나리오 모드: {scenario}, {len(target_years)}개 연도")

            # 미래 S_tc 시뮬레이션
            return self._generate_future_S_tc(
                target_years=target_years, yearly_temps=yearly_temps, seed=seed
            )

        # 과거 모드
        typhoon_data = collected_data.get("typhoon_data", {})
        typhoon_tracks = typhoon_data.get("typhoon_tracks", [])
        site_location = typhoon_data.get("site_location", {"lon": 127.0, "lat": 37.5})

        if not typhoon_tracks:
            self.logger.warning("태풍 Best Track 데이터가 없습니다. 기본값 0으로 설정합니다.")
            return np.array([0.0])

        site_lon = site_location.get("lon")
        site_lat = site_location.get("lat")

        # 연도별 누적 노출 지수 계산
        yearly_exposure = {}

        for storm_data in typhoon_tracks:
            year = storm_data.get("year")
            storm_id = storm_data.get("storm_id")
            tracks = storm_data.get("tracks", [])

            if year not in yearly_exposure:
                yearly_exposure[year] = 0.0

            for track_point in tracks:
                # 각 시점(τ)에서의 bin_inst 계산
                bin_inst = self._calculate_bin_inst(track_point, site_lon, site_lat)

                # 가중치 적용하여 누적
                yearly_exposure[year] += self.w_tc[bin_inst]

        # Baseline 자동 초기화 (미래 시나리오 계산 대비)
        if self.baseline_stats is None and typhoon_tracks:
            self.logger.info("Baseline 자동 초기화 중...")
            self.baseline_stats = self._extract_baseline_statistics(yearly_exposure)

        # 연도별로 정렬하여 배열로 변환
        years = sorted(yearly_exposure.keys())
        exposure_values = [yearly_exposure[y] for y in years]

        exposure_array = np.array(exposure_values, dtype=float)
        self.logger.info(
            f"태풍 노출 지수: {len(exposure_array)}개 연도, "
            f"범위: {exposure_array.min():.2f} ~ {exposure_array.max():.2f}"
        )

        return exposure_array

    def get_future_S_tc_all_scenarios(
        self, target_years: List[int], scenario_temps: Dict[str, Dict[int, float]]
    ) -> Dict[str, np.ndarray]:
        """
        모든 SSP 시나리오에 대해 미래 S_tc 계산

        Args:
                target_years: 계산할 연도 리스트
                scenario_temps: 시나리오별 연도별 기온
                        {
                                'SSP126': {2026: 15.0, 2027: 15.1, ...},
                                'SSP245': {...},
                                'SSP370': {...},
                                'SSP585': {...}
                        }

        Returns:
                시나리오별 S_tc 배열
                {
                        'SSP126': np.array([...]),
                        'SSP245': np.array([...]),
                        'SSP370': np.array([...]),
                        'SSP585': np.array([...])
                }
        """
        if self.baseline_stats is None:
            raise ValueError(
                "Baseline이 초기화되지 않았습니다. " "먼저 initialize_baseline()을 호출하세요."
            )

        scenarios = ["SSP126", "SSP245", "SSP370", "SSP585"]
        results = {}

        for scenario in scenarios:
            yearly_temps = scenario_temps.get(scenario, {})
            results[scenario] = self._generate_future_S_tc(
                target_years=target_years,
                yearly_temps=yearly_temps,
                seed=42,  # 동일 시드로 재현성 보장
            )

        return results

    def _calculate_bin_inst(
        self, track_point: Dict[str, Any], site_lon: float, site_lat: float
    ) -> int:
        """
        시점별 태풍 영향 등급 bin_inst 계산

        Args:
                track_point: Best Track 시점 데이터
                        {'lon': float, 'lat': float, 'grade': str,
                         'gale_long': float, 'gale_short': float, 'gale_dir': float,
                         'storm_long': float, 'storm_short': float, 'storm_dir': float}
                site_lon: 사이트 경도
                site_lat: 사이트 위도

        Returns:
                bin_inst (0: 영향없음, 1: TS급, 2: STS급, 3: TY급)
        """
        typhoon_lon = track_point.get("lon", 0.0)
        typhoon_lat = track_point.get("lat", 0.0)
        grade = track_point.get("grade", "TD")

        # 태풍 중심과 사이트 사이 거리 계산 (위경도 → km 변환)
        # 위도 1도 ≈ 111km, 경도 1도 ≈ 111km × cos(위도)
        avg_lat = (site_lat + typhoon_lat) / 2
        km_per_deg_lon = 111.0 * math.cos(math.radians(avg_lat))
        km_per_deg_lat = 111.0

        dx_km = (site_lon - typhoon_lon) * km_per_deg_lon
        dy_km = (site_lat - typhoon_lat) * km_per_deg_lat

        # 폭풍(STORM) 타원 체크
        storm_long = track_point.get("storm_long", 0.0)
        storm_short = track_point.get("storm_short", 0.0)
        storm_dir = track_point.get("storm_dir", 0.0)

        inside_storm = self._is_inside_ellipse(dx_km, dy_km, storm_long, storm_short, storm_dir)

        if inside_storm:
            if grade == "TY":
                return 3  # bin4: TY급 영향
            else:
                return 2  # bin3: STS급 영향

        # 강풍(GALE) 타원 체크
        gale_long = track_point.get("gale_long", 0.0)
        gale_short = track_point.get("gale_short", 0.0)
        gale_dir = track_point.get("gale_dir", 0.0)

        inside_gale = self._is_inside_ellipse(dx_km, dy_km, gale_long, gale_short, gale_dir)

        if inside_gale:
            if grade in ["TS", "STS", "TY"]:
                return 1  # bin2: TS급 영향
            else:
                return 0  # bin1: 영향 없음
        else:
            return 0  # bin1: 영향 없음

    def _is_inside_ellipse(
        self, dx: float, dy: float, semi_major: float, semi_minor: float, direction: float
    ) -> bool:
        """
        타원 내부 여부 판정

        Args:
                dx, dy: 중심으로부터의 거리
                semi_major: 장반경 (km)
                semi_minor: 단반경 (km)
                direction: 회전 각도 (도)

        Returns:
                타원 내부 여부
        """
        if semi_major == 0 or semi_minor == 0:
            return False

        # 각도를 라디안으로 변환
        theta = math.radians(direction)

        # 회전 변환
        x_rot = dx * math.cos(theta) + dy * math.sin(theta)
        y_rot = -dx * math.sin(theta) + dy * math.cos(theta)

        # 타원 방정식
        ellipse_value = (x_rot / semi_major) ** 2 + (y_rot / semi_minor) ** 2

        return ellipse_value <= 1.0

    def _classify_into_bins(self, intensity_values: np.ndarray) -> np.ndarray:
        """
        누적 노출 지수를 bin으로 분류 (태풍 전용)

        Args:
                intensity_values: 연도별 누적 노출 지수 배열

        Returns:
                각 연도의 bin 인덱스 배열 (0-based)
        """
        bin_indices = np.zeros(len(intensity_values), dtype=int)

        for idx, s_tc in enumerate(intensity_values):
            if s_tc == 0:
                bin_indices[idx] = 0  # bin1: 영향 없음
            elif s_tc <= 5:
                bin_indices[idx] = 1  # bin2: 약한 노출
            elif s_tc <= 15:
                bin_indices[idx] = 2  # bin3: 중간~강한 노출
            else:
                bin_indices[idx] = 3  # bin4: 매우 강한 노출

        return bin_indices

    def _build_collected_data(self, timeseries_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        ClimateDataLoader에서 가져온 데이터를 collected_data 형식으로 변환

        Args:
                timeseries_data: get_typhoon_data() 반환값
                        - typhoons: 태풍 상세 레코드 리스트
                        - typhoon_frequency: 태풍 빈도
                        - max_wind_speed_ms: 최대 풍속
                        - distance_to_coast_m: 해안선 거리
                        - data_source: 데이터 소스

        Returns:
                calculate_probability()에 전달할 collected_data
        """
        typhoon_frequency = timeseries_data.get("typhoon_frequency", 0)
        max_wind = timeseries_data.get("max_wind_speed_ms", 30.0)
        typhoons = timeseries_data.get("typhoons", [])

        # typhoons 레코드를 typhoon_tracks 형식으로 변환
        # {tcid+year: {year, storm_id, tracks: [...]}} 그룹핑
        storm_dict = {}
        for rec in typhoons:
            tcid = rec.get("tcid", "unknown")
            year = rec.get("year", 2020)
            storm_key = f"{tcid}_{year}"

            if storm_key not in storm_dict:
                storm_dict[storm_key] = {"year": year, "storm_id": tcid, "tracks": []}

            # track_point 형식으로 변환 (None/-999 값 처리)
            def safe_float(val, default):
                if val is None or val == -999 or val == -999.0:
                    return default
                try:
                    return float(val)
                except:
                    return default

            track_point = {
                "lon": safe_float(rec.get("lon"), 0.0),
                "lat": safe_float(rec.get("lat"), 0.0),
                "grade": rec.get("grade") or "TD",
                "max_wind_speed": safe_float(rec.get("max_wind_speed"), 0.0),
                "central_pressure": safe_float(rec.get("central_pressure"), 1000.0),
                "gale_long": safe_float(rec.get("gale_long"), 200.0),  # 기본 강풍반경 200km
                "gale_short": safe_float(rec.get("gale_short"), 150.0),
                "gale_dir": safe_float(rec.get("gale_dir"), 0.0),
                "storm_long": safe_float(rec.get("storm_long"), 100.0),  # 기본 폭풍반경 100km
                "storm_short": safe_float(rec.get("storm_short"), 80.0),
                "storm_dir": safe_float(rec.get("storm_dir"), 0.0),
            }
            storm_dict[storm_key]["tracks"].append(track_point)

        typhoon_tracks = list(storm_dict.values())

        # site_location은 calculate() 호출 시 설정됨
        return {
            "typhoon_data": {
                "typhoon_tracks": typhoon_tracks,
                "typhoon_frequency": typhoon_frequency,
                "max_wind_speed_ms": max_wind,
                "data_source": timeseries_data.get("data_source", "unknown"),
            }
        }

    def _get_fallback_data(self) -> Dict[str, Any]:
        """ClimateDataLoader가 없을 때 사용할 기본 데이터"""
        return {
            "typhoon_data": {
                "typhoon_tracks": [],
                "typhoon_frequency": 0,
                "max_wind_speed_ms": 30.0,
                "data_source": "fallback",
            }
        }
