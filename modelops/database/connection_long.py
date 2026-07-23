from typing import Dict, List, Any
import json
from .connection import DatabaseConnection  # Retaining for get_connection()


class DatabaseConnectionLong:
    """
    Long-term database connection and data retrieval logic.
    Specialized for fetching 10-year averaged climate data for specific decades
    (2020s, 2030s, 2040s, 2050s) and for saving all calculated results with target_year.
    """

    # Decade mapping configuration
    DECADE_MAP = {2020: (2021, 2029), 2030: (2030, 2039), 2040: (2040, 2049), 2050: (2050, 2059)}

    # Scenario mapping (Input -> DB Column)
    SCENARIO_MAP = {
        "ssp126": "ssp1",
        "ssp1": "ssp1",
        "ssp245": "ssp2",
        "ssp2": "ssp2",
        "ssp370": "ssp3",
        "ssp3": "ssp3",
        "ssp585": "ssp5",
        "ssp5": "ssp5",
        "SSP126": "ssp1",
        "SSP245": "ssp2",
        "SSP370": "ssp3",
        "SSP585": "ssp5",
    }

    @classmethod
    def fetch_climate_data_by_decade(
        cls,
        latitude: float,
        longitude: float,
        decade_int_representation: int,
        ssp_scenario: str = "ssp2",
    ) -> Dict[str, List[float]]:
        """
        Fetches 10-year average climate data for a specific decade.
        `decade_int_representation` should be an integer like 2020, 2030 etc.
        """
        if decade_int_representation not in cls.DECADE_MAP:
            valid_decades = list(cls.DECADE_MAP.keys())
            raise ValueError(
                f"Invalid decade: {decade_int_representation}. Supported decades: {valid_decades}"
            )

        db_column = cls.SCENARIO_MAP.get(ssp_scenario)
        if not db_column:
            db_column = cls.SCENARIO_MAP.get(ssp_scenario.lower())

        if not db_column:
            db_column = "ssp2"

        start_year, end_year = cls.DECADE_MAP[decade_int_representation]

        return cls._fetch_averaged_data(latitude, longitude, start_year, end_year, db_column)

    @staticmethod
    def _fetch_averaged_data(
        latitude: float, longitude: float, start_year: int, end_year: int, db_column: str
    ) -> Dict[str, List[float]]:
        """
        Internal method to execute the aggregation queries.
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT grid_id
                FROM location_grid
                WHERE latitude = %s AND longitude = %s
                LIMIT 1
            """,
                (latitude, longitude),
            )

            grid_result = cursor.fetchone()
            if not grid_result:
                return {}

            grid_id = grid_result["grid_id"]
            averaged_data = {}

            # Monthly Data Aggregation
            monthly_tables = {
                "tamax": "tamax_data",
                "tamin": "tamin_data",
                "ta": "ta_data",
                "rn": "rn_data",
                "ws": "ws_data",
                "rhm": "rhm_data",
                "si": "si_data",
                "spei12": "spei12_data",
            }

            for key, table in monthly_tables.items():
                query = f"""
                    SELECT 
                        EXTRACT(MONTH FROM observation_date) as month,
                        AVG({db_column}) as avg_val
                    FROM {table}
                    WHERE grid_id = %s
                      AND EXTRACT(YEAR FROM observation_date) BETWEEN %s AND %s
                    GROUP BY month
                    ORDER BY month
                """
                cursor.execute(query, (grid_id, start_year, end_year))
                rows = cursor.fetchall()

                month_map = {int(row["month"]): row["avg_val"] for row in rows}
                averaged_data[key] = [month_map.get(m, 0.0) for m in range(1, 13)]

            # Yearly Data Aggregation
            yearly_tables = {
                "wsdi": "wsdi_data",
                "csdi": "csdi_data",
                "rx1day": "rx1day_data",
                "rx5day": "rx5day_data",
                "cdd": "cdd_data",
                "rain80": "rain80_data",
                "sdii": "sdii_data",
            }

            for key, table in yearly_tables.items():
                query = f"""
                    SELECT AVG({db_column}) as avg_val
                    FROM {table}
                    WHERE grid_id = %s
                      AND year BETWEEN %s AND %s
                """
                cursor.execute(query, (grid_id, start_year, end_year))
                result = cursor.fetchone()

                val = result["avg_val"] if result and result["avg_val"] is not None else 0.0
                averaged_data[key] = [float(val)]

            # Sea Level Rise Data Aggregation
            cursor.execute(
                """
                SELECT grid_id
                FROM sea_level_grid
                ORDER BY ST_Distance(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                )
                LIMIT 1
            """,
                (longitude, latitude),
            )

            slr_grid_result = cursor.fetchone()
            if slr_grid_result:
                slr_grid_id = slr_grid_result["grid_id"]
                query = f"""
                    SELECT AVG({db_column}) as avg_val
                    FROM sea_level_data
                    WHERE grid_id = %s
                      AND year BETWEEN %s AND %s
                """
                cursor.execute(query, (slr_grid_id, start_year, end_year))
                result = cursor.fetchone()
                val = result["avg_val"] if result and result["avg_val"] is not None else 0.0
                averaged_data["sea_level_rise"] = [float(val)]

            # Typhoon Data Aggregation
            cursor.execute(
                """
                SELECT COUNT(DISTINCT typ_seq)::float / NULLIF((%s - %s + 1), 0) as avg_count
                FROM api_typhoon_info
                WHERE year BETWEEN %s AND %s
                  AND eff_korea = true
            """,
                (end_year, start_year, start_year, end_year),
            )

            typhoon_result = cursor.fetchone()
            typhoon_count = (
                typhoon_result["avg_count"]
                if typhoon_result and typhoon_result["avg_count"] is not None
                else 0.0
            )

            cursor.execute(
                """
                SELECT AVG(max_ws) as avg_ws
                FROM api_typhoon_info
                WHERE year BETWEEN %s AND %s
                  AND eff_korea = true
            """,
                (start_year, end_year),
            )

            ws_result = cursor.fetchone()
            typhoon_ws = (
                ws_result["avg_ws"] if ws_result and ws_result["avg_ws"] is not None else 0.0
            )

            averaged_data["typhoon"] = [float(typhoon_count), float(typhoon_ws)]

            return averaged_data

    # ==================== Save Methods for all results (handling target_year as TEXT) ====================

    @staticmethod
    def save_probability_results(results: List[Dict[str, Any]]) -> None:
        """
        Save P(H) results including target_year (as text, e.g., '2030s').
        Matches Datawarehouse.dbml schema with SSP-specific columns.
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            for result in results:
                target_year_str = str(result.get("target_year", "2030s"))

                # JSON serialization for array/jsonb fields
                damage_rates_json = json.dumps(result.get("damage_rates", []))

                # Bin probabilities for each scenario
                ssp126_probs_json = json.dumps(result.get("ssp126_bin_probs", []))
                ssp245_probs_json = json.dumps(result.get("ssp245_bin_probs", []))
                ssp370_probs_json = json.dumps(result.get("ssp370_bin_probs", []))
                ssp585_probs_json = json.dumps(result.get("ssp585_bin_probs", []))

                cursor.execute(
                    """
                    INSERT INTO probability_results
                    (
                        latitude, longitude, risk_type, target_year,
                        ssp126_base_aal, ssp245_base_aal, ssp370_base_aal, ssp585_aal,
                        damage_rates,
                        ssp126_bin_probs, ssp245_bin_probs, ssp370_bin_probs, ssp585_bin_probs
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                    ON CONFLICT (latitude, longitude, risk_type, target_year)
                    DO UPDATE SET
                        ssp126_base_aal = EXCLUDED.ssp126_base_aal,
                        ssp245_base_aal = EXCLUDED.ssp245_base_aal,
                        ssp370_base_aal = EXCLUDED.ssp370_base_aal,
                        ssp585_aal = EXCLUDED.ssp585_aal,
                        damage_rates = EXCLUDED.damage_rates,
                        ssp126_bin_probs = EXCLUDED.ssp126_bin_probs,
                        ssp245_bin_probs = EXCLUDED.ssp245_bin_probs,
                        ssp370_bin_probs = EXCLUDED.ssp370_bin_probs,
                        ssp585_bin_probs = EXCLUDED.ssp585_bin_probs
                """,
                    (
                        result["latitude"],
                        result["longitude"],
                        result["risk_type"],
                        target_year_str,
                        result.get("ssp126_base_aal"),
                        result.get("ssp245_base_aal"),
                        result.get("ssp370_base_aal"),
                        result.get("ssp585_aal"),
                        damage_rates_json,
                        ssp126_probs_json,
                        ssp245_probs_json,
                        ssp370_probs_json,
                        ssp585_probs_json,
                    ),
                )

    @staticmethod
    def save_hazard_results(results: List[Dict[str, Any]]) -> None:
        """
        Save Hazard Score results including target_year.
        Matches Datawarehouse.dbml schema with SSP-specific scores.
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            for result in results:
                target_year_str = str(result.get("target_year", "2030s"))
                cursor.execute(
                    """
                    INSERT INTO hazard_results
                    (
                        latitude, longitude, risk_type, target_year,
                        ssp126_score_100, ssp245_score_100, ssp370_score_100, ssp585_score_100
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (latitude, longitude, risk_type, target_year)
                    DO UPDATE SET
                        ssp126_score_100 = EXCLUDED.ssp126_score_100,
                        ssp245_score_100 = EXCLUDED.ssp245_score_100,
                        ssp370_score_100 = EXCLUDED.ssp370_score_100,
                        ssp585_score_100 = EXCLUDED.ssp585_score_100
                """,
                    (
                        result["latitude"],
                        result["longitude"],
                        result["risk_type"],
                        target_year_str,
                        result.get("ssp126_score_100"),
                        result.get("ssp245_score_100"),
                        result.get("ssp370_score_100"),
                        result.get("ssp585_score_100"),
                    ),
                )

    @staticmethod
    def save_exposure_results(results: List[Dict[str, Any]]) -> None:
        """
        Save Exposure results.
        Requires 'site_id' as per Datawarehouse.dbml.
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            for result in results:
                target_year_str = str(result.get("target_year", "2030s"))
                if "site_id" not in result:
                    continue  # Skip if site_id is missing (DB constraint)

                cursor.execute(
                    """
                    INSERT INTO exposure_results
                    (site_id, latitude, longitude, risk_type, target_year, exposure_score)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (site_id, risk_type, target_year)
                    DO UPDATE SET
                        exposure_score = EXCLUDED.exposure_score,
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude
                """,
                    (
                        result["site_id"],
                        result["latitude"],
                        result["longitude"],
                        result["risk_type"],
                        target_year_str,
                        result.get("exposure_score", 0.0),
                    ),
                )

    @staticmethod
    def save_vulnerability_results(results: List[Dict[str, Any]]) -> None:
        """
        Save Vulnerability results.
        Requires 'site_id' as per Datawarehouse.dbml.
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            for result in results:
                target_year_str = str(result.get("target_year", "2030s"))
                if "site_id" not in result:
                    continue

                cursor.execute(
                    """
                    INSERT INTO vulnerability_results
                    (site_id, latitude, longitude, risk_type, target_year, vulnerability_score)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (site_id, risk_type, target_year)
                    DO UPDATE SET
                        vulnerability_score = EXCLUDED.vulnerability_score,
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude
                """,
                    (
                        result["site_id"],
                        result["latitude"],
                        result["longitude"],
                        result["risk_type"],
                        target_year_str,
                        result.get("vulnerability_score", 0.0),
                    ),
                )

    @staticmethod
    def save_aal_scaled_results(results: List[Dict[str, Any]]) -> None:
        """
        Save AAL scaled results.
        Requires 'site_id' and matches SSP-specific columns in Datawarehouse.dbml.
        """
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            for result in results:
                target_year_str = str(result.get("target_year", "2030s"))
                if "site_id" not in result:
                    continue

                cursor.execute(
                    """
                    INSERT INTO aal_scaled_results
                    (
                        site_id, latitude, longitude, risk_type, target_year,
                        ssp126_final_aal, ssp245_final_aal, ssp370_final_aal, ssp585_final_aal
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (site_id, risk_type, target_year)
                    DO UPDATE SET
                        ssp126_final_aal = EXCLUDED.ssp126_final_aal,
                        ssp245_final_aal = EXCLUDED.ssp245_final_aal,
                        ssp370_final_aal = EXCLUDED.ssp370_final_aal,
                        ssp585_final_aal = EXCLUDED.ssp585_final_aal,
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude
                """,
                    (
                        result["site_id"],
                        result["latitude"],
                        result["longitude"],
                        result["risk_type"],
                        target_year_str,
                        result.get("ssp126_final_aal"),
                        result.get("ssp245_final_aal"),
                        result.get("ssp370_final_aal"),
                        result.get("ssp585_final_aal"),
                    ),
                )
