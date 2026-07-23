"""
IntegratedRiskAgent 완전 통합 테스트
H × E × V 계산 검증
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from modelops.agents.risk_assessment.integrated_risk_agent import IntegratedRiskAgent


def test_integrated_risk_agent():
    """
    IntegratedRiskAgent 전체 파이프라인 테스트

    테스트 위치: 서울 강남구 (37.5, 127.0)
    검증 항목:
    1. HazardDataCollector를 통한 데이터 수집
    2. 9개 리스크별 H, E, V 계산
    3. H × E × V 통합 리스크 점수 계산
    4. Top 3 리스크 식별
    """
    print("=" * 80)
    print("IntegratedRiskAgent 완전 통합 테스트")
    print("=" * 80)

    # 테스트 좌표
    latitude = 37.5
    longitude = 127.0

    # IntegratedRiskAgent 초기화
    print(f"\n1. IntegratedRiskAgent 초기화")
    print(f"   - 시나리오: SSP245")
    print(f"   - 분석 연도: 2030")

    agent = IntegratedRiskAgent(
        scenario="SSP245", target_year=2030, database_connection=None  # DB 없이 테스트
    )

    print(f"   [OK] Agent 초기화 완료")
    print(f"   - HazardDataCollector: {agent.hazard_data_collector is not None}")
    print(f"   - Hazard Agents: {len(agent.hazard_agents)}개")
    print(f"   - Risk Types: {len(agent.risk_types)}개")

    # 통합 리스크 계산
    print(f"\n2. 통합 리스크 계산 시작")
    print(f"   - 위치: ({latitude}, {longitude})")
    print("-" * 80)

    results = agent.calculate_all_risks(latitude=latitude, longitude=longitude)

    # 결과 검증
    print(f"\n3. 결과 검증")
    print("-" * 80)

    # 3.1 메타데이터 확인
    metadata = results["metadata"]
    print(f"\n[메타데이터]")
    print(f"   - 계산 시간: {metadata['calculation_time']:.2f}초")
    print(f"   - 시나리오: {metadata['scenario']}")
    print(f"   - 분석 연도: {metadata['target_year']}")
    print(f"   - 처리된 리스크 수: {metadata['total_risks_processed']}")

    # 3.2 Hazard 결과 확인
    print(f"\n[Hazard 점수]")
    for risk_type, h_result in results["hazard"].items():
        h_score = h_result.get("hazard_score", 0.0)
        h_level = h_result.get("hazard_level", "N/A")
        print(f"   - {risk_type:20s}: {h_score:6.2f} ({h_level})")

    # 3.3 Exposure 결과 확인
    print(f"\n[Exposure 점수]")
    for risk_type, e_result in results["exposure"].items():
        e_score = e_result.get("exposure_score", 0.0)
        print(f"   - {risk_type:20s}: {e_score:6.2f}")

    # 3.4 Vulnerability 결과 확인
    print(f"\n[Vulnerability 점수]")
    for risk_type, v_result in results["vulnerability"].items():
        v_score = v_result.get("vulnerability_score", 0.0)
        v_level = v_result.get("vulnerability_level", "N/A")
        print(f"   - {risk_type:20s}: {v_score:6.2f} ({v_level})")

    # 3.5 통합 리스크 (H×E×V) 결과 확인
    print(f"\n[통합 리스크 (H × E × V)]")
    print(f"{'Risk Type':<20} {'H':>8} {'E':>8} {'V':>8} {'Risk':>10} {'Level':<12} {'Formula'}")
    print("-" * 100)

    for risk_type, integrated_risk in results["integrated_risk"].items():
        h_score = integrated_risk.get("h_score", 0.0)
        e_score = integrated_risk.get("e_score", 0.0)
        v_score = integrated_risk.get("v_score", 0.0)
        risk_score = integrated_risk.get("integrated_risk_score", 0.0)
        risk_level = integrated_risk.get("risk_level", "N/A")
        formula = integrated_risk.get("formula", "")

        print(
            f"{risk_type:<20} {h_score:>8.2f} {e_score:>8.2f} {v_score:>8.2f} {risk_score:>10.2f} {risk_level:<12} {formula}"
        )

    # 3.6 요약 통계
    summary = results["summary"]
    print(f"\n[요약 통계]")
    print(f"   - 평균 Hazard:         {summary['average_hazard']:.2f}")
    print(f"   - 평균 Exposure:       {summary['average_exposure']:.2f}")
    print(f"   - 평균 Vulnerability:  {summary['average_vulnerability']:.2f}")
    print(f"   - 평균 통합 리스크:    {summary['average_integrated_risk']:.2f}")

    # 3.7 Top 3 리스크
    print(f"\n[Top 3 리스크 (통합 리스크 점수 기준)]")
    for top_risk in summary["top_3_risks"]:
        rank = top_risk["rank"]
        risk_type = top_risk["risk_type"]
        score = top_risk["integrated_risk_score"]
        level = top_risk["risk_level"]
        print(f"   {rank}. {risk_type:20s}: {score:6.2f} ({level})")

    # 3.8 최고 리스크
    highest = summary["highest_integrated_risk"]
    if highest:
        print(f"\n[최고 통합 리스크]")
        print(f"   - 리스크 유형: {highest['risk_type']}")
        print(f"   - 통합 점수:   {highest['integrated_risk_score']:.2f}")
        print(f"   - 위험 등급:   {highest['risk_level']}")

    # 4. 검증
    print(f"\n4. 검증 결과")
    print("=" * 80)

    assertions = []

    # 4.1 모든 리스크가 계산되었는지 확인
    assert len(results["hazard"]) == 9, "Hazard 결과가 9개가 아님"
    assertions.append("[OK] 9개 Hazard 점수 계산 완료")

    assert len(results["exposure"]) == 9, "Exposure 결과가 9개가 아님"
    assertions.append("[OK] 9개 Exposure 점수 계산 완료")

    assert len(results["vulnerability"]) == 9, "Vulnerability 결과가 9개가 아님"
    assertions.append("[OK] 9개 Vulnerability 점수 계산 완료")

    assert len(results["integrated_risk"]) == 9, "통합 리스크 결과가 9개가 아님"
    assertions.append("[OK] 9개 통합 리스크 (H×E×V) 계산 완료")

    # 4.2 통합 리스크 점수 범위 확인 (0-100)
    for risk_type, integrated_risk in results["integrated_risk"].items():
        risk_score = integrated_risk.get("integrated_risk_score", 0.0)
        assert 0 <= risk_score <= 100, f"{risk_type} 리스크 점수가 범위 밖: {risk_score}"
    assertions.append("[OK] 모든 통합 리스크 점수가 0-100 범위 내")

    # 4.3 H×E×V 계산 검증
    for risk_type, integrated_risk in results["integrated_risk"].items():
        h_score = integrated_risk.get("h_score", 0.0)
        e_score = integrated_risk.get("e_score", 0.0)
        v_score = integrated_risk.get("v_score", 0.0)
        risk_score = integrated_risk.get("integrated_risk_score", 0.0)

        # 수동 계산
        expected_risk = (h_score * e_score * v_score) / 10000.0
        assert (
            abs(risk_score - expected_risk) < 0.01
        ), f"{risk_type}: 계산 오류 (expected={expected_risk:.2f}, got={risk_score:.2f})"
    assertions.append("[OK] H×E×V 계산 공식 검증 완료")

    # 4.4 Top 3 리스크 검증
    assert len(summary["top_3_risks"]) == 3, "Top 3 리스크가 3개가 아님"
    assertions.append("[OK] Top 3 리스크 식별 완료")

    # 4.5 결과 출력
    for assertion in assertions:
        print(f"   {assertion}")

    print(f"\n{'='*80}")
    print(f"[SUCCESS] 모든 테스트 통과!")
    print(f"{'='*80}")

    return results


if __name__ == "__main__":
    try:
        results = test_integrated_risk_agent()
        print(f"\n[SUCCESS] 테스트 성공!")
    except Exception as e:
        print(f"\n[FAILED] 테스트 실패: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
