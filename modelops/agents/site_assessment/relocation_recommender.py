"""
사업장 이전 후보지 추천기
~1000개 후보 격자를 평가하여 최적 후보지 추천
"""

from typing import Dict, Any, List, Optional
import logging
from datetime import datetime

from .site_risk_calculator import SiteRiskCalculator

logger = logging.getLogger(__name__)


class RelocationRecommender:
    """
    사업장 이전 후보지 추천기

    역할:
    - ~1000개 후보 격자를 순회하면서 각 위치의 AAL 계산
    - SiteRiskCalculator를 사용하여 E, V, AAL 계산
    - total_aal 기준으로 정렬하여 top 3 추천
    - 각 리스크별 상세 정보 포함
    """

    def __init__(self, scenario="SSP245", target_year=2040):
        """
        RelocationRecommender 초기화

        Args:
            scenario: SSP 시나리오
            target_year: 목표 연도
        """
        self.scenario = scenario
        self.target_year = target_year

        # SiteRiskCalculator 초기화
        self.risk_calculator = SiteRiskCalculator(scenario=scenario, target_year=target_year)

    def recommend_locations(
        self,
        candidate_grids: List[Dict[str, float]],
        building_info: Dict[str, Any],
        asset_info: Optional[Dict[str, Any]] = None,
        max_candidates: int = 3,
    ) -> Dict[str, Any]:
        """
        후보 격자들을 평가하여 최적 후보지 추천

        Process:
        1. candidate_grids 순회 (~1000개)
        2. 각 격자마다 SiteRiskCalculator로 리스크 계산
        3. total_aal 기준으로 정렬
        4. top N개 선택
        5. 각 후보지의 리스크 상세 정보 구성

        Args:
            candidate_grids: 후보 격자 리스트 [{'latitude': ..., 'longitude': ...}, ...]
            building_info: 건물 정보 dict
            asset_info: 자산 정보 dict (선택)
            max_candidates: 최대 추천 후보지 개수 (기본 3)

        Returns:
            {
                'candidates': [
                    {
                        'rank': 1,
                        'latitude': float,
                        'longitude': float,
                        'total_aal': float,
                        'average_aal': float, # 추가: 평균 AAL
                        'average_integrated_risk': float,
                        'risk_details': {risk_type: {...}, ...}
                    },
                    ...
                ],
                'total_grids_evaluated': int,
                'search_criteria': {...},
                'calculated_at': datetime
            }
        """
        start_time = datetime.now()
        total_grids = len(candidate_grids)
        logger.info(f"이전 후보지 추천 시작: {total_grids}개 격자 평가")
        logger.info(f"  max_candidates: {max_candidates}")

        try:
            # Step 1: 모든 후보 격자 평가
            evaluated_grids = []

            for idx, grid in enumerate(candidate_grids, 1):
                latitude = grid["latitude"]
                longitude = grid["longitude"]

                if idx % 100 == 0:
                    logger.info(f"  진행률: {idx}/{total_grids} ({idx/total_grids*100:.1f}%)")

                try:
                    # SiteRiskCalculator로 리스크 계산
                    risk_result = self.risk_calculator.calculate_site_risks(
                        latitude=latitude,
                        longitude=longitude,
                        building_info=building_info,
                        asset_info=asset_info,
                        site_id=None,  # 후보지는 site_id 없음
                    )

                    # AAL 합계 및 평균 계산
                    total_aal = risk_result["summary"]["total_final_aal"]
                    risk_count = risk_result["summary"].get("risk_count", 9)
                    average_aal = total_aal / risk_count if risk_count > 0 else 0.0

                    avg_integrated_risk = risk_result["summary"]["average_integrated_risk"]

                    # 평가 결과 저장
                    evaluated_grids.append(
                        {
                            "latitude": latitude,
                            "longitude": longitude,
                            "average_aal": average_aal,
                            "average_integrated_risk": avg_integrated_risk,
                            "risk_result": risk_result,
                        }
                    )

                except Exception as e:
                    logger.error(f"격자 ({latitude}, {longitude}) 평가 실패: {e}")
                    # 실패한 격자는 건너뜀
                    continue

            # Step 2: average_aal 기준 오름차순 정렬 (낮을수록 좋음)
            evaluated_grids.sort(key=lambda x: x["average_aal"])

            # Step 3: top N개 선택
            top_candidates = evaluated_grids[:max_candidates]

            # Step 4: 결과 구성
            candidates = []
            for rank, candidate in enumerate(top_candidates, 1):
                risk_result = candidate["risk_result"]

                # 리스크별 상세 정보 구성
                risk_details = {}
                for risk_type in self.risk_calculator.RISK_TYPES:
                    h_data = risk_result["hazard"].get(risk_type, {})
                    e_data = risk_result["exposure"].get(risk_type, {})
                    v_data = risk_result["vulnerability"].get(risk_type, {})
                    ir_data = risk_result["integrated_risk"].get(risk_type, {})
                    aal_data = risk_result["aal_scaled"].get(risk_type, {})

                    risk_details[risk_type] = {
                        "h_score": h_data.get("hazard_score_100", 0.0),
                        "e_score": e_data.get("exposure_score", 0.0),
                        "v_score": v_data.get("vulnerability_score", 0.0),
                        "integrated_risk_score": ir_data.get("integrated_risk_score", 0.0),
                        "base_aal": aal_data.get("base_aal", 0.0),
                        "f_vuln": aal_data.get("vulnerability_scale", 1.0),
                        "final_aal": aal_data.get("final_aal", 0.0),
                    }

                # total_aal 계산 (9개 리스크의 final_aal 합계)
                total_aal = sum(
                    risk_data.get("final_aal", 0.0) for risk_data in risk_details.values()
                )

                candidates.append(
                    {
                        "rank": rank,
                        "latitude": candidate["latitude"],
                        "longitude": candidate["longitude"],
                        "total_aal": round(total_aal, 6),
                        "average_aal": round(candidate["average_aal"], 6),
                        "average_integrated_risk": round(candidate["average_integrated_risk"], 2),
                        "risk_details": risk_details,
                    }
                )

            end_time = datetime.now()
            elapsed_time = (end_time - start_time).total_seconds()
            logger.info(f"이전 후보지 추천 완료: {elapsed_time:.2f}초")
            logger.info(f"  평가 성공: {len(evaluated_grids)}/{total_grids}개")

            return {
                "candidates": candidates,
                "total_grids_evaluated": len(evaluated_grids),
                "search_criteria": {
                    "max_candidates": max_candidates,
                    "ssp_scenario": self.scenario,
                    "target_year": self.target_year,
                },
                "calculated_at": end_time,
            }

        except Exception as e:
            logger.error(f"이전 후보지 추천 실패: {e}", exc_info=True)
            raise

    def compare_current_and_candidates(
        self,
        current_site: Dict[str, Any],
        candidate_result: Dict[str, Any],
        building_info: Dict[str, Any],
        asset_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        현재 사업장과 후보지들 간의 리스크 비교

        Args:
            current_site: 현재 사업장 정보 {'latitude': ..., 'longitude': ...}
            candidate_result: recommend_locations의 반환값
            building_info: 건물 정보
            asset_info: 자산 정보

        Returns:
            비교 결과 (현재 사업장 vs 후보지 1, 2, 3...)
        """
        try:
            # 1. 현재 사업장 리스크 계산
            current_result = self.risk_calculator.calculate_site_risks(
                latitude=current_site["latitude"],
                longitude=current_site["longitude"],
                building_info=building_info,
                asset_info=asset_info,
                site_id="current_site",
            )

            # 요약 정보 추출
            c_summary = current_result["summary"]
            current_avg_risk = c_summary["average_integrated_risk"]
            risk_count = c_summary.get("risk_count", 9)
            current_avg_aal = (
                c_summary["total_final_aal"] / risk_count if risk_count > 0 else 0.0
            )  # total_final_aal로 부터 평균 AAL 계산

            # 리스크별 상세
            current_details = {}
            for risk_type in self.risk_calculator.RISK_TYPES:
                current_details[risk_type] = {
                    "integrated_risk_score": current_result["integrated_risk"][risk_type].get(
                        "integrated_risk_score", 0.0
                    ),
                    "final_aal": current_result["aal_scaled"][risk_type].get("final_aal", 0.0),
                }

            comparison_data = {
                "current_site": {
                    "latitude": current_site["latitude"],
                    "longitude": current_site["longitude"],
                    "average_integrated_risk": round(current_avg_risk, 2),
                    "average_aal": round(current_avg_aal, 6),
                    "risk_details": current_details,
                },
                "candidates": [],
            }

            # 2. 후보지 정보 추가
            for cand in candidate_result["candidates"]:
                # 후보지 데이터 재구성
                cand_details = {}
                for r_type, r_data in cand["risk_details"].items():
                    cand_details[r_type] = {
                        "integrated_risk_score": r_data["integrated_risk_score"],
                        "final_aal": r_data["final_aal"],
                    }

                comparison_data["candidates"].append(
                    {
                        "rank": cand["rank"],
                        "latitude": cand["latitude"],
                        "longitude": cand["longitude"],
                        "average_integrated_risk": cand["average_integrated_risk"],
                        "average_aal": cand["average_aal"],
                        "risk_details": cand_details,
                        "improvement_aal": round(
                            current_avg_aal - cand["average_aal"], 6
                        ),  # 평균 AAL 개선도
                        "improvement_risk": round(
                            current_avg_risk - cand["average_integrated_risk"], 2
                        ),
                    }
                )

            return comparison_data

        except Exception as e:
            logger.error(f"비교 분석 실패: {e}", exc_info=True)
            raise
