"""
==================================================================
[모듈명] agents/quality_checker.py
품질 체커 에이전트

[모듈 목표]
1) 수집 데이터 품질 평가
2) 리포트 품질 검증
==================================================================
"""

from typing import Dict, Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from ..state import ESGTrendsState
from ..utils.config import Config
from ..utils.logging import get_logger
from ..prompts import QUALITY_CHECKER_PROMPT

logger = get_logger("esg_agent.quality_checker")


def check_quality(state: ESGTrendsState) -> Dict:
    """데이터 및 분석 품질 체크

    Args:
        state: 현재 상태

    Returns:
        Dict: 업데이트할 상태 필드
    """
    logger.info("품질 체크 시작")

    # 기본 품질 점수 계산
    base_score = _calculate_base_quality(state)

    # 분석 결과가 있으면 LLM으로 추가 검증
    esg_insight = state.get("esg_insight", "")

    if esg_insight and len(esg_insight) > 50:
        try:
            llm_score, feedback = _llm_quality_check(state)
            final_score = (base_score + llm_score) / 2
        except Exception as e:
            logger.warning(f"LLM 품질 체크 실패: {e}")
            final_score = base_score
            feedback = "자동 품질 체크만 수행됨"
    else:
        final_score = base_score
        feedback = "분석 결과가 불충분합니다."

    logger.info(f"품질 점수: {final_score:.2f}")

    return {
        "quality_score": final_score,
        "quality_feedback": feedback,
    }


def _calculate_base_quality(state: ESGTrendsState) -> float:
    """기본 품질 점수 계산

    Args:
        state: 현재 상태

    Returns:
        float: 품질 점수 (0.0 ~ 1.0)
    """
    score = 0.0

    # 1. 날씨 데이터 (0.2점)
    weather_data = state.get("weather_data", [])
    if weather_data:
        weather_score = min(len(weather_data) / 3.0, 1.0) * 0.2
        score += weather_score

    # 2. 국내 뉴스 (0.25점)
    domestic_news = state.get("domestic_news", [])
    if domestic_news:
        domestic_score = min(len(domestic_news) / Config.MIN_NEWS_REQUIRED, 1.0) * 0.25
        score += domestic_score

    # 3. 글로벌 뉴스 (0.25점)
    global_news = state.get("global_news", [])
    if global_news:
        global_score = min(len(global_news) / Config.MIN_NEWS_REQUIRED, 1.0) * 0.25
        score += global_score

    # 4. 분석 결과 (0.3점)
    esg_insight = state.get("esg_insight", "")
    trending_topics = state.get("trending_topics", [])
    recommendations = state.get("recommendations", [])

    if esg_insight and len(esg_insight) > 100:
        score += 0.15
    if trending_topics:
        score += 0.075
    if recommendations:
        score += 0.075

    return min(score, 1.0)


def _llm_quality_check(state: ESGTrendsState) -> tuple:
    """LLM을 사용한 품질 검증

    Args:
        state: 현재 상태

    Returns:
        tuple: (점수, 피드백)
    """
    llm = ChatOpenAI(
        model=Config.OPENAI_MODEL,
        temperature=0.1,
        api_key=Config.OPENAI_API_KEY,
    )

    # 검증할 내용 요약
    content_summary = f"""
    [수집 데이터]
    - 날씨 데이터: {len(state.get('weather_data', []))}개 지역
    - 물리적 리스크: {len(state.get('physical_risks', []))}개
    - 국내 뉴스: {len(state.get('domestic_news', []))}개
    - 글로벌 뉴스: {len(state.get('global_news', []))}개

    [분석 결과]
    - ESG 인사이트: {len(state.get('esg_insight', ''))}자
    - 트렌드 토픽: {len(state.get('trending_topics', []))}개
    - 권고사항: {len(state.get('recommendations', []))}개

    [ESG 인사이트 내용]
    {state.get('esg_insight', '')[:500]}
    """

    messages = [
        SystemMessage(content=QUALITY_CHECKER_PROMPT),
        HumanMessage(content=content_summary),
    ]

    response = llm.invoke(messages)
    result = response.content

    # 점수 추출 (예: "점수: 0.8" 형식)
    score = 0.7  # 기본값
    try:
        if "점수" in result:
            import re

            match = re.search(r"점수[:\s]*([0-9.]+)", result)
            if match:
                score = float(match.group(1))
                score = min(max(score, 0.0), 1.0)
    except Exception:
        pass

    return score, result


def should_regenerate(state: ESGTrendsState) -> Literal["regenerate", "pass"]:
    """품질 점수에 따라 재생성 여부 결정

    Args:
        state: 현재 상태

    Returns:
        str: "regenerate" 또는 "pass"
    """
    quality_score = state.get("quality_score", 0.0)

    if quality_score < Config.MIN_QUALITY_SCORE:
        logger.warning(f"품질 점수 미달: {quality_score:.2f} < {Config.MIN_QUALITY_SCORE}")
        return "regenerate"

    return "pass"
