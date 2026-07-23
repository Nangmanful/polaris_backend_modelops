"""
==================================================================
[모듈명] agents/supervisor.py
수퍼바이저 에이전트

[모듈 목표]
1) 수집 데이터 통합 및 검증
2) ESG 인사이트 분석 (LLM 활용)
==================================================================
"""

from typing import Dict, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from ..state import ESGTrendsState
from ..utils.config import Config
from ..utils.logging import get_logger
from ..prompts import SUPERVISOR_SYSTEM_PROMPT, SUPERVISOR_ANALYSIS_PROMPT

logger = get_logger("esg_agent.supervisor")

# ESG 관련 키워드 (필터링용)
ESG_KEYWORDS = [
    # E (환경)
    "환경",
    "탄소",
    "기후",
    "친환경",
    "재생에너지",
    "태양광",
    "풍력",
    "전기차",
    "EV",
    "탈탄소",
    "넷제로",
    "온실가스",
    "배출",
    "CBAM",
    "탄소국경",
    "RE100",
    "그린",
    "폐기물",
    "재활용",
    "플라스틱",
    "생물다양성",
    "수자원",
    "오염",
    "에너지",
    "지속가능",
    "ESG",
    "CDP",
    "TCFD",
    "SBTi",
    "녹색",
    # S (사회)
    "사회",
    "인권",
    "노동",
    "안전",
    "보건",
    "다양성",
    "포용",
    "공급망",
    "협력사",
    "지역사회",
    "사회공헌",
    "DEI",
    "근로자",
    "고용",
    # G (지배구조)
    "지배구조",
    "이사회",
    "주주",
    "투명성",
    "공시",
    "윤리",
    "반부패",
    "컴플라이언스",
    "거버넌스",
    "감사",
    "내부통제",
    "리스크관리",
    # 일반 ESG
    "ESG",
    "지속가능경영",
    "사회적책임",
    "CSR",
    "CSV",
    "임팩트",
    "스튜어드십",
]


def _is_esg_related(news: Dict) -> bool:
    """뉴스가 ESG와 관련있는지 확인

    Args:
        news: 뉴스 딕셔너리

    Returns:
        bool: ESG 관련 여부
    """
    title = news.get("title", "").lower()
    summary = news.get("summary", "").lower()
    category = news.get("category", "").lower()

    text = f"{title} {summary} {category}"

    for keyword in ESG_KEYWORDS:
        if keyword.lower() in text:
            return True

    return False


def _filter_esg_news(news_list: List[Dict]) -> List[Dict]:
    """ESG 관련 뉴스만 필터링

    Args:
        news_list: 뉴스 리스트

    Returns:
        List[Dict]: ESG 관련 뉴스만 포함된 리스트
    """
    filtered = [news for news in news_list if _is_esg_related(news)]
    removed_count = len(news_list) - len(filtered)

    if removed_count > 0:
        logger.info(f"ESG 관련 없는 뉴스 {removed_count}건 필터링됨")

    return filtered


def supervise_collection(state: ESGTrendsState) -> Dict:
    """수집 데이터 통합 및 분석

    Args:
        state: 현재 상태

    Returns:
        Dict: 업데이트할 상태 필드
    """
    logger.info("수퍼바이저 분석 시작")

    # 수집된 데이터 가져오기
    weather_data = state.get("weather_data", [])
    physical_risks = state.get("physical_risks", [])
    domestic_news = state.get("domestic_news", [])
    global_news = state.get("global_news", [])

    # ESG 관련 뉴스만 필터링
    domestic_news = _filter_esg_news(domestic_news)
    global_news = _filter_esg_news(global_news)

    # 날씨 요약 생성
    weather_summary = _create_weather_summary(weather_data, physical_risks)

    # ESG 뉴스 통합
    all_news = domestic_news + global_news

    if not all_news:
        logger.warning("분석할 ESG 뉴스가 없습니다")
        return {
            "weather_summary": weather_summary,
            "domestic_news": domestic_news,
            "global_news": global_news,
            "esg_insight": "수집된 ESG 뉴스가 없어 분석을 수행할 수 없습니다.",
            "trending_topics": [],
            "sudden_changes": [],
            "recommendations": [],
            "competitor_analysis": "",
        }

    # LLM을 사용한 ESG 인사이트 분석
    try:
        llm = ChatOpenAI(
            model=Config.OPENAI_MODEL,
            temperature=0.3,
            api_key=Config.OPENAI_API_KEY,
        )

        # 뉴스 요약 텍스트 생성
        news_text = _format_news_for_analysis(all_news)

        # 분석 프롬프트 생성
        analysis_prompt = SUPERVISOR_ANALYSIS_PROMPT.format(
            news_count=len(all_news),
            domestic_count=len(domestic_news),
            global_count=len(global_news),
            news_text=news_text,
        )

        messages = [
            SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
            HumanMessage(content=analysis_prompt),
        ]

        response = llm.invoke(messages)
        analysis_result = response.content

        # 분석 결과 파싱
        parsed = _parse_analysis_result(analysis_result)

        logger.info("ESG 인사이트 분석 완료")

        return {
            "weather_summary": weather_summary,
            "domestic_news": domestic_news,
            "global_news": global_news,
            "esg_insight": parsed.get("insight", analysis_result),
            "trending_topics": parsed.get("trending_topics", []),
            "sudden_changes": parsed.get("sudden_changes", []),
            "recommendations": parsed.get("recommendations", []),
            "competitor_analysis": parsed.get("competitor_analysis", ""),
        }

    except Exception as e:
        logger.error(f"LLM 분석 실패: {e}")
        return {
            "weather_summary": weather_summary,
            "domestic_news": domestic_news,
            "global_news": global_news,
            "esg_insight": f"분석 중 오류 발생: {str(e)}",
            "trending_topics": [],
            "sudden_changes": [],
            "recommendations": [],
            "competitor_analysis": "",
            "errors": [f"수퍼바이저 분석 오류: {str(e)}"],
        }


def _create_weather_summary(weather_data: List[Dict], physical_risks: List[Dict]) -> str:
    """날씨 데이터 요약 생성

    Args:
        weather_data: 날씨 데이터 리스트
        physical_risks: 물리적 리스크 분석 결과

    Returns:
        str: 날씨 요약 텍스트
    """
    if not weather_data:
        return "날씨 데이터를 수집하지 못했습니다."

    summary_parts = []

    for data in weather_data:
        location = data.get("location", "알 수 없음")
        temp = data.get("temperature", "N/A")
        condition = data.get("weather_condition", "")
        humidity = data.get("humidity", "N/A")

        summary_parts.append(f"📍 {location}: {temp}°C, {condition}, 습도 {humidity}%")

    # 물리적 리스크 요약
    high_risks = (
        [r for r in physical_risks if r.get("risk_level") == "높음"] if physical_risks else []
    )
    medium_risks = (
        [r for r in physical_risks if r.get("risk_level") == "보통"] if physical_risks else []
    )

    if physical_risks and (high_risks or medium_risks):
        summary_parts.append("")  # 빈 줄
        if high_risks:
            for risk in high_risks:
                summary_parts.append(f"🔴 {risk.get('risk_type')}: {risk.get('description')}")
        if medium_risks:
            for risk in medium_risks:
                summary_parts.append(f"🟡 {risk.get('risk_type')}: {risk.get('description')}")

    # 종합 리스크 평가 (맨 아래)
    summary_parts.append("")  # 빈 줄
    risk_assessment = _generate_risk_assessment(weather_data, high_risks, medium_risks)
    summary_parts.append(risk_assessment)

    return "\n".join(summary_parts)


def _generate_risk_assessment(
    weather_data: List[Dict], high_risks: List, medium_risks: List
) -> str:
    """물리적 리스크 종합 평가 생성

    Args:
        weather_data: 날씨 데이터 리스트
        high_risks: 고위험 리스크 리스트
        medium_risks: 중간 위험 리스크 리스트

    Returns:
        str: 종합 평가 텍스트
    """
    # 평균 기온 계산
    temps = [d.get("temperature", 0) for d in weather_data if d.get("temperature") is not None]
    avg_temp = sum(temps) / len(temps) if temps else None

    # 리스크 레벨 판단
    if high_risks:
        risk_level = "높은 편"
        risk_emoji = "⚠️"
    elif medium_risks:
        risk_level = "보통"
        risk_emoji = "🔶"
    else:
        risk_level = "낮은 편"
        risk_emoji = "✅"

    # 계절/기온 기반 권고사항
    if avg_temp is not None:
        if avg_temp <= 0:
            season_advice = "겨울철 한파 대비 필요"
        elif avg_temp <= 10:
            season_advice = "쌀쌀한 날씨로 난방 관리 점검 권장"
        elif avg_temp >= 33:
            season_advice = "폭염 주의, 냉방 및 근로자 건강관리 필요"
        elif avg_temp >= 28:
            season_advice = "더운 날씨로 냉방 관리 점검 권장"
        else:
            season_advice = "온화한 날씨로 특별한 조치 불필요"
    else:
        season_advice = "날씨 데이터 확인 필요"

    return f"{risk_emoji} 현재 물리적 기후 리스크는 {risk_level}이며, {season_advice}"


def _format_news_for_analysis(news_list: List[Dict]) -> str:
    """뉴스 리스트를 분석용 텍스트로 변환

    Args:
        news_list: ESG 뉴스 리스트

    Returns:
        str: 분석용 텍스트
    """
    formatted = []

    for i, news in enumerate(news_list[:20], 1):  # 최대 20개
        title = news.get("title", "")
        summary = news.get("summary", "")[:200]  # 요약은 200자로 제한
        source = news.get("source", "")
        region = news.get("region", "")
        category = news.get("category", "")

        formatted.append(
            f"{i}. [{category}] {title}\n"
            f"   출처: {source} | 지역: {region}\n"
            f"   요약: {summary}"
        )

    return "\n\n".join(formatted)


def _parse_analysis_result(result: str) -> Dict:
    """LLM 분석 결과 파싱

    Args:
        result: LLM 응답 텍스트

    Returns:
        Dict: 파싱된 결과
    """
    import re

    parsed = {
        "insight": result,
        "trending_topics": [],
        "sudden_changes": [],
        "recommendations": [],
        "competitor_analysis": "",
    }

    # 섹션별 내용 추출을 위한 정규식
    sections = {
        "insight": r"(?:##?\s*)?(?:주요\s*)?인사이트[^\n]*\n([\s\S]*?)(?=##|$)",
        "trending": r"(?:##?\s*)?트렌드\s*키워드[^\n]*\n([\s\S]*?)(?=##|$)",
        "changes": r"(?:##?\s*)?급변\s*감지[^\n]*\n([\s\S]*?)(?=##|$)",
        "recommendations": r"(?:##?\s*)?권고\s*사항[^\n]*\n([\s\S]*?)(?=##|$)",
        "competitor": r"(?:##?\s*)?경쟁사[/|]?업계\s*동향[^\n]*\n([\s\S]*?)(?=##|$)",
    }

    # 각 섹션 추출
    for section_key, pattern in sections.items():
        match = re.search(pattern, result, re.IGNORECASE)
        if match:
            content = match.group(1).strip()

            if section_key == "insight":
                parsed["insight"] = content if content else result
            elif section_key == "competitor":
                parsed["competitor_analysis"] = content
            else:
                # 리스트 형태의 섹션은 bullet point 추출
                items = []
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("- ") or line.startswith("• ") or line.startswith("* "):
                        items.append(line[2:].strip())
                    elif line.startswith("1.") or line.startswith("2.") or line.startswith("3."):
                        # 숫자 리스트도 처리
                        items.append(re.sub(r"^\d+\.\s*", "", line).strip())

                if section_key == "trending":
                    parsed["trending_topics"] = items
                elif section_key == "changes":
                    parsed["sudden_changes"] = items
                elif section_key == "recommendations":
                    parsed["recommendations"] = items

    # 폴백: 정규식으로 못 찾으면 기존 방식 시도
    if not parsed["trending_topics"] and not parsed["recommendations"]:
        lines = result.split("\n")
        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if "트렌드" in line or "키워드" in line:
                current_section = "trending"
            elif "급변" in line or "변화" in line:
                current_section = "changes"
            elif "권고" in line or "추천" in line:
                current_section = "recommendations"
            elif "경쟁" in line or "벤치마크" in line or "업계" in line:
                current_section = "competitor"
            elif line.startswith("- ") or line.startswith("• ") or line.startswith("* "):
                item = line[2:].strip()
                if current_section == "trending":
                    parsed["trending_topics"].append(item)
                elif current_section == "changes":
                    parsed["sudden_changes"].append(item)
                elif current_section == "recommendations":
                    parsed["recommendations"].append(item)
            elif current_section == "competitor" and not line.startswith("#"):
                # 경쟁사 분석은 리스트가 아닌 텍스트일 수 있음
                if parsed["competitor_analysis"]:
                    parsed["competitor_analysis"] += "\n" + line
                else:
                    parsed["competitor_analysis"] = line

    return parsed
