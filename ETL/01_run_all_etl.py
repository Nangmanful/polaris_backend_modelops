#!/usr/bin/env python3
"""
SKALA Physical Risk AI System - 기본 전체 ETL 실행

Local + API 데이터를 한번에 전체 적재
제외: load_climate_grid, load_vworld_geocode, load_buildings (02, 03번으로 분리)

사용법:
    python 01_run_all_etl.py              # 전체 실행
    python 01_run_all_etl.py --local-only # Local만 실행
    python 01_run_all_etl.py --api-only   # API만 실행
    python 01_run_all_etl.py --only 1,2,3 # 특정 단계만
    python 01_run_all_etl.py --skip 5,6   # 특정 단계 건너뛰기
    python 01_run_all_etl.py --list       # 단계 목록 출력

참고: SKIP_THRESHOLDS에 정의된 테이블은 임계값 이상이면 자동 스킵

최종 수정일: 2025-12-12
버전: v01
"""

import sys
import argparse
import importlib.util
from pathlib import Path
from datetime import datetime

# 현재 디렉토리를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from utils import setup_logging, get_db_connection, get_row_count

# =============================================================================
# ETL 스크립트 정의
# =============================================================================

# 기존 스크립트 경로 (etl_base = 레거시 ETL 디렉토리)
LOCAL_SCRIPTS_DIR = Path(__file__).parent / "etl_base" / "local" / "scripts"
API_SCRIPTS_DIR = Path(__file__).parent / "etl_base" / "api" / "scripts"

# 테이블별 스킵 임계값 (이 수 이상이면 스킵, 0이면 항상 실행)
SKIP_THRESHOLDS = {
    "location_admin": 5000,  # 행정구역: 5000건 이상이면 스킵
    "weather_stations": 1000,  # 기상관측소
    "grid_station_mappings": 200000,  # 그리드-관측소 매핑
    "raw_landcover": 50,  # 토지피복
    "raw_dem": 100000,  # DEM (4개 지역 기준)
    "raw_drought": 1000,  # 가뭄 지수
    "sea_level_data": 100,  # 해수면 상승
    "water_stress_rankings": 100,  # 수자원 스트레스
    "api_river_info": 100,  # 하천정보
    "api_emergency_messages": 100,  # 재난문자
    "api_typhoon_info": 10,  # 태풍 정보
}

# Local 스크립트 (제외: 08_load_climate_grid)
LOCAL_SCRIPTS = [
    ("01_load_admin_regions", "load_admin_regions", "행정구역 경계", "location_admin"),
    ("02_load_weather_stations", "load_weather_stations", "기상관측소", "weather_stations"),
    (
        "03_load_grid_station_mappings",
        "load_grid_station_mappings",
        "그리드-관측소 매핑",
        "grid_station_mappings",
    ),
    (
        "04_load_population",
        "load_population",
        "인구 전망",
        "none",
    ),  # UPDATE 작업이므로 스킵 체크 제외
    ("05_load_landcover", "load_landcover", "토지피복", "raw_landcover"),
    ("06_load_dem", "load_dem", "수치표고모델(DEM)", "raw_dem"),
    ("07_load_drought", "load_drought", "가뭄 지수", "raw_drought"),
    # ("08_load_climate_grid", "load_climate_grid", "기후 그리드", "location_grid"),  # 제외 -> 02번
    ("09_load_sea_level", "load_sea_level", "해수면 상승", "sea_level_data"),
    ("10_load_water_stress", "load_water_stress", "수자원 스트레스", "water_stress_rankings"),
    ("11_load_site_data", "load_site_data", "사이트 추가 데이터", "site_additional_data"),
]

# API 스크립트 (제외: 03_load_vworld_geocode, 06_load_buildings)
API_SCRIPTS = [
    ("01_load_river_info", "load_river_info", "하천정보", "api_river_info"),
    ("02_load_emergency_messages", "load_emergency_messages", "재난문자", "api_emergency_messages"),
    # ("03_load_vworld_geocode", "load_vworld_geocode", "역지오코딩", "api_vworld_geocode"),  # 제외 -> 02번
    ("04_load_typhoon", "load_typhoon_data", "태풍 정보", "api_typhoon_info"),
    ("05_load_wamis", "load_wamis_data", "WAMIS 용수이용량", "api_wamis"),
    # ("06_load_buildings", "load_building_data", "건축물대장", "building_aggregate_cache"),  # 제외 -> 03번
    ("15_load_disaster_yearbook", "load_disaster_yearbook", "재해연보", "api_disaster_yearbook"),
    (
        "16_load_typhoon_besttrack",
        "load_typhoon_besttrack",
        "태풍 베스트트랙",
        "api_typhoon_besttrack",
    ),
    (
        "17_load_sgis_population",
        "load_sgis_population",
        "SGIS 인구통계",
        "none",
    ),  # UPDATE이므로 스킵 체크 제외
]


def load_module_from_path(module_name: str, file_path: Path):
    """파일 경로에서 모듈 로드"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"모듈을 로드할 수 없습니다: {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_etl_script(
    script_name: str, func_name: str, description: str, scripts_dir: Path, logger
) -> bool:
    """
    개별 ETL 스크립트 실행

    Args:
        script_name: 스크립트 파일명 (확장자 제외)
        func_name: 실행할 함수명
        description: 설명
        scripts_dir: 스크립트 디렉토리
        logger: 로거

    Returns:
        성공 여부
    """
    script_path = scripts_dir / f"{script_name}.py"

    if not script_path.exists():
        logger.error(f"스크립트 없음: {script_path}")
        return False

    try:
        logger.info(f"실행 중: {description}")
        logger.info(f"   파일: {script_path.name}")

        # 스크립트 디렉토리를 path에 추가 (utils import를 위해)
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        # 모듈 로드
        module = load_module_from_path(script_name, script_path)

        # 함수 실행
        if hasattr(module, func_name):
            func = getattr(module, func_name)
            func()
            logger.info(f"   완료: {description}")
            return True
        else:
            logger.error(f"   함수 없음: {func_name}")
            return False

    except Exception as e:
        logger.error(f"   실패: {e}")
        import traceback

        traceback.print_exc()
        return False


def print_etl_list():
    """ETL 단계 목록 출력"""
    print("\n" + "=" * 70)
    print("SKALA ETL 단계 목록")
    print("=" * 70)

    print("\n[Local 데이터] - 파일 기반")
    print("-" * 70)
    for i, (script, func, desc, table) in enumerate(LOCAL_SCRIPTS, 1):
        print(f"  L{i:02d}. {desc:25} -> {table}")

    print("\n[API 데이터] - 실시간 호출")
    print("-" * 70)
    for i, (script, func, desc, table) in enumerate(API_SCRIPTS, 1):
        print(f"  A{i:02d}. {desc:25} -> {table}")

    print("\n[제외된 스크립트] - 별도 실행 필요")
    print("-" * 70)
    print("  - load_climate_grid    -> 02_load_climate_geocode.py")
    print("  - load_vworld_geocode  -> 02_load_climate_geocode.py")
    print("  - load_buildings       -> 03_load_buildings.py")
    print("=" * 70 + "\n")


def run_all_etl(
    local_only: bool = False, api_only: bool = False, only_steps: set = None, skip_steps: set = None
):
    """
    전체 ETL 실행

    Args:
        local_only: Local 스크립트만 실행
        api_only: API 스크립트만 실행
        only_steps: 실행할 단계만 (L1, L2, A1, A2 형식)
        skip_steps: 건너뛸 단계
    """
    logger = setup_logging("run_all_etl")
    start_time = datetime.now()

    logger.info("=" * 70)
    logger.info("SKALA Physical Risk - 전체 ETL 실행")
    logger.info(f"시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    if local_only:
        logger.info("모드: Local만 실행")
    elif api_only:
        logger.info("모드: API만 실행")
    else:
        logger.info("모드: 전체 실행")
    if SKIP_THRESHOLDS:
        logger.info(f"스킵 조건: {list(SKIP_THRESHOLDS.keys())}")
    logger.info("=" * 70)

    # DB 연결 테스트
    try:
        conn = get_db_connection()
        logger.info("데이터베이스 연결 확인 완료")
    except Exception as e:
        logger.error(f"데이터베이스 연결 실패: {e}")
        sys.exit(1)

    results = []

    # Local 스크립트 실행
    if not api_only:
        logger.info("\n" + "=" * 50)
        logger.info("[Local 데이터 적재]")
        logger.info("=" * 50)

        for i, (script, func, desc, table) in enumerate(LOCAL_SCRIPTS, 1):
            step_id = f"L{i}"

            # 건너뛰기 체크
            if skip_steps and step_id in skip_steps:
                logger.info(f"\n[{step_id}] {desc} - 건너뜀")
                continue

            if only_steps and step_id not in only_steps:
                logger.info(f"\n[{step_id}] {desc} - 건너뜀")
                continue

            # 테이블별 스킵 체크: SKIP_THRESHOLDS에 정의된 테이블만 체크
            threshold = SKIP_THRESHOLDS.get(table, 0)
            if threshold > 0:
                current_count = get_row_count(conn, table)
                conn.commit()  # 락 해제를 위해 커밋
                if current_count >= threshold:
                    logger.info(f"\n[{step_id}] {desc} - 스킵 (이미 {current_count:,}건 존재)")
                    results.append(
                        {
                            "step": step_id,
                            "name": desc,
                            "type": "Local",
                            "table": table,
                            "status": "SKIPPED",
                            "duration": 0,
                        }
                    )
                    continue

            # 스크립트 실행 전 커넥션 커밋 (락 해제)
            conn.commit()
            logger.info(f"\n[{step_id}] {'-' * 50}")
            script_start = datetime.now()

            success = run_etl_script(script, func, desc, LOCAL_SCRIPTS_DIR, logger)

            duration = (datetime.now() - script_start).total_seconds()
            results.append(
                {
                    "step": step_id,
                    "name": desc,
                    "type": "Local",
                    "table": table,
                    "status": "SUCCESS" if success else "FAILED",
                    "duration": duration,
                }
            )

    # API 스크립트 실행
    if not local_only:
        logger.info("\n" + "=" * 50)
        logger.info("[API 데이터 적재]")
        logger.info("=" * 50)

        for i, (script, func, desc, table) in enumerate(API_SCRIPTS, 1):
            step_id = f"A{i}"

            # 건너뛰기 체크
            if skip_steps and step_id in skip_steps:
                logger.info(f"\n[{step_id}] {desc} - 건너뜀")
                continue

            if only_steps and step_id not in only_steps:
                logger.info(f"\n[{step_id}] {desc} - 건너뜀")
                continue

            # 테이블별 스킵 체크
            threshold = SKIP_THRESHOLDS.get(table, 0)
            if threshold > 0:
                current_count = get_row_count(conn, table)
                conn.commit()  # 락 해제를 위해 커밋
                if current_count >= threshold:
                    logger.info(f"\n[{step_id}] {desc} - 스킵 (이미 {current_count:,}건 존재)")
                    results.append(
                        {
                            "step": step_id,
                            "name": desc,
                            "type": "API",
                            "table": table,
                            "status": "SKIPPED",
                            "duration": 0,
                        }
                    )
                    continue

            # 스크립트 실행 전 커넥션 커밋 (락 해제)
            conn.commit()
            logger.info(f"\n[{step_id}] {'-' * 50}")
            script_start = datetime.now()

            success = run_etl_script(script, func, desc, API_SCRIPTS_DIR, logger)

            duration = (datetime.now() - script_start).total_seconds()
            results.append(
                {
                    "step": step_id,
                    "name": desc,
                    "type": "API",
                    "table": table,
                    "status": "SUCCESS" if success else "FAILED",
                    "duration": duration,
                }
            )

    conn.close()

    # 결과 요약
    end_time = datetime.now()
    total_duration = (end_time - start_time).total_seconds()

    logger.info("\n" + "=" * 70)
    logger.info("ETL 실행 결과 요약")
    logger.info("=" * 70)

    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    fail_count = sum(1 for r in results if r["status"] == "FAILED")
    skip_count = sum(1 for r in results if r["status"] == "SKIPPED")

    logger.info(f"총 스크립트: {len(results)}개")
    logger.info(f"성공: {success_count}개")
    logger.info(f"실패: {fail_count}개")
    if skip_count > 0:
        logger.info(f"스킵: {skip_count}개 (이미 데이터 존재)")
    logger.info(f"총 소요시간: {total_duration:.1f}초")

    logger.info("\n상세 결과:")
    for r in results:
        if r["status"] == "SUCCESS":
            icon = "O"
        elif r["status"] == "SKIPPED":
            icon = "-"
        else:
            icon = "X"
        logger.info(f"  [{icon}] {r['step']} {r['name']:25} ({r['duration']:.1f}s)")

    # 테이블별 레코드 수 확인
    logger.info("\n" + "=" * 70)
    logger.info("테이블별 레코드 수")
    logger.info("=" * 70)

    try:
        conn = get_db_connection()
        tables_to_check = list(set([r["table"] for r in results]))
        tables_to_check.sort()

        for table in tables_to_check:
            count = get_row_count(conn, table)
            logger.info(f"  {table:35} {count:>10,}건")

        conn.close()
    except Exception as e:
        logger.error(f"테이블 확인 실패: {e}")

    logger.info("\n" + "=" * 70)
    logger.info("ETL 완료")
    logger.info("=" * 70)

    return 0 if fail_count == 0 else 1


def parse_steps(step_str: str) -> set:
    """
    단계 문자열 파싱 (예: "L1,L2,A1" -> {"L1", "L2", "A1"})
    또는 "1,2,3" -> {"L1", "L2", "L3"} (Local 기본)
    """
    steps = set()
    for s in step_str.split(","):
        s = s.strip().upper()
        if s.startswith("L") or s.startswith("A"):
            steps.add(s)
        else:
            # 숫자만 있으면 Local로 간주
            try:
                num = int(s)
                steps.add(f"L{num}")
            except ValueError:
                pass
    return steps


def main():
    parser = argparse.ArgumentParser(
        description="SKALA Physical Risk - 전체 ETL 실행",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python 01_run_all_etl.py              # 전체 실행
  python 01_run_all_etl.py --local-only # Local만 실행
  python 01_run_all_etl.py --api-only   # API만 실행
  python 01_run_all_etl.py --only L1,L2,A1  # 특정 단계만
  python 01_run_all_etl.py --skip L5,L6     # 특정 단계 건너뛰기
  python 01_run_all_etl.py --list           # 단계 목록 출력
        """,
    )
    parser.add_argument("--local-only", action="store_true", help="Local 스크립트만 실행")
    parser.add_argument("--api-only", action="store_true", help="API 스크립트만 실행")
    parser.add_argument("--only", type=str, help="실행할 단계만 (예: L1,L2,A1)")
    parser.add_argument("--skip", type=str, help="건너뛸 단계 (예: L5,L6)")
    parser.add_argument("--list", action="store_true", help="ETL 단계 목록 출력")

    args = parser.parse_args()

    if args.list:
        print_etl_list()
        return 0

    only_steps = parse_steps(args.only) if args.only else None
    skip_steps = parse_steps(args.skip) if args.skip else None

    return run_all_etl(
        local_only=args.local_only,
        api_only=args.api_only,
        only_steps=only_steps,
        skip_steps=skip_steps,
    )


if __name__ == "__main__":
    sys.exit(main())
