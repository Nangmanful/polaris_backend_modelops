"""
기후 데이터 집계 함수 모듈

월별 데이터 → 연별 데이터 변환
- yearly_max: 연최대값
- yearly_min: 연최소값
- yearly_mean: 연평균
- yearly_percentile: 연백분위수
"""

from typing import List, Dict, Any


class ClimateAggregators:
    """기후 데이터 집계 함수"""

    @staticmethod
    def yearly_max(monthly_data: List[float], months_per_year: int = 12) -> List[float]:
        """
        월별 데이터 → 연최대값

        Args:
            monthly_data: 월별 데이터 배열
            months_per_year: 연간 월수 (기본 12개월)

        Returns:
            연도별 최대값 배열
        """
        if not monthly_data:
            return []

        yearly_values = []
        total_years = len(monthly_data) // months_per_year

        for year in range(total_years):
            start_idx = year * months_per_year
            end_idx = start_idx + months_per_year
            year_data = monthly_data[start_idx:end_idx]

            if year_data:
                yearly_values.append(max(year_data))

        return yearly_values

    @staticmethod
    def yearly_min(monthly_data: List[float], months_per_year: int = 12) -> List[float]:
        """
        월별 데이터 → 연최소값

        Args:
            monthly_data: 월별 데이터 배열
            months_per_year: 연간 월수

        Returns:
            연도별 최소값 배열
        """
        if not monthly_data:
            return []

        yearly_values = []
        total_years = len(monthly_data) // months_per_year

        for year in range(total_years):
            start_idx = year * months_per_year
            end_idx = start_idx + months_per_year
            year_data = monthly_data[start_idx:end_idx]

            if year_data:
                yearly_values.append(min(year_data))

        return yearly_values

    @staticmethod
    def yearly_mean(monthly_data: List[float], months_per_year: int = 12) -> List[float]:
        """
        월별 데이터 → 연평균

        Args:
            monthly_data: 월별 데이터 배열
            months_per_year: 연간 월수

        Returns:
            연도별 평균값 배열
        """
        if not monthly_data:
            return []

        yearly_values = []
        total_years = len(monthly_data) // months_per_year

        for year in range(total_years):
            start_idx = year * months_per_year
            end_idx = start_idx + months_per_year
            year_data = monthly_data[start_idx:end_idx]

            if year_data:
                yearly_values.append(sum(year_data) / len(year_data))

        return yearly_values

    @staticmethod
    def yearly_sum(monthly_data: List[float], months_per_year: int = 12) -> List[float]:
        """
        월별 데이터 → 연합계

        Args:
            monthly_data: 월별 데이터 배열
            months_per_year: 연간 월수

        Returns:
            연도별 합계 배열
        """
        if not monthly_data:
            return []

        yearly_values = []
        total_years = len(monthly_data) // months_per_year

        for year in range(total_years):
            start_idx = year * months_per_year
            end_idx = start_idx + months_per_year
            year_data = monthly_data[start_idx:end_idx]

            if year_data:
                yearly_values.append(sum(year_data))

        return yearly_values

    @staticmethod
    def yearly_percentile(
        monthly_data: List[float], percentile: int = 95, months_per_year: int = 12
    ) -> List[float]:
        """
        월별 데이터 → 연백분위수

        Args:
            monthly_data: 월별 데이터 배열
            percentile: 백분위 (0-100)
            months_per_year: 연간 월수

        Returns:
            연도별 백분위수 배열
        """
        if not monthly_data:
            return []

        yearly_values = []
        total_years = len(monthly_data) // months_per_year

        for year in range(total_years):
            start_idx = year * months_per_year
            end_idx = start_idx + months_per_year
            year_data = monthly_data[start_idx:end_idx]

            if year_data:
                p_value = ClimateAggregators._calculate_percentile(year_data, percentile)
                yearly_values.append(p_value)

        return yearly_values

    @staticmethod
    def rolling_mean(data: List[float], window: int = 12) -> List[float]:
        """
        이동 평균 계산

        Args:
            data: 데이터 배열
            window: 윈도우 크기 (기본 12개월)

        Returns:
            이동 평균 배열
        """
        if not data or len(data) < window:
            return data

        rolling_values = []
        for i in range(len(data) - window + 1):
            window_data = data[i : i + window]
            rolling_values.append(sum(window_data) / len(window_data))

        return rolling_values

    @staticmethod
    def calculate_trend(data: List[float]) -> Dict[str, float]:
        """
        선형 추세 계산 (단순 선형 회귀)

        Args:
            data: 시계열 데이터 배열

        Returns:
            {
                'slope': float,      # 기울기 (증가율)
                'intercept': float,  # 절편
                'trend': str         # 'increasing', 'decreasing', 'stable'
            }
        """
        if not data or len(data) < 2:
            return {"slope": 0.0, "intercept": 0.0, "trend": "stable"}

        n = len(data)
        x = list(range(n))
        y = data

        # 평균 계산
        x_mean = sum(x) / n
        y_mean = sum(y) / n

        # 기울기 계산
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0.0
        intercept = y_mean - slope * x_mean

        # 추세 판단
        if abs(slope) < 0.01:
            trend = "stable"
        elif slope > 0:
            trend = "increasing"
        else:
            trend = "decreasing"

        return {"slope": slope, "intercept": intercept, "trend": trend}

    @staticmethod
    def _calculate_percentile(data: List[float], percentile: int) -> float:
        """백분위수 계산 (내부 함수)"""
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

    @staticmethod
    def flatten_monthly_data(monthly_nested: List[Dict[str, Any]], key: str) -> List[float]:
        """
        중첩된 월별 데이터를 flat 리스트로 변환

        Args:
            monthly_nested: [{'year': 2021, 'month': 1, 'value': 10.5}, ...]
            key: 추출할 값의 키 (예: 'value', 'ta', 'rn')

        Returns:
            [10.5, 12.3, ...] (flat list)
        """
        return [item.get(key, 0.0) for item in monthly_nested if key in item]
