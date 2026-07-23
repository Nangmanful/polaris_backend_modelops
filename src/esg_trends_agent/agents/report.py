"""
==================================================================
[모듈명] agents/report.py
리포트 생성 에이전트

[모듈 목표]
1) 최종 ESG 트렌드 리포트 생성
2) 마크다운 형식 리포트 출력
==================================================================
"""

from typing import Dict
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from ..state import ESGTrendsState
from ..utils.config import Config
from ..utils.logging import get_logger
from ..prompts import REPORT_GENERATOR_PROMPT

logger = get_logger("esg_agent.report")


def generate_report(state: ESGTrendsState) -> Dict:
    """최종 리포트 생성

    Args:
        state: 현재 상태

    Returns:
        Dict: 업데이트할 상태 필드
    """
    logger.info("리포트 생성 시작")

    try:
        llm = ChatOpenAI(
            model=Config.OPENAI_MODEL,
            temperature=0.5,
            api_key=Config.OPENAI_API_KEY,
        )

        # 리포트용 컨텍스트 준비
        context = _prepare_report_context(state)

        messages = [
            SystemMessage(content=REPORT_GENERATOR_PROMPT),
            HumanMessage(content=context),
        ]

        response = llm.invoke(messages)
        report_content = response.content

        # 리포트 헤더 추가
        today = datetime.now().strftime("%Y년 %m월 %d일")

        # LLM 응답 정제
        report_content = report_content.strip()

        # ``` 코드 블록 제거
        if report_content.startswith("```"):
            lines = report_content.split("\n")
            report_content = "\n".join(lines[1:])
        if report_content.endswith("```"):
            report_content = report_content[:-3].strip()

        # 중복 헤더 제거 (LLM이 자체 헤더를 추가한 경우)
        lines = report_content.split("\n")
        cleaned_lines = []
        skip_until_section = False

        for line in lines:
            line_lower = line.lower().strip()
            # ESG 리포트 제목/헤더 패턴 감지
            if any(
                keyword in line_lower
                for keyword in ["esg 트렌드", "esg 일간", "esg트렌드", "발행일", "품질 점수"]
            ):
                if (
                    line.startswith("#")
                    or "리포트" in line_lower
                    or "발행일" in line_lower
                    or "품질" in line_lower
                ):
                    skip_until_section = True
                    continue
            # --- 구분선도 제거 (헤더 바로 다음에 오는 경우)
            if skip_until_section and line.strip() == "---":
                continue
            # 실제 내용 시작 (1. 오늘의 핵심 포인트 등)
            if skip_until_section and (
                line.strip().startswith("1.")
                or line.strip().startswith("## 1.")
                or line.strip().startswith("**1.")
            ):
                skip_until_section = False
            if not skip_until_section:
                cleaned_lines.append(line)

        report_content = "\n".join(cleaned_lines).strip()

        final_report = f"""# 🌿 ESG 트렌드 일간 리포트

**발행일**: {today}

{report_content}


> 오늘도 ESG 경영으로 지속가능한 미래를 만들어 갑시다! 🌱

*이 리포트는 ESG Trends Agent에 의해 자동 생성되었습니다.*

**[참고]**
1. 공공데이터 포털 기상청_단기예보 ((구)_동네예보) 조회서비스
2. 공공데이터포털 대한무역투자진흥공사_ESG 동향뉴스
3. ESG Economy 뉴스
"""

        logger.info("리포트 생성 완료")

        return {
            "final_report": final_report,
        }

    except Exception as e:
        logger.error(f"리포트 생성 실패: {e}")

        # 폴백: 기본 템플릿 리포트
        fallback_report = _generate_fallback_report(state)

        return {
            "final_report": fallback_report,
            "errors": [f"LLM 리포트 생성 실패: {str(e)}"],
        }


def _prepare_report_context(state: ESGTrendsState) -> str:
    """리포트 생성용 컨텍스트 준비

    Args:
        state: 현재 상태

    Returns:
        str: 컨텍스트 텍스트
    """
    context_parts = []

    # 데이터 추출
    weather_summary = state.get("weather_summary", "")
    esg_insight = state.get("esg_insight", "")
    trending_topics = state.get("trending_topics", [])
    recommendations = state.get("recommendations", [])
    competitor_analysis = state.get("competitor_analysis", "")
    domestic_news = state.get("domestic_news", [])[:10]
    global_news = state.get("global_news", [])[:10]

    # 1. 오늘의 핵심 포인트
    context_parts.append(
        "## 1. 오늘의 핵심 포인트\n(수집된 데이터를 바탕으로 오늘의 ESG 핵심 포인트 5개를 요약해주세요)"
    )

    # 2. 사업장 위치 지역 날씨 및 물리적 리스크 현황
    if weather_summary:
        # 리스크 평가 부분을 인용으로 분리
        weather_lines = weather_summary.split("\n")
        weather_main = []
        risk_assessment = ""
        for line in weather_lines:
            if (
                "현재 물리적 기후 리스크는" in line
                or line.startswith("⚠️")
                or line.startswith("✅")
                or line.startswith("🔶")
            ):
                if "현재 물리적 기후 리스크는" in line:
                    risk_assessment = line
            else:
                weather_main.append(line)

        weather_section = "\n".join(weather_main).strip()
        if risk_assessment:
            weather_section += f"\n\n> {risk_assessment}"
        context_parts.append(
            f"## 2. 사업장 위치 지역 날씨 및 물리적 리스크 현황\n{weather_section}"
        )
    else:
        context_parts.append(
            "## 2. 사업장 위치 지역 날씨 및 물리적 리스크 현황\n날씨 데이터를 수집하지 못했습니다."
        )

    # 3. ESG 트렌드 하이라이트
    if trending_topics:
        topics_str = "\n".join([f"• {topic}" for topic in trending_topics])
        context_parts.append(f"## 3. ESG 트렌드 하이라이트\n{topics_str}")
    else:
        context_parts.append(
            "## 3. ESG 트렌드 하이라이트\n(수집된 뉴스를 바탕으로 주요 ESG 트렌드를 분석해주세요)"
        )

    # 4. 국내 동향 및 주요 뉴스 (통합)
    news_section = "## 4. 국내 동향 및 주요 뉴스\n"
    if domestic_news:
        for n in domestic_news:
            title = n.get("title", "")
            url = n.get("url", "")
            summary = n.get("summary", "")[:150] or ""
            if summary:
                news_section += f"• {title}\n"
            else:
                news_section += f"• {title}\n"
            if url:
                news_section += f"  {url}\n"
    else:
        news_section += "수집된 국내 뉴스가 없습니다.\n"
    context_parts.append(news_section)

    # 5. 글로벌 동향
    global_section = "## 5. 글로벌 동향\n"
    if global_news:
        for n in global_news:
            title = n.get("title", "")
            region = n.get("region", "")
            summary = n.get("summary", "")[:150] or ""
            if region:
                global_section += f"• [{region}] {title}\n"
            else:
                global_section += f"• {title}\n"
    else:
        global_section += "수집된 글로벌 뉴스가 없습니다.\n"
    context_parts.append(global_section)

    # 6. ESG 관련 최근 권고사항
    if recommendations:
        recs_str = "\n".join([f"{i}. {rec}" for i, rec in enumerate(recommendations, 1)])
        context_parts.append(f"## 6. ESG 관련 최근 권고사항\n{recs_str}")
    else:
        context_parts.append(
            "## 6. ESG 관련 최근 권고사항\n(수집된 데이터를 바탕으로 기업 ESG 담당자를 위한 권고사항을 작성해주세요)"
        )

    # 7. 경쟁사/업계 동향
    if competitor_analysis:
        context_parts.append(f"## 7. 경쟁사/업계 동향\n{competitor_analysis}")
    else:
        context_parts.append("## 7. 경쟁사/업계 동향\n(경쟁사 및 업계 동향을 분석해주세요)")

    # 8. ESG 인사이트 분석
    if esg_insight:
        context_parts.append(f"## 8. ESG 인사이트 분석\n{esg_insight}")
    else:
        context_parts.append(
            "## 8. ESG 인사이트 분석\n(수집된 뉴스를 종합하여 ESG 인사이트를 작성해주세요)"
        )

    return "\n\n\n".join(context_parts)


def _generate_fallback_report(state: ESGTrendsState) -> str:
    """폴백 리포트 생성

    Args:
        state: 현재 상태

    Returns:
        str: 기본 템플릿 리포트
    """
    today = datetime.now().strftime("%Y년 %m월 %d일")

    # 데이터 추출
    weather_summary = state.get("weather_summary", "")
    esg_insight = state.get("esg_insight", "")
    trending_topics = state.get("trending_topics", [])
    recommendations = state.get("recommendations", [])
    competitor_analysis = state.get("competitor_analysis", "")
    domestic_news = state.get("domestic_news", [])
    global_news = state.get("global_news", [])

    report = f"""# 🌿 ESG 트렌드 일간 리포트

**발행일**: {today}

**1. 오늘의 핵심 포인트**

"""
    # 핵심 포인트 (esg_insight에서 추출하거나 기본 메시지)
    if esg_insight:
        lines = esg_insight.split("\n")[:5]
        for line in lines:
            if line.strip():
                report += f"• {line.strip()}\n"
    else:
        report += "• 데이터 분석 중입니다.\n"

    # 2. 날씨 섹션
    report += "\n\n**2. 사업장 위치 지역 날씨 및 물리적 리스크 현황**\n\n"
    if weather_summary:
        # 리스크 평가 부분을 인용으로 분리
        weather_lines = weather_summary.split("\n")
        weather_main = []
        risk_assessment = ""
        for line in weather_lines:
            if "현재 물리적 기후 리스크는" in line:
                risk_assessment = line
            elif line.strip():
                weather_main.append(line)

        report += "\n".join(weather_main).strip() + "\n"
        if risk_assessment:
            report += f"\n> {risk_assessment}\n"
    else:
        report += "날씨 데이터를 수집하지 못했습니다.\n"

    # 3. ESG 트렌드 하이라이트
    report += "\n\n**3. ESG 트렌드 하이라이트**\n\n"
    if trending_topics:
        for topic in trending_topics:
            report += f"• {topic}\n"
    else:
        report += "• 트렌드 분석 중입니다.\n"

    # 4. 국내 동향 및 주요 뉴스
    report += "\n\n**4. 국내 동향 및 주요 뉴스**\n\n"
    if domestic_news:
        for news in domestic_news[:10]:
            title = news.get("title", "")
            url = news.get("url", "")
            report += f"• {title}\n"
            if url:
                report += f"  {url}\n"
    else:
        report += "수집된 국내 뉴스가 없습니다.\n"

    # 5. 글로벌 동향
    report += "\n\n**5. 글로벌 동향**\n\n"
    if global_news:
        for news in global_news[:10]:
            title = news.get("title", "")
            region = news.get("region", "")
            if region:
                report += f"• [{region}] {title}\n"
            else:
                report += f"• {title}\n"
    else:
        report += "수집된 글로벌 뉴스가 없습니다.\n"

    # 6. ESG 관련 최근 권고사항
    report += "\n\n**6. ESG 관련 최근 권고사항**\n\n"
    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            report += f"{i}. {rec}\n"
    else:
        report += "1. 권고사항 분석 중입니다.\n"

    # 7. 경쟁사/업계 동향
    report += "\n\n**7. 경쟁사/업계 동향**\n\n"
    if competitor_analysis:
        report += f"{competitor_analysis}\n"
    else:
        report += "경쟁사/업계 동향 분석 중입니다.\n"

    # 8. ESG 인사이트 분석
    report += "\n\n**8. ESG 인사이트 분석**\n\n"
    if esg_insight:
        report += f"{esg_insight}\n"
    else:
        report += "분석 결과가 없습니다.\n"

    # 마무리
    report += """

> 오늘도 ESG 경영으로 지속가능한 미래를 만들어 갑시다! 🌱

*이 리포트는 ESG Trends Agent에 의해 자동 생성되었습니다.*

**[참고]**
1. 공공데이터 포털 기상청_단기예보 ((구)_동네예보) 조회서비스
2. 공공데이터포털 대한무역투자진흥공사_ESG 동향뉴스
3. ESG Economy 뉴스
"""

    return report
