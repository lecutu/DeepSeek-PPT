"""grid/tests/test_profiles.py — 版式推断正确性"""
import sys
sys.path.insert(0, "D:/文献搜索员/ppt_reflex")
from grid.types import GridConfig, ContentType
from grid.canvas import GridCanvas
from grid.profiles import infer_profile


def test_auto_profile_footer():
    """底部元素应被识别为 footer locked zone。"""
    canvas = GridCanvas()
    # 底部一行 = row 8 (0-indexed, 9 rows total)
    bottom_cells = ["A9","B9","C9","D9","E9","F9","G9","H9","I9","J9",
                    "K9","L9","M9","N9","O9","P9"]
    canvas.try_place("s_footer", ContentType.TEXT, bottom_cells)

    profile = infer_profile(canvas.info_grid, canvas.config)
    assert len(profile.locked_zones) > 0, "Footer should be locked"
    assert "s_footer" in profile.decorative_elements, "Footer element should be decorative"
    print("[PASS] footer → locked")


def test_auto_profile_title():
    """顶部元素应被识别为 title zone。"""
    canvas = GridCanvas()
    canvas.try_place("s_title", ContentType.TEXT, ["A1","B1","C1","D1","E1","F1","G1","H1"])

    profile = infer_profile(canvas.info_grid, canvas.config)
    assert "title" in profile.zones, f"Title zone not detected: {profile.zones}"
    print("[PASS] title zone detected")


def test_auto_profile_background():
    """大面积覆盖应被识别为 background/locked。"""
    canvas = GridCanvas()
    # 所有 cell
    all_cells = []
    for r in range(9):
        for c in range(16):
            col_letter = chr(65 + c) if c < 26 else f"A{chr(65 + c - 26)}"
            all_cells.append(f"{col_letter}{r+1}")
    canvas.try_place("s_bg", ContentType.BACKGROUND, all_cells)

    profile = infer_profile(canvas.info_grid, canvas.config)
    assert "s_bg" in profile.decorative_elements, "BG should be decorative"
    print("[PASS] background → decorative")


if __name__ == "__main__":
    test_auto_profile_footer()
    test_auto_profile_title()
    test_auto_profile_background()
    print("\nAll profiles tests PASSED")
