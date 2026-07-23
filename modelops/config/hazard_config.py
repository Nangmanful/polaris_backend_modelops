#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Configuration settings for the Physical Risk Calculation project.

This file centralizes hardcoded values, thresholds, and other configuration
parameters to improve maintainability and clarity.
"""

# ============================================================================
# DEFAULT VALUES for data fetching fallbacks
# ============================================================================
# These values are used when the data fetcher fails to retrieve real data.
DEFAULT_BUILDING_PROPERTIES = {
    "elevation_m": 0,
    "ground_floors": 3,
    "basement_floors": 0,
    "total_area_m2": 0,
    "building_type": "주택",
    "main_purpose": "단독주택",
    "structure": "철근콘크리트조",
    "build_year": 1995,
    "building_age": 30,
    "has_piloti": False,
}

DEFAULT_DISTANCE_VALUES = {
    "distance_to_river_m": 1000,
    "distance_to_coast_m": 50000,
}

DEFAULT_HYDROLOGICAL_VALUES = {
    "watershed_area_km2": 2500,
    "stream_order": 3,
    "annual_rainfall_mm": 1200,
}

# ============================================================================
# VULNERABILITY BASE SCORES
# ============================================================================
# Base scores for each risk type before data-driven adjustments.
VULNERABILITY_BASE_SCORES = {
    "extreme_heat": 50,
    "extreme_cold": 50,
    "drought": 35,
    "river_flood": 40,
    "urban_flood": 40,
    "sea_level_rise": 40,
    "typhoon": 50,
    "wildfire": 30,
    "water_stress": 40,
}

# ============================================================================
# EXPOSURE SCORING THRESHOLDS
# ============================================================================
# Thresholds for converting exposure data into scores (0-100).

RIVER_FLOOD_EXPOSURE_SCORES = {
    "very_high": {"distance_m": 100, "score": 90},
    "high": {"distance_m": 300, "score": 70},
    "medium": {"distance_m": 1000, "score": 40},
    "low": {"score": 10},
}

TYPHOON_EXPOSURE_SCORES = {
    "very_high": {"distance_m": 5000, "score": 90},
    "high": {"distance_m": 20000, "score": 70},
    "medium": {"distance_m": 50000, "score": 40},
    "low": {"score": 10},
}

SEA_LEVEL_RISE_EXPOSURE_SCORES = {
    "critical": {"distance_m": 100, "score": 80},
    "high": {"distance_m": 500, "score": 60},
    "medium": {"distance_m": 1000, "score": 40},
    "low": {"score": 10},
}

WILDFIRE_EXPOSURE_SCORES = {
    "extreme": {"distance_m": 30, "score": 100},
    "high": {"distance_m": 100, "score": 70},
    "medium": {"distance_m": 500, "score": 40},
    "low": {"distance_m": 1000, "score": 10},
    "safe": {"score": 0},
}

EXTREME_HEAT_EXPOSURE_SCORES = {
    "high": 70,
    "medium": 50,
    "low": 30,
}

# ============================================================================
# HAZARD CALCULATION PARAMETERS
# ============================================================================

# Parameters for SPI calculation in drought hazard (to be replaced with local data)
DROUGHT_HAZARD_PARAMS = {
    "korea_mean_rainfall": 1200.0,
    "korea_std_rainfall": 250.0,
    "cdd_norm_avg": 10,
    "cdd_norm_std": 15,
}

# Parameters for Typhoon TCI calculation
TYPHOON_HAZARD_PARAMS = {
    "gale_radius_km": 200,
    "wind_norm_max_ms": 50.0,
    "rain_norm_max_mm": 500.0,
    "typhoon_analysis_period": {"end_year": 2022, "num_years": 5},  # Last available year of data
    "estimated_rx1day": {
        "strong": 300.0,  # for wind >= 33 m/s
        "medium": 200.0,  # for wind >= 25 m/s
        "weak": 100.0,
    },
}

# ============================================================================
# VULNERABILITY CALCULATION PARAMETERS
# ============================================================================

VULNERABILITY_AGE_THRESHOLDS = {"high": 30, "medium": 20}

# Penalty scores per risk for building age
VULNERABILITY_AGE_PENALTIES = {
    "heat": {"high": 20, "medium": 10},
    "cold": {"high": 20, "medium": 10},
    "drought": {"high": 15, "medium": 8},
    "river_flood": {"high": 15, "medium": 0},
    "urban_flood": {"high": 10, "medium": 0},
    "sea_level_rise": {"high": 10, "medium": 0},
    "typhoon": {"high": 20, "medium": 0},
    "wildfire": {"high": 15, "medium": 8},
    "water_stress": {"high": 15, "medium": 8},
}
