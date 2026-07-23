"""
==================================================================
[모듈명] state.py
ESG Trends Agent 상태 정의

[모듈 목표]
1) LangGraph StateGraph용 상태 타입 정의
2) 각 에이전트 간 데이터 흐름 정의
==================================================================
"""

from typing import TypedDict, List, Dict, Optional, Annotated
from operator import add


class WeatherData(TypedDict):
    """날씨 데이터"""

    location: str
    temperature: float
    humidity: int
    weather_condition: str
    wind_speed: float
    precipitation: float
    forecast_date: str
    forecast_time: str
    raw_data: Dict


class PhysicalRiskAnalysis(TypedDict):
    """물리적 리스크 분석 결과"""

    risk_type: str  # 9대 물리적 리스크 중 하나
    risk_level: str  # "높음", "보통", "낮음"
    description: str
    related_weather: List[str]


class ESGNewsItem(TypedDict):
    """ESG 뉴스 아이템"""

    title: str
    summary: str
    url: str
    source: str
    category: str  # "E", "S", "G"
    published_at: Optional[str]
    region: Optional[str]


class ESGTrendsState(TypedDict):
    """ESG Trends Agent 메인 상태

    LangGraph StateGraph에서 사용하는 전체 상태 정의
    """

    # ===== 수집 데이터 =====
    # 날씨 데이터 (지역별)
    weather_data: Annotated[List[WeatherData], add]

    # 물리적 리스크 분석
    physical_risks: List[PhysicalRiskAnalysis]

    # 국내 ESG 뉴스
    domestic_news: Annotated[List[ESGNewsItem], add]

    # 글로벌 ESG 뉴스 (KOTRA)
    global_news: Annotated[List[ESGNewsItem], add]

    # ===== 분석 결과 =====
    # 경쟁사 분석
    competitor_analysis: str

    # 트렌드 키워드
    trending_topics: List[str]

    # 급변 감지
    sudden_changes: List[str]

    # 권고사항
    recommendations: List[str]

    # ===== 리포트 =====
    # 날씨 요약
    weather_summary: str

    # ESG 인사이트 요약
    esg_insight: str

    # 최종 리포트
    final_report: str

    # ===== 메타데이터 =====
    # 수집 상태
    collection_status: Dict[str, str]  # {"weather": "success", "domestic": "success", ...}

    # 품질 점수
    quality_score: float

    # 품질 체크 결과
    quality_feedback: str

    # 에러 메시지
    errors: Annotated[List[str], add]

    # 실행 시각
    execution_time: str


def create_initial_state() -> ESGTrendsState:
    """초기 상태 생성

    Returns:
        ESGTrendsState: 빈 초기 상태
    """
    from datetime import datetime

    return ESGTrendsState(
        # 수집 데이터
        weather_data=[],
        physical_risks=[],
        domestic_news=[],
        global_news=[],
        # 분석 결과
        competitor_analysis="",
        trending_topics=[],
        sudden_changes=[],
        recommendations=[],
        # 리포트
        weather_summary="",
        esg_insight="",
        final_report="",
        # 메타데이터
        collection_status={},
        quality_score=0.0,
        quality_feedback="",
        errors=[],
        execution_time=datetime.now().isoformat(),
    )
