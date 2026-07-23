"""
파일명: water_stress_probability_agent.py
최종 수정일: 2025-12-14
버전: v3
파일 개요: 물부족 리스크 확률 P(H) 계산 Agent
변경 이력:
        - 2025-12-14: v3 - Hazard/Exposure 패턴 적용
                * _build_collected_data() 메서드 추가
                * calculate(lat, lon, ssp_scenario) 지원
                * ClimateDataLoader 기반 데이터 fetch
        - 2025-11-23: v2 - Aqueduct 4.0 BWS 기반 미래 용수이용량 추정 추가
                * SSP 시나리오별 미래 용수이용량 계산
                * 1년 단위 선형 보간 (2019, 2030, 2050, 2080 앵커)
                * SSP2-4.5: (opt + bau) / 2 보간
        - 2025-11-21: v1 - AAL에서 확률 계산으로 분리
                * 강도지표: X_wst(t) = WSI(t) = Withdrawal(t) / ARWR(t)
                * bin: [<0.2), [0.2~0.4), [0.4~0.8), [≥0.8)
                * DR_intensity: [0.01, 0.03, 0.07, 0.15]
                * 취약성 스케일링 제거
"""

from typing import Dict, Any, List
import numpy as np
from .base_probability_agent import BaseProbabilityAgent


class WaterStressProbabilityAgent(BaseProbabilityAgent):
    """
    물부족 리스크 확률 P(H) 계산 Agent

    사용 데이터:
            - WAMIS 용수이용량 (과거)
            - Aqueduct 4.0 BWS (미래 추정)
    강도지표: X_wst(t) = WSI(t) = Withdrawal(t) / ARWR(t)
    - WSI: Water Stress Index
    - ARWR = TRWR × 0.63 (환경유지유량 차감)

    미래 용수이용량 추정:
    - Aqueduct 4.0 BWS ratio 기반 선형 보간
    - SSP 시나리오: SSP1-2.6, SSP2-4.5, SSP3-7.0, SSP5-8.5
    """

    # Aqueduct 시나리오 → SSP 매핑
    # SSP2-4.5는 opt와 bau의 평균으로 보간
    SCENARIO_MAPPING = {
        "SSP1-2.6": "opt",
        "SSP2-4.5": "interpolated",  # (opt + bau) / 2
        "SSP3-7.0": "bau",
        "SSP5-8.5": "pes",
    }

    # BWS 앵커 연도
    ANCHOR_YEARS = [2019, 2030, 2050, 2080]

    def __init__(self):
        """
        WaterStressProbabilityAgent 초기화

        bin 구간 (WRI 기준):
                - bin1: WSI < 0.2 (낮은 물 스트레스)
                - bin2: 0.2 <= WSI < 0.4 (중간 물 스트레스)
                - bin3: 0.4 <= WSI < 0.8 (높은 물 스트레스)
                - bin4: WSI >= 0.8 (극심한 물 스트레스)

        기본 손상률 (DR_intensity):
                - bin1: 1%
                - bin2: 3%
                - bin3: 7%
                - bin4: 15%
        """
        bins = [(0, 0.2), (0.2, 0.4), (0.4, 0.8), (0.8, float("inf"))]

        dr_intensity = [0.01, 0.03, 0.07, 0.15]  # 1%  # 3%  # 7%  # 15%

        super().__init__(risk_type="water_stress", bins=bins, dr_intensity=dr_intensity)

    def calculate_intensity_indicator(self, collected_data: Dict[str, Any]) -> np.ndarray:
        """
        물부족 강도지표 X_wst(t) 계산
        X_wst(t) = WSI(t) = Withdrawal(t) / ARWR_future(t)

        Args:
                collected_data: 수집된 수자원 데이터
                        - water_data: 연도별 용수이용량 데이터 리스트
                                각 원소는 {'year': int, 'withdrawal': float}
                        - flow_data: 유량 관측소 일유량 데이터 (TRWR 계산용)
                                각 원소는 {'year': int, 'daily_flows': [m³/s values]}
                        - climate_data: 기후 데이터 (ET0 계산 및 스케일링용)
                                {'monthly_data': [{'year': int, 'months': [{ta, rhm, ws, si, rn}, ...]}]}
                        - baseline_years: 기준기간 연도 리스트 (예: [1991, ..., 2020])
                        - aqueduct_data: Aqueduct 4.0 BWS 데이터 (미래 용수이용량 추정용)
                                {
                                        'baseline': float,  # BWS 2019
                                        'opt': {'2030': float, '2050': float, '2080': float},
                                        'bau': {'2030': float, '2050': float, '2080': float},
                                        'pes': {'2030': float, '2050': float, '2080': float}
                                }
                        - ssp_scenario: SSP 시나리오 (기본값: 'SSP3-7.0')
                        - target_years: 계산할 연도 리스트 (미래 추정용)

        Returns:
                연도별 WSI 값 배열
        """
        water_data = collected_data.get("water_data", [])
        flow_data = collected_data.get("flow_data", [])
        climate_data_dict = collected_data.get("climate_data", {})
        baseline_years = collected_data.get("baseline_years", [])
        aqueduct_data = collected_data.get("aqueduct_data", None)
        ssp_scenario = collected_data.get("ssp_scenario", "SSP3-7.0")
        target_years = collected_data.get("target_years", None)

        if not water_data:
            self.logger.warning("수자원 데이터가 없습니다. 기본값 0으로 설정합니다.")
            return np.array([0.0])

        # 1. TRWR 계산 (기준기간 평균)
        trwr_baseline = self._calculate_trwr_baseline(flow_data, baseline_years)
        self.logger.info(f"TRWR baseline: {trwr_baseline:.2e} m³/year")

        # 2. 유효강수량 기준 스케일링 계산
        scaling_factors = self._calculate_scaling_factors(climate_data_dict, baseline_years)

        # 3. 기준 용수이용량 추출 (가장 최근 연도)
        withdrawal_baseline = self._get_baseline_withdrawal(water_data)
        self.logger.info(f"기준 용수이용량: {withdrawal_baseline:.2e} m³/year")

        # 4. 미래 용수이용량 계산 (Aqueduct BWS 기반)
        if aqueduct_data and target_years:
            future_withdrawals = self._calculate_future_withdrawals(
                withdrawal_baseline, aqueduct_data, target_years, ssp_scenario
            )
            self.logger.info(
                f"미래 용수이용량 계산 완료: {len(target_years)}개 연도, 시나리오: {ssp_scenario}"
            )
        else:
            future_withdrawals = {}

        # 5. WSI 계산
        yearly_wsi = []
        years_processed = []

        # 과거 데이터 처리
        for year_data in water_data:
            year = year_data.get("year")
            withdrawal = year_data.get("withdrawal", 0.0)  # 용수이용량 (m³/year)

            # 미래 TRWR 스케일링
            scale_factor = scaling_factors.get(year, 1.0)
            trwr_future = trwr_baseline * scale_factor

            # ARWR 계산 (환경유지유량 차감)
            arwr_future = trwr_future * 0.63  # αEFR = 0.37

            # WSI 계산
            if arwr_future > 0:
                wsi = withdrawal / arwr_future
            else:
                wsi = 0.0

            yearly_wsi.append(wsi)
            years_processed.append(year)

        # 미래 데이터 처리 (Aqueduct 기반)
        if future_withdrawals:
            for year in sorted(future_withdrawals.keys()):
                if year in years_processed:
                    continue  # 이미 처리된 연도 스킵

                withdrawal_future = future_withdrawals[year]["withdrawal"]

                # 미래 TRWR 스케일링 (기후 데이터 없으면 1.0)
                scale_factor = scaling_factors.get(year, 1.0)
                trwr_future = trwr_baseline * scale_factor

                # ARWR 계산
                arwr_future = trwr_future * 0.63

                # WSI 계산
                if arwr_future > 0:
                    wsi = withdrawal_future / arwr_future
                else:
                    wsi = 0.0

                yearly_wsi.append(wsi)
                years_processed.append(year)

        wsi_array = np.array(yearly_wsi, dtype=float)
        self.logger.info(
            f"WSI 데이터: {len(wsi_array)}개 연도, 범위: {wsi_array.min():.2f} ~ {wsi_array.max():.2f}"
        )

        return wsi_array

    def _get_baseline_withdrawal(self, water_data: List[Dict[str, Any]]) -> float:
        """
        기준 용수이용량 추출 (가장 최근 연도)

        Args:
                water_data: 연도별 용수이용량 데이터

        Returns:
                기준 용수이용량 (m³/year)
        """
        if not water_data:
            return 0.0

        # 가장 최근 연도의 용수이용량 반환
        sorted_data = sorted(water_data, key=lambda x: x.get("year", 0), reverse=True)
        return sorted_data[0].get("withdrawal", 0.0)

    def _interpolate_bws(
        self, year: int, bws_baseline: float, bws_2030: float, bws_2050: float, bws_2080: float
    ) -> float:
        """
        1년 단위 BWS 선형 보간

        Args:
                year: 목표 연도
                bws_baseline: baseline BWS (2019)
                bws_2030: 2030년 BWS
                bws_2050: 2050년 BWS
                bws_2080: 2080년 BWS

        Returns:
                보간된 BWS 값
        """
        if year <= 2019:
            return bws_baseline
        elif year <= 2030:
            rate = (bws_2030 - bws_baseline) / 11
            return bws_baseline + (year - 2019) * rate
        elif year <= 2050:
            rate = (bws_2050 - bws_2030) / 20
            return bws_2030 + (year - 2030) * rate
        elif year <= 2080:
            rate = (bws_2080 - bws_2050) / 30
            return bws_2050 + (year - 2050) * rate
        else:
            # 2080 이후는 2080 값 유지
            return bws_2080

    def _calculate_future_withdrawals(
        self,
        withdrawal_baseline: float,
        aqueduct_data: Dict[str, Any],
        target_years: List[int],
        ssp_scenario: str = "SSP3-7.0",
    ) -> Dict[int, Dict[str, float]]:
        """
        Aqueduct BWS 기반 미래 용수이용량 계산

        Args:
                withdrawal_baseline: 기준 연도 용수이용량 (m³/year)
                aqueduct_data: Aqueduct BWS 데이터
                target_years: 계산할 연도 리스트
                ssp_scenario: SSP 시나리오

        Returns:
                연도별 미래 용수이용량 딕셔너리
                {year: {'bws': float, 'bws_ratio': float, 'withdrawal': float}}
        """
        bws_baseline = aqueduct_data.get("baseline", 1.0)

        results = {}

        for year in target_years:
            aqueduct_scenario = self.SCENARIO_MAPPING.get(ssp_scenario, "bau")

            if aqueduct_scenario == "interpolated":
                # SSP2-4.5: opt와 bau 평균으로 보간
                bws_opt = self._interpolate_bws(
                    year,
                    bws_baseline,
                    aqueduct_data["opt"]["2030"],
                    aqueduct_data["opt"]["2050"],
                    aqueduct_data["opt"]["2080"],
                )
                bws_bau = self._interpolate_bws(
                    year,
                    bws_baseline,
                    aqueduct_data["bau"]["2030"],
                    aqueduct_data["bau"]["2050"],
                    aqueduct_data["bau"]["2080"],
                )
                bws_future = (bws_opt + bws_bau) / 2
            else:
                # 직접 매핑 시나리오 (SSP1-2.6, SSP3-7.0, SSP5-8.5)
                anchors = aqueduct_data.get(aqueduct_scenario, aqueduct_data.get("bau", {}))

                bws_future = self._interpolate_bws(
                    year,
                    bws_baseline,
                    anchors.get("2030", bws_baseline),
                    anchors.get("2050", bws_baseline),
                    anchors.get("2080", bws_baseline),
                )

            # BWS ratio 및 미래 용수이용량 계산
            if bws_baseline > 0:
                bws_ratio = bws_future / bws_baseline
            else:
                bws_ratio = 1.0

            withdrawal_future = withdrawal_baseline * bws_ratio

            results[year] = {
                "bws": bws_future,
                "bws_ratio": bws_ratio,
                "withdrawal": withdrawal_future,
            }

        return results

    def get_future_withdrawals_all_scenarios(
        self, withdrawal_baseline: float, aqueduct_data: Dict[str, Any], target_years: List[int]
    ) -> Dict[str, Dict[int, Dict[str, float]]]:
        """
        모든 SSP 시나리오에 대해 미래 용수이용량 계산

        Args:
                withdrawal_baseline: 기준 연도 용수이용량 (m³/year)
                aqueduct_data: Aqueduct BWS 데이터
                target_years: 계산할 연도 리스트

        Returns:
                시나리오별/연도별 미래 용수이용량
                {
                        'SSP1-2.6': {2026: {...}, 2027: {...}, ...},
                        'SSP2-4.5': {...},
                        'SSP3-7.0': {...},
                        'SSP5-8.5': {...}
                }
        """
        scenarios = ["SSP1-2.6", "SSP2-4.5", "SSP3-7.0", "SSP5-8.5"]
        results = {}

        for scenario in scenarios:
            results[scenario] = self._calculate_future_withdrawals(
                withdrawal_baseline, aqueduct_data, target_years, scenario
            )

        return results

    def _calculate_trwr_baseline(self, flow_data: list, baseline_years: list) -> float:
        """
        재생 가능 수자원 (TRWR) 기준값 계산

        Args:
                flow_data: 유량 관측소 일유량 데이터
                        각 원소는 {'year': int, 'daily_flows': [m³/s values]}
                baseline_years: 기준기간 연도 리스트

        Returns:
                TRWR 기준값 (m³/year)
        """
        if not flow_data or not baseline_years:
            self.logger.warning("유량 데이터 또는 기준기간이 없습니다. 기본값 사용.")
            return 1.0e10  # 기본값

        baseline_volumes = []

        for year_data in flow_data:
            year = year_data.get("year")
            if year not in baseline_years:
                continue

            daily_flows = year_data.get("daily_flows", [])  # m³/s

            if not daily_flows:
                continue

            # 결측값 처리
            valid_flows = [f for f in daily_flows if f is not None and f >= 0]
            missing_ratio = 1 - len(valid_flows) / len(daily_flows)

            # 결측 비율이 20~30% 이상이면 해당 연도 제외
            if missing_ratio > 0.25:
                self.logger.warning(f"{year}년 결측 비율 {missing_ratio:.1%} - 제외")
                continue

            # Volume_y 계산: 일유량 × 86400초 누적
            # 결측값은 평균으로 보정 (결측 < 10% 조건 만족)
            if missing_ratio > 0:
                mean_flow = np.mean(valid_flows)
                daily_flows_filled = [
                    f if f is not None and f >= 0 else mean_flow for f in daily_flows
                ]
            else:
                daily_flows_filled = daily_flows

            # 연간 총 유량 (m³/year)
            volume_y = sum(daily_flows_filled) * 86400

            baseline_volumes.append(volume_y)

        if not baseline_volumes:
            self.logger.warning("유효한 기준기간 유량 데이터가 없습니다.")
            return 1.0e10

        # TRWR = 기준기간 평균
        trwr = np.mean(baseline_volumes)

        return trwr

    def _calculate_scaling_factors(
        self, climate_data: Dict[str, Any], baseline_years: list
    ) -> Dict[int, float]:
        """
        유효강수량(P - ET0) 기반 TRWR 스케일링 계수 계산

        Args:
                climate_data: 기후 데이터
                        {'monthly_data': [{'year': int, 'months': [{ta, rhm, ws, si, rn}, ...]}]}
                baseline_years: 기준기간 연도 리스트

        Returns:
                연도별 스케일링 계수 딕셔너리 {year: scale_factor}
        """
        monthly_data = climate_data.get("monthly_data", [])

        if not monthly_data or not baseline_years:
            self.logger.warning("기후 데이터 또는 기준기간이 없습니다. 스케일링 계수 1.0 사용.")
            return {}

        # 1. 연도별 유효강수량 계산
        p_eff_yearly = {}

        for year_data in monthly_data:
            year = year_data.get("year")
            months = year_data.get("months", [])

            if not months:
                continue

            annual_p_eff = 0.0

            for month_data in months:
                ta = month_data.get("ta", 15.0)  # 기온 (°C)
                rhm = month_data.get("rhm", 60.0)  # 상대습도 (%)
                ws = month_data.get("ws", 2.0)  # 풍속 (m/s, 10m 기준)
                si = month_data.get("si", 150.0)  # 일사량 (W/m²)
                rn = month_data.get("rn", 50.0)  # 강수량 (mm)

                # ET0 계산 (Penman-Monteith 식)
                et0 = self._calculate_et0(ta, rhm, ws, si)

                # 월별 유효강수량
                p_eff_month = rn - et0
                annual_p_eff += p_eff_month

            p_eff_yearly[year] = annual_p_eff

        # 2. 기준기간 평균 계산
        baseline_p_eff = [p_eff_yearly[y] for y in baseline_years if y in p_eff_yearly]

        if not baseline_p_eff:
            self.logger.warning("기준기간 유효강수량 데이터가 없습니다.")
            return {}

        p_eff_baseline_mean = np.mean(baseline_p_eff)
        self.logger.info(f"기준기간 평균 유효강수량: {p_eff_baseline_mean:.2f} mm/year")

        # 3. 연도별 스케일링 계수 계산
        scaling_factors = {}

        for year, p_eff in p_eff_yearly.items():
            if p_eff_baseline_mean > 0:
                scale_factor = p_eff / p_eff_baseline_mean
            else:
                scale_factor = 1.0

            scaling_factors[year] = scale_factor

        return scaling_factors

    def _calculate_et0(self, ta: float, rhm: float, ws: float, si: float) -> float:
        """
        Penman-Monteith 식을 사용한 ET0 계산

        ET0 = [0.408 * Δ * (Rn - G) + γ * (900 / (T + 273)) * u2 * (es - ea)]
              / [Δ + γ * (1 + 0.34 * u2)]

        Args:
                ta: 월평균 기온 (°C)
                rhm: 상대습도 (%)
                ws: 풍속 (m/s, 10m 기준)
                si: 일사량 (W/m²)

        Returns:
                ET0 (mm/month, 대략값)
        """
        # 1. 포화수증기압 (kPa)
        es = 0.6108 * np.exp(17.27 * ta / (ta + 237.3))

        # 2. 실제수증기압 (kPa)
        ea = es * rhm / 100.0

        # 3. 기울기 Δ (kPa/°C)
        delta = 4098 * es / ((ta + 237.3) ** 2)

        # 4. 풍속 보정 (10m → 2m)
        u2 = ws * 4.87 / np.log(67.8 * 10 - 5.42)

        # 5. 순복사량 Rn (MJ/m²/day)
        # SI (W/m²) → Rs (MJ/m²/day): Rs ≈ SI * 0.0864
        rs = si * 0.0864

        # 순단파복사량
        rns = (1 - 0.23) * rs

        # 순장파복사량
        t_k = ta + 273.16
        # Rso 근사 (맑은 날 일사량, 간단 근사)
        rso = rs * 1.3  # 간단 근사

        rnl = (
            4.903e-9
            * (t_k**4)
            * (0.34 - 0.14 * np.sqrt(ea))
            * (1.35 * (rs / rso if rso > 0 else 0) - 0.35)
        )

        # 순복사량
        rn = rns - rnl

        # 지면열 G = 0 (월 기준)
        g = 0

        # 6. 심리계수 γ (kPa/°C)
        gamma = 0.665e-3 * 101.3  # 표준 대기압 가정

        # 7. ET0 계산 (mm/day)
        numerator = 0.408 * delta * (rn - g) + gamma * (900 / (ta + 273)) * u2 * (es - ea)
        denominator = delta + gamma * (1 + 0.34 * u2)

        if denominator > 0:
            et0_daily = numerator / denominator
        else:
            et0_daily = 0.0

        # mm/day → mm/month (30일 가정)
        et0_monthly = et0_daily * 30

        return max(et0_monthly, 0.0)  # 음수 방지

    def _build_collected_data(self, timeseries_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        ClimateDataLoader에서 가져온 데이터를 collected_data 형식으로 변환

        Args:
                timeseries_data: get_water_stress_data() 반환값
                        - annual_rainfall_mm: 연간 강수량
                        - consecutive_dry_days: 연속 무강수일
                        - cdd: CDD 값
                        - data_source: 데이터 소스

        Returns:
                calculate_probability()에 전달할 collected_data

        Note:
                물부족 계산은 WAMIS 용수이용량, 유량 데이터 등이 필요합니다.
                ClimateDataLoader의 단순 조회로는 충분하지 않아
                기본값 기반 추정을 사용합니다.
        """
        annual_rainfall = timeseries_data.get("annual_rainfall_mm", 1200.0)
        cdd = timeseries_data.get("cdd", 15)

        # 간단한 WSI 추정 (강수량 기반)
        # 가뭄 지역일수록 WSI가 높음
        # 기본 용수이용량 / 기준 수자원량으로 추정
        estimated_wsi = 0.3 if annual_rainfall > 1000 else 0.6

        return {
            "water_data": [{"year": 2020, "withdrawal": 1e9}],  # 기본 용수이용량 10억톤
            "estimated_wsi": estimated_wsi,
            "climate_scenario": timeseries_data.get("climate_scenario", "SSP245"),
        }

    def _get_fallback_data(self) -> Dict[str, Any]:
        """ClimateDataLoader가 없을 때 사용할 기본 데이터"""
        return {
            "water_data": [{"year": 2020, "withdrawal": 1e9}],
            "estimated_wsi": 0.4,
        }
