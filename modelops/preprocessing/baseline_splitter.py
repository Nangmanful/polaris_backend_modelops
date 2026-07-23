"""
기준기간/미래기간 데이터 분리 모듈

연도별 데이터(rx1day, rx5day, sdii, rain80 등)를
기준기간(baseline)과 미래기간(future)으로 분리합니다.

기준기간: 2021-2040 (20년)
미래기간: 2081-2100 (20년)
"""

from typing import Dict, List, Tuple


class BaselineSplitter:
    """기준기간/미래기간 데이터 분리기"""

    # 기준기간 연도 범위
    BASELINE_START_YEAR = 2021
    BASELINE_END_YEAR = 2040

    # 미래기간 연도 범위
    FUTURE_START_YEAR = 2081
    FUTURE_END_YEAR = 2100

    def __init__(self, start_year: int = 2021, end_year: int = 2100):
        """
        Args:
            start_year: 데이터 시작 연도
            end_year: 데이터 종료 연도
        """
        self.start_year = start_year
        self.end_year = end_year
        self.total_years = end_year - start_year + 1

    def split_rx1day(self, rx1day_data: List[float]) -> Dict[str, float]:
        """
        일최대강수량 데이터 분리

        Args:
            rx1day_data: 연도별 rx1day 배열 (2021~2100)

        Returns:
            {
                'rx1day_baseline_mm': float,  # 기준기간 평균
                'rx1day_future_mm': float     # 미래기간 평균
            }
        """
        baseline, future = self._split_by_period(rx1day_data)

        return {
            "rx1day_baseline_mm": self._calculate_mean(baseline),
            "rx1day_future_mm": self._calculate_mean(future),
        }

    def split_rx5day(self, rx5day_data: List[float]) -> Dict[str, float]:
        """
        5일최대강수량 데이터 분리

        Args:
            rx5day_data: 연도별 rx5day 배열

        Returns:
            {
                'rx5day_baseline_mm': float,
                'rx5day_future_mm': float
            }
        """
        baseline, future = self._split_by_period(rx5day_data)

        return {
            "rx5day_baseline_mm": self._calculate_mean(baseline),
            "rx5day_future_mm": self._calculate_mean(future),
        }

    def split_sdii(self, sdii_data: List[float]) -> Dict[str, float]:
        """
        강수강도 데이터 분리

        Args:
            sdii_data: 연도별 sdii 배열

        Returns:
            {
                'sdii_baseline': float,
                'sdii_future': float
            }
        """
        baseline, future = self._split_by_period(sdii_data)

        return {
            "sdii_baseline": self._calculate_mean(baseline),
            "sdii_future": self._calculate_mean(future),
        }

    def split_rain80(self, rain80_data: List[float]) -> Dict[str, float]:
        """
        80mm 이상 강수일수 데이터 분리

        Args:
            rain80_data: 연도별 rain80 배열

        Returns:
            {
                'rain80_baseline_days': float,
                'rain80_future_days': float
            }
        """
        baseline, future = self._split_by_period(rain80_data)

        return {
            "rain80_baseline_days": self._calculate_mean(baseline),
            "rain80_future_days": self._calculate_mean(future),
        }

    def split_wind(self, wind_data: List[float]) -> Dict[str, float]:
        """
        풍속 데이터 분리 (95분위수 사용)

        Args:
            wind_data: 월별 풍속 배열

        Returns:
            {
                'wind_95p_baseline': float,  # 기준기간 95분위수
                'wind_95p_future': float     # 미래기간 95분위수
            }
        """
        baseline, future = self._split_by_period(wind_data)

        return {
            "wind_95p_baseline": self._calculate_percentile(baseline, 95),
            "wind_95p_future": self._calculate_percentile(future, 95),
        }

    def split_by_period(
        self,
        data: List[float],
        baseline_years: Tuple[int, int] = None,
        future_years: Tuple[int, int] = None,
    ) -> Dict[str, List[float]]:
        """
        커스텀 기간으로 데이터 분리

        Args:
            data: 연도별 데이터 배열
            baseline_years: 기준기간 (start_year, end_year)
            future_years: 미래기간 (start_year, end_year)

        Returns:
            {
                'baseline': List[float],
                'future': List[float]
            }
        """
        baseline_years = baseline_years or (self.BASELINE_START_YEAR, self.BASELINE_END_YEAR)
        future_years = future_years or (self.FUTURE_START_YEAR, self.FUTURE_END_YEAR)

        baseline_start_idx = baseline_years[0] - self.start_year
        baseline_end_idx = baseline_years[1] - self.start_year + 1
        future_start_idx = future_years[0] - self.start_year
        future_end_idx = future_years[1] - self.start_year + 1

        # 인덱스 범위 체크
        baseline_start_idx = max(0, baseline_start_idx)
        baseline_end_idx = min(len(data), baseline_end_idx)
        future_start_idx = max(0, future_start_idx)
        future_end_idx = min(len(data), future_end_idx)

        baseline_data = data[baseline_start_idx:baseline_end_idx]
        future_data = data[future_start_idx:future_end_idx]

        return {"baseline": baseline_data, "future": future_data}

    # ===== 내부 함수 =====

    def _split_by_period(self, data: List[float]) -> Tuple[List[float], List[float]]:
        """기본 기준기간/미래기간 분리"""
        baseline_start_idx = self.BASELINE_START_YEAR - self.start_year
        baseline_end_idx = self.BASELINE_END_YEAR - self.start_year + 1
        future_start_idx = self.FUTURE_START_YEAR - self.start_year
        future_end_idx = self.FUTURE_END_YEAR - self.start_year + 1

        # 인덱스 범위 체크
        baseline_start_idx = max(0, baseline_start_idx)
        baseline_end_idx = min(len(data), baseline_end_idx)
        future_start_idx = max(0, future_start_idx)
        future_end_idx = min(len(data), future_end_idx)

        baseline_data = data[baseline_start_idx:baseline_end_idx]
        future_data = data[future_start_idx:future_end_idx]

        return baseline_data, future_data

    def _calculate_mean(self, data: List[float]) -> float:
        """평균 계산"""
        if not data:
            return 0.0
        return sum(data) / len(data)

    def _calculate_percentile(self, data: List[float], percentile: int) -> float:
        """백분위수 계산"""
        if not data:
            return 0.0

        sorted_data = sorted(data)
        n = len(sorted_data)
        k = (n - 1) * (percentile / 100.0)
        f = int(k)
        c = f + 1

        if c >= n:
            return sorted_data[-1]

        d0 = sorted_data[f]
        d1 = sorted_data[c]

        return d0 + (d1 - d0) * (k - f)
