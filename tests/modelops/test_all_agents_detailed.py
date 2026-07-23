#!/usr/bin/env python3
"""
모든 Probability Agent DB 연동 상세 테스트 및 보고서 생성
"""
import sys
from pathlib import Path

# 레포 루트를 import 경로에 추가 (직접 실행 지원)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# 테스트 좌표 (서울 강남구)
TEST_LAT = 37.5172
TEST_LON = 127.0473
SSP_SCENARIO = 'SSP245'

def test_extreme_heat():
    """폭염 에이전트 테스트"""
    from modelops.agents.probability_calculate.extreme_heat_probability_agent import ExtremeHeatProbabilityAgent
    from modelops.data_loaders.climate_data_loader import ClimateDataLoader

    agent = ExtremeHeatProbabilityAgent()
    loader = ClimateDataLoader(scenario=SSP_SCENARIO)

    # 실제 DB 데이터 fetch
    ts_data = loader.get_extreme_heat_timeseries(TEST_LAT, TEST_LON, 2021, 2050)

    return {
        'agent': 'ExtremeHeatProbabilityAgent',
        'risk_type': '폭염 (Extreme Heat)',
        'variables': ['WSDI (온난일 지속 지수)', 'TXX (최고기온 극값)'],
        'db_data': {
            'years': f"{ts_data.get('years', [])[:3]}...{ts_data.get('years', [])[-3:]}",
            'wsdi_sample': ts_data.get('wsdi', [])[:5],
            'txx_sample': ts_data.get('txx', [])[:5],
            'data_count': len(ts_data.get('wsdi', [])),
        },
        'result': agent.calculate(TEST_LAT, TEST_LON, SSP_SCENARIO)
    }

def test_extreme_cold():
    """한파 에이전트 테스트"""
    from modelops.agents.probability_calculate.extreme_cold_probability_agent import ExtremeColdProbabilityAgent
    from modelops.data_loaders.climate_data_loader import ClimateDataLoader

    agent = ExtremeColdProbabilityAgent()
    loader = ClimateDataLoader(scenario=SSP_SCENARIO)

    ts_data = loader.get_extreme_cold_timeseries(TEST_LAT, TEST_LON, 2021, 2050)

    return {
        'agent': 'ExtremeColdProbabilityAgent',
        'risk_type': '한파 (Extreme Cold)',
        'variables': ['CSDI (한랭일 지속 지수)', 'TNN (최저기온 극값)'],
        'db_data': {
            'years': f"{ts_data.get('years', [])[:3]}...{ts_data.get('years', [])[-3:]}",
            'csdi_sample': ts_data.get('csdi', [])[:5],
            'tnn_sample': ts_data.get('tnn', [])[:5],
            'data_count': len(ts_data.get('csdi', [])),
        },
        'result': agent.calculate(TEST_LAT, TEST_LON, SSP_SCENARIO)
    }

def test_river_flood():
    """하천홍수 에이전트 테스트"""
    from modelops.agents.probability_calculate.river_flood_probability_agent import RiverFloodProbabilityAgent
    from modelops.data_loaders.climate_data_loader import ClimateDataLoader

    agent = RiverFloodProbabilityAgent()
    loader = ClimateDataLoader(scenario=SSP_SCENARIO)

    ts_data = loader.get_flood_timeseries(TEST_LAT, TEST_LON, 2021, 2050)

    return {
        'agent': 'RiverFloodProbabilityAgent',
        'risk_type': '하천홍수 (River Flood)',
        'variables': ['RX1DAY (1일 최대 강수량)', 'RX5DAY (5일 최대 강수량)'],
        'db_data': {
            'years': f"{ts_data.get('years', [])[:3]}...{ts_data.get('years', [])[-3:]}",
            'rx1day_sample': ts_data.get('rx1day', [])[:5],
            'rx5day_sample': ts_data.get('rx5day', [])[:5],
            'data_count': len(ts_data.get('rx1day', [])),
        },
        'result': agent.calculate(TEST_LAT, TEST_LON, SSP_SCENARIO)
    }

def test_urban_flood():
    """도시홍수 에이전트 테스트"""
    from modelops.agents.probability_calculate.urban_flood_probability_agent import UrbanFloodProbabilityAgent
    from modelops.data_loaders.climate_data_loader import ClimateDataLoader

    agent = UrbanFloodProbabilityAgent()
    loader = ClimateDataLoader(scenario=SSP_SCENARIO)

    ts_data = loader.get_flood_timeseries(TEST_LAT, TEST_LON, 2021, 2050)

    return {
        'agent': 'UrbanFloodProbabilityAgent',
        'risk_type': '도시홍수 (Urban Flood)',
        'variables': ['RAIN80 (80mm 이상 호우일수)'],
        'db_data': {
            'years': f"{ts_data.get('years', [])[:3]}...{ts_data.get('years', [])[-3:]}",
            'rain80_sample': ts_data.get('rain80', [])[:5],
            'data_count': len(ts_data.get('rain80', [])),
        },
        'result': agent.calculate(TEST_LAT, TEST_LON, SSP_SCENARIO)
    }

def test_drought():
    """가뭄 에이전트 테스트"""
    from modelops.agents.probability_calculate.drought_probability_agent import DroughtProbabilityAgent
    from modelops.data_loaders.climate_data_loader import ClimateDataLoader

    agent = DroughtProbabilityAgent()
    loader = ClimateDataLoader(scenario=SSP_SCENARIO)

    ts_data = loader.get_drought_timeseries(TEST_LAT, TEST_LON, 2021, 2050)

    return {
        'agent': 'DroughtProbabilityAgent',
        'risk_type': '가뭄 (Drought)',
        'variables': ['SPEI12 (12개월 표준화 강수증발산 지수)', 'CDD (연속 무강수일)'],
        'db_data': {
            'years': f"{ts_data.get('years', [])[:3]}...{ts_data.get('years', [])[-3:]}",
            'spei12_sample': ts_data.get('spei12', [])[:5],
            'cdd_sample': ts_data.get('cdd', [])[:5],
            'data_count': len(ts_data.get('spei12', [])),
        },
        'result': agent.calculate(TEST_LAT, TEST_LON, SSP_SCENARIO)
    }

def test_wildfire():
    """산불 에이전트 테스트"""
    from modelops.agents.probability_calculate.wildfire_probability_agent import WildfireProbabilityAgent
    from modelops.data_loaders.climate_data_loader import ClimateDataLoader

    agent = WildfireProbabilityAgent()
    loader = ClimateDataLoader(scenario=SSP_SCENARIO)

    ts_data = loader.get_wildfire_timeseries(TEST_LAT, TEST_LON, 2021, 2050)

    return {
        'agent': 'WildfireProbabilityAgent',
        'risk_type': '산불 (Wildfire)',
        'variables': ['FWI (화재기상지수)', 'CDD (연속 무강수일)'],
        'db_data': {
            'years': f"{ts_data.get('years', [])[:3]}...{ts_data.get('years', [])[-3:]}",
            'fwi_sample': ts_data.get('fwi', [])[:5],
            'cdd_sample': ts_data.get('cdd', [])[:5],
            'data_count': len(ts_data.get('fwi', [])),
        },
        'result': agent.calculate(TEST_LAT, TEST_LON, SSP_SCENARIO)
    }

def test_typhoon():
    """태풍 에이전트 테스트"""
    from modelops.agents.probability_calculate.typhoon_probability_agent import TyphoonProbabilityAgent
    from modelops.data_loaders.climate_data_loader import ClimateDataLoader

    agent = TyphoonProbabilityAgent()
    loader = ClimateDataLoader(scenario=SSP_SCENARIO)

    ts_data = loader.get_typhoon_data(TEST_LAT, TEST_LON)

    return {
        'agent': 'TyphoonProbabilityAgent',
        'risk_type': '태풍 (Typhoon)',
        'variables': ['S_tc (태풍 노출 강도)', 'typhoon_frequency (태풍 빈도)'],
        'db_data': {
            'typhoon_frequency': ts_data.get('typhoon_frequency', 'N/A'),
            'max_wind_speed_ms': ts_data.get('max_wind_speed_ms', 'N/A'),
            'distance_to_coast_m': ts_data.get('distance_to_coast_m', 'N/A'),
            'data_source': ts_data.get('data_source', 'N/A'),
        },
        'result': agent.calculate(TEST_LAT, TEST_LON, SSP_SCENARIO)
    }

def test_sea_level_rise():
    """해수면상승 에이전트 테스트"""
    from modelops.agents.probability_calculate.sea_level_rise_probability_agent import SeaLevelRiseProbabilityAgent
    from modelops.data_loaders.climate_data_loader import ClimateDataLoader

    agent = SeaLevelRiseProbabilityAgent()
    loader = ClimateDataLoader(scenario=SSP_SCENARIO)

    ts_data = loader.get_sea_level_rise_timeseries(TEST_LAT, TEST_LON, 2021, 2050)

    return {
        'agent': 'SeaLevelRiseProbabilityAgent',
        'risk_type': '해수면상승 (Sea Level Rise)',
        'variables': ['ZOS (해수면 높이, cm)', 'DEM (지형 고도)'],
        'db_data': {
            'years': f"{ts_data.get('years', [])[:3]}...{ts_data.get('years', [])[-3:]}",
            'slr_sample': ts_data.get('slr', [])[:5],
            'data_count': len(ts_data.get('slr', [])),
        },
        'result': agent.calculate(TEST_LAT, TEST_LON, SSP_SCENARIO)
    }

def test_water_stress():
    """물스트레스 에이전트 테스트"""
    from modelops.agents.probability_calculate.water_stress_probability_agent import WaterStressProbabilityAgent
    from modelops.data_loaders.climate_data_loader import ClimateDataLoader

    agent = WaterStressProbabilityAgent()
    loader = ClimateDataLoader(scenario=SSP_SCENARIO)

    ts_data = loader.get_water_stress_data(TEST_LAT, TEST_LON)

    return {
        'agent': 'WaterStressProbabilityAgent',
        'risk_type': '물스트레스 (Water Stress)',
        'variables': ['WSI (물스트레스 지수)', 'withdrawal (용수이용량)'],
        'db_data': {
            'annual_rainfall_mm': ts_data.get('annual_rainfall_mm', 'N/A'),
            'cdd': ts_data.get('cdd', 'N/A'),
            'data_source': ts_data.get('data_source', 'N/A'),
        },
        'result': agent.calculate(TEST_LAT, TEST_LON, SSP_SCENARIO)
    }

def main():
    print("\n" + "="*80)
    print("  확률 에이전트 DB 연동 상세 테스트 및 보고서")
    print(f"  테스트 좌표: ({TEST_LAT}, {TEST_LON})  시나리오: {SSP_SCENARIO}")
    print("="*80)

    test_functions = [
        test_extreme_heat,
        test_extreme_cold,
        test_river_flood,
        test_urban_flood,
        test_drought,
        test_wildfire,
        test_typhoon,
        test_sea_level_rise,
        test_water_stress,
    ]

    results = []

    for test_func in test_functions:
        print(f"\n테스트 중: {test_func.__name__}...")
        try:
            result = test_func()
            result['status'] = 'SUCCESS'
            results.append(result)
            print(f"  ✅ 완료 - AAL: {result['result'].get('aal', 'N/A'):.6f}")
        except Exception as e:
            results.append({
                'agent': test_func.__name__,
                'status': 'FAILED',
                'error': str(e)
            })
            print(f"  ❌ 실패: {e}")

    # 상세 보고서 출력
    print("\n\n")
    print("="*80)
    print("                         상세 테스트 보고서")
    print("="*80)

    for r in results:
        if r['status'] == 'SUCCESS':
            print(f"\n{'─'*80}")
            print(f"[{r['risk_type']}]")
            print(f"에이전트: {r['agent']}")
            print(f"사용 변수: {', '.join(r['variables'])}")
            print(f"\nDB에서 가져온 데이터:")
            for key, value in r['db_data'].items():
                print(f"  - {key}: {value}")
            print(f"\n계산 결과:")
            print(f"  - AAL: {r['result'].get('aal', 'N/A'):.6f}")
            print(f"  - Bin 확률: {[f'{p:.4f}' for p in r['result'].get('probabilities', [])]}")
        else:
            print(f"\n{'─'*80}")
            print(f"[FAILED] {r['agent']}")
            print(f"  오류: {r.get('error', 'Unknown')}")

    # 요약 테이블
    print("\n\n")
    print("="*80)
    print("                           요약 테이블")
    print("="*80)
    print(f"\n{'에이전트':<35} {'상태':<10} {'AAL':>15} {'데이터수':>10}")
    print("-"*75)

    success_count = 0
    for r in results:
        if r['status'] == 'SUCCESS':
            success_count += 1
            aal = r['result'].get('aal', 0)
            data_count = r['db_data'].get('data_count', 'N/A')
            print(f"{r['agent']:<35} {'✅ 성공':<10} {aal:>15.6f} {str(data_count):>10}")
        else:
            print(f"{r.get('agent', 'Unknown'):<35} {'❌ 실패':<10} {'N/A':>15} {'N/A':>10}")

    print("-"*75)
    print(f"\n총 {len(results)}개 에이전트 중 {success_count}개 성공 ({success_count/len(results)*100:.0f}%)")

if __name__ == "__main__":
    main()
