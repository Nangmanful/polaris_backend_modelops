"""
KMA 기후 데이터 압축 해제 스크립트 (필요한 파일만)
ETL에서 사용하는 변수만 압축 해제하여 기존 경로 구조로 저장

사용법: python extract_kma_files.py
"""

import gzip
import tarfile
import subprocess
from pathlib import Path
from tqdm import tqdm

# ETL에서 사용하는 변수 목록
# 기본 기후 변수
BASIC_VARS = ["TA", "RN", "RHM", "WS", "TAMAX", "TAMIN"]
# 기후 지표 변수 (DB 테이블과 매핑)
INDEX_VARS = [
    "CDD",  # cdd_data: 연속 무강수일
    "CSDI",  # csdi_data: 한랭야 계속기간 지수
    "WSDI",  # wsdi_data: 온난야 계속기간 지수
    "RX1DAY",  # rx1day_data: 1일 최다강수량
    "RX5DAY",  # rx5day_data: 5일 최다강수량
    "SDII",  # sdii_data: 강수강도
    "SPEI12",  # spei12_data: 12개월 SPEI 가뭄지수
    "RAIN80",  # rain80_data: 80mm 이상 강수일수
    "SI",  # si_data: 열지수
]
REQUIRED_VARS = BASIC_VARS + INDEX_VARS


def is_gzip_file(file_path: Path) -> bool:
    """파일이 gzip 압축인지 확인"""
    result = subprocess.run(["file", str(file_path)], capture_output=True, text=True)
    return "gzip" in result.stdout.lower()


def extract_tar_gz_to_dest(src_path: Path, dest_dir: Path) -> list:
    """tar.gz 파일을 압축 해제하여 지정 경로에 저장"""
    extracted_files = []
    try:
        with gzip.open(src_path, "rb") as f:
            with tarfile.open(fileobj=f, mode="r:") as tar:
                for member in tar.getmembers():
                    if member.name.endswith(".nc"):
                        # 파일명만 추출
                        filename = Path(member.name).name
                        dest_path = dest_dir / filename

                        # 파일 추출
                        member.name = filename  # 경로 제거
                        tar.extract(member, dest_dir)
                        extracted_files.append(dest_path)
    except Exception as e:
        print(f"  오류: {src_path.name} - {e}")
    return extracted_files


def is_required_file(filename: str) -> bool:
    """ETL에서 필요한 파일인지 확인"""
    filename_upper = filename.upper()
    for var in REQUIRED_VARS:
        if f"_{var}_" in filename_upper or f"_{var.lower()}_" in filename:
            return True
    return False


def main():
    # 소스 디렉토리 (KMA_REAL)
    base_dir = Path(__file__).parent.parent / "data" / "KMA" / "extracted" / "KMA_REAL"

    # 대상 디렉토리 (기존 경로 구조)
    dest_base = (
        Path(__file__).parent.parent
        / "data"
        / "KMA"
        / "extracted"
        / "KMA"
        / "downloads_kma_ssp_gridraw"
    )

    if not base_dir.exists():
        print(f"소스 디렉토리를 찾을 수 없습니다: {base_dir}")
        return

    # 대상 디렉토리 생성
    dest_base.mkdir(parents=True, exist_ok=True)

    # 모든 .nc 파일 찾기 (gridraw 폴더만)
    nc_files = list(base_dir.glob("**/downloads_kma_ssp_gridraw/**/*.nc"))
    print(f"총 {len(nc_files)}개 파일 발견")

    # 필요한 파일만 필터링
    required_files = []
    for f in nc_files:
        if is_required_file(f.name):
            if is_gzip_file(f):
                required_files.append(f)

    print(f"ETL에 필요한 압축 파일: {len(required_files)}개")

    if not required_files:
        print("압축 해제할 파일이 없습니다.")
        return

    # 필요한 파일 목록 출력
    print("\n압축 해제할 파일:")
    for f in required_files:
        # SSP 이름 추출
        ssp_name = None
        for part in f.parts:
            if part.startswith("SSP"):
                ssp_name = part
                break
        print(f"  - {f.name} ({ssp_name})")

    # 압축 해제
    print(f"\n압축 해제 시작...")
    success_count = 0
    fail_count = 0

    for src_file in tqdm(required_files, desc="압축 해제"):
        # SSP 이름과 폴더 타입(monthly/yearly) 추출
        # 파일명이 아닌 폴더명에서만 추출 (파일명도 SSP로 시작하므로)
        ssp_name = None
        folder_type = None
        for i, part in enumerate(src_file.parts):
            # SSP 폴더 (SSP126, SSP245 등 - 파일명 아님)
            if part.startswith("SSP") and not part.endswith(".nc"):
                ssp_name = part
            if part in ["monthly", "yearly"]:
                folder_type = part

        if not ssp_name or not folder_type:
            print(f"  건너뜀: {src_file.name} (ssp={ssp_name}, type={folder_type})")
            fail_count += 1
            continue

        # 대상 경로 생성
        dest_dir = dest_base / ssp_name / folder_type
        dest_dir.mkdir(parents=True, exist_ok=True)

        # 압축 해제
        extracted = extract_tar_gz_to_dest(src_file, dest_dir)

        if extracted:
            success_count += 1
        else:
            fail_count += 1

    print(f"\n완료!")
    print(f"  성공: {success_count}개")
    print(f"  실패: {fail_count}개")
    print(f"\n파일 저장 위치: {dest_base}")

    # 결과 확인
    print("\n추출된 파일:")
    for ssp in ["SSP126", "SSP245", "SSP370", "SSP585"]:
        ssp_dir = dest_base / ssp
        if ssp_dir.exists():
            monthly_files = (
                list((ssp_dir / "monthly").glob("*.nc")) if (ssp_dir / "monthly").exists() else []
            )
            yearly_files = (
                list((ssp_dir / "yearly").glob("*.nc")) if (ssp_dir / "yearly").exists() else []
            )
            print(f"  {ssp}: monthly={len(monthly_files)}, yearly={len(yearly_files)}")


if __name__ == "__main__":
    main()
