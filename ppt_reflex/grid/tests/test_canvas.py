"""grid/tests/test_canvas.py — try_place / commit / rollback 集成测试"""
import sys, os
sys.path.insert(0, "D:/文献搜索员/ppt_reflex")
from grid.types import GridConfig, ContentType, Verdict
from grid.canvas import GridCanvas
from grid.supply import Supply


def test_try_place_empty_canvas():
    """空画布 — 放什么都应该通过。"""
    canvas = GridCanvas()
    r = canvas.try_place("s01", ContentType.TEXT, ["A1", "B1", "C1"])
    assert r.allowed, f"Expected ALLOW, got {r.verdict}"
    assert len(r.conflicts) == 0
    print("[PASS] try_place empty canvas")


def test_try_place_text_on_text_blocked():
    """文字叠文字 → BLOCK。"""
    canvas = GridCanvas()
    canvas.try_place("s01", ContentType.TEXT, ["A2", "B2", "C2", "D2",
                                                "A3", "B3", "C3", "D3"])
    r = canvas.try_place("s02", ContentType.TEXT, ["C2", "D2"])
    assert r.blocked, f"Expected BLOCK, got {r.verdict}"
    assert len(r.conflicts) > 0, "Should have conflicts"
    c = r.conflicts[0]
    assert c.detail and "text" in c.detail.lower()
    print(f"  Conflict: {r.conflicts[0].detail}")
    print("[PASS] text_on_text → BLOCK")


def test_try_place_text_on_textbox_allowed():
    """文字叠色块 → ALLOW。"""
    canvas = GridCanvas()
    canvas.try_place("s01", ContentType.TEXTBOX, ["A2", "B2", "C2", "D2",
                                                    "A3", "B3", "C3", "D3"])
    r = canvas.try_place("s02", ContentType.TEXT, ["A2", "B2", "C2"])
    assert r.allowed, f"Expected ALLOW, got {r.verdict}"
    print(f"  z_hint: {r.z_hint}")
    print("[PASS] text_on_textbox → ALLOW" + (f" + z_hint({r.z_hint})" if r.z_hint else ""))


def test_try_place_text_on_image_blocked():
    """文字叠图片 → BLOCK。"""
    canvas = GridCanvas()
    canvas.try_place("s01", ContentType.IMAGE, ["E2", "F2", "G2", "H2",
                                                  "E3", "F3", "G3", "H3"])
    r = canvas.try_place("s02", ContentType.TEXT, ["G2", "H2"])
    assert r.blocked, f"Expected BLOCK, got {r.verdict}"
    print(f"  Conflict: {r.conflicts[0].detail if r.conflicts else 'none'}")
    print("[PASS] text_on_image → BLOCK")


def test_try_place_lock_template():
    """模板装饰元素不参与冲突判定。"""
    canvas = GridCanvas()
    # 先放入一个 locked template 装饰
    from grid.positioning import bbox_to_fine_cells
    fine_addrs = bbox_to_fine_cells(0, 0, 960, 30, canvas.config)
    canvas.info_grid.occupy(
        fine_addrs, "deco-logo", ContentType.SHAPE,
        locked=True, source="template"
    )
    # 文字放在装饰区 → 应该 ALLOW（装饰不拦）
    r = canvas.try_place("s01", ContentType.TEXT, ["A1", "B1", "C1"])
    assert r.allowed, f"Template decor should not block. Got: {r.verdict}"
    print("[PASS] template locked element — no conflict")


def test_out_of_bounds():
    """越界 → BLOCK。"""
    canvas = GridCanvas()
    r = canvas.try_place("s01", ContentType.TEXT, ["Q1"])  # col 16 → off
    assert r.blocked, f"Expected BLOCK for OOB, got {r.verdict}"
    assert "越界" in r.conflicts[0].detail
    print("[PASS] out_of_bounds → BLOCK")


def test_free_suggestion():
    """冲突时返回空闲区域建议。"""
    canvas = GridCanvas()
    canvas.try_place("s01", ContentType.TEXT, ["A1", "B1", "C1", "D1",
                                                "A2", "B2", "C2", "D2",
                                                "A3", "B3", "C3", "D3",
                                                "A4", "B4", "C4", "D4",
                                                "A5", "B5", "C5", "D5",
                                                "A6", "B6", "C6", "D6",
                                                "A7", "B7", "C7", "D7"])
    r = canvas.try_place("s02", ContentType.IMAGE, ["C4", "D4", "C5", "D5"])
    assert r.blocked
    assert len(r.free_suggestion) > 0, "Should suggest free regions"
    print(f"  Free suggestion: {r.free_suggestion[0][:4]}...")
    print("[PASS] free_suggestion on conflict")


def test_info_grid_checkpoint_rollback():
    """checkpoint + rollback 恢复。"""
    canvas = GridCanvas()
    canvas.checkpoint()
    canvas.try_place("s01", ContentType.TEXT, ["A1", "B1", "C1"])
    canvas.rollback()
    # 回滚后画布应为空
    occ = canvas.info_grid.all_occupied()
    assert len(occ) == 0, f"Expected empty after rollback, got {len(occ)}"
    print("[PASS] checkpoint + rollback")


if __name__ == "__main__":
    test_try_place_empty_canvas()
    test_try_place_text_on_text_blocked()
    test_try_place_text_on_textbox_allowed()
    test_try_place_text_on_image_blocked()
    test_try_place_lock_template()
    test_out_of_bounds()
    test_free_suggestion()
    test_info_grid_checkpoint_rollback()
    print("\nAll canvas tests PASSED")
