"""
SK 사업장 9개에 대해서만 H, P(H), E, V, AAL 계산

사용법:
    DW_DB_HOST=localhost DW_DB_PORT=5555 DW_DB_NAME=datawarehouse DW_DB_USER=skala DW_DB_PASSWORD=skala1234 \
    PYTHONPATH=. python3 -m modelops.batch.run_sk_sites_only
"""

import logging
from typing import List, Tuple
from datetime import datetime

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# SK 사업장 9개 좌표 (ETL 02.1에서 가져옴)
SK_SITES: List[Tuple[str, float, float]] = [
    ("SK u-타워", 37.3825, 127.1220),
    ("판교 캠퍼스", 37.405879, 127.099877),
    ("수내 오피스", 37.3820, 127.1250),
    ("서린 사옥", 37.570708, 126.983577),
    ("대덕 데이터 센터", 36.3728, 127.3590),
    ("판교 데이터 센터", 37.405879, 127.099877),  # 판교 캠퍼스와 동일 좌표
    ("보라매 데이터 센터", 37.4858, 126.9302),
    ("애커튼 파트너스", 37.5712, 126.9837),
    ("애커튼 테크놀로지", 37.405879, 127.099877),  # 판교 캠퍼스와 동일 좌표
]

# 중복 제거된 좌표 (7개 고유 좌표)
UNIQUE_SK_COORDS = list(set((lat, lon) for _, lat, lon in SK_SITES))

# 시나리오 및 연도
SCENARIOS = ["SSP245"]  # 대표 시나리오 1개로 테스트
TARGET_YEARS = ["2030", "2050"]  # 대표 연도 2개
RISK_TYPES = [
    "extreme_heat",
    "extreme_cold",
    "wildfire",
    "drought",
    "water_stress",
    "sea_level_rise",
    "river_flood",
    "urban_flood",
    "typhoon",
]


def run_hazard_probability_for_sk_sites():
    """SK 사업장에 대해 H, P(H) 계산"""
    from .hazard_probability_timeseries_batch import (
        calculate_hazard,
        calculate_probability,
        save_hazard_results,
        save_probability_results,
    )

    logger.info("=" * 60)
    logger.info("SK 사업장 H, P(H) 계산 시작")
    logger.info(f"사이트 수: {len(UNIQUE_SK_COORDS)}개 고유 좌표")
    logger.info(f"시나리오: {SCENARIOS}")
    logger.info(f"연도: {TARGET_YEARS}")
    logger.info(f"리스크 타입: {len(RISK_TYPES)}개")
    logger.info("=" * 60)

    hazard_results = []
    probability_results = []

    for scenario in SCENARIOS:
        for target_year in TARGET_YEARS:
            logger.info(f"\n[{scenario}] 연도: {target_year}")

            for idx, (lat, lon) in enumerate(UNIQUE_SK_COORDS):
                site_name = next(
                    (name for name, slat, slon in SK_SITES if slat == lat and slon == lon),
                    "Unknown",
                )
                logger.info(f"  처리 중: {site_name} ({lat}, {lon})")

                for risk_type in RISK_TYPES:
                    try:
                        # H 계산
                        h_result = calculate_hazard(lat, lon, scenario, int(target_year), risk_type)
                        hazard_results.append(
                            {
                                "latitude": lat,
                                "longitude": lon,
                                "scenario": scenario,
                                "target_year": target_year,
                                "risk_type": risk_type,
                                "hazard_score": h_result["hazard_score"],
                                "hazard_score_100": h_result["hazard_score_100"],
                                "hazard_level": h_result["hazard_level"],
                            }
                        )

                        # P(H) 계산
                        p_result = calculate_probability(
                            lat,
                            lon,
                            scenario,
                            int(target_year),
                            risk_type,
                            h_result["hazard_score"],
                        )
                        probability_results.append(
                            {
                                "latitude": lat,
                                "longitude": lon,
                                "scenario": scenario,
                                "target_year": target_year,
                                "risk_type": risk_type,
                                "aal": p_result["aal"],
                                "bin_probabilities": p_result.get("bin_probabilities", []),
                                "probability_level": p_result["probability_level"],
                            }
                        )

                        logger.info(
                            f"    {risk_type}: H={h_result['hazard_score_100']:.1f}, P(H)={p_result['aal']:.4f}"
                        )

                    except Exception as e:
                        logger.error(f"    {risk_type} 실패: {e}")

    # DB 저장
    if hazard_results:
        save_hazard_results(hazard_results)
        logger.info(f"H 결과 저장: {len(hazard_results)}건")
    if probability_results:
        save_probability_results(probability_results)
        logger.info(f"P(H) 결과 저장: {len(probability_results)}건")

    return hazard_results, probability_results


def run_evaal_for_sk_sites(hazard_results: list, probability_results: list):
    """SK 사업장에 대해 E, V, AAL 계산"""
    from .evaal_ondemand_api import (
        calculate_exposure,
        calculate_vulnerability,
        calculate_aal,
        save_exposure_result,
        save_vulnerability_result,
        save_aal_result,
        generate_site_id,
    )

    logger.info("\n" + "=" * 60)
    logger.info("SK 사업장 E, V, AAL 계산 시작")
    logger.info("=" * 60)

    exposure_count = 0
    vulnerability_count = 0
    aal_count = 0

    for h_result, p_result in zip(hazard_results, probability_results):
        lat = h_result["latitude"]
        lon = h_result["longitude"]
        scenario = h_result["scenario"]
        target_year = h_result["target_year"]
        risk_type = h_result["risk_type"]
        hazard_score = h_result["hazard_score"]
        probability_value = p_result["aal"]

        try:
            site_id = generate_site_id(lat, lon)

            # E 계산
            exposure_result = calculate_exposure(lat, lon, risk_type)
            exposure_data = {
                "site_id": site_id,
                "latitude": lat,
                "longitude": lon,
                "risk_type": risk_type,
                "target_year": target_year,
                "scenario": scenario,
                **exposure_result,
            }
            save_exposure_result(exposure_data)
            exposure_count += 1

            # V 계산
            vulnerability_result = calculate_vulnerability(lat, lon, risk_type)
            vulnerability_data = {
                "site_id": site_id,
                "latitude": lat,
                "longitude": lon,
                "risk_type": risk_type,
                "target_year": target_year,
                "scenario": scenario,
                **vulnerability_result,
            }
            save_vulnerability_result(vulnerability_data)
            vulnerability_count += 1

            # AAL 계산
            exposure_value = exposure_result.get("exposure_score", 50.0)
            vulnerability_score = vulnerability_result.get("vulnerability_score", 50.0)
            base_aal = hazard_score * probability_value * (exposure_value / 100)
            final_aal = calculate_aal(base_aal, vulnerability_score)

            aal_data = {
                "site_id": site_id,
                "latitude": lat,
                "longitude": lon,
                "risk_type": risk_type,
                "target_year": target_year,
                "scenario": scenario,
                "hazard_score": hazard_score,
                "probability": probability_value,
                "exposure_score": exposure_value,
                "vulnerability_score": vulnerability_score,
                "base_aal": base_aal,
                "final_aal": final_aal,
            }
            save_aal_result(aal_data)
            aal_count += 1

        except Exception as e:
            logger.error(f"E/V/AAL 계산 실패 ({lat}, {lon}, {risk_type}): {e}")

    logger.info(f"\nE 결과 저장: {exposure_count}건")
    logger.info(f"V 결과 저장: {vulnerability_count}건")
    logger.info(f"AAL 결과 저장: {aal_count}건")


if __name__ == "__main__":
    start_time = datetime.now()

    # Step 1: H, P(H) 계산
    logger.info("=" * 70)
    logger.info("Step 1: H, P(H) 계산")
    logger.info("=" * 70)
    h_results, p_results = run_hazard_probability_for_sk_sites()

    # Step 2: E, V, AAL 계산
    logger.info("\n" + "=" * 70)
    logger.info("Step 2: E, V, AAL 계산")
    logger.info("=" * 70)
    run_evaal_for_sk_sites(h_results, p_results)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    logger.info("\n" + "=" * 70)
    logger.info("전체 완료")
    logger.info(f"소요 시간: {duration:.1f}초 ({duration/60:.1f}분)")
    logger.info("=" * 70)
