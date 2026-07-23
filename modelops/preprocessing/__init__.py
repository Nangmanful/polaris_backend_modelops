"""
ModelOps 전처리 레이어

DB 원시 데이터를 Hazard/Probability 에이전트가 요구하는 파생 지표로 변환합니다.

모듈:
- climate_indicators: 기후 지표 계산 (폭염일수, FWI 등)
- baseline_splitter: 기준기간/미래기간 데이터 분리
- aggregators: 집계 함수 (연최대, 백분위수 등)
"""

from .climate_indicators import ClimateIndicatorCalculator
from .baseline_splitter import BaselineSplitter
from .aggregators import ClimateAggregators

__all__ = [
    "ClimateIndicatorCalculator",
    "BaselineSplitter",
    "ClimateAggregators",
]
