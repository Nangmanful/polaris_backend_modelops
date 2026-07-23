"""
파일명: sea_level_rise_probability_agent.py
최종 수정일: 2025-12-14
버전: v4
파일 개요: 해수면 상승 리스크 확률 P(H) 계산 Agent
변경 이력:
        - 2025-12-14: v4 - Hazard/Exposure 패턴 적용
                * _build_collected_data() 메서드 추가
                * calculate(lat, lon, ssp_scenario) 지원
                * ClimateDataLoader 기반 데이터 fetch
        - 2025-12-11: v3 - DEM 데이터를 collected_data에서 받도록 수정
                * _load_dem_min_elevation 메서드 제거
                * collected_data['ocean_data']['dem_data']에서 DEM 데이터 직접 사용
        - 2025-11-24: v2 - DEM 데이터 기반 ground_level 사용
                * ground_level 기본값 5m → DEM 최저 고도 사용
                * DEM 경로에서 모든 .txt 파일 읽어 최저 고도 추출
        - 2025-11-21: v1 - AAL에서 확률 계산으로 분리
                * 강도지표: X_slr(t,j) = max inundation_depth(t,τ,j)
                * inundation_depth = max(zos/100 - ground_level, 0)
                * bin: [0), [0~0.3m), [0.3~1.0m), [≥1.0m)
                * DR_intensity: [0.00, 0.02, 0.15, 0.35] (국제 Damage Curve 중간값)
                * 취약성 스케일링 제거
"""

from typing import Dict, Any
import numpy as np
from .base_probability_agent import BaseProbabilityAgent


class SeaLevelRiseProbabilityAgent(BaseProbabilityAgent):
    """
    해수면 상승 리스크 확률 P(H) 계산 Agent

    사용 데이터: CMIP6 zos (해수면 높이, m)
    강도지표: X_slr(t,j) = max over τ in year t [ inundation_depth(t,τ,j) ]
    inundation_depth(t,τ,j) = max(zos(t,τ) - ground_level(j), 0)
    """

    def __init__(self):
        """
        SeaLevelRiseProbabilityAgent 초기화

        bin 구간 (침수 깊이):
                - bin1: 0 m (침수 없음)
                - bin2: 0 ~ 0.3 m (경미 피해)
                - bin3: 0.3 ~ 1.0 m (중간 피해)
                - bin4: >= 1.0 m (심각 피해)

        기본 손상률 (DR_intensity - 국제 Damage Curve 중간값):
                - bin1: 0%
                - bin2: 2%
                - bin3: 15%
                - bin4: 35%
        """
        bins = [
            (0, 0),  # bin1: 침수 없음
            (0, 0.3),  # bin2: 0 ~ 0.3m
            (0.3, 1.0),  # bin3: 0.3 ~ 1.0m
            (1.0, float("inf")),  # bin4: >= 1.0m
        ]

        dr_intensity = [0.00, 0.02, 0.15, 0.35]  # 0%  # 2%  # 15%  # 35%

        super().__init__(risk_type="sea_level_rise", bins=bins, dr_intensity=dr_intensity)

    def _extract_min_elevation_from_dem(self, dem_data: list) -> float:
        """
        DEM 데이터에서 최저 고도 추출

        Args:
                dem_data: DEM 데이터 리스트 [{'x': float, 'y': float, 'z': float}, ...]

        Returns:
                최저 고도 (meters)
        """
        if not dem_data:
            self.logger.warning("DEM 데이터가 없습니다. 기본값 0m 사용")
            return 0.0

        min_elevation = float("inf")

        for point in dem_data:
            try:
                elevation = point.get("z")
                if elevation is not None and elevation < min_elevation:
                    min_elevation = elevation
            except Exception as e:
                self.logger.warning(f"DEM 데이터 파싱 실패: {e}")
                continue

        if min_elevation == float("inf"):
            self.logger.warning("유효한 DEM 데이터를 찾을 수 없습니다. 기본값 0m 사용")
            return 0.0

        self.logger.info(f"DEM 최저 고도: {min_elevation:.2f}m")
        return min_elevation

    def calculate_intensity_indicator(self, collected_data: Dict[str, Any]) -> np.ndarray:
        """
        해수면 상승 강도지표 X_slr(t,j) 계산

        Args:
                collected_data: 수집된 해양 및 지형 데이터
                        - ocean_data:
                                - zos_data: 연도별 시점별 zos 데이터
                                        각 원소는 {'year': int, 'zos_values': [m values]}
                                - dem_data: DEM 데이터 [{'x': float, 'y': float, 'z': float}, ...]

        Returns:
                연도별 최대 침수 깊이 값 배열 (m)
        """
        ocean_data = collected_data.get("ocean_data", {})
        zos_data = ocean_data.get("zos_data", [])
        dem_data = ocean_data.get("dem_data", [])

        # DEM 데이터에서 최저 고도 추출
        ground_level = self._extract_min_elevation_from_dem(dem_data)

        if not zos_data:
            self.logger.warning("ZOS 데이터가 없습니다. 기본값 0으로 설정합니다.")
            return np.array([0.0])

        yearly_max_inundation = []

        for year_data in zos_data:
            year = year_data.get("year")
            zos_values = year_data.get("zos_values", [])  # m 단위

            if not zos_values:
                yearly_max_inundation.append(0.0)
                continue

            # 시점별 침수 깊이 계산
            inundation_depths = []
            for zos_m in zos_values:
                inundation_depth = max(zos_m - ground_level, 0.0)
                inundation_depths.append(inundation_depth)

            # 연도별 최대 침수 깊이
            max_inundation = max(inundation_depths) if inundation_depths else 0.0
            yearly_max_inundation.append(max_inundation)

        depth_array = np.array(yearly_max_inundation, dtype=float)
        self.logger.info(
            f"침수 깊이 데이터: {len(depth_array)}개 연도, "
            f"범위: {depth_array.min():.3f}m ~ {depth_array.max():.3f}m"
        )

        return depth_array

    def _classify_into_bins(self, intensity_values: np.ndarray) -> np.ndarray:
        """
        침수 깊이를 bin으로 분류 (해수면 상승 전용)

        Args:
                intensity_values: 연도별 침수 깊이 배열 (m)

        Returns:
                각 연도의 bin 인덱스 배열 (0-based)
        """
        bin_indices = np.zeros(len(intensity_values), dtype=int)

        for idx, depth in enumerate(intensity_values):
            if depth == 0:
                bin_indices[idx] = 0  # bin1: 침수 없음
            elif depth < 0.3:
                bin_indices[idx] = 1  # bin2: 0 ~ 0.3m
            elif depth < 1.0:
                bin_indices[idx] = 2  # bin3: 0.3 ~ 1.0m
            else:
                bin_indices[idx] = 3  # bin4: >= 1.0m

        return bin_indices

    def _build_collected_data(self, timeseries_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        ClimateDataLoader에서 가져온 시계열 데이터를 collected_data 형식으로 변환

        Args:
                timeseries_data: get_sea_level_rise_timeseries() 반환값
                        - years: 연도 리스트
                        - slr: 해수면 상승 값 리스트 (cm)
                        - climate_scenario: SSP 시나리오

        Returns:
                calculate_probability()에 전달할 collected_data
        """
        years = timeseries_data.get("years", [])
        slr_list = timeseries_data.get("slr", [])

        # ZOS 데이터 형식으로 변환
        # slr_cm → meters로 변환
        zos_data = []
        for i, year in enumerate(years):
            slr_cm = slr_list[i] if i < len(slr_list) else 20.0
            slr_m = slr_cm / 100.0  # cm → m
            zos_data.append({"year": year, "zos_values": [slr_m]})  # 단일 값으로 처리

        return {
            "ocean_data": {
                "zos_data": zos_data,
                "dem_data": [],  # DEM 데이터는 별도 로드 필요
            },
            "years": years,
            "climate_scenario": timeseries_data.get("climate_scenario", "SSP245"),
        }

    def _get_fallback_data(self) -> Dict[str, Any]:
        """ClimateDataLoader가 없을 때 사용할 기본 데이터"""
        # 30년치 기본 해수면 상승 데이터
        years = list(range(2021, 2051))
        zos_data = []
        for i, year in enumerate(years):
            slr_m = 0.1 + i * 0.005  # 기본값: 10cm ~ 25cm
            zos_data.append({"year": year, "zos_values": [slr_m]})

        return {
            "ocean_data": {
                "zos_data": zos_data,
                "dem_data": [],
            },
        }
