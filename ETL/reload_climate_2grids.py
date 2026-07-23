"""
grid_id 1, 4에 대해 기후 데이터만 추가 적재하는 스크립트
(좌표 변경 후 기후 데이터 재적재용)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import setup_logging, get_db_connection

# 기후 테이블 매핑
MONTHLY_TABLE_MAP = {
    "ta_data": ["ta", "TA", "TAS"],
    "rn_data": ["rn", "RN", "PR"],
    "rhm_data": ["rhm", "RHM"],
    "ws_data": ["ws", "WS"],
    "si_data": ["si", "SI", "RSDS"],
    "spei12_data": ["spei12", "SPEI12"],
    "tamax_data": ["tamax", "TAMAX", "TASMAX"],
    "tamin_data": ["tamin", "TAMIN", "TASMIN"],
}

YEARLY_TABLE_MAP = {
    "ta_yearly_data": ["ta", "TA", "aii", "AII"],
    "cdd_data": ["cdd", "CDD"],
    "csdi_data": ["csdi", "CSDI"],
    "rain80_data": ["rain80", "RAIN80"],
    "rx1day_data": ["rx1day", "RX1DAY"],
    "rx5day_data": ["rx5day", "RX5DAY"],
    "sdii_data": ["sdii", "SDII"],
    "wsdi_data": ["wsdi", "WSDI"],
}

if __name__ == "__main__":
    logger = setup_logging("reload_climate_2grids")
    logger.info("=" * 60)
    logger.info("grid_id 1, 4 기후 데이터 추가 적재 시작")
    logger.info("=" * 60)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 대상 격자 조회
    cursor.execute("""
        SELECT grid_id, longitude, latitude FROM location_grid
        WHERE grid_id IN (1, 4)
    """)
    grids = cursor.fetchall()
    logger.info(f"대상 격자: {grids}")

    # 02_load_climate_geocode.py 모듈 로드
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "climate_geocode", Path(__file__).parent / "02_load_climate_geocode.py"
    )
    climate_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(climate_module)

    # 기후 데이터 적재 (grid_id 1, 4만)
    results = climate_module.load_climate_data_for_grids(conn, cursor, grids, logger, row_limit=0)

    logger.info("=" * 60)
    logger.info("기후 데이터 적재 완료")
    for table, count in results.items():
        logger.info(f"  {table}: {count:,}건")
    logger.info("=" * 60)

    cursor.close()
    conn.close()
