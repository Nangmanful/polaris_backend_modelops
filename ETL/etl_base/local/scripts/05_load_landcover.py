"""
SKALA Physical Risk AI System - 토지피복 데이터 적재
GeoTIFF 파일에서 토지피복 래스터를 raw_landcover 테이블에 로드

데이터 소스: landcover/**/*.tif + landcover/**/*.zip (ZIP 내 TIF 포함)
대상 테이블: raw_landcover
예상 데이터: 약 239개 타일

최종 수정일: 2025-12-12
버전: v03 - ZIP 압축 해제 지원
"""

import sys
import subprocess
import tempfile
import os
import zipfile
import shutil
from pathlib import Path
from tqdm import tqdm

from utils import setup_logging, get_db_connection, get_data_dir, get_row_count

# SAMPLE_LIMIT: TIF 파일 개수 제한 (테스트용)
SAMPLE_LIMIT = int(os.environ.get("SAMPLE_LIMIT", 0))  # 0 = 전체


def get_tif_srid(tif_path: Path) -> str:
    """
    GeoTIFF 파일의 SRID를 감지

    Args:
        tif_path: TIF 파일 경로

    Returns:
        SRID 문자열 (예: "5174", "2097")
    """
    try:
        result = subprocess.run(
            ["gdalsrsinfo", "-o", "epsg", str(tif_path)], capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip()
        if output.startswith("EPSG:"):
            return output.replace("EPSG:", "")
    except:
        pass

    # Tokyo/Bessel 좌표계인 경우 Korea 1985 Central Belt (2097) 사용
    try:
        result = subprocess.run(
            ["gdalinfo", str(tif_path)], capture_output=True, text=True, timeout=30
        )
        if "Tokyo" in result.stdout or "Bessel" in result.stdout:
            return "2097"  # Korea 1985 / Central Belt
    except:
        pass

    return "5174"  # 기본값


def load_tif_to_postgres(
    tif_path: Path, table_name: str, append: bool = False, logger=None, srid: str = None
) -> bool:
    """
    GeoTIFF 파일을 PostgreSQL raster 테이블에 로드

    Args:
        tif_path: TIF 파일 경로
        table_name: 대상 테이블 이름
        append: True면 기존 테이블에 추가
        logger: 로거 인스턴스
        srid: SRID (None이면 자동 감지)

    Returns:
        성공 여부
    """
    try:
        db_host = os.getenv("DW_DB_HOST", "localhost")
        db_port = os.getenv("DW_DB_PORT", "5555")
        db_name = os.getenv("DW_DB_NAME", "datawarehouse")
        db_user = os.getenv("DW_DB_USER", "skala")
        db_password = os.getenv("DW_DB_PASSWORD", "skala1234")

        # SRID 자동 감지
        if srid is None:
            srid = get_tif_srid(tif_path)
            if logger:
                logger.info(f"   SRID 감지: {srid}")

        # raster2pgsql 명령 구성
        # 주의: -C (constraints) 옵션은 첫 파일의 extent로 제약조건을 만들어
        # 다른 영역의 파일 삽입을 막으므로 사용하지 않음
        cmd = ["raster2pgsql"]
        if append:
            cmd.extend(["-a", "-F", "-t", "100x100", "-s", srid])
        else:
            # create 모드: 인덱스만 생성 (-I), 제약조건(-C) 제외
            cmd.extend(["-c", "-I", "-M", "-F", "-t", "100x100", "-s", srid])
        cmd.extend([str(tif_path), table_name])

        raster_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        psql_cmd = ["psql", "-h", db_host, "-p", db_port, "-U", db_user, "-d", db_name, "-q"]
        psql_env = os.environ.copy()
        if db_password:
            psql_env["PGPASSWORD"] = db_password

        psql_proc = subprocess.Popen(
            psql_cmd,
            stdin=raster_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=psql_env,
        )

        raster_proc.stdout.close()
        stdout, stderr = psql_proc.communicate(timeout=120)

        if psql_proc.returncode != 0:
            if logger:
                logger.warning(f"raster2pgsql 실패: {stderr.decode()[:200]}")
            return False

        return True

    except Exception as e:
        if logger:
            logger.warning(f"오류: {e}")
        return False


def load_landcover() -> None:
    """토지피복 GeoTIFF를 raw_landcover 테이블에 로드 (ZIP 압축 해제 포함)"""
    logger = setup_logging("load_landcover")
    logger.info("=" * 60)
    logger.info("토지피복 데이터 로딩 시작")
    logger.info("=" * 60)

    try:
        conn = get_db_connection()
        logger.info("데이터베이스 연결 성공")
    except Exception as e:
        logger.error(f"데이터베이스 연결 실패: {e}")
        sys.exit(1)

    cursor = conn.cursor()

    # TIF 파일 찾기
    data_dir = get_data_dir()
    landcover_dir = data_dir / "landcover"

    if not landcover_dir.exists():
        logger.error(f"landcover 디렉토리를 찾을 수 없습니다: {landcover_dir}")
        conn.close()
        sys.exit(1)

    # 1. 직접 TIF 파일 찾기
    direct_tif_files = list(landcover_dir.glob("**/*.tif"))
    logger.info(f"직접 TIF 파일: {len(direct_tif_files)}개")

    # 2. ZIP 파일 찾기 및 압축 해제 (직접 TIF가 충분하면 건너뛰기)
    zip_files = list(landcover_dir.glob("**/*.zip"))
    logger.info(f"ZIP 파일: {len(zip_files)}개")

    # 임시 디렉토리에 ZIP 압축 해제
    tmp_dir = Path(tempfile.mkdtemp(prefix="landcover_"))
    extracted_tif_files = []

    # 직접 TIF가 ZIP 파일 수보다 많으면 이미 압축 해제된 것으로 판단
    if zip_files and len(direct_tif_files) <= len(zip_files):
        logger.info("ZIP 파일 압축 해제 중...")
        for zip_path in tqdm(zip_files, desc="ZIP 압축 해제"):
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    for name in zf.namelist():
                        if name.lower().endswith(".tif"):
                            # TIF 파일만 추출
                            zf.extract(name, tmp_dir)
                            extracted_tif_files.append(tmp_dir / name)
            except Exception as e:
                logger.warning(f"ZIP 압축 해제 실패 ({zip_path.name}): {e}")

        logger.info(f"ZIP에서 추출한 TIF: {len(extracted_tif_files)}개")
    elif zip_files:
        logger.info("직접 TIF 파일이 충분함 - ZIP 압축 해제 건너뜀")

    # 3. 모든 TIF 파일 합치기
    tif_files = direct_tif_files + extracted_tif_files
    logger.info(f"총 TIF 파일: {len(tif_files)}개")

    # SAMPLE_LIMIT 적용
    if SAMPLE_LIMIT > 0 and len(tif_files) > SAMPLE_LIMIT:
        tif_files = tif_files[:SAMPLE_LIMIT]
        logger.info(f"SAMPLE_LIMIT={SAMPLE_LIMIT} 적용 → {len(tif_files)}개 처리")

    if not tif_files:
        logger.warning("TIF 파일이 없습니다")
        conn.close()
        # 임시 디렉토리 정리
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    conn.close()

    # 기존 테이블 삭제 (psql로 직접 실행해야 raster2pgsql이 새 테이블 생성 가능)
    logger.info("기존 테이블 삭제")
    db_host = os.getenv("DW_DB_HOST", "localhost")
    db_port = os.getenv("DW_DB_PORT", "5555")
    db_name = os.getenv("DW_DB_NAME", "datawarehouse")
    db_user = os.getenv("DW_DB_USER", "skala")
    db_password = os.getenv("DW_DB_PASSWORD", "skala1234")

    drop_env = os.environ.copy()
    drop_env["PGPASSWORD"] = db_password
    subprocess.run(
        [
            "psql",
            "-h",
            db_host,
            "-p",
            db_port,
            "-U",
            db_user,
            "-d",
            db_name,
            "-c",
            "DROP TABLE IF EXISTS raw_landcover CASCADE;",
        ],
        env=drop_env,
        capture_output=True,
    )

    # TIF 파일 로드
    success_count = 0
    error_count = 0
    first_file = True

    for tif_file in tqdm(tif_files, desc="TIF 로딩"):
        success = load_tif_to_postgres(
            tif_file, "raw_landcover", append=not first_file, logger=logger
        )

        if success:
            success_count += 1
            first_file = False
        else:
            error_count += 1

    # 임시 디렉토리 정리
    logger.info("임시 파일 정리 중...")
    shutil.rmtree(tmp_dir, ignore_errors=True)

    # 결과 확인
    conn = get_db_connection()
    final_count = get_row_count(conn, "raw_landcover")
    conn.close()

    logger.info("=" * 60)
    logger.info("토지피복 데이터 로딩 완료")
    logger.info(f"   - 성공: {success_count}개 파일")
    logger.info(f"   - 실패: {error_count}개 파일")
    logger.info(f"   - 최종: {final_count:,}개 타일")
    logger.info("=" * 60)


if __name__ == "__main__":
    load_landcover()
