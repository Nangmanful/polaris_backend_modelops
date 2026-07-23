#!/usr/bin/env python3
"""
모든 Probability Agent DB 연동 테스트
"""

import sys
from pathlib import Path

# 레포 루트를 import 경로에 추가 (직접 실행 지원)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# 테스트 좌표 (서울 강남구)
TEST_LAT = 37.5172
TEST_LON = 127.0473
SSP_SCENARIO = "SSP245"


def test_agent(agent_class, agent_name):
    """단일 에이전트 테스트"""
    print(f"\n{'='*60}")
    print(f"테스트: {agent_name}")
    print("=" * 60)

    try:
        agent = agent_class()
        result = agent.calculate(TEST_LAT, TEST_LON, SSP_SCENARIO)

        print(f"✅ 성공!")
        print(f"   - AAL: {result.get('aal', 'N/A'):.6f}")
        print(f"   - Risk Type: {result.get('risk_type', 'N/A')}")

        probabilities = result.get("probabilities", [])
        if probabilities:
            print(f"   - Bin 확률: {[f'{p:.4f}' for p in probabilities]}")

        return True, result.get("aal", 0)
    except Exception as e:
        print(f"❌ 실패: {e}")
        import traceback

        traceback.print_exc()
        return False, 0


def main():
    print("\n" + "=" * 70)
    print("  확률 에이전트 DB 연동 종합 테스트")
    print("  좌표: ({}, {})  시나리오: {}".format(TEST_LAT, TEST_LON, SSP_SCENARIO))
    print("=" * 70)

    results = {}

    # 1. ExtremeHeatProbabilityAgent
    from modelops.agents.probability_calculate.extreme_heat_probability_agent import (
        ExtremeHeatProbabilityAgent,
    )

    success, aal = test_agent(ExtremeHeatProbabilityAgent, "ExtremeHeatProbabilityAgent (폭염)")
    results["extreme_heat"] = {"success": success, "aal": aal}

    # 2. ExtremeColdProbabilityAgent
    from modelops.agents.probability_calculate.extreme_cold_probability_agent import (
        ExtremeColdProbabilityAgent,
    )

    success, aal = test_agent(ExtremeColdProbabilityAgent, "ExtremeColdProbabilityAgent (한파)")
    results["extreme_cold"] = {"success": success, "aal": aal}

    # 3. RiverFloodProbabilityAgent
    from modelops.agents.probability_calculate.river_flood_probability_agent import (
        RiverFloodProbabilityAgent,
    )

    success, aal = test_agent(RiverFloodProbabilityAgent, "RiverFloodProbabilityAgent (하천홍수)")
    results["river_flood"] = {"success": success, "aal": aal}

    # 4. UrbanFloodProbabilityAgent
    from modelops.agents.probability_calculate.urban_flood_probability_agent import (
        UrbanFloodProbabilityAgent,
    )

    success, aal = test_agent(UrbanFloodProbabilityAgent, "UrbanFloodProbabilityAgent (도시홍수)")
    results["urban_flood"] = {"success": success, "aal": aal}

    # 5. DroughtProbabilityAgent
    from modelops.agents.probability_calculate.drought_probability_agent import (
        DroughtProbabilityAgent,
    )

    success, aal = test_agent(DroughtProbabilityAgent, "DroughtProbabilityAgent (가뭄)")
    results["drought"] = {"success": success, "aal": aal}

    # 6. WildfireProbabilityAgent
    from modelops.agents.probability_calculate.wildfire_probability_agent import (
        WildfireProbabilityAgent,
    )

    success, aal = test_agent(WildfireProbabilityAgent, "WildfireProbabilityAgent (산불)")
    results["wildfire"] = {"success": success, "aal": aal}

    # 7. TyphoonProbabilityAgent
    from modelops.agents.probability_calculate.typhoon_probability_agent import (
        TyphoonProbabilityAgent,
    )

    success, aal = test_agent(TyphoonProbabilityAgent, "TyphoonProbabilityAgent (태풍)")
    results["typhoon"] = {"success": success, "aal": aal}

    # 8. SeaLevelRiseProbabilityAgent
    from modelops.agents.probability_calculate.sea_level_rise_probability_agent import (
        SeaLevelRiseProbabilityAgent,
    )

    success, aal = test_agent(
        SeaLevelRiseProbabilityAgent, "SeaLevelRiseProbabilityAgent (해수면상승)"
    )
    results["sea_level_rise"] = {"success": success, "aal": aal}

    # 9. WaterStressProbabilityAgent
    from modelops.agents.probability_calculate.water_stress_probability_agent import (
        WaterStressProbabilityAgent,
    )

    success, aal = test_agent(
        WaterStressProbabilityAgent, "WaterStressProbabilityAgent (물스트레스)"
    )
    results["water_stress"] = {"success": success, "aal": aal}

    # 결과 요약
    print("\n" + "=" * 70)
    print("  테스트 결과 요약")
    print("=" * 70)

    success_count = sum(1 for r in results.values() if r["success"])
    total_count = len(results)

    print(f"\n{'에이전트':<30} {'상태':<10} {'AAL':>12}")
    print("-" * 55)

    for risk_type, result in results.items():
        status = "✅ 성공" if result["success"] else "❌ 실패"
        aal_str = f"{result['aal']:.6f}" if result["success"] else "N/A"
        print(f"{risk_type:<30} {status:<10} {aal_str:>12}")

    print("-" * 55)
    print(
        f"\n총 {total_count}개 에이전트 중 {success_count}개 성공 ({success_count/total_count*100:.0f}%)"
    )

    if success_count == total_count:
        print("\n🎉 모든 에이전트가 DB 연동 테스트를 통과했습니다!")
    else:
        print(f"\n⚠️  {total_count - success_count}개 에이전트에서 문제가 발생했습니다.")


if __name__ == "__main__":
    main()
