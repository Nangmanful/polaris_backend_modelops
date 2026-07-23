"""
AAL Scaling Agent
V (Vulnerability) 점수를 기반으로 AAL 스케일링
final_aal = base_aal × F_vuln × (1 - insurance_rate)
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class AALScalingAgent:
    """AAL 스케일링 Agent"""

    def __init__(self):
        """AALScalingAgent 초기화"""
        self.s_min = 0.9  # 최소 스케일 계수
        self.s_max = 1.1  # 최대 스케일 계수

    def scale_aal(
        self,
        base_aal: float,
        vulnerability_score: float,
        insurance_rate: float = 0.0,
        asset_value: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        AAL 스케일링 계산

        공식:
        - F_vuln = 0.9 + (V/100) × 0.2  (범위: 0.9 ~ 1.1)
        - final_aal = base_aal × F_vuln × (1 - insurance_rate) × 100 (% 단위로 변환)

        Args:
            base_aal: 기본 AAL (probability_results.aal, 0~1 확률값)
            vulnerability_score: 취약성 점수 (0-100)
            insurance_rate: 보험 보전율 (0-1, 기본값 0.0)
            asset_value: 자산 가치 (원, 선택사항)

        Returns:
            {
                'base_aal': float (% 단위, 0~100),
                'vulnerability_scale': float (F_vuln),
                'final_aal': float (% 단위, 0~100),
                'insurance_rate': float,
                'expected_loss': int | None
            }
        """
        try:
            # 1. 취약성 스케일 계수 계산 (F_vuln)
            f_vuln = self._calculate_vulnerability_scale(vulnerability_score)

            # 2. 최종 AAL 계산 (확률값)
            final_aal_ratio = base_aal * f_vuln * (1.0 - insurance_rate)

            # 3. 예상 손실액 계산 (자산 가치가 있을 경우) - 확률값 사용
            expected_loss = None
            if asset_value is not None and asset_value > 0:
                expected_loss = int(final_aal_ratio * asset_value)

            # 4. % 단위로 변환하여 반환
            return {
                "base_aal": round(base_aal * 100, 6),
                "vulnerability_scale": round(f_vuln, 4),
                "final_aal": round(final_aal_ratio * 100, 6),
                "insurance_rate": round(insurance_rate, 4),
                "expected_loss": expected_loss,
            }

        except Exception as e:
            logger.error(f"AAL 스케일링 실패: {e}")
            return {
                "base_aal": base_aal * 100,
                "vulnerability_scale": 1.0,
                "final_aal": base_aal * 100,
                "insurance_rate": 0.0,
                "expected_loss": None,
                "error": str(e),
            }

    def _calculate_vulnerability_scale(self, vulnerability_score: float) -> float:
        """
        취약성 스케일 계수 계산

        공식: F_vuln = s_min + (s_max - s_min) × (V_score / 100)

        - V = 0   → F_vuln = 0.9  (10% 감소)
        - V = 50  → F_vuln = 1.0  (변화 없음)
        - V = 100 → F_vuln = 1.1  (10% 증가)

        Args:
            vulnerability_score: 취약성 점수 (0-100)

        Returns:
            F_vuln (0.9 ~ 1.1)
        """
        # 점수 범위 검증
        v_score = max(0.0, min(100.0, vulnerability_score))

        # 스케일 계수 계산
        f_vuln = self.s_min + (self.s_max - self.s_min) * (v_score / 100.0)

        # 범위 검증
        return max(self.s_min, min(self.s_max, f_vuln))

    def batch_scale_aals(
        self,
        aal_data: Dict[str, Dict[str, float]],
        insurance_rate: float = 0.0,
        asset_value: Optional[float] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        여러 리스크에 대한 AAL 일괄 스케일링

        Args:
            aal_data: {
                risk_type: {
                    'base_aal': float,
                    'vulnerability_score': float
                }
            }
            insurance_rate: 보험 보전율
            asset_value: 자산 가치

        Returns:
            {risk_type: AAL 스케일링 결과}
        """
        results = {}

        for risk_type, data in aal_data.items():
            base_aal = data.get("base_aal", 0.0)
            v_score = data.get("vulnerability_score", 50.0)

            results[risk_type] = self.scale_aal(
                base_aal=base_aal,
                vulnerability_score=v_score,
                insurance_rate=insurance_rate,
                asset_value=asset_value,
            )

        return results

    def classify_aal_grade(self, final_aal: float) -> str:
        """
        단일 AAL 값에 대한 등급 분류

        Args:
            final_aal: 최종 스케일링된 AAL (% 단위, 0~100 범위)

        Returns:
            등급 문자열 ('-', '0~3%', '~6%', '~10%', '~16%', '~30%', '30%~')
        """
        # AAL 등급 기준 (% 단위, 0~100)
        if final_aal <= 0:  # 0% 이하 (발생 원천 없음)
            return "-"
        elif final_aal < 3.0:  # 0~3%
            return "0~3%"
        elif final_aal < 6.0:  # 3~6%
            return "~6%"
        elif final_aal < 10.0:  # 6~10%
            return "~10%"
        elif final_aal < 16.0:  # 10~16%
            return "~16%"
        elif final_aal < 30.0:  # 16~30%
            return "~30%"
        else:  # 30% 이상
            return "30%~"

    def classify_aal_grades(
        self, scaled_aals: Dict[str, Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        모든 리스크에 대한 AAL 등급 일괄 분류

        Args:
            scaled_aals: {risk_type: AAL 스케일링 결과 (final_aal 포함 dict)}

        Returns:
            {risk_type: 등급 문자열} — classify_aal_grade 반환값
            ('-', '0~3%', '~6%', '~10%', '~16%', '~30%', '30%~')
        """
        results = {}

        for risk_type, aal_result in scaled_aals.items():
            final_aal = aal_result.get("final_aal", 0.0)
            results[risk_type] = self.classify_aal_grade(final_aal)

        return results
