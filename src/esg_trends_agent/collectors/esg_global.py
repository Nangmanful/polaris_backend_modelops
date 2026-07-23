"""
==================================================================
[모듈명] collectors/esg_global.py
글로벌 ESG 뉴스 수집기

[모듈 목표]
1) KOTRA API로 글로벌 ESG 뉴스 수집
2) Fallback 검색 지원
==================================================================
"""

from typing import Dict
from ..state import ESGTrendsState, ESGNewsItem
from ..tools.kotra_api import fetch_recent_esg_news
from ..tools.search import search_global_esg_trends
from ..utils.config import Config
from ..utils.logging import get_logger

logger = get_logger("esg_agent.collector.global")


def collect_global_news(state: ESGTrendsState) -> Dict:
    """글로벌 ESG 뉴스 수집

    Args:
        state: 현재 상태

    Returns:
        Dict: 업데이트할 상태 필드
    """
    logger.info("글로벌 ESG 뉴스 수집 시작")

    news_items = []
    errors = []

    # 1. KOTRA API 시도
    try:
        logger.info("KOTRA ESG 동향뉴스 API 호출...")
        kotra_news = fetch_recent_esg_news(days=7, limit=Config.MAX_NEWS_PER_SOURCE)

        for news in kotra_news:
            news_item = ESGNewsItem(
                title=news.get("title", ""),
                summary=news.get("summary", ""),
                url=news.get("url", ""),
                source="KOTRA",
                category=_classify_esg_category(
                    news.get("title", "") + " " + news.get("summary", "")
                ),
                published_at=news.get("published_at"),
                region=news.get("country", news.get("region", "")),
            )
            news_items.append(news_item)

        logger.info(f"KOTRA API에서 {len(kotra_news)}개 뉴스 수집")

    except Exception as e:
        error_msg = f"KOTRA API 호출 실패: {str(e)}"
        logger.warning(error_msg)
        errors.append(error_msg)

    # 2. 결과가 부족하면 검색 API로 보완
    if len(news_items) < Config.MIN_NEWS_REQUIRED:
        logger.info(f"글로벌 뉴스 부족 ({len(news_items)}개), 검색 API로 보완...")

        try:
            search_results = search_global_esg_trends(
                max_results=Config.MAX_NEWS_PER_SOURCE - len(news_items)
            )

            for news in search_results:
                # 중복 체크 (제목 기반)
                existing_titles = {item["title"] for item in news_items}
                if news.get("title") and news["title"] not in existing_titles:
                    news_item = ESGNewsItem(
                        title=news.get("title", ""),
                        summary=news.get("summary", ""),
                        url=news.get("url", ""),
                        source=news.get("source", "웹검색"),
                        category=_classify_esg_category(
                            news.get("title", "") + " " + news.get("summary", "")
                        ),
                        published_at=None,
                        region=news.get("region", "글로벌"),
                    )
                    news_items.append(news_item)

            logger.info(f"검색 API로 {len(search_results)}개 글로벌 뉴스 추가 수집")

        except Exception as e:
            error_msg = f"글로벌 ESG 검색 실패: {str(e)}"
            logger.warning(error_msg)
            errors.append(error_msg)

    # 수집 상태 업데이트
    collection_status = state.get("collection_status", {}).copy()
    collection_status["global"] = "success" if news_items else "failed"

    logger.info(f"글로벌 ESG 뉴스 수집 완료: {len(news_items)}개")

    return {
        "global_news": news_items,
        "collection_status": collection_status,
        "errors": errors,
    }


def _classify_esg_category(text: str) -> str:
    """텍스트 기반 ESG 카테고리 분류

    Args:
        text: 분류할 텍스트

    Returns:
        str: "E", "S", "G", 또는 ""
    """
    text_lower = text.lower()

    # Environmental 키워드 (영어 + 한국어)
    e_keywords = [
        "환경",
        "탄소",
        "기후",
        "에너지",
        "재생",
        "폐기물",
        "오염",
        "생태",
        "environment",
        "carbon",
        "climate",
        "energy",
        "renewable",
        "emission",
        "green",
    ]
    # Social 키워드
    s_keywords = [
        "사회",
        "노동",
        "인권",
        "다양성",
        "안전",
        "지역사회",
        "공급망",
        "social",
        "labor",
        "human rights",
        "diversity",
        "safety",
        "community",
    ]
    # Governance 키워드
    g_keywords = [
        "지배구조",
        "이사회",
        "윤리",
        "투명",
        "컴플라이언스",
        "반부패",
        "governance",
        "board",
        "ethics",
        "transparency",
        "compliance",
        "corruption",
    ]

    e_score = sum(1 for kw in e_keywords if kw in text_lower)
    s_score = sum(1 for kw in s_keywords if kw in text_lower)
    g_score = sum(1 for kw in g_keywords if kw in text_lower)

    if e_score > s_score and e_score > g_score:
        return "E"
    elif s_score > e_score and s_score > g_score:
        return "S"
    elif g_score > e_score and g_score > s_score:
        return "G"
    else:
        return ""
