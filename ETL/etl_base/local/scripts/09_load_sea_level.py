"""
SKALA Physical Risk AI System - 해수면 상승 데이터 적재
NetCDF 파일에서 해수면 상승 예측 데이터를 로드

데이터 소스: sea_level_rise/*.nc
대상 테이블: sea_level_grid, sea_level_data
예상 데이터: 약 7,000개 레코드

최종 수정일: 2025-12-03
버전: v01
"""

import sys
from tqdm import tqdm
import numpy as np

from utils import setup_logging, get_db_connection, get_data_dir, get_row_count


def load_sea_level() -> None:
    """해수면 상승 데이터를 테이블에 로드"""
    logger = setup_logging("load_sea_level")
    logger.info("=" * 60)
    logger.info("해수면 상승 데이터 로딩 시작")
    logger.info("=" * 60)

    try:
        import netCDF4 as nc
    except ImportError:
        logger.error("netCDF4 모듈이 필요합니다")
        sys.exit(1)

    try:
        conn = get_db_connection()
        logger.info("데이터베이스 연결 성공")
    except Exception as e:
        logger.error(f"데이터베이스 연결 실패: {e}")
        sys.exit(1)

    cursor = conn.cursor()

    # 데이터 파일 찾기
    data_dir = get_data_dir()
    sea_level_dir = data_dir / "sea_level_rise"

    if not sea_level_dir.exists():
        logger.error(f"sea_level_rise 디렉토리를 찾을 수 없습니다")
        conn.close()
        sys.exit(1)

    nc_files = list(sea_level_dir.glob("*annual_mean*.nc"))
    # ssp1 파일이 먼저 처리되도록 정렬 (INSERT → UPDATE 순서 보장)
    nc_files = sorted(nc_files, key=lambda x: 0 if "ssp1" in x.name else 1)
    logger.info(f"{len(nc_files)}개 NetCDF 파일 발견")

    if not nc_files:
        logger.warning("NetCDF 파일이 없습니다")
        conn.close()
        return

    # sea_level_grid 테이블 초기화
    cursor.execute("TRUNCATE TABLE sea_level_grid CASCADE")
    conn.commit()

    # 첫 번째 파일에서 그리드 좌표 추출
    ds = nc.Dataset(nc_files[0])
    logger.info(f"   변수: {list(ds.variables.keys())}")

    lat = ds.variables["latitude"][:]  # 2D 배열일 수 있음
    lon = ds.variables["longitude"][:]

    # 1D로 변환
    if len(lat.shape) == 2:
        lat_1d = lat[:, 0]
        lon_1d = lon[0, :]
    else:
        lat_1d = lat
        lon_1d = lon

    logger.info(f"   그리드: {len(lat_1d)} x {len(lon_1d)}")

    # sea_level_grid에 포인트 삽입
    grid_map = {}  # (j, i) -> grid_id

    for j in range(len(lat_1d)):
        for i in range(len(lon_1d)):
            if len(lat.shape) == 2:
                lat_val = float(lat[j, i])
                lon_val = float(lon[j, i])
            else:
                lat_val = float(lat_1d[j])
                lon_val = float(lon_1d[i])

            cursor.execute(
                """
                INSERT INTO sea_level_grid (longitude, latitude, geom)
                VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                RETURNING grid_id
            """,
                (lon_val, lat_val, lon_val, lat_val),
            )
            grid_id = cursor.fetchone()[0]
            grid_map[(j, i)] = grid_id

    conn.commit()
    logger.info(f"   sea_level_grid: {len(grid_map)}개 포인트")

    ds.close()

    # SSP별 해수면 데이터 로드
    ssp_mapping = {
        "ssp1_2_6": "ssp1",
        "ssp2_4_5": "ssp2",
        "ssp3_7_0": "ssp3",
        "ssp5_8_5": "ssp5",
    }

    total_insert = 0

    for nc_file in tqdm(nc_files, desc="해수면 데이터 로딩"):
        # SSP 식별
        ssp_col = None
        for ssp_key, col_name in ssp_mapping.items():
            if ssp_key in nc_file.name:
                ssp_col = col_name
                break

        if not ssp_col:
            continue

        try:
            ds = nc.Dataset(nc_file)

            # 데이터 변수 찾기
            slr_var = None
            for var in ds.variables.keys():
                if "slr" in var.lower():
                    slr_var = var
                    break

            if not slr_var:
                ds.close()
                continue

            slr_data = ds.variables[slr_var][:]  # (time, j, i)
            time_steps = slr_data.shape[0]

            # sea_level_data 테이블 초기화 (첫 번째 SSP에서만)
            if ssp_col == "ssp1":
                cursor.execute("TRUNCATE TABLE sea_level_data")
                conn.commit()

            insert_count = 0

            for t_idx in range(time_steps):
                year = 2015 + t_idx  # 데이터 시작 연도

                for (j, i), grid_id in grid_map.items():
                    val = slr_data[t_idx, j, i]
                    if np.ma.is_masked(val) or np.isnan(val):
                        continue

                    if ssp_col == "ssp1":
                        cursor.execute(
                            """
                            INSERT INTO sea_level_data (grid_id, year, ssp1)
                            VALUES (%s, %s, %s)
                        """,
                            (grid_id, year, float(val)),
                        )
                    else:
                        cursor.execute(
                            f"""
                            UPDATE sea_level_data
                            SET {ssp_col} = %s
                            WHERE grid_id = %s AND year = %s
                        """,
                            (float(val), grid_id, year),
                        )

                    insert_count += 1

                if t_idx % 10 == 0:
                    conn.commit()

            conn.commit()
            ds.close()
            total_insert += insert_count
            logger.info(f"   {nc_file.name}: {insert_count:,}개")

        except Exception as e:
            logger.warning(f"   오류 ({nc_file.name}): {e}")

    # 결과 출력
    logger.info("=" * 60)
    logger.info("해수면 상승 데이터 로딩 완료")
    logger.info(f"   - sea_level_grid: {get_row_count(conn, 'sea_level_grid'):,}개")
    logger.info(f"   - sea_level_data: {get_row_count(conn, 'sea_level_data'):,}개")
    logger.info("=" * 60)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    load_sea_level()
