"""
==================================================================
[모듈명] agents/orchestrator.py
오케스트레이터 에이전트

[모듈 목표]
1) 워크플로우 전체 조율
2) 수집 완료 후 다음 단계 결정
==================================================================
"""

from typing import Dict, Literal
from ..state import ESGTrendsState
from ..utils.logging import get_logger

logger = get_logger("esg_agent.orchestrator")


def orchestrate(state: ESGTrendsState) -> Dict:
    """워크플로우 오케스트레이션

    수집 완료 상태를 확인하고 다음 단계를 결정

    Args:
        state: 현재 상태

    Returns:
        Dict: 업데이트할 상태 필드
    """
    logger.info("오케스트레이션 시작")

    collection_status = state.get("collection_status", {})

    # 수집 상태 확인
    weather_ok = collection_status.get("weather") == "success"
    domestic_ok = collection_status.get("domestic") == "success"
    global_ok = collection_status.get("global") == "success"

    # 로깅
    logger.info(f"수집 상태 - 날씨: {weather_ok}, 국내: {domestic_ok}, 글로벌: {global_ok}")

    # 최소 요구사항 체크: 날씨 + (국내 OR 글로벌)
    if not weather_ok:
        logger.warning("날씨 데이터 수집 실패")

    if not domestic_ok and not global_ok:
        logger.warning("ESG 뉴스 수집 모두 실패")

    # 수집 데이터 요약
    weather_count = len(state.get("weather_data", []))
    domestic_count = len(state.get("domestic_news", []))
    global_count = len(state.get("global_news", []))

    logger.info(
        f"수집 완료 - 날씨: {weather_count}개, 국내뉴스: {domestic_count}개, 글로벌뉴스: {global_count}개"
    )

    return {}


def should_continue(state: ESGTrendsState) -> Literal["continue", "end"]:
    """수집 후 계속 진행할지 결정

    Args:
        state: 현재 상태

    Returns:
        str: "continue" 또는 "end"
    """
    collection_status = state.get("collection_status", {})

    # 날씨 데이터는 필수
    if collection_status.get("weather") != "success":
        # 날씨 없어도 뉴스만 있으면 진행
        domestic_ok = collection_status.get("domestic") == "success"
        global_ok = collection_status.get("global") == "success"

        if not domestic_ok and not global_ok:
            logger.error("모든 데이터 수집 실패, 워크플로우 종료")
            return "end"

    return "continue"
