"""
==================================================================
[모듈명] graph.py
LangGraph 워크플로우 정의

[모듈 목표]
1) ESG Trends Agent 워크플로우 그래프 구성
2) 병렬 수집 → 분석 → 품질체크 → 리포트 → 배포 파이프라인
==================================================================
"""

from langgraph.graph import StateGraph, END

from .state import ESGTrendsState, create_initial_state
from .collectors.weather import collect_weather
from .collectors.esg_domestic import collect_domestic_news
from .collectors.esg_global import collect_global_news
from .agents.orchestrator import orchestrate, should_continue
from .agents.supervisor import supervise_collection
from .agents.quality_checker import check_quality, should_regenerate
from .agents.report import generate_report
from .agents.distribution import distribute_report
from .utils.logging import get_logger

logger = get_logger("esg_agent.graph")


def create_esg_trends_graph() -> StateGraph:
    """ESG Trends Agent 워크플로우 그래프 생성

    워크플로우 구조:
    1. 병렬 수집 (날씨, 국내 ESG, 글로벌 ESG)
    2. 오케스트레이션 (수집 결과 통합)
    3. 수퍼바이저 분석 (LLM 기반 인사이트)
    4. 품질 체크
    5. 리포트 생성
    6. 배포 (Slack)

    Returns:
        StateGraph: 컴파일된 워크플로우 그래프
    """
    logger.info("ESG Trends 워크플로우 그래프 생성")

    # StateGraph 초기화
    workflow = StateGraph(ESGTrendsState)

    # =========================================================================
    # 노드 추가
    # =========================================================================

    # 수집 노드들
    workflow.add_node("collect_weather", collect_weather)
    workflow.add_node("collect_domestic", collect_domestic_news)
    workflow.add_node("collect_global", collect_global_news)

    # 처리 노드들
    workflow.add_node("orchestrate", orchestrate)
    workflow.add_node("supervise", supervise_collection)
    workflow.add_node("quality_check", check_quality)
    workflow.add_node("generate_report", generate_report)
    workflow.add_node("distribute", distribute_report)

    # =========================================================================
    # 엣지 정의
    # =========================================================================

    # 시작점: 병렬 수집 시작
    workflow.set_entry_point("collect_weather")

    # 병렬 수집: 날씨 → 국내 → 글로벌 → 오케스트레이션
    # (LangGraph에서는 순차 실행, 실제 병렬화는 별도 구현 필요)
    workflow.add_edge("collect_weather", "collect_domestic")
    workflow.add_edge("collect_domestic", "collect_global")
    workflow.add_edge("collect_global", "orchestrate")

    # 오케스트레이션 후 분기
    workflow.add_conditional_edges(
        "orchestrate",
        should_continue,
        {
            "continue": "supervise",
            "end": END,
        },
    )

    # 수퍼바이저 → 품질 체크
    workflow.add_edge("supervise", "quality_check")

    # 품질 체크 후 분기
    workflow.add_conditional_edges(
        "quality_check",
        should_regenerate,
        {
            "regenerate": "supervise",  # 재분석
            "pass": "generate_report",  # 리포트 생성
        },
    )

    # 리포트 생성 → 배포
    workflow.add_edge("generate_report", "distribute")

    # 배포 → 종료
    workflow.add_edge("distribute", END)

    logger.info("워크플로우 그래프 구성 완료")

    return workflow


def compile_graph():
    """워크플로우 그래프 컴파일

    Returns:
        CompiledGraph: 실행 가능한 컴파일된 그래프
    """
    workflow = create_esg_trends_graph()
    return workflow.compile()


def run_esg_trends_workflow(initial_state: ESGTrendsState = None) -> ESGTrendsState:
    """ESG Trends 워크플로우 실행

    Args:
        initial_state: 초기 상태 (없으면 기본값 사용)

    Returns:
        ESGTrendsState: 최종 상태
    """
    logger.info("=" * 60)
    logger.info("ESG Trends 워크플로우 시작")
    logger.info("=" * 60)

    # 초기 상태 설정
    if initial_state is None:
        initial_state = create_initial_state()

    # 그래프 컴파일
    graph = compile_graph()

    # 워크플로우 실행
    try:
        final_state = graph.invoke(initial_state)

        logger.info("=" * 60)
        logger.info("ESG Trends 워크플로우 완료")
        logger.info(f"품질 점수: {final_state.get('quality_score', 0):.2f}")
        logger.info(f"에러 수: {len(final_state.get('errors', []))}")
        logger.info("=" * 60)

        return final_state

    except Exception as e:
        logger.error(f"워크플로우 실행 중 오류: {e}")
        raise


# =============================================================================
# 병렬 수집 버전 (선택적)
# =============================================================================


def create_parallel_collection_graph() -> StateGraph:
    """병렬 수집이 가능한 워크플로우 그래프

    ThreadPoolExecutor를 사용하여 수집 단계를 병렬로 실행

    Returns:
        StateGraph: 컴파일된 워크플로우 그래프
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def parallel_collect(state: ESGTrendsState) -> dict:
        """병렬 수집 실행"""
        results = {
            "weather_data": [],
            "physical_risks": [],
            "domestic_news": [],
            "global_news": [],
            "collection_status": {},
            "errors": [],
        }

        collectors = [
            ("weather", collect_weather),
            ("domestic", collect_domestic_news),
            ("global", collect_global_news),
        ]

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(collector, state): name for name, collector in collectors}

            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()

                    # 결과 병합
                    for key in ["weather_data", "domestic_news", "global_news", "errors"]:
                        if key in result:
                            results[key].extend(result[key])

                    if "physical_risks" in result:
                        results["physical_risks"] = result["physical_risks"]

                    if "collection_status" in result:
                        results["collection_status"].update(result["collection_status"])

                    logger.info(f"{name} 수집 완료")

                except Exception as e:
                    logger.error(f"{name} 수집 실패: {e}")
                    results["errors"].append(f"{name} 수집 실패: {str(e)}")
                    results["collection_status"][name] = "failed"

        return results

    # StateGraph 초기화
    workflow = StateGraph(ESGTrendsState)

    # 노드 추가
    workflow.add_node("parallel_collect", parallel_collect)
    workflow.add_node("orchestrate", orchestrate)
    workflow.add_node("supervise", supervise_collection)
    workflow.add_node("quality_check", check_quality)
    workflow.add_node("generate_report", generate_report)
    workflow.add_node("distribute", distribute_report)

    # 엣지 정의
    workflow.set_entry_point("parallel_collect")
    workflow.add_edge("parallel_collect", "orchestrate")

    workflow.add_conditional_edges(
        "orchestrate",
        should_continue,
        {
            "continue": "supervise",
            "end": END,
        },
    )

    workflow.add_edge("supervise", "quality_check")

    workflow.add_conditional_edges(
        "quality_check",
        should_regenerate,
        {
            "regenerate": "supervise",
            "pass": "generate_report",
        },
    )

    workflow.add_edge("generate_report", "distribute")
    workflow.add_edge("distribute", END)

    return workflow


def run_parallel_workflow(initial_state: ESGTrendsState = None) -> ESGTrendsState:
    """병렬 수집 워크플로우 실행

    Args:
        initial_state: 초기 상태 (없으면 기본값 사용)

    Returns:
        ESGTrendsState: 최종 상태
    """
    logger.info("=" * 60)
    logger.info("ESG Trends 워크플로우 시작 (병렬 수집 모드)")
    logger.info("=" * 60)

    if initial_state is None:
        initial_state = create_initial_state()

    graph = create_parallel_collection_graph().compile()

    try:
        final_state = graph.invoke(initial_state)

        logger.info("=" * 60)
        logger.info("ESG Trends 워크플로우 완료")
        logger.info(f"품질 점수: {final_state.get('quality_score', 0):.2f}")
        logger.info("=" * 60)

        return final_state

    except Exception as e:
        logger.error(f"워크플로우 실행 중 오류: {e}")
        raise
