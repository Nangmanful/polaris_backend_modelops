"""
==================================================================
[모듈명] tools/search.py
다중 검색 엔진 도구

[모듈 목표]
1) Tavily/DuckDuckGo 검색
2) Fallback 검색 지원
3) ESG 관련 뉴스 검색
==================================================================
"""

import os
from typing import List, Dict, Optional
from ..utils.logging import get_logger

logger = get_logger("esg_agent.search")


def evaluate_search_quality(results: List[Dict]) -> float:
    """검색 결과 품질 평가

    Args:
        results: 검색 결과 리스트

    Returns:
        float: 품질 점수 (0.0 ~ 1.0)
    """
    if not results:
        return 0.0

    score = 0.0

    # 결과 개수 점수 (최대 0.5)
    count_score = min(len(results) / 5.0, 1.0) * 0.5
    score += count_score

    # 내용 품질 점수 (최대 0.5)
    content_lengths = [len(r.get("content", "")) for r in results]
    avg_length = sum(content_lengths) / len(content_lengths) if content_lengths else 0
    content_score = min(avg_length / 200.0, 1.0) * 0.5
    score += content_score

    return score


def search_web(
    query: str, domains: Optional[List[str]] = None, min_quality: float = 0.4, max_results: int = 5
) -> Dict:
    """웹 검색 (Tavily → DuckDuckGo Fallback)

    Args:
        query: 검색 쿼리
        domains: 검색할 도메인 리스트 (옵션)
        min_quality: 최소 품질 점수 (0.0 ~ 1.0)
        max_results: 최대 결과 개수

    Returns:
        Dict: {
            "results": List[Dict],
            "source": str,  # "tavily", "duckduckgo"
            "quality": float
        }
    """
    # 1. Tavily 검색 시도
    tavily_api_key = os.getenv("TAVILY_API_KEY", "")
    if tavily_api_key:
        try:
            logger.info(f"Tavily 검색 시도: {query}")
            from tavily import TavilyClient

            tavily = TavilyClient(api_key=tavily_api_key)

            search_params = {"query": query, "max_results": max_results, "search_depth": "basic"}

            if domains:
                search_params["include_domains"] = domains

            response = tavily.search(**search_params)
            results = response.get("results", [])
            quality = evaluate_search_quality(results)

            logger.info(f"Tavily 결과: {len(results)}개, 품질: {quality:.2f}")

            if quality >= min_quality:
                return {"results": results, "source": "tavily", "quality": quality}
        except Exception as e:
            logger.warning(f"Tavily 검색 실패: {e}")

    # 2. DuckDuckGo 검색 시도
    try:
        logger.info(f"DuckDuckGo 검색 시도: {query}")
        from duckduckgo_search import DDGS

        ddgs = DDGS()
        search_query = query
        if domains:
            domain_str = " OR ".join([f"site:{d}" for d in domains])
            search_query = f"{query} ({domain_str})"

        ddg_results = list(ddgs.text(search_query, max_results=max_results))

        # 결과 포맷 통일
        results = [
            {"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")}
            for r in ddg_results
        ]

        quality = evaluate_search_quality(results)
        logger.info(f"DuckDuckGo 결과: {len(results)}개, 품질: {quality:.2f}")

        return {"results": results, "source": "duckduckgo", "quality": quality}
    except Exception as e:
        logger.error(f"DuckDuckGo 검색 실패: {e}")

    # 모든 검색 실패
    logger.error("모든 검색 엔진 실패")
    return {"results": [], "source": "none", "quality": 0.0}


def search_esg_news(query: str = "ESG 동향", max_results: int = 10) -> List[Dict]:
    """ESG 뉴스 검색

    Args:
        query: 검색 쿼리
        max_results: 최대 결과 개수

    Returns:
        List[Dict]: 뉴스 리스트
    """
    result = search_web(query=query, max_results=max_results, min_quality=0.3)

    news_list = []
    for item in result.get("results", []):
        news_list.append(
            {
                "title": item.get("title", ""),
                "summary": item.get("content", ""),
                "url": item.get("url", ""),
                "source": result.get("source", "search"),
            }
        )

    return news_list


def search_global_esg_trends(max_results: int = 10) -> List[Dict]:
    """글로벌 ESG 동향 검색 (KOTRA API Fallback용)

    Args:
        max_results: 최대 결과 개수

    Returns:
        List[Dict]: 글로벌 ESG 뉴스 리스트
    """
    queries = [
        "글로벌 ESG 동향 2024",
        "해외 ESG 규제 변화",
        "EU ESG 공시 의무화",
    ]

    all_results = []

    for query in queries:
        result = search_web(query=query, max_results=5, min_quality=0.3)
        for item in result.get("results", []):
            news = {
                "title": item.get("title", ""),
                "summary": item.get("content", ""),
                "url": item.get("url", ""),
                "region": "글로벌",
                "region_category": "기타",
                "source": "웹검색",
            }
            all_results.append(news)

        if len(all_results) >= max_results:
            break

    return all_results[:max_results]
