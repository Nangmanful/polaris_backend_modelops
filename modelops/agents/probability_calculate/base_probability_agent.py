"""
파일명: base_probability_agent.py
최종 수정일: 2025-12-14
버전: v1.4
파일 개요: 위험 발생확률 P(H) 계산 Base Agent
변경 이력:
        - 2025-12-14: v1.4 - Hazard/Exposure 패턴 적용
                * calculate(lat, lon, ssp_scenario) 메서드 추가
                * ClimateDataLoader 기반 데이터 fetch
                * _build_collected_data() 메서드 추가
                * 기존 DatabaseConnection 메서드 제거
        - 2025-12-13: v1.3 - DB 연동 기능 추가
                * DatabaseConnection import 추가
                * _db_available 플래그 추가
                * DB fetch 메서드 추가 (기후지표, 수자원, 해양, 태풍 데이터)
        - 2025-12-11: v1.2 - KDE 방식 개선 및 메타데이터 추가
                * threshold 3 → 30으로 상향 조정
                * _probability_method 플래그 추가 (사용한 계산 방식 추적)
                * calculation_details에 실제 사용한 방식(kde/count) 표시
                * bin_details에 각 bin의 실제 샘플 수 추가 (디버깅용)
        - 2025-11-22: v1.1 - 연별/월별 데이터 모두 처리 가능하도록 개선
                * time_unit 파라미터 추가 ('yearly' | 'monthly')
                * 월별 데이터의 경우 P_r[i] = (해당 bin 월 수) / (전체 월 수)
                * calculation_details에 time_unit 정보 추가
        - 2025-11-21: v1 - P(H) 계산만 수행하도록 AAL 로직에서 분리
                * bin별 발생확률 P[i] 계산
                * bin별 기본 손상률 DR_intensity[i] 계산
                * 취약성 스케일링 제거 (F_vuln 관련 로직 삭제)
                * 최종 손상률 및 AAL 계산 제거
"""

from typing import Dict, Any, List, Tuple
from abc import ABC, abstractmethod
import logging
import numpy as np
from scipy.stats import gaussian_kde
from scipy.integrate import quad

try:
    from modelops.data_loaders.climate_data_loader import ClimateDataLoader

    CLIMATE_LOADER_AVAILABLE = True
except ImportError:
    try:
        # 상대 경로 fallback
        from ...data_loaders.climate_data_loader import ClimateDataLoader

        CLIMATE_LOADER_AVAILABLE = True
    except ImportError:
        ClimateDataLoader = None
        CLIMATE_LOADER_AVAILABLE = False

logger = logging.getLogger(__name__)

# KDE 방식 사용을 위한 최소 샘플 수
MIN_SAMPLES_FOR_KDE = 3


class BaseProbabilityAgent(ABC):
    """
    위험 발생확률 P(H) 계산 Base Agent

    공통 프레임워크:
    - 강도지표 X_r(t) 계산
    - bin 분류
    - bin별 발생확률 P_r[i] 계산 (KDE 기반 또는 이산적 방식)
      * yearly: 연도 기반 (폭염, 한파, 홍수 등)
      * monthly: 월 기반 (가뭄, 산불 등)
    - bin별 기본 손상률 DR_intensity_r[i] (취약성 스케일링 적용 전)
    """

    def __init__(
        self,
        risk_type: str,
        bins: List[Tuple[float, float]],
        dr_intensity: List[float],
        time_unit: str = "yearly",
    ):
        """
        BaseProbabilityAgent 초기화

        Args:
                risk_type: 리스크 타입 (예: heat, cold, fire, drought, etc.)
                bins: 강도 구간 리스트 [(min1, max1), (min2, max2), ...]
                dr_intensity: bin별 기본 손상률 리스트 [DR1, DR2, DR3, ...]
                time_unit: 시간 단위 ('yearly' | 'monthly')
        """
        self.risk_type = risk_type
        self.bins = bins
        self.dr_intensity = dr_intensity
        self.time_unit = time_unit
        self.logger = logger
        self._probability_method = None  # 'kde' 또는 'count'
        self._climate_loader_available = CLIMATE_LOADER_AVAILABLE
        self.logger.info(f"{risk_type} 확률 계산 Agent 초기화 (v1.4, {time_unit})")

    # ========== Main Entry Point (Hazard/Exposure 패턴) ==========
    def calculate(
        self,
        lat: float,
        lon: float,
        ssp_scenario: str = "SSP245",
        start_year: int = 2021,
        end_year: int = 2050,
    ) -> Dict[str, Any]:
        """
        위험 발생확률 P(H) 계산 (DB 연동 버전)

        Hazard/Exposure Agent와 동일한 인터페이스:
        1. ClimateDataLoader로 시계열 데이터 fetch
        2. _build_collected_data()로 collected_data 구성
        3. calculate_probability(collected_data) 호출

        Args:
                lat: 위도
                lon: 경도
                ssp_scenario: SSP 시나리오 (SSP126, SSP245, SSP370, SSP585)
                start_year: 시작 연도
                end_year: 종료 연도

        Returns:
                확률 계산 결과 딕셔너리
        """
        # Decimal 타입을 float로 변환 (DB에서 Decimal로 반환될 수 있음)
        lat = float(lat)
        lon = float(lon)

        self.logger.info(
            f"{self.risk_type} 확률 계산 시작 " f"(lat={lat}, lon={lon}, ssp={ssp_scenario})"
        )

        try:
            # 1. ClimateDataLoader로 시계열 데이터 fetch
            if not self._climate_loader_available:
                self.logger.warning("ClimateDataLoader가 없습니다. 기본값으로 계산합니다.")
                collected_data = self._get_fallback_data()
            else:
                climate_loader = ClimateDataLoader(scenario=ssp_scenario)
                timeseries_data = self._fetch_timeseries_data(
                    climate_loader, lat, lon, start_year, end_year
                )
                # 2. 자식 클래스에서 구현한 _build_collected_data() 호출
                collected_data = self._build_collected_data(timeseries_data)

            # 2-1. site_location 추가 (typhoon 등에서 필요)
            if "typhoon_data" in collected_data:
                collected_data["typhoon_data"]["site_location"] = {"lon": lon, "lat": lat}

            # 3. 기존 calculate_probability() 호출
            return self.calculate_probability(collected_data)

        except Exception as e:
            self.logger.error(f"{self.risk_type} 확률 계산 실패: {e}", exc_info=True)
            return {"risk_type": self.risk_type, "status": "failed", "error": str(e)}

    def _fetch_timeseries_data(
        self,
        climate_loader: "ClimateDataLoader",
        lat: float,
        lon: float,
        start_year: int,
        end_year: int,
    ) -> Dict[str, Any]:
        """
        ClimateDataLoader를 사용해 시계열 데이터 fetch
        자식 클래스에서 필요시 오버라이드

        Args:
                climate_loader: ClimateDataLoader 인스턴스
                lat: 위도
                lon: 경도
                start_year: 시작 연도
                end_year: 종료 연도

        Returns:
                시계열 데이터 딕셔너리
        """
        # 기본 구현: risk_type에 따라 적절한 timeseries 메서드 호출
        timeseries_methods = {
            "extreme_heat": "get_extreme_heat_timeseries",
            "extreme_cold": "get_extreme_cold_timeseries",
            "drought": "get_drought_timeseries",
            "flood": "get_flood_timeseries",
            "river_flood": "get_flood_timeseries",  # 내륙 홍수
            "urban_flood": "get_flood_timeseries",  # 도시 홍수
            "wildfire": "get_wildfire_timeseries",
            "sea_level_rise": "get_sea_level_rise_timeseries",
            "typhoon": "get_typhoon_data",  # 시계열 아님, 단일 조회
            "water_stress": "get_water_stress_data",  # 시계열 아님
            "landslide": "get_flood_timeseries",  # 강수 기반
        }

        method_name = timeseries_methods.get(self.risk_type)
        if method_name and hasattr(climate_loader, method_name):
            method = getattr(climate_loader, method_name)
            # 시계열 메서드인 경우
            if "timeseries" in method_name:
                return method(lat, lon, start_year, end_year)
            else:
                # 단일 조회 메서드인 경우 (typhoon, water_stress)
                return method(lat, lon)

        self.logger.warning(f"{self.risk_type}에 대한 시계열 메서드가 없습니다. 기본값 반환")
        return {}

    def _build_collected_data(self, timeseries_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        시계열 데이터를 collected_data 형식으로 변환
        자식 클래스에서 구현 필요

        Args:
                timeseries_data: ClimateDataLoader에서 가져온 시계열 데이터

        Returns:
                calculate_probability()에 전달할 collected_data 형식
        """
        # 기본 구현: climate_data 키로 래핑
        return {"climate_data": timeseries_data}

    def _get_fallback_data(self) -> Dict[str, Any]:
        """
        ClimateDataLoader가 없을 때 사용할 기본 데이터
        자식 클래스에서 오버라이드 가능

        Returns:
                기본 collected_data
        """
        return {"climate_data": {}}

    def calculate_probability(self, collected_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        위험 발생확률 P(H) 계산

        Args:
                collected_data: 수집된 기후 데이터 (시계열 데이터 포함)

        Returns:
                확률 계산 결과 딕셔너리
                        - aal: 연간 평균 손실률 (Annual Average Loss)
                        - bin_probabilities: bin별 발생확률 P_r[i]
                        - bin_base_damage_rates: bin별 기본 손상률 DR_intensity_r[i]
                        - calculation_details: 계산 상세 내역
                        - status: 분석 상태
        """
        self.logger.info(f"{self.risk_type} 확률 계산 시작 (v1)")

        try:
            # 1. 강도지표 X_r(t) 계산 (추상 메서드)
            intensity_values = self.calculate_intensity_indicator(collected_data)

            # 2. bin 분류 및 발생확률 P_r[i] 계산
            bin_probabilities = self._calculate_bin_probabilities(intensity_values)

            # 3. AAL 계산: Σ(P[i] × DR[i])
            aal = self._calculate_aal(bin_probabilities, self.dr_intensity)

            result = {
                "risk_type": self.risk_type,
                "aal": round(aal, 6),
                "bin_probabilities": [round(p, 4) for p in bin_probabilities],
                "bin_base_damage_rates": [round(dr, 4) for dr in self.dr_intensity],
                "calculation_details": self._get_calculation_details(
                    bin_probabilities, intensity_values
                ),
                "status": "completed",
            }

            self.logger.info(
                f"{self.risk_type} 확률 계산 완료: " f"AAL={aal:.6f}, P_r[i]={bin_probabilities}"
            )

            return result

        except Exception as e:
            self.logger.error(f"{self.risk_type} 확률 계산 중 오류: {str(e)}", exc_info=True)
            return {"risk_type": self.risk_type, "status": "failed", "error": str(e)}

    @abstractmethod
    def calculate_intensity_indicator(self, collected_data: Dict[str, Any]) -> np.ndarray:
        """
        강도지표 X_r(t) 계산
        각 연도별 리스크 강도 값 산출

        Args:
                collected_data: 수집된 기후 데이터 (시계열)

        Returns:
                연도별 강도지표 배열 (numpy array)
        """
        pass

    def _classify_into_bins(self, intensity_values: np.ndarray) -> np.ndarray:
        """
        강도지표를 bin으로 분류

        Args:
                intensity_values: 연도별 강도지표 배열

        Returns:
                각 연도의 bin 인덱스 배열 (0-based)
        """
        bin_indices = np.zeros(len(intensity_values), dtype=int)

        for idx, value in enumerate(intensity_values):
            for i, (bin_min, bin_max) in enumerate(self.bins):
                if bin_min <= value < bin_max:
                    bin_indices[idx] = i
                    break
            else:
                # 마지막 bin (upper bound 없음)
                bin_indices[idx] = len(self.bins) - 1

        return bin_indices

    def _calculate_bin_probabilities(self, intensity_values: np.ndarray) -> List[float]:
        """
        bin별 발생확률 P_r[i] 계산 (KDE 기반 연속적 확률)

        기존 방식 (이산적):
                P_r[i] = (해당 bin에 속한 샘플 수) / (전체 샘플 수)

        새 방식 (연속적):
                Kernel Density Estimation으로 분포 추정 후
                각 bin 구간에 대한 적분으로 확률 계산

        Args:
                intensity_values: 강도지표 배열 (연별 또는 월별)

        Returns:
                bin별 발생확률 리스트 (연속적인 값)
        """
        sample_count = len(intensity_values)

        if sample_count < MIN_SAMPLES_FOR_KDE:
            # 샘플이 너무 적으면 기존 방식 사용
            self.logger.info(
                f"샘플 수({sample_count})가 MIN_SAMPLES_FOR_KDE({MIN_SAMPLES_FOR_KDE})보다 적음. "
                f"이산적 방식(count) 사용"
            )
            self._probability_method = "count"
            return self._calculate_bin_probabilities_count(intensity_values)

        try:
            # Kernel Density Estimation
            kde = gaussian_kde(intensity_values, bw_method="scott")

            probabilities = []
            for i in range(len(self.bins)):
                bin_min, bin_max = self.bins[i]

                # 무한대 처리
                if bin_max == float("inf"):
                    # 마지막 bin: 데이터 최댓값의 1.2배까지만 적분
                    bin_max = np.max(intensity_values) * 1.2

                if bin_min == float("-inf"):
                    # 첫 bin: 데이터 최솟값의 0.8배부터 적분
                    bin_min = np.min(intensity_values) * 0.8

                # bin 구간 내에서 KDE 적분
                try:
                    prob, _ = quad(kde, bin_min, bin_max, limit=100)
                    probabilities.append(max(0.0, min(1.0, prob)))
                except:
                    # 적분 실패 시 중점 근사
                    mid_point = (bin_min + bin_max) / 2
                    prob = kde(mid_point)[0] * (bin_max - bin_min)
                    probabilities.append(max(0.0, min(1.0, prob)))

            # 정규화 (합이 1이 되도록)
            total = sum(probabilities)
            if total > 0:
                probabilities = [p / total for p in probabilities]

            self._probability_method = "kde"
            self.logger.info(f"KDE 방식으로 확률 계산 완료 (샘플 {sample_count}개)")
            return probabilities

        except Exception as e:
            logger.warning(f"KDE 계산 실패, 기존 방식으로 전환: {e}")
            self._probability_method = "count"
            return self._calculate_bin_probabilities_count(intensity_values)

    def _calculate_bin_probabilities_count(self, intensity_values: np.ndarray) -> List[float]:
        """
        bin별 발생확률 계산 (기존 방식 - 이산적)
        P_r[i] = (해당 bin에 속한 샘플 수) / (전체 샘플 수)

        Args:
                intensity_values: 강도지표 배열

        Returns:
                bin별 발생확률 리스트
        """
        bin_indices = self._classify_into_bins(intensity_values)
        total_samples = len(intensity_values)

        probabilities = []
        for i in range(len(self.bins)):
            count = np.sum(bin_indices == i)
            prob = count / total_samples if total_samples > 0 else 0.0
            probabilities.append(prob)

        return probabilities

    def _calculate_aal(self, bin_probabilities: List[float], damage_rates: List[float]) -> float:
        """
        AAL (Annual Average Loss) 계산

        AAL = Σ(P[i] × DR[i])

        Args:
                bin_probabilities: bin별 발생확률
                damage_rates: bin별 기본 손상률

        Returns:
                연간 평균 손실률 (0~1 범위)
        """
        aal = sum(p * dr for p, dr in zip(bin_probabilities, damage_rates))
        return aal

    def _get_calculation_details(
        self, bin_probabilities: List[float], intensity_values: np.ndarray
    ) -> Dict[str, Any]:
        """
        계산 상세 내역 생성

        Args:
                bin_probabilities: bin별 발생확률
                intensity_values: 강도지표 배열 (연별 또는 월별)

        Returns:
                계산 상세 내역 딕셔너리
        """
        # bin별 실제 샘플 수 계산 (디버깅용)
        bin_indices = self._classify_into_bins(intensity_values)
        bin_sample_counts = []
        for i in range(len(self.bins)):
            count = int(np.sum(bin_indices == i))
            bin_sample_counts.append(count)

        # bin 상세 정보 생성
        bin_details = []
        for i in range(len(self.bins)):
            bin_details.append(
                {
                    "bin": i + 1,
                    "range": f"{self.bins[i][0]} ~ {self.bins[i][1]}",
                    "probability": round(bin_probabilities[i], 4),
                    "sample_count": bin_sample_counts[i],  # 실제 샘플 수 추가
                    "base_damage_rate": round(self.dr_intensity[i], 4),
                }
            )

        total_samples = len(intensity_values)

        # 실제 사용한 계산 방식에 따라 formula 설정
        if self._probability_method == "kde":
            formula = "P_r[i] = ∫[bin_min~bin_max] KDE(x) dx (Kernel Density Estimation)"
            method_description = "Gaussian KDE를 사용한 연속적 확률 분포 추정"
        else:  # 'count'
            if self.time_unit == "monthly":
                formula = "P_r[i] = (해당 bin 월 수) / (전체 월 수)"
            else:
                formula = "P_r[i] = (해당 bin 연도 수) / (전체 연도 수)"
            method_description = "이산적 샘플 카운트 기반 확률 계산"

        if self.time_unit == "monthly":
            return {
                "method": self._probability_method,
                "method_description": method_description,
                "formula": formula,
                "time_unit": "monthly",
                "total_months": total_samples,
                "total_years": total_samples,
                "bins": bin_details,
            }
        else:
            return {
                "method": self._probability_method,
                "method_description": method_description,
                "formula": formula,
                "time_unit": "yearly",
                "total_years": total_samples,
                "bins": bin_details,
            }
