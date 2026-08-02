import math

from app.core import admin_service


def test_get_square_pool_axis_bounds():
    min_c, max_c = admin_service._get_square_pool_axis_bounds(4.0, -10.0, 10.0)
    assert math.isclose(min_c, -8.0, rel_tol=1e-9)
    assert math.isclose(max_c, 8.0, rel_tol=1e-9)


def test_build_covering_axis_centers_includes_edges_and_start():
    centers = admin_service._build_covering_axis_centers(-10.0, 10.0, 6.0, 0.0)
    # must include start (0.0) and the two edge centers
    rounded = [round(c, 6) for c in centers]
    assert round(0.0, 6) in rounded
    assert round(-7.0, 6) in rounded
    assert round(7.0, 6) in rounded
    # ensure list is sorted by distance from start (first element is start)
    assert abs(centers[0] - 0.0) <= abs(centers[1] - 0.0)


def test_build_square_pool_cells_count_and_order():
    start_lat, start_lng, step, cells = admin_service._build_square_pool_cells(5.0)
    # cells should be a non-empty list of (lat, lng) tuples
    assert isinstance(cells, list)
    assert len(cells) > 0
    for lat, lng in cells:
        assert isinstance(lat, float)
        assert isinstance(lng, float)


def test_select_square_pool_rounds_selects_unique_and_ordered():
    # create 10 dummy candidates with increasing playability_score
    candidates = [{'square_id': i + 1, 'playability_score': float(i)} for i in range(10)]
    selected = admin_service._select_square_pool_rounds(candidates, 5, [])
    assert len(selected) == 5
    # ensure unique
    ids = [c['square_id'] for c in selected]
    assert len(set(ids)) == 5
