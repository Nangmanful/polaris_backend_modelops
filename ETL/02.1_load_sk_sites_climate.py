"""
SKALA Physical Risk AI System - SK 사업장 전용 기후 데이터 ETL

SK 사업장 9개만 location_grid에 등록하고 기후 데이터 적재
(울산 격자 제외, SK 사업장만 빠르게 처리)

사용법:
    DW_HOST=localhost DW_PORT=5555 DW_NAME=datawarehouse DW_USER=skala DW_PASSWORD=skala1234 \
    VWORLD_API_KEY=xxx python 02.1_load_sk_sites_climate.py

최종 수정일: 2025-12-14
"""

import os
import sys
import io
import csv
import time
import tarfile
import requests
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from utils import setup_logging, get_db_connection, get_data_dir

# SK 사업장 좌표 (9개)
SK_SITES: List[Tuple[str, float, float, str]] = [
    ("SK u-타워", 37.3825, 127.1220, "경기도 성남시 분당구 성남대로343번길 9"),
    ("판교 캠퍼스", 37.405879, 127.099877, "경기도 성남시 분당구 판교로255번길 38"),
    ("수내 오피스", 37.3820, 127.1250, "경기도 성남시 분당구 수내로 39"),
    ("서린 사옥", 37.570708, 126.983577, "서울특별시 종로구 종로 26"),
    ("대덕 데이터 센터", 36.3728, 127.3590, "대전광역시 유성구 엑스포로 325"),
    ("판교 데이터 센터", 37.405879, 127.099877, "경기도 성남시 분당구 판교로255번길 38"),
    ("보라매 데이터 센터", 37.4858, 126.9302, "서울특별시 관악구 보라매로5길 1"),
    ("애커튼 파트너스", 37.5712, 126.9837, "서울특별시 종로구 청계천로 41"),
    ("애커튼 테크놀로지", 37.405879, 127.099877, "경기도 성남시 분당구 판교로255번길 38"),
]

# 기후 데이터 테이블 매핑 (월별) - 파일 패턴과 변수명
# format: (file_pattern, variable_names)
MONTHLY_TABLE_MAP = {
    "ta_data": ("_TA_", ["ta", "TA", "TAS"]),
    "rn_data": ("_RN_", ["rn", "RN", "PR"]),
    "rhm_data": ("_RHM_", ["rhm", "RHM"]),
    "ws_data": ("_WS_", ["ws", "WS"]),
    "si_data": ("_SI_", ["si", "SI", "RSDS"]),
    "spei12_data": ("_SPEI12_", ["spei12", "SPEI12"]),
    "tamax_data": ("_TAMAX_", ["tamax", "TAMAX", "TASMAX"]),
    "tamin_data": ("_TAMIN_", ["tamin", "TAMIN", "TASMIN"]),
}

# 기후 데이터 테이블 매핑 (연간) - 파일 패턴과 변수명
YEARLY_TABLE_MAP = {
    "ta_yearly_data": ("_aii_", ["ta", "TA", "aii", "AII"]),
    "cdd_data": ("_CDD_", ["cdd", "CDD"]),
    "csdi_data": ("_CSDI_", ["csdi", "CSDI"]),
    "rain80_data": ("_RAIN80_", ["rain80", "RAIN80"]),
    "rx1day_data": ("_RX1DAY_", ["rx1day", "RX1DAY"]),
    "rx5day_data": ("_RX5DAY_", ["rx5day", "RX5DAY"]),
    "sdii_data": ("_SDII_", ["sdii", "SDII"]),
    "wsdi_data": ("_WSDI_", ["wsdi", "WSDI"]),
}

# sgg261 일별 데이터 매핑
SGG261_DAILY_TABLE_MAP = {
    "tamax_daily_sgg261": "TAMAX",
    "tamin_daily_sgg261": "TAMIN",
    "rn_daily_sgg261": "RN",
}

# SK 사업장 시군구 코드 (sgg261 필터링용 - 10자리)
SK_SIGUNGU_CODES = {
    "3102300000",  # 경기도 성남시 분당구
    "1101000000",  # 서울특별시 종로구
    "2504000000",  # 대전광역시 유성구
    "1121000000",  # 서울특별시 관악구
}


def geocode_reverse(api_key: str, lat: float, lon: float, logger) -> Optional[Dict]:
    """VWorld 역지오코딩 API 호출"""
    url = "https://api.vworld.kr/req/address"
    params = {
        "service": "address",
        "request": "getAddress",
        "version": "2.0",
        "crs": "epsg:4326",
        "point": f"{lon},{lat}",
        "format": "json",
        "type": "PARCEL",
        "key": api_key,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("response", {}).get("status") != "OK":
            return None

        result = data["response"]["result"][0]
        structure = result.get("structure", {})

        return {
            "sido": structure.get("level1", ""),
            "sigungu": structure.get("level2", ""),
            "bjdong": structure.get("level4L", ""),
            "full_address": result.get("text", ""),
            "sigungu_cd": structure.get("level2LC", "")[:5] if structure.get("level2LC") else None,
            "bjdong_cd": (
                structure.get("level4LC", "")[5:10]
                if len(structure.get("level4LC", "")) >= 10
                else None
            ),
        }
    except Exception as e:
        logger.warning(f"VWorld API 오류 ({lat}, {lon}): {e}")
        return None


def insert_sk_sites(conn, cursor, logger) -> List[Dict]:
    """SK 사업장 좌표를 location_grid에 삽입 (site_name 컬럼 없이)"""
    logger.info("\n[1단계] SK 사업장 좌표 삽입")

    sk_grids = []
    for site_name, lat, lon, address in SK_SITES:
        try:
            cursor.execute(
                """
                SELECT grid_id FROM location_grid
                WHERE ABS(latitude - %s) < 0.0001 AND ABS(longitude - %s) < 0.0001
            """,
                (lat, lon),
            )

            existing = cursor.fetchone()
            if existing:
                grid_id = existing["grid_id"] if isinstance(existing, dict) else existing[0]
                logger.info(f"   {site_name}: 이미 존재 (grid_id={grid_id})")
                sk_grids.append(
                    {"grid_id": grid_id, "latitude": lat, "longitude": lon, "name": site_name}
                )
                continue

            cursor.execute("SELECT COALESCE(MAX(grid_id), 0) + 1 FROM location_grid")
            result = cursor.fetchone()
            new_grid_id = result["max"] if isinstance(result, dict) else result[0]
            if new_grid_id is None:
                new_grid_id = 1

            cursor.execute(
                """
                INSERT INTO location_grid (grid_id, latitude, longitude, full_address)
                VALUES (%s, %s, %s, %s)
            """,
                (new_grid_id, lat, lon, f"[SK] {site_name}: {address}"),
            )

            sk_grids.append(
                {"grid_id": new_grid_id, "latitude": lat, "longitude": lon, "name": site_name}
            )
            logger.info(f"   {site_name}: 삽입 완료 (grid_id={new_grid_id})")

        except Exception as e:
            logger.warning(f"   {site_name} 삽입 실패: {e}")
            conn.rollback()

    conn.commit()
    logger.info(f"   SK 사업장 {len(sk_grids)}개 처리 완료")
    return sk_grids


def geocode_sk_sites(conn, cursor, api_key: str, logger, sk_grids: List[Dict]):
    """SK 사업장 역지오코딩"""
    logger.info("\n[2단계] SK 사업장 역지오코딩")
    logger.info(f"   역지오코딩 대상: {len(sk_grids)}개")

    success = 0
    for grid in sk_grids:
        result = geocode_reverse(api_key, float(grid["latitude"]), float(grid["longitude"]), logger)

        if result:
            try:
                cursor.execute(
                    """
                    UPDATE location_grid
                    SET sido = %s, sigungu = %s, dong = %s,
                        full_address = %s, sigungu_cd = %s, bjdong_cd = %s,
                        geocoded_at = CURRENT_TIMESTAMP
                    WHERE grid_id = %s
                """,
                    (
                        result["sido"],
                        result["sigungu"],
                        result["bjdong"],
                        result["full_address"],
                        result["sigungu_cd"],
                        result["bjdong_cd"],
                        grid["grid_id"],
                    ),
                )
                conn.commit()
                success += 1
                logger.info(f"   {grid['name']}: {result['full_address']}")
            except Exception as e:
                logger.warning(f"   업데이트 실패: {e}")
                conn.rollback()

        time.sleep(0.1)

    logger.info(f"   역지오코딩 완료: {success}/{len(sk_grids)}")


def load_climate_data_for_sk(conn, cursor, logger, sk_grids: List[Dict]):
    """SK 사업장에 대한 기후 데이터 로드"""
    logger.info("\n[3단계] SK 사업장 기후 데이터 로드")
    logger.info(f"   대상: {len(sk_grids)}개 SK 사업장")

    if not sk_grids:
        logger.warning("   SK 사업장 격자 없음")
        return

    # NetCDF 파일 찾기
    data_dir = get_data_dir()
    kma_dir = data_dir / "KMA" / "extracted" / "KMA" / "downloads_kma_ssp_gridraw"

    if not kma_dir.exists():
        logger.warning(f"   KMA 디렉토리 없음: {kma_dir}")
        return

    ssp_dirs = sorted(kma_dir.glob("SSP*"))
    if not ssp_dirs:
        logger.warning("   SSP 디렉토리 없음")
        return

    logger.info(f"   {len(ssp_dirs)}개 SSP 시나리오 발견")

    # NetCDF import
    try:
        import netCDF4 as nc
    except ImportError:
        logger.error("   netCDF4 모듈 없음")
        return

    # 월별 데이터 처리
    logger.info("\n   [월별 데이터]")
    for table_name, (file_pattern, var_names) in MONTHLY_TABLE_MAP.items():
        try:
            process_monthly_table(
                conn,
                cursor,
                logger,
                kma_dir,
                ssp_dirs,
                table_name,
                file_pattern,
                var_names,
                sk_grids,
            )
        except Exception as e:
            logger.warning(f"   {table_name} 처리 실패: {e}")

    # 연간 데이터 처리
    logger.info("\n   [연간 데이터]")
    for table_name, (file_pattern, var_names) in YEARLY_TABLE_MAP.items():
        try:
            process_yearly_table(
                conn,
                cursor,
                logger,
                kma_dir,
                ssp_dirs,
                table_name,
                file_pattern,
                var_names,
                sk_grids,
            )
        except Exception as e:
            logger.warning(f"   {table_name} 처리 실패: {e}")


def process_monthly_table(
    conn, cursor, logger, kma_dir, ssp_dirs, table_name, file_pattern, var_names, sk_grids
):
    """월별 테이블 처리"""
    import netCDF4 as nc

    total_inserted = 0

    for ssp_dir in ssp_dirs:
        ssp_name = ssp_dir.name
        ssp_col = {"SSP126": "ssp1", "SSP245": "ssp2", "SSP370": "ssp3", "SSP585": "ssp5"}.get(
            ssp_name, "ssp1"
        )

        monthly_dir = ssp_dir / "monthly"
        if not monthly_dir.exists():
            continue

        # .nc 파일 찾기 (정확한 패턴 사용)
        pattern = f"*{file_pattern}*monthly*.nc"
        nc_files = list(monthly_dir.glob(pattern))

        if not nc_files:
            continue

        nc_file = nc_files[0]

        try:
            dataset = nc.Dataset(nc_file, "r")

            lats = dataset.variables.get("lat", dataset.variables.get("latitude", None))
            lons = dataset.variables.get("lon", dataset.variables.get("longitude", None))

            if lats is None or lons is None:
                dataset.close()
                continue

            lats = lats[:]
            lons = lons[:]

            # 데이터 변수 찾기
            data_var = None
            for vn in var_names:
                if vn in dataset.variables:
                    data_var = dataset.variables[vn]
                    break
                if vn.lower() in dataset.variables:
                    data_var = dataset.variables[vn.lower()]
                    break

            if data_var is None:
                dataset.close()
                continue

            data = data_var[:]

            # SK 사업장별 처리
            for grid in sk_grids:
                lat_idx = np.argmin(np.abs(lats - grid["latitude"]))
                lon_idx = np.argmin(np.abs(lons - grid["longitude"]))

                for t_idx in range(min(data.shape[0], 960)):
                    if lat_idx >= data.shape[1] or lon_idx >= data.shape[2]:
                        continue

                    val = data[t_idx, lat_idx, lon_idx]
                    if np.ma.is_masked(val) or np.isnan(val):
                        continue

                    year = 2021 + t_idx // 12
                    month = (t_idx % 12) + 1
                    obs_date = f"{year}-{month:02d}-01"

                    try:
                        if ssp_name == "SSP126":
                            cursor.execute(
                                f"""
                                INSERT INTO {table_name} (grid_id, observation_date, {ssp_col})
                                VALUES (%s, %s, %s)
                                ON CONFLICT (observation_date, grid_id) DO UPDATE SET {ssp_col} = EXCLUDED.{ssp_col}
                            """,
                                (grid["grid_id"], obs_date, float(val)),
                            )
                        else:
                            cursor.execute(
                                f"""
                                UPDATE {table_name} SET {ssp_col} = %s
                                WHERE grid_id = %s AND observation_date = %s
                            """,
                                (float(val), grid["grid_id"], obs_date),
                            )
                        total_inserted += 1
                    except Exception:
                        pass

                conn.commit()

            dataset.close()

        except Exception as e:
            logger.warning(f"      {nc_file.name} 오류: {e}")

    if total_inserted > 0:
        logger.info(f"      {table_name}: {total_inserted:,}건")


def process_yearly_table(
    conn, cursor, logger, kma_dir, ssp_dirs, table_name, file_pattern, var_names, sk_grids
):
    """연간 테이블 처리"""
    import netCDF4 as nc

    total_inserted = 0

    for ssp_dir in ssp_dirs:
        ssp_name = ssp_dir.name
        ssp_col = {"SSP126": "ssp1", "SSP245": "ssp2", "SSP370": "ssp3", "SSP585": "ssp5"}.get(
            ssp_name, "ssp1"
        )

        yearly_dir = ssp_dir / "yearly"
        if not yearly_dir.exists():
            continue

        # .nc 파일 찾기 (정확한 패턴 사용)
        pattern = f"*{file_pattern}*yearly*.nc"
        nc_files = list(yearly_dir.glob(pattern))

        if not nc_files:
            continue

        nc_file = nc_files[0]

        try:
            dataset = nc.Dataset(nc_file, "r")

            lats = dataset.variables.get("lat", dataset.variables.get("latitude", None))
            lons = dataset.variables.get("lon", dataset.variables.get("longitude", None))

            if lats is None or lons is None:
                dataset.close()
                continue

            lats = lats[:]
            lons = lons[:]

            data_var = None
            for vn in var_names:
                if vn in dataset.variables:
                    data_var = dataset.variables[vn]
                    break
                if vn.lower() in dataset.variables:
                    data_var = dataset.variables[vn.lower()]
                    break

            if data_var is None:
                dataset.close()
                continue

            data = data_var[:]

            for grid in sk_grids:
                lat_idx = np.argmin(np.abs(lats - grid["latitude"]))
                lon_idx = np.argmin(np.abs(lons - grid["longitude"]))

                for year_idx in range(min(data.shape[0], 80)):
                    if lat_idx >= data.shape[1] or lon_idx >= data.shape[2]:
                        continue

                    val = data[year_idx, lat_idx, lon_idx]
                    if np.ma.is_masked(val) or np.isnan(val):
                        continue

                    year = 2021 + year_idx

                    try:
                        if ssp_name == "SSP126":
                            cursor.execute(
                                f"""
                                INSERT INTO {table_name} (grid_id, year, {ssp_col})
                                VALUES (%s, %s, %s)
                                ON CONFLICT (year, grid_id) DO UPDATE SET {ssp_col} = EXCLUDED.{ssp_col}
                            """,
                                (grid["grid_id"], year, float(val)),
                            )
                        else:
                            cursor.execute(
                                f"""
                                UPDATE {table_name} SET {ssp_col} = %s
                                WHERE grid_id = %s AND year = %s
                            """,
                                (float(val), grid["grid_id"], year),
                            )
                        total_inserted += 1
                    except Exception:
                        pass

                conn.commit()

            dataset.close()

        except Exception as e:
            logger.warning(f"      {nc_file.name} 오류: {e}")

    if total_inserted > 0:
        logger.info(f"      {table_name}: {total_inserted:,}건")


def load_sgg261_daily_data(conn, cursor, logger):
    """SK 사업장 시군구의 sgg261 일별 데이터 로드"""
    logger.info("\n[4단계] sgg261 일별 데이터 로드 (SK 사업장 시군구)")

    data_dir = get_data_dir()
    sgg261_dir = data_dir / "KMA" / "extracted" / "KMA" / "downloads_kma_ssp_sgg261"

    if not sgg261_dir.exists():
        logger.warning(f"   sgg261 디렉토리 없음: {sgg261_dir}")
        return {}

    ssp_dirs = sorted(sgg261_dir.glob("SSP*"))
    if not ssp_dirs:
        logger.warning("   SSP 디렉토리 없음")
        return {}

    logger.info(f"   {len(ssp_dirs)}개 SSP 시나리오, 필터: {SK_SIGUNGU_CODES}")

    results = {}
    admin_codes_cache = {}

    # SSP126 먼저
    ssp_dirs = sorted(ssp_dirs, key=lambda x: 0 if "SSP126" in x.name else 1)

    for table_name, var_name in SGG261_DAILY_TABLE_MAP.items():
        table_total = 0

        for ssp_dir in ssp_dirs:
            ssp_name = ssp_dir.name
            daily_dir = ssp_dir / "daily"

            if not daily_dir.exists():
                continue

            pattern = f"{ssp_name}_{var_name}_sgg261_daily_*.asc"
            asc_files = list(daily_dir.glob(pattern))

            if not asc_files:
                continue

            asc_file = asc_files[0]
            ssp_col = {"SSP126": "ssp1", "SSP245": "ssp2", "SSP370": "ssp3", "SSP585": "ssp5"}.get(
                ssp_name, "ssp1"
            )

            try:
                with tarfile.open(asc_file, "r:gz") as tar:
                    members = [m for m in tar.getmembers() if m.name.endswith(".txt")]
                    # 처음 5개 연도만 샘플 처리
                    members = members[:5]

                    ssp_inserted = 0

                    for member in members:
                        f = tar.extractfile(member)
                        if not f:
                            continue

                        content = f.read().decode("utf-8")
                        reader = csv.reader(io.StringIO(content))
                        rows = list(reader)

                        if len(rows) < 4:
                            continue

                        admin_codes = rows[0][1:]
                        sido_names = rows[1][1:]
                        sigungu_names = rows[2][1:]

                        # location_sgg261에 SK 시군구만 등록
                        if ssp_name == "SSP126" and not admin_codes_cache:
                            for i, admin_code in enumerate(admin_codes):
                                if admin_code not in SK_SIGUNGU_CODES:
                                    continue

                                if admin_code not in admin_codes_cache:
                                    sido = sido_names[i] if i < len(sido_names) else ""
                                    sigungu = sigungu_names[i] if i < len(sigungu_names) else ""

                                    cursor.execute(
                                        """
                                        INSERT INTO location_sgg261 (admin_code, sido_name, sigungu_name)
                                        VALUES (%s, %s, %s)
                                        ON CONFLICT (admin_code) DO NOTHING
                                    """,
                                        (admin_code, sido, sigungu),
                                    )
                                    admin_codes_cache[admin_code] = True

                            conn.commit()
                            logger.info(
                                f"      location_sgg261: {len(admin_codes_cache)}개 행정구역"
                            )

                        # 데이터 행 처리
                        for row in rows[3:]:
                            if len(row) < 2:
                                continue

                            date_str = row[0]
                            try:
                                obs_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                            except ValueError:
                                continue

                            for i, admin_code in enumerate(admin_codes):
                                if i + 1 >= len(row):
                                    break

                                if admin_code not in SK_SIGUNGU_CODES:
                                    continue

                                try:
                                    val = float(row[i + 1])
                                    if val == -999 or np.isnan(val):
                                        continue

                                    if ssp_name == "SSP126":
                                        cursor.execute(
                                            f"""
                                            INSERT INTO {table_name} (admin_code, observation_date, {ssp_col})
                                            VALUES (%s, %s, %s)
                                            ON CONFLICT (observation_date, admin_code) DO UPDATE SET {ssp_col} = EXCLUDED.{ssp_col}
                                        """,
                                            (admin_code, obs_date, val),
                                        )
                                    else:
                                        cursor.execute(
                                            f"""
                                            UPDATE {table_name} SET {ssp_col} = %s
                                            WHERE admin_code = %s AND observation_date = %s
                                        """,
                                            (val, admin_code, obs_date),
                                        )

                                    ssp_inserted += 1
                                except (ValueError, TypeError):
                                    pass

                        conn.commit()

                    table_total += ssp_inserted

            except Exception as e:
                logger.warning(f"      {asc_file.name} 오류: {e}")

        if table_total > 0:
            logger.info(f"      {table_name}: {table_total:,}건")
            results[table_name] = table_total

    return results


def main():
    """SK 사업장 전용 기후 데이터 ETL"""
    logger = setup_logging("load_sk_climate")
    logger.info("=" * 60)
    logger.info("SK 사업장 전용 기후 데이터 ETL 시작")
    logger.info("=" * 60)

    api_key = os.getenv("VWORLD_API_KEY")
    if not api_key:
        logger.warning("VWORLD_API_KEY 없음 - 역지오코딩 스킵")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. SK 사업장 삽입
        sk_grids = insert_sk_sites(conn, cursor, logger)

        # 2. 역지오코딩
        if api_key:
            geocode_sk_sites(conn, cursor, api_key, logger, sk_grids)

        # 3. 기후 데이터 로드 (격자 기반)
        load_climate_data_for_sk(conn, cursor, logger, sk_grids)

        # 4. sgg261 일별 데이터 로드
        load_sgg261_daily_data(conn, cursor, logger)

        # 결과 확인
        logger.info("\n" + "=" * 60)
        logger.info("SK 사업장 전용 ETL 완료")
        logger.info("=" * 60)

        cursor.execute("SELECT COUNT(*) FROM location_grid WHERE full_address LIKE '[SK]%'")
        sk_count = cursor.fetchone()[0]
        logger.info(f"   SK 사업장: {sk_count}개")

        # SK 사업장 grid_id 목록
        sk_grid_ids = [g["grid_id"] for g in sk_grids]
        if sk_grid_ids:
            # 월별 테이블 검증
            logger.info("   [월별 데이터]")
            for table in MONTHLY_TABLE_MAP.keys():
                try:
                    cursor.execute(
                        f"""
                        SELECT COUNT(*) FROM {table}
                        WHERE grid_id = ANY(%s)
                    """,
                        (sk_grid_ids,),
                    )
                    count = cursor.fetchone()[0]
                    logger.info(f"      {table}: {count:,}건")
                except:
                    pass

            # 연간 테이블 검증
            logger.info("   [연간 데이터]")
            for table in YEARLY_TABLE_MAP.keys():
                try:
                    cursor.execute(
                        f"""
                        SELECT COUNT(*) FROM {table}
                        WHERE grid_id = ANY(%s)
                    """,
                        (sk_grid_ids,),
                    )
                    count = cursor.fetchone()[0]
                    logger.info(f"      {table}: {count:,}건")
                except:
                    pass

    except Exception as e:
        logger.error(f"오류 발생: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
