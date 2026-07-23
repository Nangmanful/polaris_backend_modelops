"""
파일명: extreme_heat_probability_agent.py
최종 수정일: 2025-12-14
버전: v3
파일 개요: 극심한 고온 리스크 확률 P(H) 계산 Agent
변경 이력:
        - 2025-12-14: v3 - Hazard/Exposure 패턴 적용
                * _build_collected_data() 메서드 추가
                * calculate(lat, lon, ssp_scenario) 지원
                * ClimateDataLoader 기반 데이터 fetch
        - 2025-11-24: v2 - 분위수 기반 동적 bin 설정으로 변경
                * bin: Q80, Q90, Q95, Q99 분위수 기반 5단계
                * 기준기간 데이터로 분위수 임계값 계산
                * 국제 연구 관행 (ETCCDI) 기준 적용
        - 2025-11-21: v1 - AAL에서 확률 계산으로 분리
                * 강도지표: X_heat(t) = WSDI(t) (Warm Spell Duration Index)
                * bin: [0~3), [3~8), [8~20), [20~) (고정값)
                * DR_intensity: [0.001, 0.003, 0.010, 0.020]
                * 취약성 스케일링 제거
"""

from typing import Dict, Any, Optional
import numpy as np
from .base_probability_agent import BaseProbabilityAgent


class ExtremeHeatProbabilityAgent(BaseProbabilityAgent):
    """
    극심한 고온 리스크 확률 P(H) 계산 Agent

    사용 데이터: KMA 연간 극값 지수 WSDI (Warm Spell Duration Index)
    강도지표: X_heat(t) = WSDI(t)
    의미: 평년 기준 상위 분위수 이상 고온이 연속적으로 지속된 기간의 연간 합

    bin 설정 (분위수 기반, 국제 연구 관행):
            - bin1: WSDI < Q80 (일반적 수준)
            - bin2: Q80 ≤ WSDI < Q90 (상위 20% 더위)
            - bin3: Q90 ≤ WSDI < Q95 (상위 10% 더위)
            - bin4: Q95 ≤ WSDI < Q99 (상위 5% 더위)
            - bin5: WSDI ≥ Q99 (상위 1% 극한)
    """

    # 분위수 임계값 (백분위)
    PERCENTILES = [80, 90, 95, 99]

    def __init__(self):
        """
        ExtremeHeatProbabilityAgent 초기화

        bin 구간 (분위수 기반 - 동적 설정):
                - bin1: WSDI < Q80 (일반적 수준)
                - bin2: Q80 ≤ WSDI < Q90 (상위 20% 더위)
                - bin3: Q90 ≤ WSDI < Q95 (상위 10% 더위)
                - bin4: Q95 ≤ WSDI < Q99 (상위 5% 더위)
                - bin5: WSDI ≥ Q99 (상위 1% 극한)

        기본 손상률 (DR_intensity):
                - bin1: 0.1%
                - bin2: 0.3%
                - bin3: 1.0%
                - bin4: 2.0%
                - bin5: 3.5%
        """
        # 초기 bins는 placeholder (기준기간 데이터로 동적 설정)
        bins = [
            (0, 1),  # bin1: < Q80 (placeholder)
            (1, 2),  # bin2: Q80 ~ Q90 (placeholder)
            (2, 3),  # bin3: Q90 ~ Q95 (placeholder)
            (3, 4),  # bin4: Q95 ~ Q99 (placeholder)
            (4, float("inf")),  # bin5: ≥ Q99 (placeholder)
        ]

        dr_intensity = [
            0.001,  # 0.1% (일반적 수준)
            0.003,  # 0.3% (상위 20%)
            0.010,  # 1.0% (상위 10%)
            0.020,  # 2.0% (상위 5%)
            0.035,  # 3.5% (상위 1% 극한)
        ]

        super().__init__(risk_type="extreme_heat", bins=bins, dr_intensity=dr_intensity)

        # 분위수 임계값 저장
        self.percentile_thresholds: Optional[Dict[int, float]] = None

    def set_baseline_percentiles(self, baseline_data: np.ndarray) -> None:
        """
        기준기간 데이터로 분위수 임계값 설정

        Args:
                baseline_data: 기준기간 WSDI 데이터 배열
        """
        if len(baseline_data) < 10:
            self.logger.warning(
                f"기준기간 데이터가 부족합니다 ({len(baseline_data)}개). "
                "최소 10개 이상 권장. 기본값 사용."
            )
            # 기본 임계값 (fallback)
            self.percentile_thresholds = {80: 3, 90: 8, 95: 15, 99: 25}
        else:
            self.percentile_thresholds = {
                p: np.percentile(baseline_data, p) for p in self.PERCENTILES
            }

        # bins 동적 업데이트
        q80 = self.percentile_thresholds[80]
        q90 = self.percentile_thresholds[90]
        q95 = self.percentile_thresholds[95]
        q99 = self.percentile_thresholds[99]

        self.bins = [
            (0, q80),  # bin1: < Q80
            (q80, q90),  # bin2: Q80 ~ Q90
            (q90, q95),  # bin3: Q90 ~ Q95
            (q95, q99),  # bin4: Q95 ~ Q99
            (q99, float("inf")),  # bin5: ≥ Q99
        ]

        self.logger.info(
            f"분위수 임계값 설정 완료: "
            f"Q80={q80:.1f}, Q90={q90:.1f}, Q95={q95:.1f}, Q99={q99:.1f}"
        )

    def calculate_intensity_indicator(self, collected_data: Dict[str, Any]) -> np.ndarray:
        """
        극심한 고온 강도지표 X_heat(t) 계산
        X_heat(t) = WSDI(t)

        Args:
                collected_data: 수집된 기후 데이터
                        - climate_data.wsdi: 연도별 WSDI 값 리스트 또는 배열
                        - baseline_wsdi: 기준기간 WSDI 데이터 (분위수 계산용, 선택)

        Returns:
                연도별 WSDI 값 배열
        """
        climate_data = collected_data.get("climate_data", {})
        wsdi_data = climate_data.get("wsdi", [])
        baseline_wsdi = collected_data.get("baseline_wsdi", None)

        if not wsdi_data:
            self.logger.warning("WSDI 데이터가 없습니다. 기본값 0으로 설정합니다.")
            wsdi_data = [0]

        # numpy 배열로 변환
        wsdi_array = np.array(wsdi_data, dtype=float)

        # 기준기간 데이터가 있으면 분위수 임계값 설정
        if baseline_wsdi is not None and self.percentile_thresholds is None:
            baseline_array = np.array(baseline_wsdi, dtype=float)
            self.set_baseline_percentiles(baseline_array)
        elif self.percentile_thresholds is None:
            # 기준기간 데이터 없으면 현재 데이터로 설정
            self.logger.warning("기준기간 데이터가 없습니다. 현재 데이터로 분위수 계산합니다.")
            self.set_baseline_percentiles(wsdi_array)

        self.logger.info(
            f"WSDI 데이터: {len(wsdi_array)}개 연도, "
            f"범위: {wsdi_array.min():.2f} ~ {wsdi_array.max():.2f}"
        )

        return wsdi_array

    def _classify_into_bins(self, intensity_values: np.ndarray) -> np.ndarray:
        """
        WSDI 값을 분위수 기반 bin으로 분류

        Args:
                intensity_values: 연도별 WSDI 값 배열

        Returns:
                각 연도의 bin 인덱스 배열 (0-based)
        """
        if self.percentile_thresholds is None:
            self.logger.warning("분위수 임계값이 설정되지 않았습니다. 기본 분류 사용.")
            return super()._classify_into_bins(intensity_values)

        q80 = self.percentile_thresholds[80]
        q90 = self.percentile_thresholds[90]
        q95 = self.percentile_thresholds[95]
        q99 = self.percentile_thresholds[99]

        bin_indices = np.zeros(len(intensity_values), dtype=int)

        for idx, value in enumerate(intensity_values):
            if value < q80:
                bin_indices[idx] = 0  # bin1: < Q80
            elif value < q90:
                bin_indices[idx] = 1  # bin2: Q80 ~ Q90
            elif value < q95:
                bin_indices[idx] = 2  # bin3: Q90 ~ Q95
            elif value < q99:
                bin_indices[idx] = 3  # bin4: Q95 ~ Q99
            else:
                bin_indices[idx] = 4  # bin5: ≥ Q99

        return bin_indices

    def _build_collected_data(self, timeseries_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        ClimateDataLoader에서 가져온 시계열 데이터를 collected_data 형식으로 변환

        Args:
                timeseries_data: get_extreme_heat_timeseries() 반환값
                        - years: 연도 리스트
                        - wsdi: WSDI 값 리스트
                        - txx: 최고기온 리스트
                        - climate_scenario: SSP 시나리오

        Returns:
                calculate_probability()에 전달할 collected_data
        """
        wsdi_list = timeseries_data.get("wsdi", [])
        txx_list = timeseries_data.get("txx", [])

        # 기준기간 데이터 (첫 30년을 baseline으로 사용)
        baseline_wsdi = wsdi_list[:30] if len(wsdi_list) >= 30 else wsdi_list

        return {
            "climate_data": {
                "wsdi": wsdi_list,
                "txx": txx_list,
            },
            "baseline_wsdi": baseline_wsdi,
            "years": timeseries_data.get("years", []),
            "climate_scenario": timeseries_data.get("climate_scenario", "SSP245"),
        }

    def _get_fallback_data(self) -> Dict[str, Any]:
        """ClimateDataLoader가 없을 때 사용할 기본 데이터"""
        # 30년치 기본 WSDI 데이터 생성
        default_wsdi = [10 + i * 0.3 for i in range(30)]
        return {
            "climate_data": {
                "wsdi": default_wsdi,
            },
            "baseline_wsdi": default_wsdi,
        }
