"""
SKALA Physical Risk AI System - 행정구역 데이터 적재
GeoJSON/Shapefile에서 시군구 경계 데이터를 location_admin 테이블에 로드

데이터 소스: N3A_G0110000 (시군구 경계 GeoJSON 또는 Shapefile)
대상 테이블: location_admin
예상 데이터: 약 5,000개 행정구역

최종 수정일: 2025-12-03
버전: v02
"""

import sys
import json
from tqdm import tqdm
import geopandas as gpd

from utils import setup_logging, get_db_connection, get_data_dir, table_exists, get_row_count


def load_admin_regions() -> None:
    """시군구 경계 GeoJSON/Shapefile을 location_admin 테이블에 로드"""
    logger = setup_logging("load_admin_regions")
    logger.info("=" * 60)
    logger.info("행정구역 데이터 로딩 시작")
    logger.info("=" * 60)

    # 데이터베이스 연결
    try:
        conn = get_db_connection()
        logger.info("데이터베이스 연결 성공")
    except Exception as e:
        logger.error(f"데이터베이스 연결 실패: {e}")
        sys.exit(1)

    # 테이블 존재 확인
    if not table_exists(conn, "location_admin"):
        logger.error("location_admin 테이블이 존재하지 않습니다")
        conn.close()
        sys.exit(1)

    cursor = conn.cursor()

    # 데이터 파일 찾기 (GeoJSON 또는 Shapefile)
    data_dir = get_data_dir()
    admin_dir = data_dir / "N3A_G0110000"

    if not admin_dir.exists():
        logger.error(f"행정구역 디렉토리를 찾을 수 없습니다: {admin_dir}")
        conn.close()
        sys.exit(1)

    # GeoJSON 먼저 찾고, 없으면 Shapefile 찾기
    geojson_files = list(admin_dir.glob("*.geojson")) + list(admin_dir.glob("*.json"))
    shp_files = list(admin_dir.glob("*.shp"))

    if geojson_files:
        data_files = geojson_files
        file_type = "GeoJSON"
    elif shp_files:
        data_files = shp_files
        file_type = "Shapefile"
    else:
        logger.error(f"GeoJSON 또는 Shapefile을 찾을 수 없습니다")
        conn.close()
        sys.exit(1)

    logger.info(f"{len(data_files)}개 {file_type} 파일 발견")

    # 기존 데이터 확인 및 삭제
    existing_count = get_row_count(conn, "location_admin")
    if existing_count > 0:
        logger.warning(f"기존 데이터 {existing_count:,}개 삭제")
        cursor.execute("TRUNCATE TABLE location_admin CASCADE")
        conn.commit()

    # 데이터 로드 (geopandas 사용 - GeoJSON/Shapefile 모두 지원)
    insert_count = 0
    error_count = 0

    for data_file in data_files:
        logger.info(f"처리 중: {data_file.name}")

        try:
            # geopandas로 읽기 (GeoJSON, Shapefile 모두 지원)
            gdf = gpd.read_file(data_file)

            # 좌표계 변환 (EPSG:4326으로 통일)
            if gdf.crs and gdf.crs.to_epsg() != 4326:
                logger.info(f"   좌표계 변환: {gdf.crs} → EPSG:4326")
                gdf = gdf.to_crs(epsg=4326)

            logger.info(f"   {len(gdf):,}개 피처 발견")
            logger.info(f"   컬럼: {list(gdf.columns)}")

            for idx, row in tqdm(gdf.iterrows(), total=len(gdf), desc=f"  {data_file.name}"):
                try:
                    # 속성 추출 (다양한 컬럼명 지원)
                    admin_code = str(
                        row.get(
                            "ADM_CD", row.get("adm_cd", row.get("SIG_CD", row.get("EMD_CD", "")))
                        )
                    )
                    admin_name = str(
                        row.get(
                            "ADM_NM",
                            row.get("adm_nm", row.get("SIG_KOR_NM", row.get("EMD_KOR_NM", ""))),
                        )
                    )

                    # 컬럼명이 없으면 다른 컬럼 시도
                    if not admin_code or admin_code == "nan":
                        for col in gdf.columns:
                            if "CD" in col.upper() and col.upper() != "GEOMETRY":
                                admin_code = str(row.get(col, ""))
                                break

                    if not admin_name or admin_name == "nan":
                        for col in gdf.columns:
                            if "NM" in col.upper() or "NAME" in col.upper():
                                admin_name = str(row.get(col, ""))
                                break

                    geom = row.geometry
                    if geom is None or geom.is_empty:
                        continue

                    # GeoJSON 형식으로 변환
                    geom_json = json.dumps(geom.__geo_interface__)

                    # 코드 파싱
                    sido_code = admin_code[:2] if len(admin_code) >= 2 else None
                    sigungu_code = admin_code[:5] if len(admin_code) >= 5 else None
                    emd_code = admin_code[:8] if len(admin_code) >= 8 else None

                    # 레벨 결정 (코드 길이로)
                    if len(admin_code) >= 8:
                        level = 3  # 읍면동
                    elif len(admin_code) >= 5:
                        level = 2  # 시군구
                    else:
                        level = 1  # 시도

                    # 테이블 SRID가 5174이므로 좌표 변환 수행
                    # ST_Multi()로 Polygon을 MultiPolygon으로 변환 (테이블 타입 호환성)
                    cursor.execute(
                        """
                        INSERT INTO location_admin (
                            admin_code, admin_name, level,
                            sido_code, sigungu_code, emd_code,
                            geom, centroid
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s,
                            ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 5174)),
                            ST_Centroid(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 5174))
                        )
                    """,
                        (
                            admin_code,
                            admin_name,
                            level,
                            sido_code,
                            sigungu_code,
                            emd_code,
                            geom_json,
                            geom_json,
                        ),
                    )
                    insert_count += 1

                except Exception as e:
                    error_count += 1
                    conn.rollback()  # 트랜잭션 롤백으로 연쇄 오류 방지
                    if error_count <= 5:
                        logger.warning(f"피처 처리 오류: {e}")

            conn.commit()

        except Exception as e:
            logger.error(f"파일 처리 오류 ({data_file.name}): {e}")
            error_count += 1

    # 결과 출력
    final_count = get_row_count(conn, "location_admin")

    logger.info("=" * 60)
    logger.info("행정구역 데이터 로딩 완료")
    logger.info(f"   - 삽입: {insert_count:,}개")
    logger.info(f"   - 오류: {error_count:,}개")
    logger.info(f"   - 최종: {final_count:,}개")
    logger.info("=" * 60)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    load_admin_regions()
