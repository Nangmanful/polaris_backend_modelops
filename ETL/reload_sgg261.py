"""
sgg261 테이블만 재적재하는 스크립트
SGG261_FILTER_CODES 수정 후 사용
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import setup_logging, get_db_connection

# 수정된 SGG261_FILTER_CODES
SGG261_FILTER_CODES = {
    "31",  # 울산광역시 전체 (31xxx)
    "26290",  # 부산광역시 남구
    "46840",  # 전라남도 무안군
    "51230",  # 강원특별자치도 삼척시
    "44210",  # 충청남도 서산시
    "41135",  # 경기도 성남시 분당구
    "41610",  # 경기도 광주시
    "47280",  # 경상북도 문경시
    "48860",  # 경상남도 산청군
    "11110",  # 서울특별시 종로구
    "11620",  # 서울특별시 관악구
    "30200",  # 대전광역시 유성구
}

# 02_load_climate_geocode.py에서 필요한 부분 가져오기
import importlib.util

spec = importlib.util.spec_from_file_location(
    "climate_geocode", Path(__file__).parent / "02_load_climate_geocode.py"
)
climate_module = importlib.util.module_from_spec(spec)

# 모듈 로드 전에 SGG261_FILTER_CODES 패치

original_load = spec.loader.exec_module


def patched_load(module):
    original_load(module)
    module.SGG261_FILTER_CODES = SGG261_FILTER_CODES


spec.loader.exec_module = patched_load
spec.loader.exec_module(climate_module)

if __name__ == "__main__":
    logger = setup_logging("reload_sgg261")
    logger.info("=" * 60)
    logger.info("sgg261 테이블 재적재 시작")
    logger.info("=" * 60)
    logger.info(f"수정된 SGG261_FILTER_CODES: {SGG261_FILTER_CODES}")

    conn = get_db_connection()
    cursor = conn.cursor()

    # sgg261 데이터만 재적재
    results = climate_module.load_sgg261_daily_data(conn, cursor, logger, row_limit=0)

    logger.info("=" * 60)
    logger.info("재적재 완료")
    for table, count in results.items():
        logger.info(f"  {table}: {count:,}건")
    logger.info("=" * 60)

    cursor.close()
    conn.close()
