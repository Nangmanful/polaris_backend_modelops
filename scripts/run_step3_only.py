"""
STEP 3만 실행: E, V, AAL 계산
(H, PH, 건물 데이터는 이미 DB에 적재되어 있음)
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# 레포 루트를 import 경로에 추가
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from modelops.batch.evaal_ondemand_api import calculate_evaal_ondemand  # noqa: E402

# CLI 인자: DB 접속 정보는 환경변수(.env)로, 로그 파일 경로만 인자로 받는다
parser = argparse.ArgumentParser(
    description="STEP 3만 실행: E, V, AAL 계산. "
    "DB 접속 정보는 .env 또는 DATABASE_* 환경변수로 설정한다."
)
parser.add_argument(
    "--log-file",
    default="step3_only.log",
    help="로그 파일 경로 (기본값: ./step3_only.log)",
)
args = parser.parse_args()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(args.log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# ========== 설정 ==========
SITES = [
    {
        'id': '12c452cd-a34d-497c-8348-01c816618553',  # 대덕 데이터센터
        'name': '대덕 데이터센터',
        'latitude': 36.38012284,
        'longitude': 127.39798889,
        'type': 'data_center'
    },
    {
        'id': '1fd4921d-a9b1-46b0-835f-58b9a27cf24e',  # SK u타워
        'name': 'SK u타워',
        'latitude': 37.36633726,
        'longitude': 127.10661717,
        'type': 'office'
    },
    {
        'id': 'c6122327-1eba-47c9-a61e-17fa6c2110cf',  # 판교 캠퍼스
        'name': '판교 캠퍼스',
        'latitude': 37.40588477,
        'longitude': 127.09987781,
        'type': 'campus'
    }
]

SCENARIOS = ['SSP126', 'SSP245', 'SSP370', 'SSP585']
TARGET_YEARS = list(range(2021, 2101))  # 2021~2100 (80년)
RISK_TYPES = [
    'extreme_heat', 'extreme_cold', 'drought',
    'river_flood', 'urban_flood', 'sea_level_rise',
    'typhoon', 'wildfire', 'water_stress'
]

if __name__ == '__main__':
    start_time = datetime.now()
    logger.info("=" * 80)
    logger.info("📊 STEP 3: E, V, AAL 계산 시작")
    logger.info(f"   시작 시간: {start_time.isoformat()}")
    logger.info("   → DB에서 H, PH 조회")
    logger.info("   → DB에서 건물 데이터 조회 (building_aggregate_cache)")
    logger.info("   → E, V, AAL 계산")
    logger.info("   → exposure_results, vulnerability_results 테이블에 저장")
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
                        logger.info(f"   평균 E: {summary.get('average_exposure', 0):.2f}")
                        logger.info(f"   평균 V: {summary.get('average_vulnerability', 0):.2f}")
                        logger.info(f"   DB 저장: E={save_summary.get('exposure_saved', 0)}, "
                                  f"V={save_summary.get('vulnerability_saved', 0)}, "
                                  f"AAL={save_summary.get('aal_saved', 0)}")
                    else:
                        failed += 1
                        logger.error(f"❌ 계산 실패: {task_name}")
                        logger.error(f"   에러: {result.get('error', 'Unknown error')}")

                except Exception as e:
                    failed += 1
                    logger.error(f"❌ 계산 예외: {task_name}")
                    logger.error(f"   에러: {str(e)}", exc_info=True)

                # 진행률 출력
                progress = ((completed + failed) / total_tasks) * 100
                print(f"\r📊 진행률: {progress:.1f}% ({completed + failed}/{total_tasks})", end='', flush=True)

    evaal_end = datetime.now()
    evaal_duration = (evaal_end - evaal_start).total_seconds()

    # 최종 요약
    end_time = datetime.now()
    total_duration = (end_time - start_time).total_seconds()

    print()  # 줄바꿈
    logger.info("\n" + "=" * 80)
    logger.info("✅ 전체 계산 완료")
    logger.info(f"   종료 시간: {end_time.isoformat()}")
    logger.info(f"   총 소요 시간: {total_duration:.1f}초 ({total_duration/60:.1f}분)")
    logger.info(f"   STEP 3 (E, V, AAL 계산): {evaal_duration:.1f}초")
    logger.info(f"   전체 작업: {total_tasks}개")
    logger.info(f"   성공: {completed}개")
    logger.info(f"   실패: {failed}개")
    logger.info("=" * 80)
