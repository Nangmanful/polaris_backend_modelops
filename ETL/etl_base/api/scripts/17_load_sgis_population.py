"""
SKALA Physical Risk AI System - SGIS 인구통계 API ETL

API: SGIS (통계지리정보서비스) - 통계청
URL: https://sgisapi.mods.go.kr/OpenAPI3/stats/searchpopulation.json
용도: 읍면동 단위 현재 인구 데이터 수집 (Physical Risk Exposure 계산용)

데이터 흐름:
1. SGIS OAuth 토큰 발급
2. 전국 시도(level=1) 조회
3. 각 시도별 시군구(level=2) 조회
4. 각 시군구별 읍면동(level=3) 인구 조회
5. location_admin 테이블 UPDATE (population_current, population_current_year)

환경변수 필요:
- SGIS_SERVICE_ID: SGIS 서비스 ID (consumer_key)
- SGIS_SECURITY_KEY: SGIS 보안 키 (consumer_secret)

최종 수정일: 2025-12-14
버전: v03 (시도코드 매핑 19개, 강원/전북 신코드 추가)
"""

import os
import sys
import time
import requests
from pathlib import Path

# 상위 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    setup_logging,
    get_db_connection,
    get_api_key,
)

# SGIS API 엔드포인트 (2025년 11월 20일 이후 새 도메인)
SGIS_AUTH_URL = "https://sgisapi.mods.go.kr/OpenAPI3/auth/authentication.json"
SGIS_POPULATION_URL = "https://sgisapi.mods.go.kr/OpenAPI3/stats/searchpopulation.json"
SGIS_ADDR_STAGE_URL = "https://sgisapi.mods.go.kr/OpenAPI3/addr/stage.json"

# 기준 연도 (최신 데이터)
TARGET_YEAR = "2024"

# 행정동-SGIS 시도 코드 매핑 (19개: 기본 17 + 특별자치도 신코드 2)
# 행정동 코드: 11(서울), 26(부산), 27(대구), ...
# SGIS 코드:  11(서울), 21(부산), 22(대구), ...
# 참고: 강원/전북은 기존코드(42,45)와 신코드(51,52) 모두 지원
SIDO_CODE_MAPPING = [
    ("11", "11", "서울특별시"),
    ("26", "21", "부산광역시"),
    ("27", "22", "대구광역시"),
    ("28", "23", "인천광역시"),
    ("29", "24", "광주광역시"),
    ("30", "25", "대전광역시"),
    ("31", "26", "울산광역시"),
    ("36", "29", "세종특별자치시"),
    ("41", "31", "경기도"),
    ("42", "32", "강원특별자치도"),  # 기존 코드
    ("51", "32", "강원특별자치도"),  # 신규 코드
    ("43", "33", "충청북도"),
    ("44", "34", "충청남도"),
    ("45", "35", "전북특별자치도"),  # 기존 코드
    ("52", "35", "전북특별자치도"),  # 신규 코드
    ("46", "36", "전라남도"),
    ("47", "37", "경상북도"),
    ("48", "38", "경상남도"),
    ("50", "39", "제주특별자치도"),
]


class SGISClient:
    """SGIS API 클라이언트"""

    def __init__(self, service_id: str, security_key: str, logger):
        self.service_id = service_id
        self.security_key = security_key
        self.logger = logger
        self.access_token = None
        self.token_expires = 0

    def get_token(self) -> str:
        """OAuth Access Token 발급"""
        # 토큰이 유효하면 재사용
        if self.access_token and time.time() < self.token_expires - 60:
            return self.access_token

        params = {"consumer_key": self.service_id, "consumer_secret": self.security_key}

        try:
            response = requests.get(SGIS_AUTH_URL, params=params, timeout=30)
            data = response.json()

            if data.get("errCd") == 0:
                result = data.get("result", {})
                self.access_token = result.get("accessToken")
                # accessTimeout은 밀리초 단위
                timeout_ms = int(result.get("accessTimeout", 0))
                self.token_expires = timeout_ms / 1000

                self.logger.info(f"SGIS 토큰 발급 성공")
                return self.access_token
            else:
                self.logger.error(f"SGIS 토큰 발급 실패: {data.get('errMsg')}")
                return None

        except Exception as e:
            self.logger.error(f"SGIS 토큰 발급 오류: {e}")
            return None

    def get_admin_codes(self, adm_cd: str = None) -> list:
        """
        행정구역 코드 목록 조회

        Args:
            adm_cd: 행정구역 코드 (None이면 시도 목록)

        Returns:
            행정구역 코드 리스트
        """
        token = self.get_token()
        if not token:
            return []

        params = {
            "accessToken": token,
        }
        if adm_cd:
            params["cd"] = adm_cd

        try:
            response = requests.get(SGIS_ADDR_STAGE_URL, params=params, timeout=30)
            data = response.json()

            if data.get("errCd") == 0:
                return data.get("result", [])
            else:
                self.logger.warning(f"행정구역 조회 실패: {data.get('errMsg')}")
                return []

        except Exception as e:
            self.logger.error(f"행정구역 조회 오류: {e}")
            return []

    def get_population(self, adm_cd: str, year: str = TARGET_YEAR, low_search: str = "1") -> list:
        """
        인구통계 조회

        Args:
            adm_cd: 행정구역 코드
            year: 기준 연도
            low_search: 하위 행정구역 조회 (0=자신만, 1=1단계 하위, 2=2단계 하위)

        Returns:
            인구통계 리스트
        """
        token = self.get_token()
        if not token:
            return []

        params = {
            "accessToken": token,
            "year": year,
            "adm_cd": adm_cd,
            "low_search": low_search,
            "gender": "0",  # 전체
        }

        try:
            response = requests.get(SGIS_POPULATION_URL, params=params, timeout=30)
            data = response.json()

            if data.get("errCd") == 0:
                return data.get("result", [])
            else:
                self.logger.warning(f"인구 조회 실패 ({adm_cd}): {data.get('errMsg')}")
                return []

        except Exception as e:
            self.logger.error(f"인구 조회 오류 ({adm_cd}): {e}")
            return []


def populate_code_mappings(conn, logger):
    """
    행정동-SGIS 코드 매핑 테이블 생성

    1. sido_code_mapping: 정적 17개 시도 매핑
    2. sigungu_code_mapping: 읍면동 이름 매칭으로 자동 도출
    """
    cursor = conn.cursor()

    # 테이블 존재 여부 확인
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'sido_code_mapping'
        )
    """)
    if not cursor.fetchone()[0]:
        logger.warning("sido_code_mapping 테이블 없음 - 15_create_code_mapping.sql 실행 필요")
        cursor.close()
        return

    logger.info("\n=== 코드 매핑 테이블 생성 ===")

    # 1. 시도 코드 매핑 (정적 17개)
    logger.info("1. sido_code_mapping 적재 (17개)")
    for admin_sido, sgis_sido, sido_name in SIDO_CODE_MAPPING:
        cursor.execute(
            """
            INSERT INTO sido_code_mapping (admin_sido, sgis_sido, sido_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (admin_sido) DO UPDATE SET
                sgis_sido = EXCLUDED.sgis_sido,
                sido_name = EXCLUDED.sido_name
        """,
            (admin_sido, sgis_sido, sido_name),
        )
    conn.commit()
    logger.info(f"   시도 매핑 완료: {len(SIDO_CODE_MAPPING)}개")

    # 2. 시군구 코드 매핑 (읍면동 이름 매칭으로 자동 도출)
    logger.info("2. sigungu_code_mapping 자동 생성 중...")

    # 기존 데이터 삭제 후 재생성
    cursor.execute("DELETE FROM sigungu_code_mapping")

    # 읍면동 이름 매칭으로 시군구 매핑 도출
    cursor.execute("""
        WITH correct_sido_match AS (
            SELECT
                la.sido_code as admin_sido,
                scm.sgis_sido,
                la.sigungu_code as admin_sigungu,
                asp.sigungu_code as sgis_sigungu,
                asp.sigungu_name,
                COUNT(*) as match_count
            FROM location_admin la
            JOIN sido_code_mapping scm ON la.sido_code = scm.admin_sido
            JOIN api_sgis_population asp
                ON scm.sgis_sido = asp.sido_code
                AND la.admin_name = asp.admin_name
            WHERE la.level = 3
            GROUP BY la.sido_code, scm.sgis_sido, la.sigungu_code, asp.sigungu_code, asp.sigungu_name
        ),
        best_match AS (
            SELECT
                admin_sido as sido_code,
                admin_sigungu,
                sgis_sigungu,
                sigungu_name,
                match_count,
                ROW_NUMBER() OVER (PARTITION BY admin_sido, admin_sigungu ORDER BY match_count DESC) as rn
            FROM correct_sido_match
        )
        INSERT INTO sigungu_code_mapping (sido_code, admin_sigungu, sgis_sigungu, sigungu_name, verified)
        SELECT sido_code, admin_sigungu, sgis_sigungu, sigungu_name, FALSE
        FROM best_match
        WHERE rn = 1
    """)
    auto_mapped = cursor.rowcount
    conn.commit()
    logger.info(f"   자동 매핑 완료: {auto_mapped}개")

    # 3. 누락된 매핑 수동 추가 (알려진 케이스)
    manual_mappings = [
        # 서울
        ("11", "11260", "11070", "중랑구"),  # 상봉동
        ("11", "11320", "11100", "도봉구"),  # 창동
        ("11", "11350", "11110", "노원구"),  # 월계동
        ("11", "11470", "11150", "양천구"),  # 목동
        # 부산
        ("26", "26110", "21010", "중구"),
        ("26", "26200", "21020", "서구"),
        ("26", "26470", "21130", "연제구"),
        # 대구
        ("27", "27170", "22030", "서구"),
        # 인천
        ("28", "28200", "23090", "미추홀구"),
        ("28", "28245", "23090", "미추홀구"),
        # 경기
        ("41", "41171", "31041", "안양시 만안구"),
    ]

    manual_added = 0
    for sido_code, admin_sigungu, sgis_sigungu, sigungu_name in manual_mappings:
        cursor.execute(
            """
            INSERT INTO sigungu_code_mapping (sido_code, admin_sigungu, sgis_sigungu, sigungu_name, verified)
            VALUES (%s, %s, %s, %s, TRUE)
            ON CONFLICT (sido_code, admin_sigungu) DO UPDATE SET
                sgis_sigungu = EXCLUDED.sgis_sigungu,
                sigungu_name = EXCLUDED.sigungu_name,
                verified = TRUE
        """,
            (sido_code, admin_sigungu, sgis_sigungu, sigungu_name),
        )
        if cursor.rowcount > 0:
            manual_added += 1
    conn.commit()
    logger.info(f"   수동 매핑 추가: {manual_added}개")

    # 4. 최종 통계
    cursor.execute("SELECT COUNT(*) FROM sigungu_code_mapping")
    total_mapped = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT sigungu_code)
        FROM location_admin WHERE level = 3
    """)
    total_sigungu = cursor.fetchone()[0]

    coverage = total_mapped * 100 / total_sigungu if total_sigungu else 0
    logger.info(f"   총 매핑: {total_mapped}/{total_sigungu}개 ({coverage:.1f}%)")

    cursor.close()


def load_sgis_population(sample_limit: int = None):
    """
    SGIS 인구통계 데이터 적재

    Args:
        sample_limit: 샘플 제한 (테스트용 - 시도 개수 제한)
    """
    logger = setup_logging("load_sgis_population")
    logger.info("=" * 60)
    logger.info("SGIS 인구통계 API ETL 시작 (v03 + 코드 매핑)")
    logger.info(f"기준 연도: {TARGET_YEAR}")
    logger.info("=" * 60)

    # API 키 확인
    service_id = get_api_key("SGIS_SERVICE_ID")
    security_key = get_api_key("SGIS_SECURITY_KEY")

    if not service_id or not security_key:
        logger.error("SGIS_SERVICE_ID, SGIS_SECURITY_KEY 환경변수 필요")
        logger.error("SGIS API 키 발급: https://sgis.mods.go.kr")
        return

    # DB 연결
    conn = get_db_connection()
    cursor = conn.cursor()
    logger.info("DB 연결 완료")

    # api_sgis_population 테이블 존재 여부 확인
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'api_sgis_population'
        )
    """)
    if not cursor.fetchone()[0]:
        logger.error("api_sgis_population 테이블이 없습니다.")
        logger.error("14_alter_location_admin_population.sql 실행 필요")
        conn.close()
        return

    # location_admin 컬럼 존재 여부 확인
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'location_admin'
          AND column_name = 'population_current'
    """)
    if not cursor.fetchone():
        logger.error("population_current 컬럼이 없습니다.")
        logger.error("14_alter_location_admin_population.sql 실행 필요")
        conn.close()
        return

    # SGIS 클라이언트 초기화
    client = SGISClient(service_id, security_key, logger)

    # 토큰 테스트
    if not client.get_token():
        logger.error("SGIS 인증 실패")
        conn.close()
        return

    # 전국 시도 목록 조회
    logger.info("\n1. 전국 시도 목록 조회")
    sido_list = client.get_admin_codes()
    logger.info(f"   {len(sido_list)}개 시도 발견")

    if sample_limit:
        sido_list = sido_list[:sample_limit]
        logger.info(f"   샘플 제한 적용: {sample_limit}개 시도만 처리")

    total_inserted = 0
    total_updated = 0
    total_not_matched = 0
    api_call_count = 0

    # 시도별 처리
    for sido in sido_list:
        sido_cd = sido.get("cd")
        sido_nm = sido.get("addr_name", sido.get("nm", ""))

        logger.info(f"\n2. {sido_nm} ({sido_cd}) 처리 중...")

        # 시군구 목록 조회
        sigungu_list = client.get_admin_codes(sido_cd)
        api_call_count += 1
        logger.info(f"   {len(sigungu_list)}개 시군구 발견")

        for sigungu in sigungu_list:
            sigungu_cd = sigungu.get("cd")
            sigungu_nm = sigungu.get("addr_name", sigungu.get("nm", ""))

            # 읍면동 인구 조회 (low_search=1: 1단계 하위)
            population_data = client.get_population(sigungu_cd, year=TARGET_YEAR, low_search="1")
            api_call_count += 1

            if not population_data:
                logger.warning(f"   {sigungu_nm}: 인구 데이터 없음")
                continue

            # 읍면동별 인구 처리
            emd_inserted = 0
            emd_updated = 0
            emd_not_matched = 0

            for item in population_data:
                adm_cd = item.get("adm_cd")
                population = item.get("population")
                adm_nm = item.get("adm_nm", "")

                if not adm_cd or population is None:
                    continue

                try:
                    pop_int = int(population)
                except (ValueError, TypeError):
                    continue

                # 1) api_sgis_population 테이블에 INSERT (100% 저장)
                cursor.execute(
                    """
                    INSERT INTO api_sgis_population
                        (sgis_code, admin_name, sido_code, sido_name,
                         sigungu_code, sigungu_name, population, year, gender)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (sgis_code, year, gender)
                    DO UPDATE SET
                        population = EXCLUDED.population,
                        cached_at = NOW()
                """,
                    (
                        adm_cd,  # sgis_code (8자리)
                        adm_nm,  # admin_name
                        sido_cd[:2],  # sido_code (2자리)
                        sido_nm,  # sido_name
                        sigungu_cd,  # sigungu_code (5자리)
                        sigungu_nm,  # sigungu_name
                        pop_int,  # population
                        int(TARGET_YEAR),  # year
                        "total",  # gender
                    ),
                )
                emd_inserted += 1

                # 2) location_admin 테이블 UPDATE (이름 매칭)
                if adm_nm:
                    cursor.execute(
                        """
                        UPDATE location_admin
                        SET population_current = %s,
                            population_current_year = %s
                        WHERE admin_name = %s
                          AND level = 3
                          AND population_current IS NULL
                    """,
                        (pop_int, int(TARGET_YEAR), adm_nm),
                    )

                    if cursor.rowcount > 0:
                        emd_updated += cursor.rowcount
                    else:
                        emd_not_matched += 1
                else:
                    emd_not_matched += 1

            conn.commit()
            total_inserted += emd_inserted
            total_updated += emd_updated
            total_not_matched += emd_not_matched

            logger.info(
                f"   {sigungu_nm}: INSERT {emd_inserted}건, UPDATE {emd_updated}건, 미매칭 {emd_not_matched}건"
            )

            # API 호출 제한 방지 (최소 대기)
            time.sleep(0.1)

    # 결과 출력
    logger.info("\n" + "=" * 60)
    logger.info("SGIS 인구통계 ETL 결과")
    logger.info("=" * 60)
    logger.info(f"API 호출 횟수: {api_call_count}회")
    logger.info(f"api_sgis_population INSERT: {total_inserted}건")
    logger.info(f"location_admin UPDATE: {total_updated}건")
    logger.info(f"location_admin 미매칭: {total_not_matched}건")

    # api_sgis_population 통계
    cursor.execute(
        """
        SELECT
            COUNT(*) as total,
            COUNT(DISTINCT sido_name) as sido_count,
            COUNT(DISTINCT sigungu_name) as sigungu_count,
            SUM(population) as total_population
        FROM api_sgis_population
        WHERE year = %s
    """,
        (int(TARGET_YEAR),),
    )
    sgis_stats = cursor.fetchone()
    if sgis_stats:
        logger.info(f"\napi_sgis_population 통계 ({TARGET_YEAR}년):")
        logger.info(f"  전체 레코드: {sgis_stats[0]}개")
        logger.info(f"  시도 수: {sgis_stats[1]}개")
        logger.info(f"  시군구 수: {sgis_stats[2]}개")
        if sgis_stats[3]:
            logger.info(f"  총 인구: {sgis_stats[3]:,}명")

    # location_admin 통계
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(population_current) as with_population,
            AVG(population_current) as avg_population,
            SUM(population_current) as total_population
        FROM location_admin
        WHERE level = 3
    """)
    stats = cursor.fetchone()
    if stats:
        logger.info(f"\nlocation_admin (level=3) 통계:")
        logger.info(f"  전체 읍면동: {stats[0]}개")
        logger.info(
            f"  인구 데이터 있음: {stats[1]}개 ({stats[1]*100//stats[0] if stats[0] else 0}%)"
        )
        if stats[2]:
            logger.info(f"  평균 인구: {stats[2]:,.0f}명")
        if stats[3]:
            logger.info(f"  총 인구: {stats[3]:,.0f}명")

    # 인구 데이터 확인 (상위 10개)
    cursor.execute(
        """
        SELECT sgis_code, admin_name, sido_name, sigungu_name, population
        FROM api_sgis_population
        WHERE year = %s
        ORDER BY population DESC
        LIMIT 10
    """,
        (int(TARGET_YEAR),),
    )
    rows = cursor.fetchall()
    if rows:
        logger.info(f"\n인구 상위 10개 읍면동 (api_sgis_population):")
        for row in rows:
            logger.info(f"  {row[2]} {row[3]} {row[1]} ({row[0]}): {row[4]:,}명")

    # 코드 매핑 테이블 생성
    populate_code_mappings(conn, logger)

    cursor.close()
    conn.close()
    logger.info("\nSGIS 인구통계 API ETL 완료")


if __name__ == "__main__":
    sample_limit = int(os.getenv("SAMPLE_LIMIT", 0)) or None
    load_sgis_population(sample_limit=sample_limit)
