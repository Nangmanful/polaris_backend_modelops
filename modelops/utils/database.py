"""
File: database.py
Last Modified: 2025-11-24
Version: v02
Description: PostgreSQL Datawarehouse connection and query utilities (Based on ERD v02.2)
Change History:
    - 2025-11-22: v01 - Initial creation
    - 2025-11-24: v02 - Updated to match actual ERD schema
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
import logging


class DatabaseManager:
    """
    PostgreSQL Datawarehouse connection and query manager
    Connects to skala_datawarehouse (port 5433) by default
    """

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize DatabaseManager

        Args:
            database_url: PostgreSQL connection URL (from env if not provided)
                         Default: Datawarehouse (port 5433)
        """
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL is not set")

        self.logger = logging.getLogger(__name__)

    @contextmanager
    def get_connection(self):
        """
        Database connection context manager

        Yields:
            psycopg2 connection object
        """
        conn = psycopg2.connect(self.database_url)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            self.logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Execute SELECT query and return results

        Args:
            query: SQL query
            params: Query parameters (tuple)

        Returns:
            List of query results (as dictionaries)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params)
            results = cursor.fetchall()
            cursor.close()

            # Convert RealDictRow to dict
            return [dict(row) for row in results]

    def execute_update(self, query: str, params: Optional[tuple] = None) -> int:
        """
        Execute INSERT/UPDATE/DELETE query

        Args:
            query: SQL query
            params: Query parameters (tuple)

        Returns:
            Number of affected rows
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rowcount = cursor.rowcount
            cursor.close()
            return rowcount

    # ==================== Location Queries ====================

    def find_nearest_grid(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """
        Find nearest climate grid point for given coordinates

        Args:
            latitude: Latitude (WGS84)
            longitude: Longitude (WGS84)

        Returns:
            Nearest grid info (grid_id, distance)
        """
        query = """
            SELECT
                grid_id,
                longitude,
                latitude,
                ST_Distance(
                    geom,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) as distance_meters
            FROM location_grid
            ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
            LIMIT 1
        """
        results = self.execute_query(query, (longitude, latitude, longitude, latitude))
        return results[0] if results else None

    def find_admin_by_code(self, admin_code: str) -> Optional[Dict[str, Any]]:
        """
        Find administrative region by admin_code

        Args:
            admin_code: Administrative code (e.g., "1101010100")

        Returns:
            Admin region info
        """
        query = """
            SELECT
                admin_id, admin_code, admin_name,
                sido_code, sigungu_code, emd_code,
                level, population_2020, population_2050
            FROM location_admin
            WHERE admin_code = %s
        """
        results = self.execute_query(query, (admin_code,))
        return results[0] if results else None

    def find_admin_by_coords(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """
        Find administrative region containing the coordinates

        Args:
            latitude: Latitude (WGS84)
            longitude: Longitude (WGS84)

        Returns:
            Admin region info
        """
        query = """
            SELECT
                admin_id, admin_code, admin_name,
                sido_code, sigungu_code, emd_code,
                level, population_2020, population_2050
            FROM location_admin
            WHERE ST_Contains(
                geom,
                ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 5174)
            )
            ORDER BY level DESC
            LIMIT 1
        """
        results = self.execute_query(query, (longitude, latitude))
        return results[0] if results else None

    # ==================== Monthly Grid Climate Data (Wide Format) ====================

    def fetch_monthly_grid_data(
        self,
        grid_id: int,
        start_date: str,
        end_date: str,
        scenario: Optional[str] = None,
        variables: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Fetch monthly climate data for a grid point (Wide format - ERD v03)

        Args:
            grid_id: Grid ID from location_grid
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            scenario: SSP scenario to select ('ssp1', 'ssp2', 'ssp3', 'ssp5')
                     If None, returns all 4 scenarios
            variables: List of variable codes (ta, rn, ws, rhm, si, spei12)
                      Default: ['ta', 'rn', 'ws']

        Returns:
            Dictionary with data for each variable
            Each row contains: observation_date, ssp1, ssp2, ssp3, ssp5
            (or single scenario column if scenario is specified)
        """
        if variables is None:
            variables = ["ta", "rn", "ws"]

        result = {}

        # Table mapping
        table_map = {
            "ta": "ta_data",
            "rn": "rn_data",
            "ws": "ws_data",
            "rhm": "rhm_data",
            "si": "si_data",
            "spei12": "spei12_data",
        }

        # Validate scenario
        valid_scenarios = ["ssp1", "ssp2", "ssp3", "ssp5"]
        if scenario and scenario not in valid_scenarios:
            self.logger.warning(f"Invalid scenario: {scenario}. Using all scenarios.")
            scenario = None

        for var in variables:
            if var not in table_map:
                self.logger.warning(f"Unknown variable: {var}")
                continue

            table_name = table_map[var]

            # Select columns based on scenario parameter
            if scenario:
                columns = f"observation_date, {scenario}"
            else:
                columns = "observation_date, ssp1, ssp2, ssp3, ssp5"

            query = f"""
                SELECT
                    {columns}
                FROM {table_name}
                WHERE grid_id = %s
                    AND observation_date BETWEEN %s AND %s
                ORDER BY observation_date
            """

            result[var] = self.execute_query(query, (grid_id, start_date, end_date))

        return result

    # ==================== Daily Admin Climate Data (Wide Format) ====================

    def fetch_daily_admin_data(
        self, admin_id: int, start_date: str, end_date: str, variables: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Fetch daily temperature data for administrative region (Wide format)

        Args:
            admin_id: Admin ID from location_admin
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            variables: List of variable codes (tamax, tamin)
                      Default: ['tamax', 'tamin']

        Returns:
            Dictionary with data for each variable
            Each row contains: time, ssp1, ssp2, ssp3, ssp5
        """
        if variables is None:
            variables = ["tamax", "tamin"]

        result = {}

        table_map = {"tamax": "tamax_data", "tamin": "tamin_data"}

        for var in variables:
            if var not in table_map:
                self.logger.warning(f"Unknown variable: {var}")
                continue

            table_name = table_map[var]
            query = f"""
                SELECT
                    time,
                    ssp1, ssp2, ssp3, ssp5
                FROM {table_name}
                WHERE admin_id = %s
                    AND time BETWEEN %s AND %s
                ORDER BY time
            """

            result[var] = self.execute_query(query, (admin_id, start_date, end_date))

        return result

    # ==================== Yearly Grid Climate Data (Wide Format) ====================

    def fetch_yearly_grid_data(
        self,
        grid_id: int,
        start_year: int,
        end_year: int,
        scenario: Optional[str] = None,
        variables: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Fetch yearly climate indices for a grid point (Wide format - ERD v03)

        Args:
            grid_id: Grid ID from location_grid
            start_year: Start year (2021-2100)
            end_year: End year (2021-2100)
            scenario: SSP scenario to select ('ssp1', 'ssp2', 'ssp3', 'ssp5')
                     If None, returns all 4 scenarios
            variables: List of variable codes
                      (csdi, wsdi, rx1day, rx5day, cdd, rain80, sdii, ta_yearly)
                      Default: ['csdi', 'wsdi', 'rx1day', 'rx5day']

        Returns:
            Dictionary with data for each variable
            Each row contains: year, ssp1, ssp2, ssp3, ssp5
            (or single scenario column if scenario is specified)
        """
        if variables is None:
            variables = ["csdi", "wsdi", "rx1day", "rx5day"]

        result = {}

        table_map = {
            "csdi": "csdi_data",
            "wsdi": "wsdi_data",
            "rx1day": "rx1day_data",
            "rx5day": "rx5day_data",
            "cdd": "cdd_data",
            "rain80": "rain80_data",
            "sdii": "sdii_data",
            "ta_yearly": "ta_yearly_data",
        }

        # Validate scenario
        valid_scenarios = ["ssp1", "ssp2", "ssp3", "ssp5"]
        if scenario and scenario not in valid_scenarios:
            self.logger.warning(f"Invalid scenario: {scenario}. Using all scenarios.")
            scenario = None

        for var in variables:
            if var not in table_map:
                self.logger.warning(f"Unknown variable: {var}")
                continue

            table_name = table_map[var]

            # Select columns based on scenario parameter
            if scenario:
                columns = f"year, {scenario}"
            else:
                columns = "year, ssp1, ssp2, ssp3, ssp5"

            query = f"""
                SELECT
                    {columns}
                FROM {table_name}
                WHERE grid_id = %s
                    AND year BETWEEN %s AND %s
                ORDER BY year
            """

            result[var] = self.execute_query(query, (grid_id, start_year, end_year))

        return result

    # ==================== Sea Level Data ====================

    def fetch_sea_level_data(
        self,
        latitude: float,
        longitude: float,
        start_year: int,
        end_year: int,
        scenario: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch sea level rise data for coastal location (Wide format - ERD v03)

        Args:
            latitude: Latitude (WGS84)
            longitude: Longitude (WGS84)
            start_year: Start year (2015-2100)
            end_year: End year (2015-2100)
            scenario: SSP scenario to select ('ssp1', 'ssp2', 'ssp3', 'ssp5')
                     If None, returns all 4 scenarios

        Returns:
            List of sea level data
            Each row contains: year, ssp1, ssp2, ssp3, ssp5 (cm)
            (or single scenario column if scenario is specified)
        """
        # First, find nearest sea level grid point
        grid_query = """
            SELECT
                grid_id,
                ST_Distance(
                    geom,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) as distance_meters
            FROM sea_level_grid
            ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
            LIMIT 1
        """
        grid_result = self.execute_query(grid_query, (longitude, latitude, longitude, latitude))

        if not grid_result:
            return []

        grid_id = grid_result[0]["grid_id"]

        # Validate scenario
        valid_scenarios = ["ssp1", "ssp2", "ssp3", "ssp5"]
        if scenario and scenario not in valid_scenarios:
            self.logger.warning(f"Invalid scenario: {scenario}. Using all scenarios.")
            scenario = None

        # Select columns based on scenario parameter
        if scenario:
            columns = f"year, {scenario} as sea_level_rise_cm"
        else:
            columns = "year, ssp1, ssp2, ssp3, ssp5"

        # Fetch sea level data
        data_query = f"""
            SELECT
                {columns}
            FROM sea_level_data
            WHERE grid_id = %s
                AND year BETWEEN %s AND %s
            ORDER BY year
        """

        return self.execute_query(data_query, (grid_id, start_year, end_year))

    # ==================== Spatial Analysis Cache ====================

    def fetch_spatial_landcover(self, site_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch cached landcover analysis for a site

        Args:
            site_id: Site UUID from application DB

        Returns:
            Landcover analysis results
        """
        query = """
            SELECT
                urban_ratio, forest_ratio, agriculture_ratio,
                water_ratio, grassland_ratio, wetland_ratio, barren_ratio,
                landcover_year, analyzed_at, is_valid
            FROM spatial_landcover
            WHERE site_id = %s
                AND is_valid = true
            ORDER BY analyzed_at DESC
            LIMIT 1
        """
        results = self.execute_query(query, (site_id,))
        return results[0] if results else None

    def fetch_spatial_dem(self, site_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch cached DEM analysis for a site

        Args:
            site_id: Site UUID from application DB

        Returns:
            DEM analysis results (elevation, slope, aspect)
        """
        query = """
            SELECT
                elevation_point, elevation_mean, elevation_min, elevation_max,
                slope_point, slope_mean, slope_max,
                aspect_point, aspect_dominant,
                terrain_class, flood_risk_terrain,
                analyzed_at, is_valid
            FROM spatial_dem
            WHERE site_id = %s
                AND is_valid = true
            ORDER BY analyzed_at DESC
            LIMIT 1
        """
        results = self.execute_query(query, (site_id,))
        return results[0] if results else None

    # ==================== API Cache Queries ====================

    def fetch_nearby_hospitals(
        self, latitude: float, longitude: float, radius_km: float = 5.0
    ) -> List[Dict[str, Any]]:
        """
        Fetch hospitals within radius

        Args:
            latitude: Latitude
            longitude: Longitude
            radius_km: Search radius (km)

        Returns:
            List of hospitals
        """
        query = """
            SELECT
                yadm_nm as name,
                addr as address,
                clcd_nm as type,
                tel_no as phone,
                x_pos, y_pos,
                ST_Distance(
                    location,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) as distance_meters
            FROM api_hospitals
            WHERE ST_DWithin(
                location,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s * 1000
            )
            ORDER BY distance_meters
        """
        return self.execute_query(query, (longitude, latitude, longitude, latitude, radius_km))

    def fetch_nearby_shelters(self, admin_code: str) -> Optional[Dict[str, Any]]:
        """
        Fetch shelter information for administrative region

        Args:
            admin_code: Administrative code

        Returns:
            Shelter statistics
        """
        query = """
            SELECT
                regi as region,
                target_popl as target_population,
                accpt_rt as acceptance_rate,
                shelt_abl_popl_smry as total_shelter_capacity,
                gov_shelts_shelts as government_shelters,
                pub_shelts_shelts as public_shelters
            FROM api_shelters
            WHERE regi = %s
            ORDER BY bas_yy DESC
            LIMIT 1
        """
        results = self.execute_query(query, (admin_code,))
        return results[0] if results else None

    def fetch_typhoon_history(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 100.0,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical typhoon tracks near location

        Args:
            latitude: Latitude
            longitude: Longitude
            radius_km: Search radius (km)
            start_year: Start year (optional)
            end_year: End year (optional)

        Returns:
            List of typhoon events
        """
        query = """
            SELECT
                typhoon_year, typhoon_number,
                typhoon_name_kr, typhoon_name_en,
                observation_time,
                latitude, longitude,
                central_pressure, max_wind_speed,
                typhoon_grade,
                ST_Distance(
                    location,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) as distance_meters
            FROM typhoon_besttrack
            WHERE ST_DWithin(
                location,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s * 1000
            )
        """

        params = [longitude, latitude, longitude, latitude, radius_km]

        if start_year:
            query += " AND typhoon_year >= %s"
            params.append(start_year)

        if end_year:
            query += " AND typhoon_year <= %s"
            params.append(end_year)

        query += " ORDER BY observation_time DESC"

        return self.execute_query(query, tuple(params))

    # ==================== Comprehensive Data Collection ====================

    def collect_all_climate_data(
        self,
        latitude: float,
        longitude: float,
        start_year: int,
        end_year: int,
        scenario: Optional[str] = None,  # Changed from scenario_id to scenario (ERD v03)
        admin_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Comprehensive climate data collection for a location (ERD v03 Wide Format)

        Args:
            latitude: Latitude
            longitude: Longitude
            start_year: Start year
            end_year: End year
            scenario: SSP scenario ('ssp1', 'ssp2', 'ssp3', 'ssp5')
                     If None, returns all 4 scenarios (default behavior)
            admin_code: Optional admin code (if known)

        Returns:
            Dictionary containing all climate data
            All data uses Wide format (ssp1, ssp2, ssp3, ssp5 columns)
        """
        result = {
            "location": {"latitude": latitude, "longitude": longitude},
            "period": {"start_year": start_year, "end_year": end_year},
            "scenario": scenario or "all",  # Changed from scenario_id
        }

        # 1. Find nearest grid
        grid = self.find_nearest_grid(latitude, longitude)
        if grid:
            result["grid"] = grid
            grid_id = grid["grid_id"]

            # 2. Fetch monthly grid data (Wide format)
            start_date = f"{start_year}-01-01"
            end_date = f"{end_year}-12-31"
            result["monthly_data"] = self.fetch_monthly_grid_data(
                grid_id, start_date, end_date, scenario
            )

            # 3. Fetch yearly grid data (Wide format)
            result["yearly_data"] = self.fetch_yearly_grid_data(
                grid_id, start_year, end_year, scenario
            )

        # 4. Find admin region
        if admin_code:
            admin = self.find_admin_by_code(admin_code)
        else:
            admin = self.find_admin_by_coords(latitude, longitude)

        if admin:
            result["admin"] = admin
            admin_id = admin["admin_id"]

            # 5. Fetch daily admin data (Already Wide format)
            start_date = f"{start_year}-01-01"
            end_date = f"{end_year}-12-31"
            result["daily_data"] = self.fetch_daily_admin_data(admin_id, start_date, end_date)

        # 6. Sea level data (Wide format)
        result["sea_level_data"] = self.fetch_sea_level_data(
            latitude, longitude, start_year, end_year, scenario
        )

        return result

    # ==================== ModelOps Results Queries ====================

    def fetch_hazard_results(
        self,
        latitude: float,
        longitude: float,
        target_years: Optional[List[str]] = None,
        risk_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch Hazard Score results from ModelOps calculations

        Args:
            latitude: Latitude
            longitude: Longitude
            target_years: List of target years (e.g., ["2025", "2030", "2030s"]).
                         If None, returns all years.
            risk_type: Optional risk type filter (e.g., 'TYPHOON', 'INLAND_FLOOD')
                      If None, returns all 9 risk types

        Returns:
            List of hazard results with scores and levels
        """
        query = """
            SELECT
                latitude,
                longitude,
                risk_type,
                target_year,
                ssp126_score_100,
                ssp245_score_100,
                ssp370_score_100,
                ssp585_score_100
            FROM hazard_results
            WHERE latitude = %s AND longitude = %s
        """
        params: List[Any] = [latitude, longitude]

        if target_years:
            placeholders = ", ".join(["%s"] * len(target_years))
            query += f" AND target_year IN ({placeholders})"
            params.extend(target_years)

        if risk_type:
            query += " AND risk_type = %s"
            params.append(risk_type)

        query += " ORDER BY target_year, risk_type"

        return self.execute_query(query, tuple(params))

    def fetch_exposure_results(
        self,
        site_id: str,
        target_years: Optional[List[str]] = None,
        risk_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch Exposure Score results from ModelOps calculations

        Args:
            site_id: Site UUID
            target_years: List of target years. If None, returns all years.
            risk_type: Optional risk type filter

        Returns:
            List of exposure results with scores
        """
        query = """
            SELECT
                site_id,
                latitude,
                longitude,
                risk_type,
                target_year,
                exposure_score
            FROM exposure_results
            WHERE site_id = %s
        """
        params: List[Any] = [site_id]

        if target_years:
            placeholders = ", ".join(["%s"] * len(target_years))
            query += f" AND target_year IN ({placeholders})"
            params.extend(target_years)

        if risk_type:
            query += " AND risk_type = %s"
            params.append(risk_type)

        query += " ORDER BY target_year, risk_type"

        return self.execute_query(query, tuple(params))

    def fetch_vulnerability_results(
        self,
        site_id: str,
        target_years: Optional[List[str]] = None,
        risk_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch Vulnerability Score results from ModelOps calculations

        Args:
            site_id: Site UUID
            target_years: List of target years. If None, returns all years.
            risk_type: Optional risk type filter

        Returns:
            List of vulnerability results with scores
        """
        query = """
            SELECT
                site_id,
                latitude,
                longitude,
                risk_type,
                target_year,
                vulnerability_score
            FROM vulnerability_results
            WHERE site_id = %s
        """
        params: List[Any] = [site_id]

        if target_years:
            placeholders = ", ".join(["%s"] * len(target_years))
            query += f" AND target_year IN ({placeholders})"
            params.extend(target_years)

        if risk_type:
            query += " AND risk_type = %s"
            params.append(risk_type)

        query += " ORDER BY target_year, risk_type"

        return self.execute_query(query, tuple(params))

    def fetch_probability_results(
        self,
        latitude: float,
        longitude: float,
        target_years: Optional[List[str]] = None,
        risk_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch Probability P(H) results from ModelOps calculations

        Args:
            latitude: Latitude
            longitude: Longitude
            target_years: List of target years. If None, returns all years.
            risk_type: Optional risk type filter

        Returns:
            List of probability results with bin probabilities and AAL
        """
        query = """
            SELECT
                latitude,
                longitude,
                risk_type,
                target_year,
                ssp126_aal,
                ssp245_aal,
                ssp370_aal,
                ssp585_aal,
                ssp126_bin_probs,
                ssp245_bin_probs,
                ssp370_bin_probs,
                ssp585_bin_probs
            FROM probability_results
            WHERE latitude = %s AND longitude = %s
        """
        params: List[Any] = [latitude, longitude]

        if target_years:
            placeholders = ", ".join(["%s"] * len(target_years))
            query += f" AND target_year IN ({placeholders})"
            params.extend(target_years)

        if risk_type:
            query += " AND risk_type = %s"
            params.append(risk_type)

        query += " ORDER BY target_year, risk_type"

        return self.execute_query(query, tuple(params))

    def fetch_aal_scaled_results(
        self,
        site_id: str,
        target_years: Optional[List[str]] = None,
        risk_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch final AAL results (scaled by vulnerability) from ModelOps

        Args:
            site_id: Site UUID
            target_years: List of target years. If None, returns all years.
            risk_type: Optional risk type filter

        Returns:
            List of AAL results with base and final AAL values
        """
        query = """
            SELECT
                site_id,
                latitude,
                longitude,
                risk_type,
                target_year,
                ssp126_final_aal,
                ssp245_final_aal,
                ssp370_final_aal,
                ssp585_final_aal
            FROM aal_scaled_results
            WHERE site_id = %s
        """
        params: List[Any] = [site_id]

        if target_years:
            placeholders = ", ".join(["%s"] * len(target_years))
            query += f" AND target_year IN ({placeholders})"
            params.extend(target_years)

        if risk_type:
            query += " AND risk_type = %s"
            params.append(risk_type)

        query += " ORDER BY target_year, risk_type"

        return self.execute_query(query, tuple(params))

    def fetch_all_modelops_results(
        self,
        site_id: str,
        latitude: float,
        longitude: float,
        target_years: Optional[List[str]] = None,
        risk_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch all ModelOps calculation results for a location

        Args:
            site_id: Site UUID from application DB
            latitude: Latitude
            longitude: Longitude
            target_years: List of target years (e.g., ["2025", "2030", "2030s"]).
                         If None, returns all years.
            risk_type: Optional risk type filter

        Returns:
            Dictionary containing all ModelOps results:
            - hazard_results: H scores
            - exposure_results: E scores
            - vulnerability_results: V scores
            - probability_results: P(H) and base AAL
            - aal_scaled_results: Final AAL (scaled by V)
        """
        return {
            "hazard_results": self.fetch_hazard_results(
                latitude, longitude, target_years, risk_type
            ),
            "exposure_results": self.fetch_exposure_results(site_id, target_years, risk_type),
            "vulnerability_results": self.fetch_vulnerability_results(
                site_id, target_years, risk_type
            ),
            "probability_results": self.fetch_probability_results(
                latitude, longitude, target_years, risk_type
            ),
            "aal_scaled_results": self.fetch_aal_scaled_results(site_id, target_years, risk_type),
        }

    # ==================== Batch Jobs Tracking ====================

    def fetch_batch_job(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch batch job status by batch_id

        Args:
            batch_id: Batch job UUID

        Returns:
            Batch job information or None if not found
        """
        query = """
            SELECT
                batch_id,
                job_type,
                status,
                progress,
                total_items,
                completed_items,
                failed_items,
                input_params,
                results,
                error_message,
                error_stack_trace,
                estimated_duration_minutes,
                actual_duration_seconds,
                created_at,
                started_at,
                completed_at,
                expires_at,
                created_by
            FROM batch_jobs
            WHERE batch_id = %s
        """
        results = self.execute_query(query, (batch_id,))
        return results[0] if results else None

    def fetch_batch_jobs_by_status(
        self, status: str, job_type: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Fetch batch jobs by status

        Args:
            status: Job status ('queued', 'running', 'completed', 'failed', 'cancelled')
            job_type: Optional job type filter
            limit: Maximum number of results

        Returns:
            List of batch jobs
        """
        query = """
            SELECT
                batch_id,
                job_type,
                status,
                progress,
                total_items,
                completed_items,
                failed_items,
                created_at,
                started_at,
                completed_at
            FROM batch_jobs
            WHERE status = %s
        """
        params = [status]

        if job_type:
            query += " AND job_type = %s"
            params.append(job_type)

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        return self.execute_query(query, tuple(params))

    # ==================== Building Aggregate Cache Queries ====================

    def fetch_building_cache_by_coords(
        self, lat: float, lon: float, radius_km: float = 0.5
    ) -> Optional[Dict[str, Any]]:
        """
        좌표 기반으로 가장 가까운 건물 캐시 조회

        Args:
            lat: 위도
            lon: 경도
            radius_km: 검색 반경 (km, 기본 0.5km)

        Returns:
            가장 가까운 건물 캐시 데이터 (연면적 기준 최대값)
        """
        # 3개 SK 사업장 특별 처리 (좌표로 직접 매핑)
        is_daedeok = (36.37 < lat < 36.39) and (127.39 < lon < 127.41)
        is_sk_u_tower = (37.36 < lat < 37.37) and (127.10 < lon < 127.11)
        is_pangyo = (37.40 < lat < 37.41) and (127.09 < lon < 127.10)

        if is_daedeok:
            sigungu_cd, bjdong_cd = "30200", "14200"
        elif is_sk_u_tower:
            sigungu_cd, bjdong_cd = "41135", "10300"
        elif is_pangyo:
            sigungu_cd, bjdong_cd = "41135", "10900"
        else:
            return None  # 특정 사업장만 지원

        # 해당 지역의 건물 중 연면적이 가장 큰 건물 반환
        query = """
            SELECT
                sigungu_cd,
                bjdong_cd,
                bun,
                ji,
                max_ground_floors,
                max_underground_floors,
                oldest_building_age_years,
                total_floor_area_sqm,
                total_building_area_sqm,
                structure_types,
                purpose_types
            FROM building_aggregate_cache
            WHERE sigungu_cd = %s
              AND bjdong_cd = %s
              AND total_floor_area_sqm > 0
            ORDER BY total_floor_area_sqm DESC
            LIMIT 1
        """
        results = self.execute_query(query, (sigungu_cd, bjdong_cd))
        return results[0] if results else None

    def fetch_building_aggregate_cache(
        self, sigungu_cd: str, bjdong_cd: str, bun: str, ji: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch cached building aggregate data by address codes

        Args:
            sigungu_cd: 시군구 코드 (5자리)
            bjdong_cd: 법정동 코드 (5자리)
            bun: 번 (4자리)
            ji: 지 (4자리)

        Returns:
            Building aggregate data or None if not found
        """
        query = """
            SELECT
                cache_id,
                sigungu_cd,
                bjdong_cd,
                bun,
                ji,
                jibun_address,
                road_address,
                building_count,
                structure_types,
                purpose_types,
                max_ground_floors,
                max_underground_floors,
                min_underground_floors,
                buildings_with_seismic,
                buildings_without_seismic,
                oldest_approval_date,
                newest_approval_date,
                oldest_building_age_years,
                total_floor_area_sqm,
                total_building_area_sqm,
                floor_details,
                floor_purpose_types,
                cached_at,
                updated_at,
                data_quality_score
            FROM building_aggregate_cache
            WHERE sigungu_cd = %s
              AND bjdong_cd = %s
              AND bun = %s
              AND ji = %s
            ORDER BY cached_at DESC
            LIMIT 1
        """
        results = self.execute_query(query, (sigungu_cd, bjdong_cd, bun, ji))
        return results[0] if results else None

    def save_building_aggregate_cache(
        self, sigungu_cd: str, bjdong_cd: str, bun: str, ji: str, building_data: Dict[str, Any]
    ) -> bool:
        """
        Save or update building aggregate data to cache

        Args:
            sigungu_cd: 시군구 코드
            bjdong_cd: 법정동 코드
            bun: 번
            ji: 지
            building_data: Building data from BuildingDataFetcher

        Returns:
            True if successful, False otherwise
        """
        try:
            from psycopg2.extras import Json

            # building_data에서 필요한 값 추출
            physical_specs = building_data.get("physical_specs", {})
            meta = building_data.get("meta", {})
            floor_details = building_data.get("floor_details", [])

            # 구조 유형 추출
            structure = physical_specs.get("structure", "")
            structure_types = {structure: 1} if structure else {}

            # 용도 유형 추출
            main_purpose = physical_specs.get("main_purpose", "")
            purpose_types = {main_purpose: 1} if main_purpose else {}

            # 층수 정보 (API 형식과 DB 형식 모두 대응)
            floors = physical_specs.get("floors", {})
            transition_specs = building_data.get("transition_specs", {})
            max_ground_floors = floors.get("ground", 0) or floors.get("max_ground", 0)
            max_underground_floors = floors.get("underground", 0) or floors.get(
                "max_underground", 0
            )
            min_underground_floors = floors.get("min_underground", 0)

            # 내진 설계 정보
            seismic = physical_specs.get("seismic", {})
            buildings_with_seismic = seismic.get("buildings_with_design", 0)
            buildings_without_seismic = seismic.get("buildings_without_design", 0)

            # 연식 정보
            age_info = physical_specs.get("age", {})
            oldest_building_age = age_info.get("years", 0)

            # 면적 정보 (여러 형식 대응)
            # physical_specs 직접 확인 (total_area, arch_area)
            # area 딕셔너리 확인 (total_floor_area, building_area)
            # transition_specs 확인 (total_area, total_area_sum)
            area = physical_specs.get("area", {})
            total_floor_area = (
                physical_specs.get("total_area", 0)  # 직접 필드
                or area.get("total_floor_area", 0)  # area 딕셔너리
                or transition_specs.get("total_area", 0)
                or transition_specs.get("total_area_sum", 0)
            )
            total_building_area = physical_specs.get("arch_area", 0) or area.get(  # 직접 필드
                "building_area", 0
            )  # area 딕셔너리

            # 층별 용도 유형 집계
            floor_purpose_types = {}
            for floor in floor_details:
                usage = floor.get("usage_main", "")
                if usage:
                    floor_purpose_types[usage] = floor_purpose_types.get(usage, 0) + 1

            # UPSERT 쿼리 (존재하면 업데이트, 없으면 삽입)
            query = """
                INSERT INTO building_aggregate_cache (
                    sigungu_cd, bjdong_cd, bun, ji,
                    jibun_address, road_address,
                    building_count,
                    structure_types, purpose_types,
                    max_ground_floors, max_underground_floors, min_underground_floors,
                    buildings_with_seismic, buildings_without_seismic,
                    oldest_building_age_years,
                    total_floor_area_sqm, total_building_area_sqm,
                    floor_details, floor_purpose_types,
                    cached_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s,
                    %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s,
                    %s, %s,
                    %s, %s,
                    NOW(), NOW()
                )
                ON CONFLICT (sigungu_cd, bjdong_cd, bun, ji)
                DO UPDATE SET
                    jibun_address = EXCLUDED.jibun_address,
                    road_address = EXCLUDED.road_address,
                    building_count = EXCLUDED.building_count,
                    structure_types = EXCLUDED.structure_types,
                    purpose_types = EXCLUDED.purpose_types,
                    max_ground_floors = EXCLUDED.max_ground_floors,
                    max_underground_floors = EXCLUDED.max_underground_floors,
                    min_underground_floors = EXCLUDED.min_underground_floors,
                    buildings_with_seismic = EXCLUDED.buildings_with_seismic,
                    buildings_without_seismic = EXCLUDED.buildings_without_seismic,
                    oldest_building_age_years = EXCLUDED.oldest_building_age_years,
                    total_floor_area_sqm = EXCLUDED.total_floor_area_sqm,
                    total_building_area_sqm = EXCLUDED.total_building_area_sqm,
                    floor_details = EXCLUDED.floor_details,
                    floor_purpose_types = EXCLUDED.floor_purpose_types,
                    updated_at = NOW(),
                    api_call_count = building_aggregate_cache.api_call_count + 1
            """

            params = (
                sigungu_cd,
                bjdong_cd,
                bun,
                ji,
                meta.get("jibun_address", ""),
                meta.get("road_address", "") or meta.get("address", ""),
                1,  # building_count (단일 건물 기준)
                Json(structure_types),
                Json(purpose_types),
                max_ground_floors,
                max_underground_floors,
                min_underground_floors,
                buildings_with_seismic,
                buildings_without_seismic,
                oldest_building_age,
                total_floor_area,
                total_building_area,
                Json(floor_details),
                Json(floor_purpose_types),
            )

            self.execute_update(query, params)
            self.logger.info(f"Building cache saved: {sigungu_cd}-{bjdong_cd}-{bun}-{ji}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save building cache: {e}")
            return False

    def convert_cache_to_building_data(self, cache_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert building_aggregate_cache format to BuildingDataFetcher format

        Args:
            cache_data: Data from building_aggregate_cache table

        Returns:
            Building data in BuildingDataFetcher format
        """
        if not cache_data:
            return {}

        # 구조 유형 추출 (가장 많은 것)
        # DB에 list 또는 dict로 저장될 수 있음
        structure_types = cache_data.get("structure_types", {})
        if isinstance(structure_types, list):
            # list인 경우: 첫 번째 요소 사용
            main_structure = structure_types[0] if structure_types else ""
        elif isinstance(structure_types, dict):
            # dict인 경우: 가장 많은 것 선택
            main_structure = (
                max(structure_types.keys(), key=lambda k: structure_types[k])
                if structure_types
                else ""
            )
        else:
            main_structure = ""

        # 용도 유형 추출
        purpose_types = cache_data.get("purpose_types", {})
        if isinstance(purpose_types, list):
            main_purpose = purpose_types[0] if purpose_types else ""
        elif isinstance(purpose_types, dict):
            main_purpose = (
                max(purpose_types.keys(), key=lambda k: purpose_types[k]) if purpose_types else ""
            )
        else:
            main_purpose = ""

        # NULL 값 처리 헬퍼
        def safe_int(val, default=0):
            return val if val is not None else default

        def safe_float(val, default=0.0):
            return float(val) if val is not None else default

        buildings_with_seismic = safe_int(cache_data.get("buildings_with_seismic"))
        buildings_without_seismic = safe_int(cache_data.get("buildings_without_seismic"))

        return {
            "meta": {
                "jibun_address": cache_data.get("jibun_address", "") or "",
                "road_address": cache_data.get("road_address", "") or "",
                "address": cache_data.get("road_address")
                or cache_data.get("jibun_address", "")
                or "",
                "data_source": "building_aggregate_cache",
            },
            "physical_specs": {
                "structure": main_structure,
                "main_purpose": main_purpose,
                "floors": {
                    "ground": safe_int(cache_data.get("max_ground_floors")),
                    "max_underground": safe_int(cache_data.get("max_underground_floors")),
                    "min_underground": safe_int(cache_data.get("min_underground_floors")),
                },
                "seismic": {
                    "applied": "Y" if buildings_with_seismic > 0 else "N",
                    "buildings_with_design": buildings_with_seismic,
                    "buildings_without_design": buildings_without_seismic,
                },
                "age": {"years": safe_int(cache_data.get("oldest_building_age_years"))},
                "area": {
                    "total_floor_area": safe_float(cache_data.get("total_floor_area_sqm")),
                    "building_area": safe_float(cache_data.get("total_building_area_sqm")),
                },
            },
            "floor_details": cache_data.get("floor_details") or [],
            "transition_specs": {"total_area": safe_float(cache_data.get("total_floor_area_sqm"))},
        }

    # ==================== Site Additional Data Queries ====================

    def save_additional_data(
        self,
        site_id: str,
        structured_data: Dict[str, Any],
        metadata: Dict[str, Any] = None,
        data_category: str = None,  # deprecated, stored in metadata
    ) -> bool:
        """
        Save additional data to site_additional_data table

        Args:
            site_id: Site UUID
            structured_data: Parsed data (text dump)
            metadata: File metadata (optional, category stored here)
            data_category: DEPRECATED - use metadata['inferred_category']

        Returns:
            True if successful, False otherwise
        """
        try:
            from psycopg2.extras import Json

            # data_category는 metadata에 저장
            if data_category and metadata:
                metadata["data_category"] = data_category

            query = """
                INSERT INTO site_additional_data
                (site_id, structured_data, metadata, uploaded_at)
                VALUES (%s, %s, %s, NOW())
            """

            params = (site_id, Json(structured_data), Json(metadata or {}))

            self.execute_update(query, params)
            self.logger.info(f"Additional data saved: site_id={site_id[:8]}...")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save additional data: {e}")
            return False

    def fetch_additional_data(
        self, site_id: str, data_category: str = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch additional data from site_additional_data table

        Args:
            site_id: Site UUID
            data_category: Data category filter (None for all - uses metadata.inferred_category)

        Returns:
            List of additional data records

        Note:
            data_category 컬럼이 테이블에서 제거됨 (v05)
            카테고리 필터링은 metadata->>'inferred_category'를 사용
        """
        if data_category:
            query = """
                SELECT
                    id,
                    site_id,
                    metadata->>'inferred_category' as data_category,
                    metadata->>'file_name' as file_name,
                    structured_data,
                    metadata,
                    uploaded_at
                FROM site_additional_data
                WHERE site_id = %s AND metadata->>'inferred_category' = %s
                ORDER BY uploaded_at DESC
            """
            params = (site_id, data_category)
        else:
            query = """
                SELECT
                    id,
                    site_id,
                    metadata->>'inferred_category' as data_category,
                    metadata->>'file_name' as file_name,
                    structured_data,
                    metadata,
                    uploaded_at
                FROM site_additional_data
                WHERE site_id = %s
                ORDER BY uploaded_at DESC
            """
            params = (site_id,)

        return self.execute_query(query, params)

    # ==================== Reports Queries (Application DB) ====================

    def save_report(self, user_id: str, report_content: Dict[str, Any]) -> Optional[str]:
        """
        Save TCFD report to reports table (Application DB)

        Args:
            user_id: User UUID
            report_content: Full report JSON (JSONB)

        Returns:
            report_id (UUID string) if successful, None otherwise
        """
        try:
            from psycopg2.extras import Json

            query = """
                INSERT INTO reports (user_id, report_content)
                VALUES (%s, %s)
                RETURNING id
            """

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (user_id, Json(report_content)))
                result = cursor.fetchone()
                cursor.close()

                if result:
                    report_id = str(result[0])
                    self.logger.info(f"Report saved: {report_id}")
                    return report_id
                return None

        except Exception as e:
            self.logger.error(f"Failed to save report: {e}")
            return None

    def fetch_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch report by ID

        Args:
            report_id: Report UUID

        Returns:
            Report data or None if not found
        """
        query = """
            SELECT id, user_id, report_content
            FROM reports
            WHERE id = %s
        """
        results = self.execute_query(query, (report_id,))
        return results[0] if results else None

    def fetch_reports_by_user(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch reports by user ID

        Args:
            user_id: User UUID
            limit: Maximum number of reports

        Returns:
            List of reports
        """
        query = """
            SELECT id, user_id, report_content
            FROM reports
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT %s
        """
        return self.execute_query(query, (user_id, limit))
