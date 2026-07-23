"""
파일명: base_hazard_hscore_agent.py
최종 수정일: 2025-12-14
버전: v3
파일 개요: Hazard 점수(H) 계산 베이스 Agent (순수 계산 로직만)
변경 이력:
        - 2025-11-21: v1 - H×E×V에서 H만 계산하도록 분리
        - 2025-12-13: v2 - DB 연동 기능 추가
        - 2025-12-14: v3 - 원래 설계 복원 (DB 로직 제거, 순수 계산만)
"""

from typing import Dict, Any
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class BaseHazardHScoreAgent(ABC):
    """
    Hazard 점수(H) 계산 베이스 Agent
    기후 위험의 강도 및 발생 빈도 평가

    원래 설계:
    - Agent는 순수 계산 로직만 담당
    - 데이터는 HazardDataCollector → data_loaders에서 수집
    - Agent는 collected_data를 받아 계산만 수행
    """

    def __init__(self, risk_type: str):
        """
        BaseHazardHScoreAgent 초기화

        Args:
                risk_type: 리스크 타입 (예: 'extreme_heat', 'typhoon')
        """
        self.risk_type = risk_type
        self.logger = logger
        self.logger.info(f"{risk_type} Hazard Score Agent 초기화")

    def calculate_hazard_score(self, collected_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Hazard 점수 계산 진입점

        Args:
                collected_data: HazardDataCollector가 수집한 데이터
                        {
                                'latitude': float,
                                'longitude': float,
                                'risk_type': str,
                                'scenario': str,
                                'target_year': int,
                                'climate_data': {...},
                                'spatial_data': {...},
                                'building_data': {...},
                                ...
                        }

        Returns:
                {
                        'risk_type': str,
                        'hazard_score': float (0-1),
                        'hazard_score_100': float (0-100),
                        'hazard_level': str,
                        'recommendation': str,
                        'details': {...},
                        'status': str
                }
        """
        try:
            # 하위 클래스에서 구현한 calculate_hazard() 호출
            hazard_score = self.calculate_hazard(collected_data)

            # 0-100 스케일로 변환
            hazard_score_100 = hazard_score * 100

            # 위험 등급 및 권고사항
            hazard_level = self.get_hazard_level(hazard_score_100)
            recommendation = self.get_recommendation(hazard_score_100)

            result = {
                "risk_type": self.risk_type,
                "hazard_score": hazard_score,
                "hazard_score_100": hazard_score_100,
                "hazard_level": hazard_level,
                "recommendation": recommendation,
                "details": {
                    "input_data": {
                        "scenario": collected_data.get("scenario", "SSP245"),
                        "target_year": collected_data.get("target_year", 2030),
                        "latitude": collected_data.get("latitude"),
                        "longitude": collected_data.get("longitude"),
                    }
                },
                "status": "completed",
            }

            self.logger.info(
                f"{self.risk_type} Hazard Score 계산 완료: "
                f"{hazard_score_100:.2f}/100 (H={hazard_score:.4f})"
            )
            return result

        except Exception as e:
            self.logger.error(
                f"{self.risk_type} Hazard Score 계산 중 오류: {str(e)}", exc_info=True
            )
            return {"risk_type": self.risk_type, "status": "failed", "error": str(e)}

    @abstractmethod
    def calculate_hazard(self, collected_data: Dict[str, Any]) -> float:
        """
        Hazard 점수 계산 (하위 클래스에서 구현)

        Args:
                collected_data: 수집된 데이터 (climate_data, spatial_data 등)

        Returns:
                Hazard 점수 (0.0 ~ 1.0)
        """
        pass

    def get_hazard_level(self, hazard_score_100: float) -> str:
        """
        Hazard 점수에 따른 위험 등급 반환

        Args:
                hazard_score_100: Hazard 점수 (0 ~ 100)

        Returns:
                위험 등급 문자열
                        - 'Very High': 80 이상
                        - 'High': 60 ~ 80
                        - 'Medium': 40 ~ 60
                        - 'Low': 20 ~ 40
                        - 'Very Low': 20 미만
        """
        if hazard_score_100 >= 80:
            return "Very High"
        elif hazard_score_100 >= 60:
            return "High"
        elif hazard_score_100 >= 40:
            return "Medium"
        elif hazard_score_100 >= 20:
            return "Low"
        else:
            return "Very Low"

    def get_recommendation(self, hazard_score_100: float) -> str:
        """
        Hazard 점수에 따른 권고사항 생성

        Args:
                hazard_score_100: Hazard 점수 (0 ~ 100)

        Returns:
                권고사항 문자열
        """
        hazard_level = self.get_hazard_level(hazard_score_100)

        recommendations = {
            "Very High": f"{self.risk_type} 위험이 매우 높습니다. 즉각적인 모니터링과 대응 준비가 필요합니다.",
            "High": f"{self.risk_type} 위험이 높습니다. 예방적 조치를 강화하세요.",
            "Medium": f"{self.risk_type} 위험을 지속적으로 모니터링하세요.",
            "Low": f"{self.risk_type} 위험은 낮으나 정기적인 확인이 필요합니다.",
            "Very Low": f"{self.risk_type} 위험은 매우 낮지만 기후 변화 추세를 주시하세요.",
        }

        return recommendations.get(hazard_level, "정기적인 위험 재평가가 필요합니다.")

    # ==================== 유틸리티 메서드 ====================

    def normalize_score(
        self, value: float, min_val: float, max_val: float, clip: bool = True
    ) -> float:
        """
        값을 0-1 범위로 정규화

        Args:
                value: 정규화할 값
                min_val: 최소값
                max_val: 최대값
                clip: True이면 0-1 범위로 클리핑

        Returns:
                정규화된 값 (0.0 ~ 1.0)
        """
        if max_val == min_val:
            return 0.5

        normalized = (value - min_val) / (max_val - min_val)

        if clip:
            return max(0.0, min(1.0, normalized))
        return normalized

    def get_value_with_fallback(self, data: Dict, keys: list, fallback: Any) -> Any:
        """
        딕셔너리에서 값을 찾되, 여러 키를 순차적으로 시도

        Args:
                data: 데이터 딕셔너리
                keys: 시도할 키 목록
                fallback: 모든 키가 없을 때 반환할 기본값

        Returns:
                찾은 값 또는 기본값
        """
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return fallback
