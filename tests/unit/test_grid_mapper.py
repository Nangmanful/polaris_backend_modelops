"""GridMapper 순수 유틸 단위 테스트.

검증 대상 (modelops/utils/grid_mapper.py, DB 미사용 메서드만):
- _round_to_grid: 0.01도 해상도 반올림
- validate_coordinates: 위도/경도 유효 범위 경계값
- get_grid_bounds: 격자 중심 -> 경계 좌표 (반해상도 오프셋)
"""

import pytest

from modelops.utils.grid_mapper import GridMapper


class TestRoundToGrid:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (37.5678, 37.57),
            (127.0012, 127.00),
            (37.57, 37.57),     # 이미 격자 값
            (0.0, 0.0),
            (-35.234, -35.23),  # 음수 좌표
            (37.566, 37.57),    # 올림 방향
            (37.564, 37.56),    # 내림 방향
        ],
    )
    def test_rounding(self, value, expected):
        assert GridMapper._round_to_grid(value) == pytest.approx(expected, abs=1e-9)

    def test_resolution_constant(self):
        assert GridMapper.GRID_RESOLUTION == 0.01


class TestValidateCoordinates:
    @pytest.mark.parametrize(
        "lat, lon",
        [
            (0.0, 0.0),
            (90.0, 180.0),    # 상한 경계 (포함)
            (-90.0, -180.0),  # 하한 경계 (포함)
            (37.5665, 126.9780),  # 서울
        ],
    )
    def test_valid(self, lat, lon):
        assert GridMapper.validate_coordinates(lat, lon) is True

    @pytest.mark.parametrize(
        "lat, lon",
        [
            (90.01, 0.0),
            (-90.01, 0.0),
            (0.0, 180.01),
            (0.0, -180.01),
        ],
    )
    def test_invalid(self, lat, lon):
        assert GridMapper.validate_coordinates(lat, lon) is False


class TestGridBounds:
    def test_bounds_are_half_resolution_offsets(self):
        bounds = GridMapper.get_grid_bounds(37.57, 126.98)
        assert bounds["min_lat"] == pytest.approx(37.565)
        assert bounds["max_lat"] == pytest.approx(37.575)
        assert bounds["min_lon"] == pytest.approx(126.975)
        assert bounds["max_lon"] == pytest.approx(126.985)

    def test_bounds_width_equals_resolution(self):
        bounds = GridMapper.get_grid_bounds(0.0, 0.0)
        assert bounds["max_lat"] - bounds["min_lat"] == pytest.approx(GridMapper.GRID_RESOLUTION)
        assert bounds["max_lon"] - bounds["min_lon"] == pytest.approx(GridMapper.GRID_RESOLUTION)
