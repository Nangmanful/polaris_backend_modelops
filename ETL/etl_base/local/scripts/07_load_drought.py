"""
SKALA Physical Risk AI System - 가뭄 데이터 적재
HDF/NetCDF 파일을 GeoTIFF로 변환 후 raw_drought 래스터 테이블에 로드

데이터 소스: drought/*.hdf, drought/*.h5, drought/*.nc
대상 테이블: raw_drought (raster)
예상 데이터: 약 10개 타일

최종 수정일: 2025-12-03
버전: v04
"""

import sys
import subprocess
import tempfile
import os
from pathlib import Path
from tqdm import tqdm

from utils import setup_logging, get_db_connection, get_data_dir, get_row_count


def hdf5_to_geotiff(h5_path: Path, output_dir: Path, logger=None) -> list:
    """
    HDF5 파일을 GeoTIFF로 변환

    Args:
        h5_path: HDF5 파일 경로
        output_dir: 출력 디렉토리
        logger: 로거

    Returns:
        생성된 GeoTIFF 파일 경로 리스트
    """
    tif_files = []

    # SMAP L4 데이터셋 목록
    datasets = [
        "Analysis_Data/sm_surface_analysis",
        "Analysis_Data/sm_rootzone_analysis",
    ]

    for dataset in datasets:
        var_name = dataset.split("/")[-1]
        output_tif = output_dir / f"{h5_path.stem}_{var_name}.tif"

        try:
            # gdal_translate로 HDF5 서브데이터셋을 GeoTIFF로 변환
            cmd = ["gdal_translate", "-q", f'HDF5:"{h5_path}"://{dataset}', str(output_tif)]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode == 0 and output_tif.exists():
                tif_files.append(output_tif)
                if logger:
                    logger.info(f"   변환 성공: {var_name}")
            else:
                if logger:
                    logger.warning(f"   변환 실패: {var_name} - {result.stderr[:100]}")

        except Exception as e:
            if logger:
                logger.warning(f"   변환 오류: {var_name} - {e}")

    return tif_files


def load_tif_to_raster(tif_path: Path, table_name: str, append: bool = False, logger=None) -> bool:
    """
    GeoTIFF를 PostgreSQL raster 테이블에 로드

    Args:
        tif_path: TIF 파일 경로
        table_name: 테이블 이름
        append: 추가 모드 여부
        logger: 로거

    Returns:
        성공 여부
    """
    try:
        db_host = os.getenv("DW_HOST", "localhost")
        db_port = os.getenv("DW_PORT", "5434")
        db_name = os.getenv("DW_NAME", "skala_datawarehouse")
        db_user = os.getenv("DW_USER", "skala_dw_user")
        db_password = os.getenv("DW_PASSWORD", "skala_dw_2025")

        # raster2pgsql 명령
        cmd = ["raster2pgsql"]
        cmd.append("-a" if append else "-c")
        cmd.extend(["-I", "-C", "-M", "-F", "-t", "100x100", "-s", "4326"])
        cmd.extend([str(tif_path), table_name])

        raster_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        psql_cmd = ["psql", "-h", db_host, "-p", db_port, "-U", db_user, "-d", db_name, "-q"]
        psql_env = os.environ.copy()
        psql_env["PGPASSWORD"] = db_password

        psql_proc = subprocess.Popen(
            psql_cmd,
            stdin=raster_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=psql_env,
        )

        raster_proc.stdout.close()
        _, stderr = psql_proc.communicate(timeout=120)

        if psql_proc.returncode != 0:
            if logger:
                logger.warning(f"   raster2pgsql 실패: {stderr.decode()[:100]}")
            return False

        return True

    except Exception as e:
        if logger:
            logger.warning(f"   적재 오류: {e}")
        return False


def load_drought() -> None:
    """가뭄 데이터를 raw_drought 래스터 테이블에 로드"""
    logger = setup_logging("load_drought")
    logger.info("=" * 60)
    logger.info("가뭄 데이터 로딩 시작 (래스터 방식)")
    logger.info("=" * 60)

    try:
        conn = get_db_connection()
        logger.info("데이터베이스 연결 성공")
    except Exception as e:
        logger.error(f"데이터베이스 연결 실패: {e}")
        sys.exit(1)

    conn.close()

    # 데이터 파일 찾기
    data_dir = get_data_dir()
    drought_dir = data_dir / "drought"

    if not drought_dir.exists():
        logger.warning(f"drought 디렉토리를 찾을 수 없습니다: {drought_dir}")
        drought_dir = data_dir / "KMA" / "extracted"

    # HDF5, NetCDF 파일 찾기
    h5_files = list(drought_dir.glob("**/*.h5"))
    nc_files = list(drought_dir.glob("**/*drought*.nc")) + list(drought_dir.glob("**/*spei*.nc"))
    hdf_files = list(drought_dir.glob("**/*.hdf"))

    logger.info(f"HDF5 파일: {len(h5_files)}개")
    logger.info(f"NetCDF 파일: {len(nc_files)}개")
    logger.info(f"HDF4 파일: {len(hdf_files)}개")

    # 기존 테이블 삭제 (psql로)
    logger.info("기존 테이블 삭제")
    db_host = os.getenv("DW_HOST", "localhost")
    db_port = os.getenv("DW_PORT", "5434")
    db_name = os.getenv("DW_NAME", "skala_datawarehouse")
    db_user = os.getenv("DW_USER", "skala_dw_user")
    db_password = os.getenv("DW_PASSWORD", "skala_dw_2025")

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
            "DROP TABLE IF EXISTS raw_drought CASCADE;",
        ],
        env=drop_env,
        capture_output=True,
    )

    # 임시 디렉토리
    tmp_dir = Path(tempfile.mkdtemp())
    success_count = 0
    error_count = 0
    first_file = True

    # HDF5 파일 처리
    for h5_file in tqdm(h5_files, desc="HDF5 변환"):
        logger.info(f"처리 중: {h5_file.name}")
        tif_files = hdf5_to_geotiff(h5_file, tmp_dir, logger)

        for tif_file in tif_files:
            success = load_tif_to_raster(
                tif_file, "raw_drought", append=not first_file, logger=logger
            )
            if success:
                success_count += 1
                first_file = False
            else:
                error_count += 1

            # 임시 파일 삭제
            try:
                tif_file.unlink()
            except:
                pass

    # NetCDF 파일 처리 (gdal_translate 지원)
    for nc_file in tqdm(nc_files, desc="NetCDF 처리"):
        output_tif = tmp_dir / f"{nc_file.stem}.tif"
        try:
            result = subprocess.run(
                ["gdal_translate", "-q", str(nc_file), str(output_tif)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0 and output_tif.exists():
                success = load_tif_to_raster(
                    output_tif, "raw_drought", append=not first_file, logger=logger
                )
                if success:
                    success_count += 1
                    first_file = False
                else:
                    error_count += 1
                output_tif.unlink()
        except Exception as e:
            error_count += 1
            logger.warning(f"NetCDF 처리 오류: {e}")

    # 임시 디렉토리 정리
    try:
        import shutil

        shutil.rmtree(tmp_dir)
    except:
        pass

    # 결과 확인
    conn = get_db_connection()
    final_count = get_row_count(conn, "raw_drought")
    conn.close()

    logger.info("=" * 60)
    logger.info("가뭄 데이터 로딩 완료")
    logger.info(f"   - 성공: {success_count}개 파일")
    logger.info(f"   - 실패: {error_count}개 파일")
    logger.info(f"   - 최종: {final_count:,}개 타일")
    logger.info("=" * 60)


if __name__ == "__main__":
    load_drought()
