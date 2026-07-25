"""grid/tests/test_positioning.py"""
from ppt_reflex.grid.positioning import (
    cell_name, parse_cell, cells_to_bbox, bbox_to_coarse_cells,
    bbox_to_fine_cells, cell_range, is_cell_in_bounds,
)
from ppt_reflex.grid.types import GridConfig


def test_cell_name():
    assert cell_name(0, 0) == "A1"
    assert cell_name(15, 8) == "P9"
    assert cell_name(0, 1) == "A2"
    print("[PASS] cell_name")


def test_parse_cell():
    assert parse_cell("A1") == (0, 0)
    assert parse_cell("P9") == (15, 8)
    assert parse_cell("a1") == (0, 0)  # lowercase
    assert parse_cell("H5") == (7, 4)
    try:
        parse_cell("")
        assert False, "should error"
    except ValueError:
        pass
    print("[PASS] parse_cell")


def test_cells_to_bbox():
    assert cells_to_bbox(["A1"]) == {"x": 0, "y": 0, "w": 60, "h": 60}
    assert cells_to_bbox(["A2", "B2", "A3", "B3"]) == {"x": 0, "y": 60, "w": 120, "h": 120}
    assert cells_to_bbox(["D5"]) == {"x": 180, "y": 240, "w": 60, "h": 60}
    print("[PASS] cells_to_bbox")


def test_bbox_to_coarse():
    cells = bbox_to_coarse_cells(0, 60, 120, 120)
    assert set(cells) == {"A2", "B2", "A3", "B3"}, f"got {cells}"

    cells = bbox_to_coarse_cells(0, 0, 960, 540)
    assert "A1" in cells
    assert "P9" in cells
    print("[PASS] bbox_to_coarse_cells")


def test_bbox_to_fine():
    cells = bbox_to_fine_cells(0, 0, 30, 30)
    assert len(cells) == 1
    assert cells[0] == "A1"

    cells = bbox_to_fine_cells(0, 0, 60, 60)
    assert len(cells) == 4  # 2×2 cells
    print("[PASS] bbox_to_fine_cells")


def test_cell_range():
    assert cell_range(["A1"]) == "A1"
    assert cell_range(["A1", "A2", "B1", "B2"]) == "A1:B2"
    assert cell_range([]) == ""
    print("[PASS] cell_range")


def test_is_cell_in_bounds():
    cfg = GridConfig()
    assert is_cell_in_bounds("A1", cfg) == True
    assert is_cell_in_bounds("AF18", cfg) == True    # col 31, row 17 — fine-grid (0-31, 0-17)
    assert is_cell_in_bounds("BG1", cfg) == False     # col 32 → off (fine_cols=32, so max col=31)
    assert is_cell_in_bounds("A19", cfg) == False     # row 18 → off (fine_rows=18, so max row=17)
    print("[PASS] is_cell_in_bounds")


def test_config_override():
    config = GridConfig(coarse_cols=8, coarse_rows=6, fine_cols=16, fine_rows=12,
                        coarse_cell_pt=100.0, canvas_w_pt=800, canvas_h_pt=600)
    cells = bbox_to_coarse_cells(0, 0, 100, 100, config)
    assert set(cells) == {"A1"}
    assert is_cell_in_bounds("P12", config) == True    # col 15, row 11 → fine-grid (0-15, 0-11)
    assert is_cell_in_bounds("Q1", config) == False     # col 16 → off
    assert is_cell_in_bounds("A13", config) == False    # row 12 → off
    print("[PASS] config_override")


if __name__ == "__main__":
    test_cell_name()
    test_parse_cell()
    test_cells_to_bbox()
    test_bbox_to_coarse()
    test_bbox_to_fine()
    test_cell_range()
    test_is_cell_in_bounds()
    test_config_override()
    print("\n✓ All positioning tests PASSED")
