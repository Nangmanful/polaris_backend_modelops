#!/usr/bin/env python3
"""
4개 시군구 sgg261 일별 기후데이터 추가 적재
- 26290 (부산 남구)
- 51230 (삼척시)
- 47280 (문경시)
- 48860 (산청군)
"""

import os
import csv
import io
import tarfile
import logging
from datetime import datetime
from pathlib import Path

import psycopg2

# 추가할 시군구 코드 (sgg261 파일의 10자리 형식 기준)
# - 부산 남구: 2107000000
# - 삼척시: 3207000000
# - 문경시: 3709000000
# - 산청군: 3840000000
NEW_SGG_CODES = {"2107000000", "3207000000", "3709000000", "3840000000"}

SGG261_DAILY_TABLE_MAP = {
    "ta_daily_sgg261": "TA",
    "tamax_daily_sgg261": "TAMAX",
    "tamin_daily_sgg261": "TAMIN",
    "rn_daily_sgg261": "RN",
    "rhm_daily_sgg261": "RHM",
    "ws_daily_sgg261": "WS",
    "si_daily_sgg261": "SI",
}

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("add_4sgg_climate")


def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("DW_DB_HOST", "localhost"),
        port=int(os.environ.get("DW_DB_PORT", 5555)),
        database=os.environ.get("DW_DB_NAME", "datawarehouse"),
        user=os.environ.get("DW_DB_USER", "skala"),
        password=os.environ.get("DW_DB_PASSWORD", "skala1234"),
    )


def main():
    # 데이터 디렉토리: 환경변수 ETL_DATA_DIR 우선, 기본은 레포 내 ETL/etl_base/local/data
    data_dir = Path(
        os.environ.get(
            "ETL_DATA_DIR", str(Path(__file__).resolve().parent / "etl_base" / "local" / "data")
        )
    )
    sgg261_dir = data_dir / "KMA" / "extracted" / "KMA" / "downloads_kma_ssp_sgg261"

    if not sgg261_dir.exists():
        logger.error(f"sgg261 디렉토리 없음: {sgg261_dir}")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    logger.info("=" * 60)
    logger.info("4개 시군구 sgg261 일별 기후데이터 추가 적재")
    logger.info(f"대상 시군구: {NEW_SGG_CODES}")
    logger.info("=" * 60)

    # 먼저 location_sgg261에 4개 시군구 추가
    sgg_info = {
        "2107000000": ("부산광역시", "남구"),
        "3207000000": ("강원특별자치도", "삼척시"),
        "3709000000": ("경상북도", "문경시"),
        "3840000000": ("경상남도", "산청군"),
    }

    for admin_code_10, (sido, sigungu) in sgg_info.items():
        cursor.execute(
            """
            INSERT INTO location_sgg261 (admin_code, sido_name, sigungu_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (admin_code) DO NOTHING
        """,
            (admin_code_10, sido, sigungu),
        )
    conn.commit()
    logger.info(f"location_sgg261에 4개 시군구 추가 완료")

    ssp_dirs = sorted(sgg261_dir.glob("SSP*"))
    # SSP126 먼저
    ssp_dirs = sorted(ssp_dirs, key=lambda x: 0 if "SSP126" in x.name else 1)

    results = {}

    for table_name, var_name in SGG261_DAILY_TABLE_MAP.items():
        logger.info(f"\n[{table_name}] 처리 시작 (변수: {var_name})")
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

            logger.info(f"   {ssp_name}: {asc_file.name} 파싱...")

            ssp_inserted = 0

            try:
                with tarfile.open(asc_file, "r:gz") as tar:
                    members = [m for m in tar.getmembers() if m.name.endswith(".txt")]

                    for member in members:
                        f = tar.extractfile(member)
                        if not f:
                            continue

                        content = f.read().decode("utf-8")
                        reader = csv.reader(io.StringIO(content))
                        rows = list(reader)

                        if len(rows) < 4:
                            continue

                        admin_codes = rows[0][1:]  # 첫 컬럼 제외

                        # 4개 시군구 인덱스 찾기
                        target_indices = []
                        for i, code in enumerate(admin_codes):
                            # 10자리 전체 비교
                            if code in NEW_SGG_CODES:
                                target_indices.append((i, code))

                        if not target_indices:
                            continue

                        # 데이터 행 처리 (Row 3부터)
                        for row in rows[3:]:
                            if len(row) < 2:
                                continue

                            date_str = row[0]
                            try:
                                obs_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                            except ValueError:
                                continue

                            for idx, admin_code in target_indices:
                                if idx + 1 >= len(row):
                                    continue

                                try:
                                    val = float(row[idx + 1])
                                except (ValueError, TypeError):
                                    continue

                                if ssp_name == "SSP126":
                                    cursor.execute(
                                        f"""
                                        INSERT INTO {table_name} (admin_code, observation_date, {ssp_col})
                                        VALUES (%s, %s, %s)
                                        ON CONFLICT (admin_code, observation_date) DO UPDATE SET {ssp_col} = EXCLUDED.{ssp_col}
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

                    conn.commit()

            except Exception as e:
                logger.error(f"   오류: {e}")
                continue

            table_total += ssp_inserted
            logger.info(f"      {ssp_name}: {ssp_inserted:,}건 추가")

        if table_total > 0:
            results[table_name] = table_total
            logger.info(f"   → {table_name} 총: {table_total:,}건")

    cursor.close()
    conn.close()

    logger.info("\n" + "=" * 60)
    logger.info("적재 결과:")
    for table, cnt in results.items():
        logger.info(f"   {table}: {cnt:,}건")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
