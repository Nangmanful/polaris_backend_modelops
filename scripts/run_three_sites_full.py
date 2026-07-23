"""
3개 SK 사업장에 대한 완전한 EVAAL 계산
1단계: H (Hazard) 계산 → DB 저장
2단계: E, V, AAL 계산 (DB의 H 사용) → DB 저장

- 대덕 데이터센터
- SK u타워
- 판교 캠퍼스
"""

import os
import logging
from datetime import datetime

# DB 설정 (데이터웨어하우스는 포트 5556)
os.environ['DATABASE_PORT'] = os.getenv('DATABASE_PORT', '5556')
os.environ['DATABASE_NAME'] = os.getenv('DATABASE_NAME', 'datawarehouse')
os.environ['DATABASE_USER'] = os.getenv('DATABASE_USER', 'skala')
os.environ['DATABASE_PASSWORD'] = os.getenv('DATABASE_PASSWORD', 'skala_test_1234')

# 건물 데이터 API 키 설정 (.env에서 로드)
# .env 파일에 다음 변수들이 필요:
# VWORLD_API_KEY=your_key
# PUBLICDATA_API_KEY=your_key
os.environ['DW_HOST'] = os.getenv('DW_HOST', 'localhost')
os.environ['DW_PORT'] = os.getenv('DW_PORT', '5556')
os.environ['DW_NAME'] = os.getenv('DW_NAME', 'datawarehouse')
os.environ['DW_USER'] = os.getenv('DW_USER', 'skala')
os.environ['DW_PASSWORD'] = os.getenv('DW_PASSWORD', 'skala_test_1234')

from modelops.batch.hazard_timeseries_batch import run_hazard_batch
from modelops.batch.probability_timeseries_batch import run_probability_batch
from modelops.batch.evaal_ondemand_api import calculate_evaal_ondemand
import asyncio
import sys

# etl 폴더를 sys.path에 추가
sys.path.insert(0, '/Users/odong-i/Desktop/SKALA/FinalProject/DB_ALL/modelops/etl')
sys.path.insert(0, '/Users/odong-i/Desktop/SKALA/FinalProject/DB_ALL/modelops')

# BuildingDataLoader import
from building_characteristics_loader import BuildingDataLoader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/Users/odong-i/Desktop/SKALA/FinalProject/DB_ALL/modelops/three_sites_full.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 3개 사업장 정보
SITES = [
    {
        'id': 'c6a81920-9aa9-4aa7-9298-f4f1896e7529',
        'name': '대덕 데이터센터',
        'latitude': 36.38012284,
        'longitude': 127.39798889,
        'type': 'data_center'
    },
    {
        'id': '1fd4921d-a9b1-46b0-835f-58b9a27cf24e',
        'name': 'SK u타워',
        'latitude': 37.36633726,
        'longitude': 127.10661717,
        'type': 'office'
    },
    {
        'id': 'c6122327-1eba-47c9-a61e-17fa6c2110cf',
        'name': '판교 캠퍼스',
        'latitude': 37.40588477,
        'longitude': 127.09987781,
        'type': 'office'
    }
]

# 시나리오 및 연도
SCENARIOS = ["SSP126", "SSP245", "SSP370", "SSP585"]
TARGET_YEARS = list(range(2021, 2101))  # 2021-2100년 전체

RISK_TYPES = [
    'extreme_heat',
    'extreme_cold',
    'drought',
    'river_flood',
    'urban_flood',
    'sea_level_rise',
    'typhoon',
    'wildfire',
    'water_stress'
]


def main():
    start_time = datetime.now()

    logger.info("=" * 80)
    logger.info("🏢 3개 SK 사업장 완전 계산 시작")
    logger.info(f"   시작 시간: {start_time.isoformat()}")
    logger.info(f"   사업장: {len(SITES)}개")
    logger.info(f"   시나리오: {SCENARIOS}")
    logger.info(f"   목표 연도: {len(TARGET_YEARS)}개 ({TARGET_YEARS[0]}-{TARGET_YEARS[-1]})")
    logger.info(f"   리스크 타입: {len(RISK_TYPES)}개")
    logger.info("=" * 80)

    # ========== STEP 1: H, PH 계산 ==========
    logger.info("\n")
    logger.info("=" * 80)
    logger.info("🔥 STEP 1: H (Hazard), PH (Probability) 계산 시작")
    logger.info("   → 3개 사업장에 대한 H, PH 계산")
    logger.info("   → hazard_results, probability_results 테이블에 저장")
    logger.info("=" * 80)

    # 3개 사업장 좌표 리스트
    grid_points = [(site['latitude'], site['longitude']) for site in SITES]

    # STEP 1-A: H 계산 (이미 완료됨 - 주석 처리)
    # logger.info("📍 STEP 1-A: H (Hazard) 계산 - 이미 DB에 있음, 건너뜀")
    # try:
    #     h_start = datetime.now()
    #     run_hazard_batch(
    #         grid_points=grid_points,
    #         scenarios=SCENARIOS,
    #         years=[str(y) for y in TARGET_YEARS],
    #         risk_types=RISK_TYPES,
    #         batch_size=100,
    #         max_workers=2
    #     )
    #     h_end = datetime.now()
    #     h_duration = (h_end - h_start).total_seconds()
    #     logger.info(f"✅ STEP 1-A 완료: H 계산 ({h_duration:.1f}초)")
    # except Exception as e:
    #     logger.error(f"❌ STEP 1-A 실패: {e}", exc_info=True)
    #     h_duration = 0

    # STEP 1-B: PH 계산 (실행 필요)
    logger.info("\n📍 STEP 1-B: PH (Probability) 계산 시작")
    logger.info(f"   → 좌표 {len(grid_points)}개 × 시나리오 {len(SCENARIOS)}개 × 년도 {len(TARGET_YEARS)}개 × 리스크 {len(RISK_TYPES)}개")

    try:
        ph_start = datetime.now()

        run_probability_batch(
            grid_points=grid_points,
            scenarios=SCENARIOS,
            years=TARGET_YEARS,  # int 리스트로 전달
            risk_types=RISK_TYPES,
            batch_size=100,
            max_workers=2
        )

        ph_end = datetime.now()
        ph_duration = (ph_end - ph_start).total_seconds()

        logger.info("\n" + "=" * 80)
        logger.info(f"✅ STEP 1-B 완료: PH 계산 ({ph_duration:.1f}초)")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"❌ STEP 1-B 실패: PH 계산 중 오류 - {e}", exc_info=True)
        logger.warning("⚠️  계속 진행")
        ph_duration = 0

    h_duration = ph_duration  # 전체 STEP 1 시간

    # ========== STEP 2: 건물 특성 데이터 적재 ==========
    logger.info("\n")
    logger.info("=" * 80)
    logger.info("🏗️  STEP 2: 건물 특성 데이터 적재 시작")
    logger.info("   → 3개 사업장에 대한 건물 특성 데이터 수집")
    logger.info("   → building_aggregate_cache 테이블에 저장")
    logger.info("   → (실제 서비스: 사용자 주소 입력 트리거)")
    logger.info("=" * 80)

    try:
        building_start = datetime.now()

        # BuildingDataLoader 초기화
        db_url = f"postgresql://{os.environ['DATABASE_USER']}:{os.environ['DATABASE_PASSWORD']}@localhost:{os.environ['DATABASE_PORT']}/{os.environ['DATABASE_NAME']}"
        loader = BuildingDataLoader(db_url=db_url)

        # 3개 사업장에 대해 건물 데이터 적재
        for site in SITES:
            logger.info(f"\n🏢 {site['name']} 건물 데이터 적재 중...")
            logger.info(f"   좌표: ({site['latitude']}, {site['longitude']})")

            try:
                building_data = loader.load_and_cache(
                    lat=site['latitude'],
                    lon=site['longitude'],
                    address=None  # 좌표로 API 조회
                )

                if building_data:
                    meta = building_data.get('meta', {})
                    logger.info(f"   ✅ {site['name']} 건물 데이터 적재 완료")
                    logger.info(f"      주소: {meta.get('road_address', 'N/A')}")
                    logger.info(f"      건물 수: {meta.get('building_count', 0)}개")
                else:
                    logger.warning(f"   ⚠️  {site['name']} 건물 데이터 조회 실패")

            except Exception as e:
                logger.error(f"   ❌ {site['name']} 건물 데이터 적재 실패: {e}")

        building_end = datetime.now()
        building_duration = (building_end - building_start).total_seconds()

        logger.info("\n" + "=" * 80)
        logger.info(f"✅ STEP 2 완료: 건물 특성 데이터 적재 ({building_duration:.1f}초)")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"❌ STEP 2 실패: 건물 특성 데이터 적재 중 오류 - {e}", exc_info=True)
        logger.warning("⚠️  계속 진행 (목데이터 사용)")
        building_duration = 0

    # ========== STEP 3: E, V, AAL 계산 ==========
    logger.info("\n")
    logger.info("=" * 80)
    logger.info("📊 STEP 3: E, V, AAL 계산 시작")
    logger.info("   → DB에서 H, PH 조회")
    logger.info("   → DB에서 건물 데이터 조회")
    logger.info("   → E, V, AAL 계산")
    logger.info("   → exposure_results, vulnerability_results, aal_scaled_results 테이블에 저장")
    logger.info("=" * 80)

    evaal_start = datetime.now()
    total_tasks = len(SITES) * len(SCENARIOS) * len(TARGET_YEARS)
    completed = 0
    failed = 0

    for site in SITES:
        logger.info(f"\n{'='*80}")
        logger.info(f"🏢 사업장: {site['name']}")
        logger.info(f"   좌표: ({site['latitude']}, {site['longitude']})")
        logger.info(f"   타입: {site['type']}")
        logger.info(f"{'='*80}")

        for scenario in SCENARIOS:
            for target_year in TARGET_YEARS:
                task_name = f"{site['name']} - {scenario} - {target_year}"
                logger.info(f"\n▶️  계산 시작: {task_name}")

                try:
                    result = calculate_evaal_ondemand(
                        latitude=site['latitude'],
                        longitude=site['longitude'],
                        scenario=scenario,
                        target_year=target_year,
                        risk_types=RISK_TYPES,
                        save_to_db=True,
                        site_id=site['id']
                    )

                    if result['status'] == 'success':
                        completed += 1
                        summary = result.get('summary', {})
                        save_summary = result.get('save_summary', {})

                        logger.info(f"✅ 계산 완료: {task_name}")
                        logger.info(f"   평균 H: {summary.get('average_hazard', 0):.2f}")
                        logger.info(f"   평균 E: {summary.get('average_exposure', 0):.2f}")
                        logger.info(f"   평균 V: {summary.get('average_vulnerability', 0):.2f}")
                        logger.info(f"   평균 통합 리스크: {summary.get('average_integrated_risk', 0):.2f}")
                        logger.info(f"   DB 저장: E={save_summary.get('exposure_saved', 0)}, "
                                  f"V={save_summary.get('vulnerability_saved', 0)}, "
                                  f"AAL={save_summary.get('aal_saved', 0)}")

                        # 최고 리스크 출력
                        highest = summary.get('highest_integrated_risk', {})
                        if highest:
                            logger.info(f"   ⚠️  최고 리스크: {highest.get('risk_type')} "
                                      f"({highest.get('score', 0):.2f}, {highest.get('level')})")
                    else:
                        failed += 1
                        logger.error(f"❌ 계산 실패: {task_name}")
                        logger.error(f"   에러: {result.get('error', 'Unknown error')}")

                except Exception as e:
                    failed += 1
                    logger.error(f"❌ 계산 예외: {task_name}")
                    logger.error(f"   에러: {str(e)}", exc_info=True)

                # 진행률 출력
                if (completed + failed) % 10 == 0:
                    progress = ((completed + failed) / total_tasks) * 100
                    logger.info(f"\n📊 진행률: {progress:.1f}% ({completed + failed}/{total_tasks})")

    evaal_end = datetime.now()
    evaal_duration = (evaal_end - evaal_start).total_seconds()

    # 최종 요약
    end_time = datetime.now()
    total_duration = (end_time - start_time).total_seconds()

    logger.info("\n" + "=" * 80)
    logger.info("✅ 전체 계산 완료")
    logger.info(f"   종료 시간: {end_time.isoformat()}")
    logger.info(f"   총 소요 시간: {total_duration:.1f}초 ({total_duration/60:.1f}분)")
    logger.info(f"   ")
    logger.info(f"   STEP 1 (H, PH 계산): {h_duration:.1f}초")
    logger.info(f"   STEP 2 (건물 데이터 적재): {building_duration:.1f}초")
    logger.info(f"   STEP 3 (E, V, AAL 계산): {evaal_duration:.1f}초")
    logger.info(f"   ")
    logger.info(f"   전체 작업: {total_tasks}개")
    logger.info(f"   성공: {completed}개")
    logger.info(f"   실패: {failed}개")
    logger.info(f"   성공률: {(completed/total_tasks*100):.1f}%")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
