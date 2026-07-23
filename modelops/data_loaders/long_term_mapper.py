from typing import Dict, Any


class LongTermDataMapper:
    """
    장기(Decadal) 기후 데이터를 Hazard Agent가 사용할 수 있는 포맷으로 변환하는 Mapper
    """

    def __init__(self):
        pass

    @staticmethod
    def map_data(
        risk_type: str, raw_avg_data: Dict[str, Any], base_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        DatabaseConnectionLong의 결과를 HazardAgent 입력 포맷으로 매핑

        Args:
            risk_type: 리스크 유형
            raw_avg_data: 10년 평균 기후 데이터 (DB 조회 결과)
            base_info: 기본 정보 (latitude, longitude, scenario, target_year, building_data 등)

        Returns:
            HazardAgent용 collected_data 딕셔너리
        """
        # 기본 구조 복사
        collected_data = base_info.copy()
        collected_data["risk_type"] = risk_type

        # climate_data, spatial_data, disaster_data 초기화 (없으면 빈 딕셔너리)
        if "climate_data" not in collected_data:
            collected_data["climate_data"] = {}
        if "spatial_data" not in collected_data:
            collected_data["spatial_data"] = {}
        if "disaster_data" not in collected_data:
            collected_data["disaster_data"] = {}

        # 헬퍼 함수
        def get_scalar(key, default=0.0):
            val_list = raw_avg_data.get(key, [])
            return float(val_list[0]) if val_list else default

        def get_monthly_avg(key, default=0.0):
            val_list = raw_avg_data.get(key, [])
            return sum(val_list) / len(val_list) if val_list else default

        # 리스크별 매핑 로직
        if risk_type == "extreme_heat":
            collected_data["climate_data"] = {
                "annual_max_temp_celsius": max(raw_avg_data.get("tamax", [30.0])),
                "heatwave_days_per_year": 10,
                "tropical_nights": 5,
                "heat_wave_duration": get_scalar("wsdi", 10.0),
            }
        elif risk_type == "extreme_cold":
            collected_data["climate_data"] = {
                "annual_min_temp_celsius": min(raw_avg_data.get("tamin", [-10.0])),
                "coldwave_days_per_year": 5,
                "ice_days": 2,
                "cold_wave_duration": get_scalar("csdi", 5.0),
            }
        elif risk_type == "river_flood":
            collected_data["climate_data"] = {
                "max_1day_rainfall_mm": get_scalar("rx1day", 100.0),
                "max_5day_rainfall_mm": get_scalar("rx5day", 200.0),
                "heavy_rain_days": int(get_scalar("rain80", 5.0)),
                "extreme_rain_95p": get_scalar("rx1day", 100.0) * 0.9,
            }
        elif risk_type == "urban_flood":
            collected_data["climate_data"] = {
                "max_1day_rainfall_mm": get_scalar("rx1day", 100.0),
                "max_5day_rainfall_mm": get_scalar("rx5day", 200.0),
                "heavy_rain_days": int(get_scalar("rain80", 5.0)),
                "extreme_rain_95p": get_scalar("rx1day", 100.0) * 0.9,
            }
        elif risk_type == "drought":
            collected_data["climate_data"] = {
                "spei12_index": get_monthly_avg("spei12", -0.5),
                "annual_rainfall_mm": sum(raw_avg_data.get("rn", [1000.0])),
                "consecutive_dry_days": int(get_scalar("cdd", 20.0)),
                "rainfall_intensity": get_scalar("sdii", 10.0),
            }
        elif risk_type == "wildfire":
            collected_data["climate_data"] = {
                "temperature": get_monthly_avg("ta", 15.0),
                "relative_humidity": get_monthly_avg("rhm", 60.0),
                "wind_speed": get_monthly_avg("ws", 2.0),
                "rainfall": get_monthly_avg("rn", 100.0) / 30.0,
            }
        elif risk_type == "water_stress":
            collected_data["climate_data"] = {
                "spei12_index": get_monthly_avg("spei12", -0.5),
                "annual_rainfall_mm": sum(raw_avg_data.get("rn", [1000.0])),
                "consecutive_dry_days": int(get_scalar("cdd", 20.0)),
                "rainfall_intensity": get_scalar("sdii", 10.0),
            }
        elif risk_type == "sea_level_rise":
            slr_val = 0.0
            if "sea_level_rise" in raw_avg_data:
                val_list = raw_avg_data["sea_level_rise"]
                if val_list:
                    slr_val = float(val_list[0])

            collected_data["climate_data"] = {
                "slr_cm": slr_val,
                "slr_m": slr_val / 100.0,
                "target_year": base_info.get("target_year"),
            }
        elif risk_type == "typhoon":
            typhoon_count = 0.0
            typhoon_ws = 0.0
            if "typhoon" in raw_avg_data:
                val_list = raw_avg_data["typhoon"]
                if len(val_list) >= 2:
                    typhoon_count = float(val_list[0])
                    typhoon_ws = float(val_list[1])

            collected_data["typhoon_data"] = {
                "typhoons": [],
                "avg_frequency": typhoon_count,
                "avg_max_wind_speed": typhoon_ws,
                "note": "Decadal average",
            }

        return collected_data
