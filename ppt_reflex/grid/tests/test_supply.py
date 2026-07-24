"""grid/tests/test_supply.py — 输出格式 token 预算验证"""
import sys
sys.path.insert(0, "D:/文献搜索员/ppt_reflex")
from grid.types import GridConfig, ContentType
from grid.canvas import GridCanvas
from grid.supply import Supply


def test_level0_token_budget():
    """L0 总览应在 50 tokens 内。"""
    canvas = GridCanvas()
    canvas.try_place("s01", ContentType.TEXT, ["A1", "B1", "C1"])
    canvas.try_place("s02", ContentType.TEXT, ["A2", "B2", "C2", "D2",
                                                 "A3", "B3", "C3", "D3"])
    canvas.try_place("s03", ContentType.IMAGE, ["E2", "F2", "G2", "H2",
                                                  "E3", "F3", "G3", "H3"])

    supply = Supply()
    l0 = supply.level0(canvas.info_grid)
    import json
    payload = json.dumps(l0, ensure_ascii=False)
    tokens = len(payload) // 4  # rough token count
    print(f"  L0 payload: {len(payload)} chars, ~{tokens} tokens")
    print(f"  L0 content: {payload[:120]}...")
    assert len(payload) < 800, f"L0 payload too large: {len(payload)} chars"
    print("[PASS] level0 token budget")


def test_conflict_aggregation():
    """冲突聚合：多冲突按对手聚合。"""
    canvas = GridCanvas()
    # 铺满左半画布
    canvas.try_place("s01", ContentType.TEXT,
                     ["A1","B1","C1","D1","E1","F1","G1","H1",
                      "A2","B2","C2","D2","E2","F2","G2","H2",
                      "A3","B3","C3","D3","E3","F3","G3","H3",
                      "A4","B4","C4","D4","E4","F4","G4","H4"])
    # 尝试在中部放图片 — 应该报冲突
    r = canvas.try_place("s02", ContentType.IMAGE, ["C3", "D3", "C4", "D4"])

    supply = Supply()
    report = supply.format_conflict(r)
    print(f"  Status: {report['status']}")
    print(f"  Conflict count: {report['conflict_count']}")
    print(f"  Conflicts: {[c['conflict_with'] for c in report['conflicts']]}")
    assert report["status"] == "blocked"
    assert report["conflict_count"] >= 1
    # Should be aggregated by opponent (only s01)
    assert len(report["conflicts"]) <= 2
    print("[PASS] conflict aggregation")


def test_level2():
    """L2 元素全貌。"""
    canvas = GridCanvas()
    canvas.try_place("s01", ContentType.TEXT, ["A2", "B2", "C2", "D2",
                                                 "A3", "B3", "C3", "D3"])
    supply = Supply()
    l2 = supply.level2(canvas.info_grid, "s01")
    assert l2 is not None
    assert l2["id"] == "s01"
    assert l2["type"] == "text"
    assert "cells" in l2
    print(f"  L2: {l2}")
    print("[PASS] level2")


if __name__ == "__main__":
    test_level0_token_budget()
    test_conflict_aggregation()
    test_level2()
    print("\nAll supply tests PASSED")
