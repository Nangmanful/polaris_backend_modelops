"""
SKALA Physical Risk AI System - 그리드-관측소 매핑 데이터 적재
JSON 파일에서 그리드별 최근접 관측소 매핑을 로드

데이터 소스: grid_to_nearest_stations.json (67MB)
대상 테이블: grid_station_mappings
예상 데이터: 약 290,000개 매핑

최종 수정일: 2025-12-03
버전: v02
"""

import sys
import json
from tqdm import tqdm

from utils import setup_logging, get_db_connection, get_data_dir, table_exists, get_row_count


def load_grid_station_mappings() -> None:
    """그리드-관측소 매핑 JSON을 grid_station_mappings 테이블에 로드"""
    logger = setup_logging("load_grid_station_mappings")
    logger.info("=" * 60)
    logger.info("그리드-관측소 매핑 데이터 로딩 시작")
    logger.info("=" * 60)

    try:
        conn = get_db_connection()
        logger.info("데이터베이스 연결 성공")
    except Exception as e:
        logger.error(f"데이터베이스 연결 실패: {e}")
        sys.exit(1)

    if not table_exists(conn, "grid_station_mappings"):
        logger.error("grid_station_mappings 테이블이 존재하지 않습니다")
        conn.close()
        sys.exit(1)

    cursor = conn.cursor()

    # JSON 파일 찾기
    data_dir = get_data_dir()
    json_files = list(data_dir.glob("*grid*nearest*.json"))

    if not json_files:
        logger.error(f"grid mapping JSON 파일을 찾을 수 없습니다")
        conn.close()
        sys.exit(1)

    json_file = json_files[0]
    logger.info(f"데이터 파일: {json_file.name}")
    logger.info(f"   파일 크기: {json_file.stat().st_size / 1024 / 1024:.1f} MB")

    # 기존 데이터 삭제
    existing_count = get_row_count(conn, "grid_station_mappings")
    if existing_count > 0:
        logger.warning(f"기존 데이터 {existing_count:,}개 삭제")
        cursor.execute("TRUNCATE TABLE grid_station_mappings")
        conn.commit()

    # JSON 로드 (대용량 파일)
    logger.info("JSON 파일 읽는 중... (대용량 파일, 잠시 기다려주세요)")
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            mappings = json.load(f)
    except Exception as e:
        logger.error(f"JSON 파일 읽기 실패: {e}")
        conn.close()
        sys.exit(1)

    # grid_mapping 키가 있으면 그것을 사용
    if isinstance(mappings, dict) and "grid_mapping" in mappings:
        actual_mappings = mappings["grid_mapping"]
        logger.info(f"   메타데이터: k_nearest={mappings.get('k_nearest')}")
    else:
        actual_mappings = mappings

    logger.info(f"{len(actual_mappings):,}개 그리드 매핑 발견")

    # 데이터 삽입 (배치 처리)
    insert_count = 0
    error_count = 0
    batch_size = 5000

    items = list(actual_mappings.items()) if isinstance(actual_mappings, dict) else actual_mappings

    for i in tqdm(range(0, len(items), batch_size), desc="매핑 로딩"):
        batch = items[i : i + batch_size]

        for item in batch:
            try:
                if isinstance(item, tuple):
                    grid_key, station_info = item
                else:
                    grid_key = item.get("grid_id", item.get("grid_key"))
                    station_info = item

                # grid_key 파싱 (실제 데이터: "row,col" 형식 또는 "lon_lat" 형식)
                if isinstance(grid_key, str):
                    if "," in grid_key:
                        # "row,col" 형식 - lat/lon은 station_info에서 추출
                        grid_lat = station_info.get("lat")
                        grid_lon = station_info.get("lon")
                    elif "_" in grid_key:
                        parts = grid_key.split("_")
                        grid_lon = float(parts[0])
                        grid_lat = float(parts[1])
                    else:
                        continue
                elif isinstance(grid_key, (list, tuple)):
                    grid_lon, grid_lat = float(grid_key[0]), float(grid_key[1])
                else:
                    continue

                if not grid_lat or not grid_lon:
                    continue

                # station_info에서 관측소 정보 추출
                # 실제 데이터 형식: {"lat": 33.21, "lon": 126.28, "nearest_stations": [...]}
                if isinstance(station_info, dict):
                    nearest_stations = station_info.get("nearest_stations", [])

                    if nearest_stations:
                        # 가장 가까운 관측소 사용
                        nearest = nearest_stations[0]
                        station_id = nearest.get("obscd", nearest.get("station_id"))
                        distance = nearest.get("distance_km", nearest.get("distance"))
                    else:
                        station_id = station_info.get("station_id", station_info.get("obscd"))
                        distance = station_info.get("distance_km", station_info.get("distance"))
                elif isinstance(station_info, (list, tuple)):
                    station_id = station_info[0] if len(station_info) > 0 else None
                    distance = station_info[1] if len(station_info) > 1 else None
                else:
                    station_id = station_info
                    distance = None

                # 실제 테이블 구조: grid_lat, grid_lon, basin_code, basin_name,
                # station_rank (1-3), obscd, obsnm, station_lat, station_lon, distance_km, geom
                basin_code = station_info.get("basin_code")
                basin_name = station_info.get("basin_name")
                nearest_stations = station_info.get("nearest_stations", [])

                # 최대 3개 관측소 삽입 (station_rank 1, 2, 3)
                for rank, station in enumerate(nearest_stations[:3], start=1):
                    obscd = station.get("obscd")
                    if not obscd:
                        continue

                    obsnm = station.get("obsnm")
                    station_lat = station.get("lat")
                    station_lon = station.get("lon")
                    distance = station.get("distance_km")

                    cursor.execute(
                        """
                        INSERT INTO grid_station_mappings (
                            grid_lat, grid_lon, basin_code, basin_name,
                            station_rank, obscd, obsnm, station_lat, station_lon,
                            distance_km, geom
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                        )
                    """,
                        (
                            grid_lat,
                            grid_lon,
                            basin_code,
                            basin_name,
                            rank,
                            obscd,
                            obsnm,
                            station_lat,
                            station_lon,
                            distance,
                            grid_lon,
                            grid_lat,
                        ),
                    )
                    insert_count += 1

            except Exception as e:
                error_count += 1
                if error_count <= 5:
                    logger.warning(f"매핑 처리 오류: {e}")

        conn.commit()

    # 결과 출력
    final_count = get_row_count(conn, "grid_station_mappings")

    logger.info("=" * 60)
    logger.info("그리드-관측소 매핑 데이터 로딩 완료")
    logger.info(f"   - 삽입: {insert_count:,}개")
    logger.info(f"   - 오류: {error_count:,}개")
    logger.info(f"   - 최종: {final_count:,}개")
    logger.info("=" * 60)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    load_grid_station_mappings()
