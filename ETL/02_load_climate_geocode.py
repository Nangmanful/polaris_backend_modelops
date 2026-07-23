"""
SKALA Physical Risk AI System - 울산 격자 + SK사업장 + 전체 기후 데이터 ETL

기능:
1. 울산 지역 격자 1000개 + SK 사업장 9개 생성
2. VWorld 역지오코딩으로 행정구역 정보 업데이트
3. NetCDF에서 전체 기후 데이터 추출 → 모든 기후 테이블에 적재
4. sgg261 시군구 단위 일별 기후 데이터 적재 (TAMAX, TAMIN, TA, RN, RHM, WS, SI)

대상 테이블:
  - location_grid
  - 월별: ta_data, rn_data, rhm_data, ws_data, si_data, spei12_data, tamax_data, tamin_data
  - 연간: ta_yearly_data, cdd_data, csdi_data, rain80_data, rx1day_data, rx5day_data, sdii_data, wsdi_data
  - 일별 (sgg261): location_sgg261, ta_daily_sgg261, tamax_daily_sgg261, tamin_daily_sgg261,
                   rn_daily_sgg261, rhm_daily_sgg261, ws_daily_sgg261, si_daily_sgg261

API: VWorld 역지오코딩 (VWORLD_API_KEY)
데이터: KMA NetCDF (SSP 시나리오별 기후 데이터), KMA sgg261 (시군구 단위 일별 데이터)

최종 수정일: 2025-12-14
버전: v05 - sgg261 일별 기후 데이터 적재 추가
"""

import os
import sys
import time
import gzip
import shutil
import tempfile
import tarfile
import csv
import io
import requests
import numpy as np
from pathlib import Path
from datetime import date, datetime
from typing import Optional, Dict, List, Tuple

# 현재 디렉토리 추가
sys.path.insert(0, str(Path(__file__).parent))

from utils import setup_logging, get_db_connection, get_row_count, get_data_dir

# SAMPLE_LIMIT: 테스트용 행 수 제한 (0=전체, N=각 테이블당 N개 row만 적재)
SAMPLE_LIMIT = int(os.environ.get("SAMPLE_LIMIT", 0))

# 울산 영역 (대략적인 경위도 범위)
ULSAN_BOUNDS = {
    "lat_min": 35.42,  # 울산 육지 영역
    "lat_max": 35.72,
    "lon_min": 129.05,
    "lon_max": 129.45,
}

# 1km ≈ 0.009° (위도), 0.011° (경도, 35°N 기준)
GRID_STEP_LAT = 0.009  # 약 1km
GRID_STEP_LON = 0.011  # 약 1km

# SK 사업장 좌표 (9개)
SK_SITES: List[Tuple[str, float, float, str]] = [
    # (사업장명, 위도, 경도, 주소)
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

# 기후 데이터 테이블 매핑 (월별)
MONTHLY_TABLE_MAP = {
    "ta_data": ["ta", "TA", "TAS"],  # 기온
    "rn_data": ["rn", "RN", "PR"],  # 강수량
    "rhm_data": ["rhm", "RHM"],  # 상대습도
    "ws_data": ["ws", "WS"],  # 풍속
    "si_data": ["si", "SI", "RSDS"],  # 일사량
    "spei12_data": ["spei12", "SPEI12"],  # SPEI 12개월
    "tamax_data": ["tamax", "TAMAX", "TASMAX"],  # 최고기온
    "tamin_data": ["tamin", "TAMIN", "TASMIN"],  # 최저기온
}

# 기후 데이터 테이블 매핑 (연간)
YEARLY_TABLE_MAP = {
    "ta_yearly_data": ["ta", "TA", "aii", "AII"],  # 연평균 기온
    "cdd_data": ["cdd", "CDD"],  # 연속무강수일
    "csdi_data": ["csdi", "CSDI"],  # 한파지속지수
    "rain80_data": ["rain80", "RAIN80"],  # 80mm 이상 강수일수
    "rx1day_data": ["rx1day", "RX1DAY"],  # 1일 최대 강수량
    "rx5day_data": ["rx5day", "RX5DAY"],  # 5일 최대 강수량
    "sdii_data": ["sdii", "SDII"],  # 강수강도
    "wsdi_data": ["wsdi", "WSDI"],  # 폭염지속지수
}

# sgg261 일별 기후 데이터 테이블 매핑 (시군구 단위)
SGG261_DAILY_TABLE_MAP = {
    "ta_daily_sgg261": "TA",  # 일 평균기온
    "tamax_daily_sgg261": "TAMAX",  # 일 최고기온
    "tamin_daily_sgg261": "TAMIN",  # 일 최저기온
    "rn_daily_sgg261": "RN",  # 일 강수량
    "rhm_daily_sgg261": "RHM",  # 일 상대습도
    "ws_daily_sgg261": "WS",  # 일 풍속
    "si_daily_sgg261": "SI",  # 일 일사량
}

# sgg261 필터링: 울산 + SK 사업장 시군구만 (전국 261개 중 일부만 적재)
SGG261_FILTER_CODES = {
    "31",  # 울산광역시 전체 (31xxx)
    "41135",  # 경기도 성남시 분당구 (SK u-타워, 판교 캠퍼스, 수내 오피스, 판교 DC, 애커튼 테크)
    "11110",  # 서울특별시 종로구 (서린 사옥, 애커튼 파트너스)
    "30200",  # 대전광역시 유성구 (대덕 데이터 센터)
    "11620",  # 서울특별시 관악구 (보라매 데이터 센터)
}


def geocode_reverse(api_key: str, lat: float, lon: float, logger) -> Optional[Dict]:
    """VWorld 역지오코딩 API 호출"""
    url = "https://api.vworld.kr/req/address"
    params = {
        "service": "address",
        "request": "getAddress",
        "version": "2.0",
        "crs": "EPSG:4326",
        "point": f"{lon},{lat}",
        "format": "json",
        "type": "BOTH",
        "zipcode": "true",
        "simple": "false",
        "key": api_key,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("response", {}).get("status") != "OK":
            return None

        results = data.get("response", {}).get("result", [])
        if not results:
            return None

        parcel_result = None
        for item in results:
            if item.get("type") == "parcel":
                parcel_result = item
                break

        if not parcel_result:
            return None

        structure = parcel_result.get("structure", {})
        dong_code = structure.get("level4LC", "")
        sigungu_cd = dong_code[:5] if len(dong_code) >= 5 else ""
        bjdong_cd = dong_code[5:10] if len(dong_code) >= 10 else ""

        return {
            "sido": structure.get("level1", ""),
            "sigungu": structure.get("level2", ""),
            "sigungu_cd": sigungu_cd,
            "dong": structure.get("level4L", ""),
            "bjdong_cd": bjdong_cd,
            "dong_code": dong_code,
            "full_address": parcel_result.get("text", ""),
        }

    except Exception as e:
        logger.warning(f"VWorld API 오류 ({lat}, {lon}): {e}")
        return None


def create_ulsan_1km_grids(conn, cursor, logger) -> int:
    """
    울산 지역에 1km 단위 격자 1000개 생성 (없으면 생성)

    Returns:
        생성된 격자 수
    """
    logger.info("\n[1-1단계] 울산 1km 격자 생성")

    # 울산 범위에서 1km 간격 격자 좌표 생성
    lat_range = np.arange(ULSAN_BOUNDS["lat_min"], ULSAN_BOUNDS["lat_max"], GRID_STEP_LAT)
    lon_range = np.arange(ULSAN_BOUNDS["lon_min"], ULSAN_BOUNDS["lon_max"], GRID_STEP_LON)

    total_possible = len(lat_range) * len(lon_range)
    logger.info(
        f"   울산 범위: lat {ULSAN_BOUNDS['lat_min']:.2f}~{ULSAN_BOUNDS['lat_max']:.2f}, lon {ULSAN_BOUNDS['lon_min']:.2f}~{ULSAN_BOUNDS['lon_max']:.2f}"
    )
    logger.info(f"   1km 간격: {len(lat_range)} x {len(lon_range)} = {total_possible}개 가능")

    # 최대 1000개까지 생성
    created = 0
    max_grids = 1000

    for lat in lat_range:
        if created >= max_grids:
            break
        for lon in lon_range:
            if created >= max_grids:
                break

            # 이미 존재하는지 확인 (0.001도 = 약 100m 이내)
            cursor.execute(
                """
                SELECT grid_id FROM location_grid
                WHERE ABS(latitude - %s) < 0.001 AND ABS(longitude - %s) < 0.001
            """,
                (float(lat), float(lon)),
            )

            existing = cursor.fetchone()
            if existing:
                continue  # 이미 있으면 건너뜀

            # 새 격자 ID 생성
            cursor.execute("SELECT COALESCE(MAX(grid_id), 0) + 1 FROM location_grid")
            new_grid_id = cursor.fetchone()[0]

            # 울산 격자 삽입
            cursor.execute(
                """
                INSERT INTO location_grid (grid_id, latitude, longitude, full_address)
                VALUES (%s, %s, %s, %s)
            """,
                (new_grid_id, float(lat), float(lon), f"[울산격자] {lat:.4f}, {lon:.4f}"),
            )

            created += 1

    conn.commit()
    logger.info(f"   울산 1km 격자 {created}개 생성 완료")
    return created


def insert_sk_sites(conn, cursor, logger):
    """SK 사업장 좌표를 location_grid에 삽입"""
    logger.info("\n[1-2단계] SK 사업장 좌표 삽입")

    inserted = 0
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
                logger.info(f"   {site_name}: 이미 존재 (grid_id={existing[0]})")
                continue

            cursor.execute("SELECT COALESCE(MAX(grid_id), 0) + 1 FROM location_grid")
            new_grid_id = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO location_grid (grid_id, latitude, longitude, full_address)
                VALUES (%s, %s, %s, %s)
            """,
                (new_grid_id, lat, lon, f"[SK] {site_name}: {address}"),
            )

            inserted += 1
            logger.info(f"   {site_name}: 삽입 완료 (grid_id={new_grid_id})")

        except Exception as e:
            logger.warning(f"   {site_name} 삽입 실패: {e}")
            conn.rollback()

    conn.commit()
    logger.info(f"   SK 사업장 {inserted}개 삽입 완료")
    return inserted


def decompress_if_gzip(file_path: Path) -> Path:
    """
    gzip/tar.gz 압축 파일이면 압축 해제

    일부 .nc 파일은 실제로 tar.gz 형식으로 내부에 진짜 .nc 파일이 있음
    (예: ssp585_tamax_gridraw_monthly_2021-2100.nc → tar.gz 안에 AR6_SSP585_5ENSMN_skorea_TAMAX_gridraw_monthly_2021_2100.nc)
    """
    import subprocess
    import tarfile

    result = subprocess.run(["file", str(file_path)], capture_output=True, text=True)

    if "gzip" in result.stdout.lower():
        # gzip 해제 후 임시 파일 생성
        temp_gz_path = Path(tempfile.mktemp(suffix=".tar"))
        with gzip.open(file_path, "rb") as f_in:
            with open(temp_gz_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        # tar 아카이브인지 확인
        tar_check = subprocess.run(["file", str(temp_gz_path)], capture_output=True, text=True)

        if "tar" in tar_check.stdout.lower() or "POSIX" in tar_check.stdout:
            # tar 아카이브에서 .nc 파일 추출
            try:
                with tarfile.open(temp_gz_path, "r") as tar:
                    nc_files = [m for m in tar.getmembers() if m.name.endswith(".nc")]
                    if nc_files:
                        extract_dir = Path(tempfile.mkdtemp())
                        tar.extract(nc_files[0], extract_dir)
                        temp_gz_path.unlink()  # tar 파일 삭제
                        return extract_dir / nc_files[0].name
            except Exception:
                pass
            temp_gz_path.unlink()
            return file_path
        else:
            # tar가 아닌 순수 gzip이면 바로 사용
            decompressed_path = Path(tempfile.mktemp(suffix=".nc"))
            shutil.move(str(temp_gz_path), str(decompressed_path))
            return decompressed_path

    return file_path


def find_nc_file(directory: Path, var_names: List[str]) -> Optional[Path]:
    """변수명에 해당하는 NetCDF 파일 찾기"""
    for var in var_names:
        # ar6_ssp126_5ensmn_skorea_ta_gridraw_monthly_2021_2100.nc 형식
        patterns = [
            f"*_{var}_*.nc",
            f"*_{var.lower()}_*.nc",
            f"*{var}*.nc",
            f"*{var.lower()}*.nc",
        ]
        for pattern in patterns:
            files = list(directory.glob(pattern))
            if files:
                return files[0]
    return None


def table_exists(conn, table_name: str) -> bool:
    """테이블 존재 여부 확인"""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        )
    """,
        (table_name,),
    )
    exists = cursor.fetchone()[0]
    cursor.close()
    return exists


def load_climate_data_for_grids(conn, cursor, grids: List[Tuple], logger, row_limit: int = 0):
    """
    location_grid의 격자들에 대해 NetCDF에서 전체 기후 데이터 추출하여 적재

    Args:
        conn: DB 연결
        cursor: DB 커서
        grids: [(grid_id, lon, lat), ...] 격자 목록
        logger: 로거
        row_limit: 0이면 전체, N이면 각 테이블당 N개 row만 적재 후 다음 테이블로
    """
    try:
        import netCDF4 as nc
    except ImportError:
        logger.error("netCDF4 모듈 필요: pip install netCDF4")
        return {}

    data_dir = get_data_dir()
    kma_dir = data_dir / "KMA" / "extracted" / "KMA" / "downloads_kma_ssp_gridraw"

    if not kma_dir.exists():
        logger.warning(f"KMA 디렉토리 없음: {kma_dir}")
        return {}

    ssp_dirs = list(kma_dir.glob("SSP*"))
    if not ssp_dirs:
        logger.warning("SSP 디렉토리 없음")
        return {}

    # SSP126이 먼저 처리되도록 정렬
    ssp_dirs = sorted(ssp_dirs, key=lambda x: 0 if "SSP126" in x.name else 1)

    logger.info(f"\n[기후 데이터 로드] {len(ssp_dirs)}개 SSP 시나리오 발견")

    # 샘플 파일에서 좌표 배열 가져오기
    sample_files = list(kma_dir.glob("**/monthly/*_ta_*.nc"))
    if not sample_files:
        sample_files = list(kma_dir.glob("**/*.nc"))
    if not sample_files:
        logger.warning("NetCDF 파일 없음")
        return {}

    sample_file = decompress_if_gzip(sample_files[0])
    ds = nc.Dataset(sample_file)

    lon_name = "longitude" if "longitude" in ds.variables else "lon"
    lat_name = "latitude" if "latitude" in ds.variables else "lat"
    nc_lon = ds.variables[lon_name][:]
    nc_lat = ds.variables[lat_name][:]
    ds.close()

    logger.info(f"   NetCDF 그리드: {len(nc_lon)} x {len(nc_lat)}")

    # 각 격자의 가장 가까운 NetCDF 인덱스 찾기
    grid_nc_idx = {}
    for grid_id, grid_lon, grid_lat in grids:
        lon_idx = np.argmin(np.abs(nc_lon - float(grid_lon)))
        lat_idx = np.argmin(np.abs(nc_lat - float(grid_lat)))
        grid_nc_idx[grid_id] = (lon_idx, lat_idx)

    logger.info(f"   {len(grid_nc_idx)}개 격자 인덱스 매핑 완료")

    results = {}
    grid_ids = list(grid_nc_idx.keys())

    # ========== 월별 데이터 적재 ==========
    logger.info("\n   [월별 데이터]")

    for table_name, var_names in MONTHLY_TABLE_MAP.items():
        if not table_exists(conn, table_name):
            continue

        table_total = 0

        for ssp_dir in ssp_dirs:
            ssp_name = ssp_dir.name
            monthly_dir = ssp_dir / "monthly"

            if not monthly_dir.exists():
                continue

            nc_file_path = find_nc_file(monthly_dir, var_names)
            if not nc_file_path:
                continue

            nc_file = decompress_if_gzip(nc_file_path)

            try:
                ds = nc.Dataset(nc_file)

                # 변수 찾기
                data_var = None
                for v in ds.variables.keys():
                    if v.upper() in [vn.upper() for vn in var_names]:
                        data_var = v
                        break

                if not data_var:
                    ds.close()
                    continue

                data = ds.variables[data_var][:]
                time_steps = data.shape[0]

                ssp_col = {
                    "SSP126": "ssp1",
                    "SSP245": "ssp2",
                    "SSP370": "ssp3",
                    "SSP585": "ssp5",
                }.get(ssp_name, "ssp1")

                # 첫 SSP에서 기존 데이터 삭제
                if ssp_name == "SSP126":
                    cursor.execute(f"DELETE FROM {table_name} WHERE grid_id = ANY(%s)", (grid_ids,))
                    conn.commit()

                max_steps = min(time_steps, 960)

                ssp_inserted = 0
                row_limit_reached = False

                for t_idx in range(max_steps):
                    if row_limit_reached:
                        break

                    year = 2021 + (t_idx // 12)
                    month = (t_idx % 12) + 1
                    obs_date = date(year, month, 1)

                    for grid_id, (lon_idx, lat_idx) in grid_nc_idx.items():
                        # row_limit 체크 (테이블당 N개 row만)
                        if row_limit > 0 and table_total + ssp_inserted >= row_limit:
                            row_limit_reached = True
                            break

                        if lat_idx >= data.shape[1] or lon_idx >= data.shape[2]:
                            continue

                        val = data[t_idx, lat_idx, lon_idx]
                        if np.ma.is_masked(val) or np.isnan(val):
                            continue

                        if ssp_name == "SSP126":
                            cursor.execute(
                                f"""
                                INSERT INTO {table_name} (grid_id, observation_date, {ssp_col})
                                VALUES (%s, %s, %s)
                                ON CONFLICT (observation_date, grid_id) DO UPDATE SET {ssp_col} = EXCLUDED.{ssp_col}
                            """,
                                (grid_id, obs_date, float(val)),
                            )
                        else:
                            cursor.execute(
                                f"""
                                UPDATE {table_name} SET {ssp_col} = %s
                                WHERE grid_id = %s AND observation_date = %s
                            """,
                                (float(val), grid_id, obs_date),
                            )

                        ssp_inserted += 1

                    if t_idx % 12 == 0:
                        conn.commit()

                conn.commit()
                ds.close()
                table_total += ssp_inserted

                # row_limit 도달하면 다음 SSP 스킵
                if row_limit > 0 and table_total >= row_limit:
                    break

            except Exception as e:
                logger.warning(f"      {table_name} {ssp_name} 오류: {e}")

        if table_total > 0:
            logger.info(f"      {table_name}: {table_total:,}건")
            results[table_name] = table_total

    # ========== 연간 데이터 적재 ==========
    logger.info("\n   [연간 데이터]")

    for table_name, var_names in YEARLY_TABLE_MAP.items():
        if not table_exists(conn, table_name):
            continue

        table_total = 0

        for ssp_dir in ssp_dirs:
            ssp_name = ssp_dir.name
            yearly_dir = ssp_dir / "yearly"

            if not yearly_dir.exists():
                continue

            nc_file_path = find_nc_file(yearly_dir, var_names)
            if not nc_file_path:
                continue

            nc_file = decompress_if_gzip(nc_file_path)

            try:
                ds = nc.Dataset(nc_file)

                # 변수 찾기
                data_var = None
                for v in ds.variables.keys():
                    if v.upper() in [vn.upper() for vn in var_names]:
                        data_var = v
                        break

                if not data_var:
                    # 첫 번째 데이터 변수 사용
                    for v in ds.variables.keys():
                        if v.upper() not in ["TIME", "LON", "LAT", "LONGITUDE", "LATITUDE"]:
                            data_var = v
                            break

                if not data_var:
                    ds.close()
                    continue

                data = ds.variables[data_var][:]

                ssp_col = {
                    "SSP126": "ssp1",
                    "SSP245": "ssp2",
                    "SSP370": "ssp3",
                    "SSP585": "ssp5",
                }.get(ssp_name, "ssp1")

                # 첫 SSP에서 기존 데이터 삭제
                if ssp_name == "SSP126":
                    cursor.execute(f"DELETE FROM {table_name} WHERE grid_id = ANY(%s)", (grid_ids,))
                    conn.commit()

                max_years = min(data.shape[0], 80)

                ssp_inserted = 0
                row_limit_reached = False

                for year_idx in range(max_years):
                    if row_limit_reached:
                        break

                    year = 2021 + year_idx

                    for grid_id, (lon_idx, lat_idx) in grid_nc_idx.items():
                        # row_limit 체크 (테이블당 N개 row만)
                        if row_limit > 0 and table_total + ssp_inserted >= row_limit:
                            row_limit_reached = True
                            break

                        if lat_idx >= data.shape[1] or lon_idx >= data.shape[2]:
                            continue

                        val = data[year_idx, lat_idx, lon_idx]
                        if np.ma.is_masked(val) or np.isnan(val):
                            continue

                        if ssp_name == "SSP126":
                            cursor.execute(
                                f"""
                                INSERT INTO {table_name} (grid_id, year, {ssp_col})
                                VALUES (%s, %s, %s)
                                ON CONFLICT (year, grid_id) DO UPDATE SET {ssp_col} = EXCLUDED.{ssp_col}
                            """,
                                (grid_id, year, float(val)),
                            )
                        else:
                            cursor.execute(
                                f"""
                                UPDATE {table_name} SET {ssp_col} = %s
                                WHERE grid_id = %s AND year = %s
                            """,
                                (float(val), grid_id, year),
                            )

                        ssp_inserted += 1

                conn.commit()
                ds.close()
                table_total += ssp_inserted

                # row_limit 도달하면 다음 SSP 스킵
                if row_limit > 0 and table_total >= row_limit:
                    break

            except Exception as e:
                logger.warning(f"      {table_name} {ssp_name} 오류: {e}")

        if table_total > 0:
            logger.info(f"      {table_name}: {table_total:,}건")
            results[table_name] = table_total

    return results


def load_sgg261_daily_data(conn, cursor, logger, row_limit: int = 0) -> Dict[str, int]:
    """
    sgg261 시군구 단위 일별 기후 데이터 적재

    Args:
        conn: DB 연결
        cursor: DB 커서
        logger: 로거
        row_limit: 0이면 전체, N이면 각 테이블당 N개 row만 적재

    Returns:
        테이블별 적재 건수 딕셔너리
    """
    data_dir = get_data_dir()
    sgg261_dir = data_dir / "KMA" / "extracted" / "KMA" / "downloads_kma_ssp_sgg261"

    if not sgg261_dir.exists():
        logger.warning(f"sgg261 디렉토리 없음: {sgg261_dir}")
        return {}

    ssp_dirs = sorted(sgg261_dir.glob("SSP*"))
    if not ssp_dirs:
        logger.warning("SSP 디렉토리 없음")
        return {}

    logger.info(f"\n[sgg261 일별 데이터] {len(ssp_dirs)}개 SSP 시나리오 발견")

    results = {}
    admin_codes_cache = {}  # 행정코드 캐시

    # SSP126이 먼저 처리되도록 정렬
    ssp_dirs = sorted(ssp_dirs, key=lambda x: 0 if "SSP126" in x.name else 1)

    for table_name, var_name in SGG261_DAILY_TABLE_MAP.items():
        if not table_exists(conn, table_name):
            logger.warning(f"   {table_name} 테이블 없음, 건너뜀")
            continue

        table_total = 0

        for ssp_dir in ssp_dirs:
            ssp_name = ssp_dir.name
            daily_dir = ssp_dir / "daily"

            if not daily_dir.exists():
                continue

            # 파일 찾기: SSP126_TAMAX_sgg261_daily_2021-2100.asc
            pattern = f"{ssp_name}_{var_name}_sgg261_daily_*.asc"
            asc_files = list(daily_dir.glob(pattern))

            if not asc_files:
                continue

            asc_file = asc_files[0]
            logger.info(f"      {table_name} ({ssp_name}): {asc_file.name}")

            ssp_col = {"SSP126": "ssp1", "SSP245": "ssp2", "SSP370": "ssp3", "SSP585": "ssp5"}.get(
                ssp_name, "ssp1"
            )

            # 첫 SSP + 첫 테이블에서만 location_sgg261 초기화
            if ssp_name == "SSP126":
                cursor.execute(f"TRUNCATE TABLE {table_name}")
                if table_name == "ta_daily_sgg261":  # 첫 테이블에서만 location_sgg261 초기화
                    cursor.execute("TRUNCATE TABLE location_sgg261")
                conn.commit()

            try:
                # tar.gz 압축 해제 후 읽기
                with tarfile.open(asc_file, "r:gz") as tar:
                    members = [m for m in tar.getmembers() if m.name.endswith(".txt")]

                    # SAMPLE_LIMIT 적용: row_limit > 0이면 제한된 연도만 처리
                    if row_limit > 0:
                        # row_limit개 일수만 처리 (약 1년 = 365일)
                        max_years = max(1, row_limit // 365)
                        members = members[:max_years]

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

                        # 헤더 파싱
                        # Row 0: 년-월-일, admin_code1, admin_code2, ...
                        # Row 1: 년-월-일, sido1, sido2, ...
                        # Row 2: 년-월-일, sigungu1, sigungu2, ...
                        # Row 3+: 날짜, 값1, 값2, ...

                        admin_codes = rows[0][1:]  # 첫 컬럼 제외
                        sido_names = rows[1][1:]
                        sigungu_names = rows[2][1:]

                        # location_sgg261에 행정구역 정보 삽입 (첫 SSP 첫 파일에서만, 울산+SK만)
                        if (
                            ssp_name == "SSP126"
                            and table_name == "ta_daily_sgg261"
                            and not admin_codes_cache
                        ):
                            for i, admin_code in enumerate(admin_codes):
                                # 필터링: 울산(31xxx) 또는 SK 사업장 시군구만
                                if not any(
                                    admin_code.startswith(code) for code in SGG261_FILTER_CODES
                                ):
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
                                f"      location_sgg261: {len(admin_codes)}개 행정구역 등록"
                            )

                        # 데이터 행 처리 (Row 3부터)
                        for row in rows[3:]:
                            if row_limit > 0 and table_total + ssp_inserted >= row_limit:
                                break

                            if len(row) < 2:
                                continue

                            date_str = row[0]
                            try:
                                obs_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                            except ValueError:
                                continue

                            # 각 행정구역별 값 삽입 (울산 + SK 사업장 시군구만 필터링)
                            for i, admin_code in enumerate(admin_codes):
                                if i + 1 >= len(row):
                                    break

                                # 필터링: 울산(31xxx) 또는 SK 사업장 시군구만
                                if not any(
                                    admin_code.startswith(code) for code in SGG261_FILTER_CODES
                                ):
                                    continue

                                try:
                                    val = float(row[i + 1])
                                except (ValueError, IndexError):
                                    continue

                                if ssp_name == "SSP126":
                                    cursor.execute(
                                        f"""
                                        INSERT INTO {table_name} (admin_code, observation_date, {ssp_col})
                                        VALUES (%s, %s, %s)
                                        ON CONFLICT (observation_date, admin_code)
                                        DO UPDATE SET {ssp_col} = EXCLUDED.{ssp_col}
                                    """,
                                        (admin_code, obs_date, val),
                                    )
                                else:
                                    cursor.execute(
                                        f"""
                                        UPDATE {table_name}
                                        SET {ssp_col} = %s
                                        WHERE admin_code = %s AND observation_date = %s
                                    """,
                                        (val, admin_code, obs_date),
                                    )

                                ssp_inserted += 1

                            # row_limit 체크
                            if row_limit > 0 and table_total + ssp_inserted >= row_limit:
                                break

                        # 파일 단위로 커밋
                        conn.commit()

                        # row_limit 체크
                        if row_limit > 0 and table_total + ssp_inserted >= row_limit:
                            break

                    table_total += ssp_inserted

            except Exception as e:
                logger.warning(f"      {table_name} {ssp_name} 오류: {e}")
                conn.rollback()

            # row_limit 도달하면 다음 SSP 스킵
            if row_limit > 0 and table_total >= row_limit:
                break

        if table_total > 0:
            logger.info(f"      {table_name}: {table_total:,}건 적재 완료")
            results[table_name] = table_total

    return results


def load_climate_geocode():
    """울산 격자 + SK 사업장 역지오코딩 + 전체 기후 데이터 적재"""
    logger = setup_logging("load_climate_geocode")
    logger.info("=" * 60)
    logger.info("울산 격자 + SK사업장 + 전체 기후 데이터 ETL 시작")
    logger.info("=" * 60)

    # API 키 확인
    api_key = os.getenv("VWORLD_API_KEY")
    if not api_key:
        logger.error("VWORLD_API_KEY 환경변수 필요")
        return

    logger.info(f"API Key: {api_key[:10]}...")

    # DB 연결
    try:
        conn = get_db_connection()
        logger.info("데이터베이스 연결 성공")
    except Exception as e:
        logger.error(f"데이터베이스 연결 실패: {e}")
        return

    cursor = conn.cursor()

    # 1. 역지오코딩 컬럼 추가
    logger.info("\nlocation_grid 테이블 컬럼 확인/추가")

    geocode_columns = [
        ("sido", "VARCHAR(50)"),
        ("sigungu", "VARCHAR(50)"),
        ("sigungu_cd", "VARCHAR(10)"),
        ("dong", "VARCHAR(50)"),
        ("bjdong_cd", "VARCHAR(10)"),
        ("dong_code", "VARCHAR(20)"),
        ("full_address", "VARCHAR(200)"),
        ("geocoded_at", "TIMESTAMP"),
    ]

    for col_name, col_type in geocode_columns:
        try:
            cursor.execute(f"""
                ALTER TABLE location_grid
                ADD COLUMN IF NOT EXISTS {col_name} {col_type}
            """)
        except Exception as e:
            logger.warning(f"컬럼 추가 실패 ({col_name}): {e}")

    conn.commit()
    logger.info("   컬럼 확인/추가 완료")

    # 2. 울산 1km 격자 생성 (없으면)
    create_ulsan_1km_grids(conn, cursor, logger)

    # 3. SK 사업장 좌표 삽입
    insert_sk_sites(conn, cursor, logger)

    # 4. 울산 격자 + SK 사업장 역지오코딩 대상 조회 (좌표 기반)
    logger.info("\n[2단계] 역지오코딩 대상 조회 (좌표 기반)")

    # 울산 좌표 범위 격자 중 sido가 NULL인 것
    cursor.execute(
        """
        SELECT grid_id, longitude, latitude
        FROM location_grid
        WHERE latitude BETWEEN %s AND %s
          AND longitude BETWEEN %s AND %s
          AND sido IS NULL
        ORDER BY grid_id
    """,
        (
            ULSAN_BOUNDS["lat_min"],
            ULSAN_BOUNDS["lat_max"],
            ULSAN_BOUNDS["lon_min"],
            ULSAN_BOUNDS["lon_max"],
        ),
    )
    ulsan_grids = cursor.fetchall()
    logger.info(f"   울산 좌표 범위 격자: {len(ulsan_grids)}개 (미완료)")

    # SK 사업장 (full_address가 [SK]로 시작하고 sido가 NULL인 것)
    cursor.execute("""
        SELECT grid_id, longitude, latitude
        FROM location_grid
        WHERE full_address LIKE '[SK]%'
          AND sido IS NULL
        ORDER BY grid_id
    """)
    sk_grids = cursor.fetchall()
    logger.info(f"   SK 사업장: {len(sk_grids)}개 (미완료)")

    # 5. 전체 격자 합치기
    all_grids = sk_grids + list(ulsan_grids)
    total_grids = len(all_grids)

    if total_grids == 0:
        logger.info("   역지오코딩할 격자 없음 (이미 완료)")
    else:
        # SAMPLE_LIMIT 적용
        if SAMPLE_LIMIT > 0 and total_grids > SAMPLE_LIMIT:
            all_grids = all_grids[:SAMPLE_LIMIT]
            logger.info(f"   SAMPLE_LIMIT={SAMPLE_LIMIT} 적용 → {len(all_grids)}개 처리")

        # 6. 역지오코딩 실행
        logger.info(f"\n[4단계] 역지오코딩 실행 (총 {len(all_grids)}개)")

        success_count = 0
        fail_count = 0
        ulsan_count = 0
        sk_count = 0

        for i, (grid_id, lon, lat) in enumerate(all_grids):
            result = geocode_reverse(api_key, float(lat), float(lon), logger)

            if result:
                try:
                    cursor.execute(
                        """
                        UPDATE location_grid
                        SET sido = %s,
                            sigungu = %s,
                            sigungu_cd = %s,
                            dong = %s,
                            bjdong_cd = %s,
                            dong_code = %s,
                            full_address = %s,
                            geocoded_at = CURRENT_TIMESTAMP
                        WHERE grid_id = %s
                    """,
                        (
                            result["sido"],
                            result["sigungu"],
                            result["sigungu_cd"],
                            result["dong"],
                            result["bjdong_cd"],
                            result["dong_code"],
                            result["full_address"],
                            grid_id,
                        ),
                    )
                    success_count += 1

                    if "울산" in result.get("sido", ""):
                        ulsan_count += 1

                    if i < len(sk_grids):
                        sk_count += 1

                except Exception as e:
                    logger.warning(f"DB 업데이트 실패 (grid_id={grid_id}): {e}")
                    fail_count += 1
            else:
                fail_count += 1

            if (i + 1) % 50 == 0:
                logger.info(
                    f"   진행: {i + 1}/{len(all_grids)} (성공: {success_count}, SK: {sk_count}, 울산: {ulsan_count})"
                )
                conn.commit()

            time.sleep(0.1)

        conn.commit()

    # 7. 전체 기후 데이터 로드
    # SK 사업장 + 울산 1km 격자 모두 조회 (좌표 기반 - 지오코딩과 독립)
    cursor.execute(
        """
        SELECT grid_id, longitude, latitude
        FROM location_grid
        WHERE (latitude BETWEEN %s AND %s AND longitude BETWEEN %s AND %s)
           OR full_address LIKE '[SK]%%'
        ORDER BY grid_id
    """,
        (
            ULSAN_BOUNDS["lat_min"],
            ULSAN_BOUNDS["lat_max"],
            ULSAN_BOUNDS["lon_min"],
            ULSAN_BOUNDS["lon_max"],
        ),
    )
    climate_grids = cursor.fetchall()
    logger.info(f"\n[5단계] 전체 기후 데이터 로드 대상: {len(climate_grids)}개 격자")
    if SAMPLE_LIMIT > 0:
        logger.info(f"   ⚠️  SAMPLE_LIMIT={SAMPLE_LIMIT} → 각 테이블당 {SAMPLE_LIMIT}개 row만 적재")

    # SAMPLE_LIMIT가 있으면 각 테이블당 N개 row만 적재
    climate_results = load_climate_data_for_grids(conn, cursor, climate_grids, logger, SAMPLE_LIMIT)

    # 8. sgg261 시군구 단위 일별 데이터 로드
    logger.info(f"\n[6단계] sgg261 일별 기후 데이터 로드")
    if SAMPLE_LIMIT > 0:
        logger.info(f"   ⚠️  SAMPLE_LIMIT={SAMPLE_LIMIT} → 각 테이블당 {SAMPLE_LIMIT}개 row만 적재")

    sgg261_results = load_sgg261_daily_data(conn, cursor, logger, SAMPLE_LIMIT)

    # 9. 결과 요약
    total_geocoded = get_row_count(conn, "location_grid")
    cursor.execute("SELECT COUNT(*) FROM location_grid WHERE sido IS NOT NULL")
    geocoded_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM location_grid WHERE sido LIKE '%울산%'")
    ulsan_total = cursor.fetchone()[0]

    logger.info("\n" + "=" * 60)
    logger.info("울산 격자 + SK사업장 + 전체 기후 데이터 ETL 완료")
    logger.info(f"   [역지오코딩]")
    if total_grids > 0:
        logger.info(f"   - 처리: {len(all_grids)}개 격자")
        logger.info(f"   - 성공: {success_count}개")
        logger.info(f"   - 실패: {fail_count}개")
        logger.info(f"   - SK 사업장: {sk_count}개")
        logger.info(f"   - 울산: {ulsan_count}개 (이번 실행)")
    logger.info(f"   [격자 현황]")
    logger.info(f"   - 전체 격자: {total_geocoded}개")
    logger.info(f"   - 역지오코딩 완료: {geocoded_count}개")
    logger.info(f"   - 울산 총계: {ulsan_total}개")
    logger.info(f"   [기후 데이터 적재 - 격자]")
    for table_name, count in climate_results.items():
        logger.info(f"   - {table_name}: {count:,}건")
    logger.info(f"   [기후 데이터 적재 - sgg261 일별]")
    for table_name, count in sgg261_results.items():
        logger.info(f"   - {table_name}: {count:,}건")
    logger.info("=" * 60)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    load_climate_geocode()
