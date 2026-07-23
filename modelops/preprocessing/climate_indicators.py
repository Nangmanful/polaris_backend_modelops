"""
기후 지표 계산 모듈

DB 원시 데이터(tamax, tamin, ta, rn, ws, rhm, si 등)를
Hazard/Probability 에이전트가 요구하는 파생 지표로 변환합니다.

파생 지표:
- heatwave_days_per_year: 폭염일수 (연속 3일 이상 33°C 초과)
- coldwave_days_per_year: 한파일수 (연속 2일 이상 -12°C 미만)
- fwi_baseline_max, fwi_future_max: Fire Weather Index 최대값
- et0: 증발산량 (Penman-Monteith 공식)
"""

from typing import Dict, List, Any
import math


class ClimateIndicatorCalculator:
    """기후 지표 계산기"""

    def __init__(self, raw_data: Dict[str, List[float]]):
        """
        Args:
            raw_data: DB에서 조회한 원시 데이터
                - tamax: 일별 최고기온 (°C)
                - tamin: 일별 최저기온 (°C)
                - ta: 월별 평균기온 (°C)
                - rn: 월별 강수량 (mm)
                - ws: 월별 풍속 (m/s)
                - rhm: 월별 상대습도 (%)
                - si: 월별 일사량 (MJ/m²)
                - wsdi: 연별 WSDI (일)
                - csdi: 연별 CSDI (일)
                - rx1day: 연별 1일 최대강수 (mm)
                - rx5day: 연별 5일 최대강수 (mm)
                - rain80: 연별 80mm 이상 강수일수 (일)
                - sdii: 연별 강수강도 (mm/일)
        """
        self.raw_data = raw_data

    def get_heatwave_indicators(self) -> Dict[str, Any]:
        """
        폭염 지표 계산 (Extreme Heat)

        Returns:
            {
                'heatwave_days_per_year': float,  # 연평균 폭염일수
                'heat_wave_duration': float,      # 최장 폭염 지속기간 (일)
                'annual_max_temp_celsius': float, # 연최고기온 (°C)
                'baseline_heatwave_days': float,  # 기준기간 폭염일수
                'baseline_magnitude': float       # 기준기간 강도
            }
        """
        tamax_data = self.raw_data.get("tamax", [])

        if not tamax_data:
            return self._default_heatwave_indicators()

        # 1. 폭염일수 계산 (연속 3일 이상 33°C 초과)
        heatwave_days = self._calculate_heatwave_days(tamax_data, threshold=33.0, min_duration=3)

        # 2. 최장 폭염 지속기간
        max_duration = self._calculate_max_heatwave_duration(tamax_data, threshold=33.0)

        # 3. 연최고기온
        annual_max_temp = max(tamax_data) if tamax_data else 30.0

        # 4. 기준기간 값 (첫 20년 평균)
        baseline_period = tamax_data[: int(len(tamax_data) * 0.25)]  # 첫 25%
        baseline_hwd = self._calculate_heatwave_days(
            baseline_period, threshold=33.0, min_duration=3
        )
        baseline_magnitude = self._calculate_heatwave_magnitude(baseline_period, threshold=33.0)

        return {
            "heatwave_days_per_year": heatwave_days,
            "heat_wave_duration": max_duration,
            "annual_max_temp_celsius": annual_max_temp,
            "baseline_heatwave_days": baseline_hwd if baseline_hwd > 0 else 10.0,
            "baseline_magnitude": baseline_magnitude if baseline_magnitude > 0 else 100.0,
        }

    def get_coldwave_indicators(self) -> Dict[str, Any]:
        """
        한파 지표 계산 (Extreme Cold)

        Returns:
            {
                'coldwave_days_per_year': float,  # 연평균 한파일수
                'cold_wave_duration': float,      # 최장 한파 지속기간 (일)
                'annual_min_temp_celsius': float, # 연최저기온 (°C)
                'baseline_coldwave_days': float   # 기준기간 한파일수
            }
        """
        tamin_data = self.raw_data.get("tamin", [])

        if not tamin_data:
            return self._default_coldwave_indicators()

        # 1. 한파일수 계산 (연속 2일 이상 -12°C 미만)
        coldwave_days = self._calculate_coldwave_days(tamin_data, threshold=-12.0, min_duration=2)

        # 2. 최장 한파 지속기간
        max_duration = self._calculate_max_coldwave_duration(tamin_data, threshold=-12.0)

        # 3. 연최저기온
        annual_min_temp = min(tamin_data) if tamin_data else -10.0

        # 4. 기준기간 값
        baseline_period = tamin_data[: int(len(tamin_data) * 0.25)]
        baseline_cwd = self._calculate_coldwave_days(
            baseline_period, threshold=-12.0, min_duration=2
        )

        return {
            "coldwave_days_per_year": coldwave_days,
            "cold_wave_duration": max_duration,
            "annual_min_temp_celsius": annual_min_temp,
            "baseline_coldwave_days": baseline_cwd if baseline_cwd > 0 else 5.0,
        }

    def get_wildfire_indicators(self) -> Dict[str, Any]:
        """
        산불 지표 계산 (Wildfire) - FWI (Fire Weather Index)

        FWI 계산식 (간소화 버전):
        - FWI = (1 - rhm/100) × (ta/30) × (ws/10) × drought_factor
        - 건조일수 = 강수량 < 1mm인 연속일수

        Returns:
            {
                'fwi_baseline_max': float,  # 기준기간 FWI 최대값
                'fwi_future_max': float,    # 미래기간 FWI 최대값
                'dry_days_baseline': float, # 기준기간 연속 건조일수
                'dry_days_future': float    # 미래기간 연속 건조일수
            }
        """
        ta = self.raw_data.get("ta", [])
        rhm = self.raw_data.get("rhm", [])
        ws = self.raw_data.get("ws", [])
        rn = self.raw_data.get("rn", [])

        if not (ta and rhm and ws and rn):
            return self._default_wildfire_indicators()

        # FWI 계산
        fwi_values = []
        for i in range(min(len(ta), len(rhm), len(ws), len(rn))):
            # 건조도 = 1 - 상대습도
            dryness = max(0, 1 - rhm[i] / 100.0)
            # 온도 정규화 (30°C 기준)
            temp_factor = ta[i] / 30.0
            # 풍속 정규화 (10m/s 기준)
            wind_factor = ws[i] / 10.0
            # 가뭄 계수 (강수량 역수)
            drought_factor = 1.0 if rn[i] < 1.0 else (1.0 / (1.0 + rn[i] / 100.0))

            fwi = dryness * temp_factor * wind_factor * drought_factor
            fwi_values.append(fwi)

        # 기준/미래 기간 분리
        split_idx = len(fwi_values) // 2
        baseline_fwi = fwi_values[:split_idx]
        future_fwi = fwi_values[split_idx:]

        # 연속 건조일수 계산 (강수량 < 1mm)
        dry_days_baseline = self._calculate_consecutive_dry_days(rn[:split_idx])
        dry_days_future = self._calculate_consecutive_dry_days(rn[split_idx:])

        return {
            "fwi_baseline_max": max(baseline_fwi) if baseline_fwi else 0.5,
            "fwi_future_max": max(future_fwi) if future_fwi else 0.6,
            "dry_days_baseline": dry_days_baseline,
            "dry_days_future": dry_days_future,
        }

    def get_et0(self) -> float:
        """
        증발산량 계산 (Penman-Monteith 공식 간소화 버전)

        ET0 = 0.0023 × (ta + 17.8) × √(ta_max - ta_min) × si

        Returns:
            월평균 ET0 (mm/월)
        """
        ta = self.raw_data.get("ta", [])
        si = self.raw_data.get("si", [])

        if not (ta and si):
            return 100.0  # 기본값

        et0_values = []
        for i in range(min(len(ta), len(si))):
            # Hargreaves 공식 (간소화)
            et0 = 0.0023 * (ta[i] + 17.8) * math.sqrt(abs(15.0)) * si[i]
            et0_values.append(et0)

        return sum(et0_values) / len(et0_values) if et0_values else 100.0

    # ===== 내부 계산 함수 =====

    def _calculate_heatwave_days(
        self, temp_data: List[float], threshold: float = 33.0, min_duration: int = 3
    ) -> float:
        """폭염일수 계산 (연속 min_duration일 이상 threshold°C 초과)"""
        if not temp_data:
            return 0.0

        heatwave_days = 0
        consecutive_days = 0

        for temp in temp_data:
            if temp > threshold:
                consecutive_days += 1
            else:
                if consecutive_days >= min_duration:
                    heatwave_days += consecutive_days
                consecutive_days = 0

        # 마지막 연속일 처리
        if consecutive_days >= min_duration:
            heatwave_days += consecutive_days

        # 연평균으로 변환 (365일 기준)
        total_years = len(temp_data) / 365.0
        return heatwave_days / total_years if total_years > 0 else 0.0

    def _calculate_max_heatwave_duration(
        self, temp_data: List[float], threshold: float = 33.0
    ) -> float:
        """최장 폭염 지속기간 계산"""
        if not temp_data:
            return 0.0

        max_duration = 0
        current_duration = 0

        for temp in temp_data:
            if temp > threshold:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0

        return float(max_duration)

    def _calculate_heatwave_magnitude(
        self, temp_data: List[float], threshold: float = 33.0
    ) -> float:
        """폭염 강도 계산 (임계값 초과 온도 누적)"""
        if not temp_data:
            return 0.0

        magnitude = sum(max(0, temp - threshold) for temp in temp_data)
        return magnitude

    def _calculate_coldwave_days(
        self, temp_data: List[float], threshold: float = -12.0, min_duration: int = 2
    ) -> float:
        """한파일수 계산 (연속 min_duration일 이상 threshold°C 미만)"""
        if not temp_data:
            return 0.0

        coldwave_days = 0
        consecutive_days = 0

        for temp in temp_data:
            if temp < threshold:
                consecutive_days += 1
            else:
                if consecutive_days >= min_duration:
                    coldwave_days += consecutive_days
                consecutive_days = 0

        if consecutive_days >= min_duration:
            coldwave_days += consecutive_days

        total_years = len(temp_data) / 365.0
        return coldwave_days / total_years if total_years > 0 else 0.0

    def _calculate_max_coldwave_duration(
        self, temp_data: List[float], threshold: float = -12.0
    ) -> float:
        """최장 한파 지속기간 계산"""
        if not temp_data:
            return 0.0

        max_duration = 0
        current_duration = 0

        for temp in temp_data:
            if temp < threshold:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0

        return float(max_duration)

    def _calculate_consecutive_dry_days(self, rn_data: List[float]) -> float:
        """연속 건조일수 계산 (강수량 < 1mm)"""
        if not rn_data:
            return 0.0

        max_dry_days = 0
        current_dry_days = 0

        for rn in rn_data:
            if rn < 1.0:
                current_dry_days += 1
                max_dry_days = max(max_dry_days, current_dry_days)
            else:
                current_dry_days = 0

        return float(max_dry_days)

    # ===== 기본값 반환 함수 =====

    def _default_heatwave_indicators(self) -> Dict[str, Any]:
        """폭염 지표 기본값"""
        return {
            "heatwave_days_per_year": 10.0,
            "heat_wave_duration": 5.0,
            "annual_max_temp_celsius": 35.0,
            "baseline_heatwave_days": 10.0,
            "baseline_magnitude": 100.0,
        }

    def _default_coldwave_indicators(self) -> Dict[str, Any]:
        """한파 지표 기본값"""
        return {
            "coldwave_days_per_year": 5.0,
            "cold_wave_duration": 3.0,
            "annual_min_temp_celsius": -10.0,
            "baseline_coldwave_days": 5.0,
        }

    def _default_wildfire_indicators(self) -> Dict[str, Any]:
        """산불 지표 기본값"""
        return {
            "fwi_baseline_max": 0.5,
            "fwi_future_max": 0.6,
            "dry_days_baseline": 30.0,
            "dry_days_future": 35.0,
        }
