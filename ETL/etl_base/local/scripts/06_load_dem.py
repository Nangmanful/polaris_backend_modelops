"""
SKALA Physical Risk AI System - DEM 데이터 적재
ZIP 파일 또는 압축 해제된 폴더에서 ASCII DEM을 로드하여 raw_dem 테이블에 적재

데이터 소스: DEM/*.zip 또는 DEM/*_ascii/ 폴더 (ASCII XYZ 포맷)
대상 테이블: raw_dem (Point geometry)
예상 데이터: 약 500,000개 포인트

최종 수정일: 2025-12-12
버전: v02 - 압축 해제된 폴더 우선 지원
"""

import sys
import os
import zipfile
import re
import unicodedata
from pathlib import Path
from tqdm import tqdm

from utils import setup_logging, get_db_connection, get_data_dir, get_row_count

# SAMPLE_LIMIT: 소스(폴더/ZIP) 개수 제한 (테스트용)
SAMPLE_LIMIT = int(os.environ.get("SAMPLE_LIMIT", 0))  # 0 = 전체

# 대상 지역 필터 (SK 사업장 + 울산)
TARGET_REGIONS = [
    "경기도",  # SK u-타워, 판교 캠퍼스, 수내 오피스, 판교 DC
    "서울특별시",  # 서린 사옥, 보라매 DC, 애커튼 파트너스
    "대전광역시",  # 대덕 데이터 센터
    "울산광역시",  # 울산 지역
]


def extract_zip_with_korean(zip_path: Path, extract_dir: Path) -> list:
    """
    한글 파일명이 포함된 ZIP 파일 압축 해제

    Args:
        zip_path: ZIP 파일 경로
        extract_dir: 압축 해제 디렉토리

    Returns:
        추출된 파일 경로 리스트
    """
    extracted_files = []

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                try:
                    # CP437 → EUC-KR 변환 (한글 인코딩 문제 해결)
                    decoded_name = info.filename.encode("cp437").decode("euc-kr")
                except:
                    decoded_name = info.filename

                info.filename = decoded_name
                extracted_path = extract_dir / decoded_name
                zf.extract(info, extract_dir)
                extracted_files.append(extracted_path)

    except Exception as e:
        raise Exception(f"ZIP 압축 해제 실패: {e}")

    return extracted_files


def load_dem() -> None:
    """DEM ASCII 데이터를 raw_dem 테이블에 로드 (Point geometry)"""
    logger = setup_logging("load_dem")
    logger.info("=" * 60)
    logger.info("DEM 데이터 로딩 시작")
    logger.info("=" * 60)

    try:
        conn = get_db_connection()
        logger.info("데이터베이스 연결 성공")
    except Exception as e:
        logger.error(f"데이터베이스 연결 실패: {e}")
        sys.exit(1)

    cursor = conn.cursor()

    data_dir = get_data_dir()
    dem_dir = data_dir / "DEM"

    if not dem_dir.exists():
        logger.error(f"DEM 디렉토리를 찾을 수 없습니다: {dem_dir}")
        conn.close()
        sys.exit(1)

    # 1. 압축 해제된 폴더 먼저 찾기 (우선순위)
    all_dirs = [d for d in dem_dir.iterdir() if d.is_dir() and "_ascii" in d.name]
    all_zips = list(dem_dir.glob("*.zip"))

    # TARGET_REGIONS 필터 적용 (macOS NFD → NFC 정규화)
    def matches_target_region(name: str) -> bool:
        normalized_name = unicodedata.normalize("NFC", name)
        return any(region in normalized_name for region in TARGET_REGIONS)

    extracted_dirs = [d for d in all_dirs if matches_target_region(d.name)]
    zip_files = [z for z in all_zips if matches_target_region(z.name)]

    # 이미 폴더가 있는 ZIP은 제외 (NFC 정규화 적용)
    extracted_regions = set()
    for d in extracted_dirs:
        match = re.search(r"_(.+?)_ascii", d.name)
        if match:
            # NFC 정규화하여 저장
            extracted_regions.add(unicodedata.normalize("NFC", match.group(1)))

    # ZIP 필터링 시에도 NFC 정규화하여 비교
    zip_files = [
        z
        for z in zip_files
        if not any(region in unicodedata.normalize("NFC", z.name) for region in extracted_regions)
    ]

    logger.info(f"대상 지역: {TARGET_REGIONS}")
    logger.info(f"압축 해제된 폴더: {len(extracted_dirs)}개 (전체 {len(all_dirs)}개 중)")
    logger.info(f"처리할 ZIP 파일: {len(zip_files)}개")

    total_sources = len(extracted_dirs) + len(zip_files)
    if total_sources == 0:
        logger.warning("처리할 DEM 데이터가 없습니다")
        conn.close()
        return

    # SAMPLE_LIMIT 적용
    if SAMPLE_LIMIT > 0 and total_sources > SAMPLE_LIMIT:
        # 폴더 우선, 나머지 ZIP
        if len(extracted_dirs) >= SAMPLE_LIMIT:
            extracted_dirs = extracted_dirs[:SAMPLE_LIMIT]
            zip_files = []
        else:
            remaining = SAMPLE_LIMIT - len(extracted_dirs)
            zip_files = zip_files[:remaining]
        logger.info(
            f"   SAMPLE_LIMIT={SAMPLE_LIMIT} 적용 → 폴더 {len(extracted_dirs)}개, ZIP {len(zip_files)}개"
        )

    # 테이블 재생성 (Point geometry 기반)
    logger.info("테이블 재생성 (Point geometry)")
    cursor.execute("DROP TABLE IF EXISTS raw_dem CASCADE;")
    cursor.execute("""
        CREATE TABLE raw_dem (
            rid SERIAL PRIMARY KEY,
            x DOUBLE PRECISION NOT NULL,
            y DOUBLE PRECISION NOT NULL,
            elevation DOUBLE PRECISION NOT NULL,
            region VARCHAR(100),
            geom GEOMETRY(Point, 5186)
        );
    """)
    conn.commit()

    insert_count = 0
    error_count = 0
    batch_data = []
    batch_size = 10000

    def process_txt_file(txt_file: Path, region_name: str):
        """txt 파일 처리 - 배치 데이터에 추가"""
        nonlocal insert_count, error_count, batch_data

        try:
            # 여러 인코딩 시도
            encodings = ["utf-8", "cp949", "euc-kr"]
            content = None
            for enc in encodings:
                try:
                    with open(txt_file, "r", encoding=enc) as f:
                        content = f.readlines()
                    break
                except UnicodeDecodeError:
                    continue

            if content is None:
                error_count += 1
                return

            for line in content:
                parts = line.strip().split()
                if len(parts) >= 3:
                    try:
                        x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                        batch_data.append((x, y, z, region_name, x, y))

                        if len(batch_data) >= batch_size:
                            cursor.executemany(
                                """
                                INSERT INTO raw_dem (x, y, elevation, region, geom)
                                VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 5186))
                            """,
                                batch_data,
                            )
                            insert_count += len(batch_data)
                            batch_data = []
                            conn.commit()
                    except ValueError:
                        continue
        except Exception as e:
            error_count += 1
            if error_count <= 5:
                logger.warning(f"파일 처리 오류 ({txt_file.name}): {e}")

    # 2. 압축 해제된 폴더 처리 (빠름)
    for extract_dir in tqdm(extracted_dirs, desc="폴더 처리"):
        match = re.search(r"_(.+?)_ascii", extract_dir.name)
        region_name = match.group(1) if match else "Unknown"

        txt_files = list(extract_dir.glob("*.txt"))
        for txt_file in txt_files:
            process_txt_file(txt_file, region_name)

        conn.commit()

    # 3. ZIP 파일 처리 (폴더가 없는 경우만)
    import tempfile

    tmp_dir = Path(tempfile.mkdtemp())

    for zip_file in tqdm(zip_files, desc="ZIP 처리"):
        match = re.search(r"_(.+?)_ascii", zip_file.name)
        region_name = match.group(1) if match else "Unknown"

        try:
            extracted_files = extract_zip_with_korean(zip_file, tmp_dir)
            txt_files = [f for f in extracted_files if str(f).endswith(".txt")]

            for txt_file in txt_files:
                process_txt_file(txt_file, region_name)
                try:
                    txt_file.unlink()  # 임시 파일 삭제
                except:
                    pass

        except Exception as e:
            error_count += 1
            logger.warning(f"ZIP 처리 오류 ({zip_file.name}): {e}")

    # 남은 배치 처리
    if batch_data:
        cursor.executemany(
            """
            INSERT INTO raw_dem (x, y, elevation, region, geom)
            VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 5186))
        """,
            batch_data,
        )
        insert_count += len(batch_data)
        conn.commit()

    # 인덱스 생성
    logger.info("인덱스 생성")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_dem_geom ON raw_dem USING GIST (geom);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_dem_region ON raw_dem (region);")
    conn.commit()

    # 임시 디렉토리 정리
    try:
        import shutil

        shutil.rmtree(tmp_dir)
    except:
        pass

    # 결과 확인
    final_count = get_row_count(conn, "raw_dem")

    logger.info("=" * 60)
    logger.info("DEM 데이터 로딩 완료")
    logger.info(f"   - 삽입: {insert_count:,}개 포인트")
    logger.info(f"   - 오류: {error_count:,}개")
    logger.info(f"   - 최종: {final_count:,}개")
    logger.info("=" * 60)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    load_dem()
