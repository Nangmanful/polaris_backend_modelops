"""
==================================================================
[모듈명] collectors/weather.py
날씨 데이터 수집기

[모듈 목표]
1) 기상청 API로 날씨 데이터 수집
2) 9대 물리적 리스크 분석
==================================================================
"""

from typing import Dict
from ..state import ESGTrendsState, WeatherData, PhysicalRiskAnalysis
from ..tools.weather_api import (
    fetch_weather_for_location,
    analyze_physical_risks,
    LOCATION_GRID_MAP,
)
from ..utils.config import Config
from ..utils.logging import get_logger

logger = get_logger("esg_agent.collector.weather")


def collect_weather(state: ESGTrendsState) -> Dict:
    """날씨 데이터 수집 및 물리적 리스크 분석

    Args:
        state: 현재 상태

    Returns:
        Dict: 업데이트할 상태 필드
    """
    logger.info("날씨 데이터 수집 시작")

    weather_data_list = []
    all_risks = []
    errors = []

    for location in Config.WEATHER_LOCATIONS:
        try:
            logger.info(f"{location} 날씨 데이터 수집 중...")

            # 좌표 확인
            if location not in LOCATION_GRID_MAP:
                logger.warning(f"{location}의 좌표 정보가 없습니다. 건너뜁니다.")
                continue

            # 날씨 데이터 가져오기
            weather_result = fetch_weather_for_location(location)

            if weather_result:
                weather_data = WeatherData(
                    location=location,
                    temperature=weather_result.get("temperature", 0.0),
                    humidity=weather_result.get("humidity", 0),
                    weather_condition=weather_result.get("sky_condition", ""),
                    wind_speed=weather_result.get("wind_speed", 0.0),
                    precipitation=weather_result.get("precipitation", 0.0),
                    forecast_date=weather_result.get("observed_at", "")[:10],
                    forecast_time=weather_result.get("observed_at", "")[11:16],
                    raw_data=weather_result,
                )
                weather_data_list.append(weather_data)
                logger.info(
                    f"{location} 날씨: {weather_data['temperature']}°C, {weather_data['weather_condition']}"
                )
            else:
                errors.append(f"{location} 날씨 데이터 수집 실패")

        except Exception as e:
            error_msg = f"{location} 날씨 수집 오류: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)

    # 물리적 리스크 분석
    if weather_data_list:
        logger.info("물리적 리스크 분석 중...")
        try:
            for weather_data in weather_data_list:
                # raw_data를 사용하여 리스크 분석
                raw = weather_data.get("raw_data", weather_data)
                risk_names = analyze_physical_risks(raw)

                for risk_name in risk_names:
                    physical_risk = PhysicalRiskAnalysis(
                        risk_type=risk_name,
                        risk_level="높음",
                        description=f"{weather_data['location']}에서 {risk_name} 위험 감지",
                        related_weather=[weather_data["location"]],
                    )
                    all_risks.append(physical_risk)

            logger.info(f"물리적 리스크 분석 완료: {len(all_risks)}개 리스크 감지")

        except Exception as e:
            error_msg = f"물리적 리스크 분석 오류: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)

    # 수집 상태 업데이트
    collection_status = state.get("collection_status", {}).copy()
    collection_status["weather"] = "success" if weather_data_list else "failed"

    logger.info(f"날씨 데이터 수집 완료: {len(weather_data_list)}개 지역")

    return {
        "weather_data": weather_data_list,
        "physical_risks": all_risks,
        "collection_status": collection_status,
        "errors": errors,
    }
