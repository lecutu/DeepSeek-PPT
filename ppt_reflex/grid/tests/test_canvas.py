"""grid/tests/test_canvas.py — try_place / commit / role-driven collision tests"""
import sys, os
sys.path.insert(0, "D:/文献搜索员/ppt_reflex")
from grid.types import GridConfig, ContentType, Verdict, SemanticRole
from grid.canvas import GridCanvas
from grid.supply import Supply


def test_try_place_empty_canvas():
    """空画布 → ALLOW"""
    canvas = GridCanvas()
    r = canvas.try_place("s01", ContentType.TEXT, ["A1", "B1", "C1"])
    assert r.allowed, f"Expected ALLOW, got {r.verdict}"
    assert len(r.conflicts) == 0
    print("[PASS] empty canvas → ALLOW")


def test_entity_on_entity_blocked():
    """两个 ENTITY 重叠 → BLOCK"""
    canvas = GridCanvas()
    from grid.types import ElementPayload
    canvas.try_place("s01", ContentType.TEXTBOX, ["A2","B2","C2","D2","A3","B3","C3","D3"],
        payload=ElementPayload(role=SemanticRole.ENTITY, text="Entity A"))
    r = canvas.try_place("s02", ContentType.TEXTBOX, ["C2","D2"],
        payload=ElementPayload(role=SemanticRole.ENTITY, text="Entity B"))
    assert r.blocked, f"Expected BLOCK, got {r.verdict}"
    assert len(r.conflicts) > 0
    assert "ENTITY" in str(r.conflicts[0].detail.upper()) or "Entity" in r.conflicts[0].detail
    print(f"  {r.conflicts[0].detail[:80]}...")
    print("[PASS] entity×entity → BLOCK")


def test_annotation_on_entity_allowed():
    """ANNOTATION 叠 ENTITY → ALLOW（装饰叠实体）"""
    canvas = GridCanvas()
    from grid.types import ElementPayload
    canvas.try_place("s01", ContentType.TEXTBOX, ["A2","B2","C2","D2","A3","B3","C3","D3"],
        payload=ElementPayload(role=SemanticRole.ENTITY, text="band"))
    r = canvas.try_place("s02", ContentType.TEXT, ["A2","B2","C2"],
        payload=ElementPayload(role=SemanticRole.ANNOTATION, text="label"))
    assert r.allowed, f"ANNOTATION on ENTITY should ALLOW, got {r.verdict}"
    print("[PASS] ANNOTATION on ENTITY → ALLOW")


def test_connector_on_entity_allowed():
    """CONNECTOR 穿 ENTITY → ALLOW"""
    canvas = GridCanvas()
    from grid.types import ElementPayload
    canvas.try_place("s01", ContentType.TEXTBOX, ["A5","B5","C5","D5","E5","F5","G5","H5"],
        payload=ElementPayload(role=SemanticRole.ENTITY, text="S1 band"))
    # Arrow goes right through the band
    r = canvas.try_place("conn", ContentType.CONNECTOR, ["D5"],
        payload=ElementPayload(role=SemanticRole.CONNECTOR,
            connector_from="D4", connector_to="D6"))
    assert r.allowed, f"CONNECTOR on ENTITY should ALLOW, got {r.verdict}"
    print("[PASS] CONNECTOR on ENTITY → ALLOW")


def test_emphasis_on_entity_allowed():
    """EMPHASIS（高亮框）叠 ENTITY → ALLOW"""
    canvas = GridCanvas()
    from grid.types import ElementPayload
    canvas.try_place("s01", ContentType.TEXTBOX, ["C3","D3","E3","F3","C4","D4","E4","F4"],
        payload=ElementPayload(role=SemanticRole.ENTITY, text="data"))
    r = canvas.try_place("highlight", ContentType.SHAPE, ["C3","D3","E3","F3","C4","D4","E4","F4"],
        payload=ElementPayload(role=SemanticRole.EMPHASIS, shape_id="rounded_rectangle"))
    assert r.allowed, f"EMPHASIS on ENTITY should ALLOW, got {r.verdict}"
    print("[PASS] EMPHASIS on ENTITY → ALLOW")


def test_entity_on_backdrop_allowed():
    """ENTITY 叠 BACKDROP（底纹）→ ALLOW"""
    canvas = GridCanvas()
    from grid.types import ElementPayload
    canvas.try_place("bg", ContentType.BACKGROUND, ["A4","B4","C4"],
        payload=ElementPayload(role=SemanticRole.BACKDROP))
    r = canvas.try_place("s01", ContentType.TEXTBOX, ["A4","B4","C4"],
        payload=ElementPayload(role=SemanticRole.ENTITY, text="content"))
    assert r.allowed, f"ENTITY on BACKDROP should ALLOW, got {r.verdict}"
    print("[PASS] ENTITY on BACKDROP → ALLOW")


def test_lock_template():
    """Locked template decor → no collision"""
    canvas = GridCanvas()
    from grid.positioning import bbox_to_fine_cells
    fine_addrs = bbox_to_fine_cells(0, 0, 960, 30, canvas.config)
    canvas.info_grid.occupy(fine_addrs, "deco-logo", ContentType.SHAPE,
                            locked=True, source="template", role=SemanticRole.EMPHASIS)
    r = canvas.try_place("s01", ContentType.TEXT, ["A1", "B1", "C1"])
    assert r.allowed, f"Template decor should not block. Got: {r.verdict}"
    print("[PASS] locked template → no conflict")


def test_out_of_bounds():
    """越界 → BLOCK"""
    canvas = GridCanvas()
    r = canvas.try_place("s01", ContentType.TEXT, ["BG1"])
    assert r.blocked, f"Expected BLOCK for OOB, got {r.verdict}"
    print("[PASS] out_of_bounds → BLOCK")


def test_free_suggestion():
    """实体冲突返回空闲区域建议"""
    canvas = GridCanvas()
    from grid.types import ElementPayload
    canvas.try_place("s01", ContentType.ANNOTATION, ["A1","B1","C1","D1","A2","B2","C2","D2",
        "A3","B3","C3","D3","A4","B4","C4","D4","A5","B5","C5","D5","A6","B6","C6","D6","A7","B7","C7","D7"])
    r = canvas.try_place("s02", ContentType.TEXTBOX, ["C4","D4","C5","D5"],
        payload=ElementPayload(role=SemanticRole.ENTITY))
    assert r.blocked
    assert len(r.free_suggestion) > 0
    print(f"  Free suggestion: {r.free_suggestion[0][:4]}...")
    print("[PASS] free_suggestion on entity conflict")


def test_checkpoint_rollback():
    """checkpoint + rollback 恢复"""
    canvas = GridCanvas()
    canvas.checkpoint()
    canvas.try_place("s01", ContentType.TEXT, ["A1","B1","C1"])
    canvas.rollback()
    occ = canvas.info_grid.all_occupied()
    assert len(occ) == 0, f"Expected empty after rollback, got {len(occ)}"
    print("[PASS] checkpoint + rollback")


def test_entity_and_overlay_tables():
    """entity_table() / overlay_table() 正确分类"""
    canvas = GridCanvas()
    from grid.types import ElementPayload
    canvas.try_place("e1", ContentType.TEXTBOX, ["B3","C3","B4","C4"],
        payload=ElementPayload(role=SemanticRole.ENTITY, text="band"))
    canvas.try_place("a1", ContentType.CONNECTOR, ["D3"],
        payload=ElementPayload(role=SemanticRole.CONNECTOR,
            connector_from="B3", connector_to="B6"))
    canvas.try_place("l1", ContentType.TEXT, ["D4"],
        payload=ElementPayload(role=SemanticRole.ANNOTATION, text="v'=2"))

    et = canvas.entity_table()
    ot = canvas.overlay_table()
    assert "e1" in et, "e1 should be in entity_table"
    assert "a1" in ot, "a1 should be in overlay_table"
    assert "l1" in ot, "l1 should be in overlay_table"
    print(f"  entity_table: {list(et.keys())}")
    print(f"  overlay_table: {list(ot.keys())}")
    print("[PASS] entity_table + overlay_table correct")


def test_pre_commit_role_mislabel_hint():
    """pre_commit_validation 对误标 ENTITY 的连接器给出 '改 role' 建议"""
    canvas = GridCanvas()
    from grid.types import ElementPayload

    # Put a band as ENTITY
    canvas.try_place("band", ContentType.TEXTBOX, ["D3","E3","D4","E4"],
        payload=ElementPayload(role=SemanticRole.ENTITY, text="band"))

    # Force-place an arrow as ENTITY — info_grid (bypass try_place collision)
    canvas.info_grid.occupy(["D3"], "arrow", ContentType.CONNECTOR,
        role=SemanticRole.ENTITY, source="agent",
        payload=ElementPayload(role=SemanticRole.ENTITY,
            connector_from="D2", connector_to="D6"))

    report = canvas.pre_commit_validation()
    # Role deviation hints now live in "advisories" (常识层产物)
    role_hints = [a for a in report.get("advisories", [])
                  if "role" in a.get("detail", "").lower()]
    assert len(role_hints) > 0, \
        f"Should have advisory about ENTITY role on connector. Got advisories={report.get('advisories', [])}, warnings={report.get('warnings', [])}"
    for h in role_hints:
        print(f"  ⚠ {h['owner_id']}: {h['detail'][:120]}...")
    print("[PASS] pre_commit → '改 role 别改坐标' advisory")


if __name__ == "__main__":
    test_try_place_empty_canvas()
    test_entity_on_entity_blocked()
    test_annotation_on_entity_allowed()
    test_connector_on_entity_allowed()
    test_emphasis_on_entity_allowed()
    test_entity_on_backdrop_allowed()
    test_lock_template()
    test_out_of_bounds()
    test_free_suggestion()
    test_checkpoint_rollback()
    test_entity_and_overlay_tables()
    test_pre_commit_role_mislabel_hint()
    print("\n✓ All canvas tests PASSED")
