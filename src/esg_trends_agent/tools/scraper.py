"""
==================================================================
[모듈명] tools/scraper.py
ESG Economy 웹 스크래핑

[모듈 목표]
1) esgeconomy.com 뉴스 수집
2) HTML 파싱 및 데이터 추출
==================================================================
"""

import requests
from bs4 import BeautifulSoup
from datetime import date
from typing import Dict, List, Optional
from ..utils.logging import get_logger

logger = get_logger("esg_agent.scraper")

# ESG Economy 뉴스 URL
ESG_ECONOMY_NEWS_URL = "https://www.esgeconomy.com/news/articleList.html?view_type=sm"


def scrape_esg_economy(
    limit: int = 10, target_date: Optional[date] = None, max_retries: int = 3
) -> List[Dict]:
    """ESG Economy 뉴스 스크래핑

    Args:
        limit: 수집할 뉴스 개수
        target_date: 특정 날짜의 뉴스만 수집 (없으면 전체)
        max_retries: 최대 재시도 횟수

    Returns:
        List[Dict]: 뉴스 리스트
    """
    import time

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    params = {
        "sc_section_code": "",
        "sc_sub_section_code": "",
        "sc_serial_code": "",
        "sc_area": "",
        "sc_level": "",
        "sc_article_type": "",
        "sc_view_level": "",
        "sc_sdate": "",
        "sc_edate": "",
        "sc_serial_number": "",
        "sc_word": "",
        "sc_order_by": "E",  # 최신순
        "view_type": "sm",
        "page": 1,
    }

    for attempt in range(max_retries):
        try:
            response = requests.get(
                ESG_ECONOMY_NEWS_URL, params=params, headers=headers, timeout=15
            )

            # 429/500/502/503 에러 시 대기 후 재시도
            if response.status_code in [429, 500, 502, 503]:
                wait_time = (attempt + 1) * 5
                logger.warning(
                    f"ESG Economy {response.status_code} 에러, {wait_time}초 대기 후 재시도..."
                )
                time.sleep(wait_time)
                continue

            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            news_list = parse_esg_economy_page(soup, limit, target_date)

            logger.info(f"ESG Economy 뉴스 {len(news_list)}건 수집 완료")

            # 결과 출력
            if news_list:
                print(f"\n{'='*50}")
                print(f"🇰🇷 ESG Economy 국내 뉴스 ({len(news_list)}건)")
                print(f"{'='*50}")
                for i, news in enumerate(news_list[:5], 1):
                    print(f"\n[{i}] [{news.get('category', '')}] {news.get('title', '')[:40]}...")
                    print(f"    요약: {news.get('summary', '')[:50]}...")
                    print(f"    URL: {news.get('url', '')[:50]}...")

            return news_list

        except requests.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 3
                logger.warning(f"ESG Economy 스크래핑 실패, {wait_time}초 후 재시도: {e}")
                time.sleep(wait_time)
            else:
                logger.error(f"ESG Economy 스크래핑 실패 (최대 재시도 초과): {e}")
                return []
        except Exception as e:
            logger.error(f"ESG Economy 파싱 오류: {e}")
            return []

    logger.error("ESG Economy 최대 재시도 횟수 초과")
    return []


def parse_esg_economy_page(
    soup: BeautifulSoup, limit: int, target_date: Optional[date]
) -> List[Dict]:
    """ESG Economy 페이지 파싱

    Args:
        soup: BeautifulSoup 객체
        limit: 수집할 뉴스 개수
        target_date: 특정 날짜 필터

    Returns:
        List[Dict]: 파싱된 뉴스 리스트
    """
    news_list = []

    # 기사 리스트 아이템 찾기 (li 또는 article 태그)
    articles = soup.find_all("li")
    if not articles:
        articles = soup.find_all("article")

    for article in articles:
        if len(news_list) >= limit:
            break

        try:
            # h4.titles에서 제목과 URL 추출
            title_tag = article.find("h4", class_="titles")
            if not title_tag:
                continue

            link = title_tag.find("a")
            if not link:
                continue

            title = link.get_text(strip=True)
            url = link.get("href", "")
            if url and not url.startswith("http"):
                url = f"https://www.esgeconomy.com{url}"

            # p.lead에서 요약 추출
            summary_tag = article.find("p", class_="lead")
            summary = summary_tag.get_text(strip=True) if summary_tag else ""

            # span.byline에서 날짜 추출
            date_tag = article.find("span", class_="byline")
            published_at = ""
            if date_tag:
                date_text = date_tag.get_text(strip=True)
                if "." in date_text:
                    published_at = date_text.split(" ")[0]

            # ESG 관련 키워드 필터링 (광고성 기사 제외)
            esg_keywords = [
                "ESG",
                "탄소",
                "환경",
                "기후",
                "지속가능",
                "재생에너지",
                "녹색",
                "CBAM",
                "지배구조",
            ]
            is_esg_related = any(kw in title for kw in esg_keywords)

            # ESG 관련 기사만 포함 (또는 결과가 부족할 경우 모두 포함)
            if is_esg_related or len(news_list) < 3:
                news = {
                    "title": title,
                    "summary": summary,
                    "url": url,
                    "published_at": published_at,
                    "category": classify_esg_category(title + " " + summary),
                    "source": "ESG Economy",
                }
                news_list.append(news)

        except Exception as e:
            logger.warning(f"뉴스 아이템 파싱 실패: {e}")
            continue

    return news_list


def parse_article_item(article) -> Optional[Dict]:
    """개별 뉴스 아이템 파싱

    Args:
        article: BeautifulSoup 태그 객체

    Returns:
        Dict: 파싱된 뉴스 데이터 또는 None
    """
    # 제목 및 URL
    title_tag = article.find("h4", class_="titles")
    if not title_tag:
        return None

    title_link = title_tag.find("a")
    if not title_link:
        return None

    title = title_link.get_text(strip=True)
    url = title_link.get("href", "")
    if url and not url.startswith("http"):
        url = f"https://www.esgeconomy.com{url}"

    # 요약
    summary_tag = article.find("p", class_="lead")
    summary = summary_tag.get_text(strip=True) if summary_tag else ""

    # 날짜
    date_tag = article.find("span", class_="byline")
    published_at = ""
    if date_tag:
        date_text = date_tag.get_text(strip=True)
        # "2024.01.15 10:30" 형태에서 날짜만 추출
        if "." in date_text:
            published_at = date_text.split(" ")[0]

    # 카테고리 (E, S, G 분류)
    category = classify_esg_category(title + " " + summary)

    return {
        "title": title,
        "summary": summary,
        "url": url,
        "published_at": published_at,
        "category": category,
        "source": "ESG Economy",
    }


def classify_esg_category(text: str) -> str:
    """ESG 카테고리 분류

    Args:
        text: 뉴스 제목 + 요약

    Returns:
        str: E, S, G, 또는 ESG
    """
    text_lower = text.lower()

    e_keywords = ["환경", "탄소", "기후", "에너지", "재생", "배출", "그린", "친환경", "환경부"]
    s_keywords = ["사회", "인권", "노동", "안전", "다양성", "지역사회", "복지", "고용"]
    g_keywords = ["지배구조", "이사회", "투명성", "윤리", "감사", "경영", "주주"]

    e_score = sum(1 for k in e_keywords if k in text_lower)
    s_score = sum(1 for k in s_keywords if k in text_lower)
    g_score = sum(1 for k in g_keywords if k in text_lower)

    if e_score > s_score and e_score > g_score:
        return "E"
    elif s_score > e_score and s_score > g_score:
        return "S"
    elif g_score > e_score and g_score > s_score:
        return "G"
    else:
        return "ESG"


def scrape_today_news(limit: int = 10) -> List[Dict]:
    """오늘 날짜 뉴스만 수집

    Args:
        limit: 수집할 뉴스 개수

    Returns:
        List[Dict]: 오늘 뉴스 리스트
    """
    today = date.today()
    news_list = scrape_esg_economy(limit=limit * 2, target_date=today)

    # 오늘 뉴스가 없으면 최신 뉴스 반환
    if not news_list:
        logger.info("오늘 뉴스가 없어 최신 뉴스 수집")
        news_list = scrape_esg_economy(limit=limit)

    return news_list[:limit]
