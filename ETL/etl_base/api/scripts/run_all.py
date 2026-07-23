"""
SKALA Physical Risk AI System - API ETL 전체 실행

Physical Risk 분석에 필요한 10개 API 테이블 ETL
- api_buildings: 건축물대장 (Vulnerability)
- api_wamis, api_wamis_stations: 용수이용량/관측소 (Water Stress)
- api_river_info: 하천정보 (River Flood)
- api_emergency_messages: 재난문자 (재난이력)
- api_typhoon_info/track/td/besttrack: 태풍 데이터 (AAL)
- api_disaster_yearbook: 재해연보

최종 수정일: 2025-12-03
버전: v01
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# 상위 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from utils import setup_logging, get_db_connection, get_table_count


def run_all_etl(sample_limit: int = None):
    """
    모든 API ETL 스크립트 실행

    Args:
        sample_limit: 샘플 제한 (테스트용)
    """
    logger = setup_logging("run_all_api_etl")
    start_time = datetime.now()

    logger.info("=" * 80)
    logger.info("SKALA Physical Risk API ETL 전체 실행")
    logger.info(f"시작 시간: {start_time}")
    if sample_limit:
        logger.info(f"샘플 제한: {sample_limit}건")
    logger.info("=" * 80)

    # ETL 스크립트 목록 (실행 순서)
    etl_scripts = [
        ("01_load_river_info", "load_river_info", "하천정보"),
        ("02_load_emergency_messages", "load_emergency_messages", "긴급재난문자"),
        ("03_load_vworld_geocode", "load_vworld_geocode", "VWorld 역지오코딩"),
        ("04_load_typhoon", "load_typhoon_data", "태풍 정보"),
        ("05_load_wamis", "load_wamis_data", "WAMIS 용수이용량"),
        ("06_load_buildings", "load_building_data", "건축물대장"),
        ("15_load_disaster_yearbook", "load_disaster_yearbook", "재해연보"),
        ("16_load_typhoon_besttrack", "load_typhoon_besttrack", "태풍 베스트트랙"),
    ]

    results = []

    for script_name, func_name, description in etl_scripts:
        logger.info(f"\n{'='*60}")
        logger.info(f"[{len(results)+1}/{len(etl_scripts)}] {description} ETL 시작")
        logger.info(f"{'='*60}")

        script_start = datetime.now()

        try:
            # 동적 import
            module = __import__(script_name)

            # 메인 함수 실행
            if hasattr(module, func_name):
                func = getattr(module, func_name)
                func(sample_limit=sample_limit)
            else:
                raise AttributeError(f"함수 {func_name} 없음")

            script_end = datetime.now()
            duration = (script_end - script_start).total_seconds()

            results.append(
                {
                    "script": script_name,
                    "description": description,
                    "status": "SUCCESS",
                    "duration": duration,
                }
            )

            logger.info(f"{description} ETL 완료 (소요시간: {duration:.1f}초)")

        except Exception as e:
            script_end = datetime.now()
            duration = (script_end - script_start).total_seconds()

            results.append(
                {
                    "script": script_name,
                    "description": description,
                    "status": "FAILED",
                    "error": str(e),
                    "duration": duration,
                }
            )

            logger.error(f"{description} ETL 실패: {e}")

    # 결과 요약
    end_time = datetime.now()
    total_duration = (end_time - start_time).total_seconds()

    logger.info("\n" + "=" * 80)
    logger.info("ETL 실행 결과 요약")
    logger.info("=" * 80)

    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    fail_count = sum(1 for r in results if r["status"] == "FAILED")

    logger.info(f"총 스크립트: {len(results)}개")
    logger.info(f"성공: {success_count}개")
    logger.info(f"실패: {fail_count}개")
    logger.info(f"총 소요시간: {total_duration:.1f}초")

    logger.info("\n상세 결과:")
    for r in results:
        status_icon = "O" if r["status"] == "SUCCESS" else "X"
        logger.info(f"  [{status_icon}] {r['description']}: {r['status']} ({r['duration']:.1f}초)")
        if r["status"] == "FAILED":
            logger.info(f"      Error: {r.get('error', 'Unknown')}")

    # DB 테이블 상태 확인
    logger.info("\n" + "=" * 80)
    logger.info("Physical Risk API 테이블 상태 (11개)")
    logger.info("=" * 80)

    try:
        conn = get_db_connection()

        # Physical Risk에 필요한 11개 테이블
        api_tables = [
            ("api_buildings", "건축물대장 (Vulnerability)"),
            ("api_vworld_geocode", "VWorld 역지오코딩"),
            ("api_wamis", "WAMIS 용수이용량 (Water Stress)"),
            ("api_wamis_stations", "WAMIS 관측소"),
            ("api_river_info", "하천정보 (River Flood)"),
            ("api_emergency_messages", "긴급재난문자"),
            ("api_typhoon_info", "태풍 기본정보 (AAL)"),
            ("api_typhoon_track", "태풍 경로"),
            ("api_typhoon_td", "열대저압부"),
            ("api_typhoon_besttrack", "태풍 베스트트랙"),
            ("api_disaster_yearbook", "재해연보"),
        ]

        total_records = 0
        for table, desc in api_tables:
            try:
                count = get_table_count(conn, table)
                total_records += count
                logger.info(f"  {table}: {count:,}건 - {desc}")
            except:
                logger.info(f"  {table}: (조회 실패) - {desc}")

        conn.close()
        logger.info(f"\n총 레코드: {total_records:,}건")

    except Exception as e:
        logger.error(f"DB 상태 확인 실패: {e}")

    logger.info("\n" + "=" * 80)
    logger.info("Physical Risk API ETL 전체 실행 완료")
    logger.info("=" * 80)

    return results


if __name__ == "__main__":
    sample_limit = int(os.getenv("SAMPLE_LIMIT", 0)) or None
    run_all_etl(sample_limit=sample_limit)
