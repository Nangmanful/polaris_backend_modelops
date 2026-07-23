"""
==================================================================
[모듈명] utils/config.py
ESG Agent 설정 관리

[모듈 목표]
1) 환경변수 로드 및 검증
2) 설정값 중앙 관리
3) 타입 변환 및 기본값 처리
==================================================================
"""

import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


class Config:
    """ESG Agent 설정 클래스

    환경변수를 중앙에서 관리
    """

    # LLM
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Search
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

    # Notification
    SLACK_BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN", "")
    SLACK_CHANNEL: str = os.getenv("SLACK_CHANNEL", "auto")

    # 기상청 API
    KMA_API_KEY: str = os.getenv("KMA_API_KEY", "")
    WEATHER_LOCATIONS: List[str] = [
        loc.strip() for loc in os.getenv("WEATHER_LOCATIONS", "서울,성남,대전").split(",")
    ]

    # ESG 뉴스 소스
    ESG_DOMESTIC_URL: str = os.getenv("ESG_DOMESTIC_URL", "https://www.esgeconomy.com/")
    ESG_GLOBAL_SOURCE: str = os.getenv("ESG_GLOBAL_SOURCE", "KOTRA")
    KOTRA_API_KEY: str = os.getenv("KOTRA_API_KEY", "")

    # ESG 리포트 설정
    ESG_NEWS_LIMIT: int = int(os.getenv("ESG_NEWS_LIMIT", "10"))
    ESG_REPORT_STYLE: str = os.getenv("ESG_REPORT_STYLE", "formal")
    ESG_INCLUDE_WEATHER: bool = os.getenv("ESG_INCLUDE_WEATHER", "true").lower() == "true"

    # 뉴스 수집 설정
    MAX_NEWS_PER_SOURCE: int = int(os.getenv("MAX_NEWS_PER_SOURCE", "10"))
    MIN_NEWS_REQUIRED: int = int(os.getenv("MIN_NEWS_REQUIRED", "3"))

    # 9대 물리적 리스크
    PHYSICAL_RISK_KEYWORDS: List[str] = [
        keyword.strip()
        for keyword in os.getenv(
            "PHYSICAL_RISK_KEYWORDS",
            "극심한 고온,극심한 한파,해안 홍수,도시 홍수,가뭄,물 부족,해수면 상승,태풍,산불",
        ).split(",")
    ]

    # 품질 검증
    QUALITY_MIN_WEATHER_FIELDS: int = int(os.getenv("QUALITY_MIN_WEATHER_FIELDS", "4"))
    QUALITY_MIN_DOMESTIC_NEWS: int = int(os.getenv("QUALITY_MIN_DOMESTIC_NEWS", "3"))
    QUALITY_MIN_GLOBAL_NEWS: int = int(os.getenv("QUALITY_MIN_GLOBAL_NEWS", "2"))
    QUALITY_MAX_RETRIES: int = int(os.getenv("QUALITY_MAX_RETRIES", "2"))
    MIN_QUALITY_SCORE: float = float(os.getenv("MIN_QUALITY_SCORE", "0.6"))

    # Logging
    LOG_LEVEL: str = os.getenv("ESG_LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("ESG_LOG_FILE", "logs/esg_agent.log")

    @classmethod
    def validate(cls) -> bool:
        """환경변수 체크

        Returns:
            bool: 모든 필수 환경변수가 설정되었으면 True
        """
        required_fields = [
            "OPENAI_API_KEY",
            "SLACK_BOT_TOKEN",
            "KMA_API_KEY",
        ]

        missing = []
        for field in required_fields:
            if not getattr(cls, field):
                missing.append(field)

        if missing:
            print(f"환경 변수 설정 필요: {', '.join(missing)}")
            return False

        return True

    @classmethod
    def get_weather_locations(cls) -> List[str]:
        """기상 관측 지역 목록 반환"""
        return cls.WEATHER_LOCATIONS

    @classmethod
    def get_physical_risks(cls) -> List[str]:
        """9대 물리적 리스크 목록 반환"""
        return cls.PHYSICAL_RISK_KEYWORDS


def get_config() -> Config:
    """설정 객체 반환"""
    return Config
