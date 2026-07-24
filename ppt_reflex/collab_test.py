"""
Day 1.5 人机协同验证 -- 纯 Python 模拟

验证：
  1. Revision 乐观锁：Agent 基于过期状态操作 -> 拒绝 + STATE_CHANGED
  2. 元素锁定：人锁定的元素 -> Agent 移动被拒
  3. 事务冲突：Agent 事务中 -> 人插入修改 -> 回滚
  4. 人工编辑感知：人修改后 -> audit 检测到新引入问题
  5. 连续操作：正常流转，revision 单调递增
  6. 人解锁后 -> Agent 正常操作
"""

from reflex import ReflexEngine
from engine import SlideElement, BBox, ContentRole, CollisionRole, DEFAULT_SLIDE_W, DEFAULT_SLIDE_H
from journal import Journal, OpResult
import json


# ═══════════════════════════════════════════════════════════
# 测试辅助
# ═══════════════════════════════════════════════════════════
def make_slide():
    """Create a simple slide with 3 elements."""
    elements = [
        SlideElement(
            id="shape-00", bbox=BBox(36, 36, 600, 80),
            content_role=ContentRole.TITLE, text="标题"),
        SlideElement(
            id="shape-01", bbox=BBox(36, 140, 400, 300),
            content_role=ContentRole.BODY, text="正文内容"),
        SlideElement(
            id="shape-02", bbox=BBox(480, 140, 440, 300),
            content_role=ContentRole.FIGURE, text="[图片]"),
    ]
    engine = ReflexEngine()
    engine.load_slide(elements)
    return engine


def print_step(n, desc):
    print(f"\n{'-'*60}")
    print(f"STEP {n}: {desc}")


def print_result(label, result):
    print(f"  {label}:")
    print(f"    status = {result.get('status', '?')}")
    if result.get('revision') is not None:
        print(f"    revision = {result['revision']}")
    if result.get('message'):
        print(f"    message = {result['message']}")
    if result.get('issues'):
        for iss in result['issues']:
            print(f"    issue = {iss.get('code')} {iss.get('targets')}")


def print_separator(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ═══════════════════════════════════════════════════════════
# 测试场景
# ═══════════════════════════════════════════════════════════
def test_1_normal_flow():
    """场景 1: Agent 正常操作，无人工干预。"""
    print_separator("SCENARIO 1: Agent 连续操作，revision 单调递增")

    eng = make_slide()
    rev = 0

    # Agent reads initial state
    ctx = eng.local_context(["shape-01"])
    print_step(1, "Agent reads slide state")
    print(f"  revision={rev} context has {len(ctx['targets'])} targets")

    # Agent moves shape-01 right by 50pt
    elem = eng.get_element("shape-01")
    old_x = elem.bbox.x
    new_bbox = BBox(old_x + 50, elem.bbox.y, elem.bbox.w, elem.bbox.h)

    print_step(2, f"Agent moves shape-01: x {old_x:.0f} -> {old_x+50:.0f}")
    result = eng.move_element("shape-01", new_bbox, expected_revision=rev, source="agent")
    print_result("Result", result)
    rev = result["revision"]
    assert result["status"] in ("ok", "needs_decision"), f"Expected ok, got {result['status']}"
    assert rev == 1, f"Expected rev 1, got {rev}"

    # Agent does another move
    elem = eng.get_element("shape-02")
    new_bbox_2 = BBox(420, 100, elem.bbox.w, elem.bbox.h)
    print_step(3, f"Agent moves shape-02: y {elem.bbox.y:.0f} -> 100")
    result = eng.move_element("shape-02", new_bbox_2, expected_revision=rev, source="agent")
    print_result("Result", result)
    rev2 = result["revision"]
    assert rev2 == 2, f"Expected rev 2, got {rev2}"
    assert rev2 > rev, "Revision should be monotonically increasing"

    print("\n  [PASS] PASSED: Normal flow, revision 0->1->2")

    # Verify journal entries
    entries = eng.journal.get_entries_since(0)
    assert len(entries) == 2, f"Expected 2 journal entries, got {len(entries)}"
    for e in entries:
        assert e.source == "agent", f"Expected source=agent, got {e.source}"
    print(f"  [PASS] Journal has 2 entries, both from agent")


def test_2_revision_conflict():
    """场景 2: 人修改后 Agent 基于旧 revision 操作 -> 冲突拒绝。"""
    print_separator("SCENARIO 2: Revision 乐观锁 -- 人改后 Agent 用旧 rev 操作")

    eng = make_slide()
    rev = 0

    # Agent reads state
    print_step(1, "Agent reads state (revision=0)")

    # 人手动拖动 shape-01（模拟）
    print_step(2, "Human manually moves shape-01 in PowerPoint")
    elem = eng.get_element("shape-01")
    human_new_bbox = BBox(100, 200, elem.bbox.w, elem.bbox.h)
    eng.notify_human_edit("shape-01", human_new_bbox)
    new_rev = eng.journal.last_revision()
    print(f"  Human edit -> revision bumped to {new_rev}")
    assert new_rev == 1, f"Expected rev 1 after human edit, got {new_rev}"

    # Agent 仍基于旧 rev=0 尝试操作
    print_step(3, "Agent tries move shape-02 (still thinks rev=0)")
    elem2 = eng.get_element("shape-02")
    new_bbox = BBox(elem2.bbox.x + 30, elem2.bbox.y, elem2.bbox.w, elem2.bbox.h)
    result = eng.move_element("shape-02", new_bbox, expected_revision=0, source="agent")
    print_result("Result", result)

    assert result["status"] == "state_changed", f"Expected state_changed, got {result['status']}"
    assert "Expected rev 0" in result.get("message", ""), f"Wrong message: {result.get('message')}"
    print("  [PASS] PASSED: Agent operation rejected -- STATE_CHANGED")

    # Agent 重读状态后再操作
    print_step(4, "Agent re-reads state, then retries with correct revision")
    ctx = eng.local_context(["shape-01"])
    current_rev = eng.journal.last_revision()
    print(f"  Current revision = {current_rev}")

    result = eng.move_element("shape-02", new_bbox, expected_revision=current_rev, source="agent")
    print_result("After retry", result)
    assert result["status"] in ("ok", "needs_decision"), f"Expected ok after retry, got {result['status']}"

    print("  [PASS] PASSED: Conflict detected + Agent re-reads + succeeds")


def test_3_element_locking():
    """场景 3: 人锁定元素 -> Agent 无法移动。"""
    print_separator("SCENARIO 3: 元素锁定 -- 人锁定的元素 Agent 无法碰")

    eng = make_slide()

    # 人锁定 shape-01
    print_step(1, "Human locks shape-01")
    eng.lock_element("shape-01", locked_by="human")
    elem = eng.get_element("shape-01")
    assert elem.locked == True
    assert elem.locked_by == "human"
    print(f"  shape-01 locked={elem.locked} by={elem.locked_by}")

    # Agent 尝试移动被锁定的元素
    print_step(2, "Agent tries to move locked shape-01")
    new_bbox = BBox(100, 200, 300, 200)
    result = eng.move_element("shape-01", new_bbox, source="agent")
    print_result("Result", result)

    assert result["status"] == "blocked", f"Expected blocked, got {result['status']}"
    assert "locked" in result.get("message", "").lower(), f"Expected lock message, got: {result.get('message')}"
    print("  [PASS] PASSED: Locked element blocked Agent move")

    # Agent 仍然可以操作未锁定的元素
    print_step(3, "Agent moves unlocked shape-02 -- should succeed")
    elem2 = eng.get_element("shape-02")
    new_bbox_2 = BBox(elem2.bbox.x + 20, elem2.bbox.y, elem2.bbox.w, elem2.bbox.h)
    result = eng.move_element("shape-02", new_bbox_2, source="agent")
    print_result("Result", result)
    assert result["status"] in ("ok", "needs_decision"), f"Expected ok, got {result['status']}"
    print("  [PASS] PASSED: Unlocked element still works")

    # 人解锁后 Agent 可以操作
    print_step(4, "Human unlocks shape-01, Agent retries")
    eng.unlock_element("shape-01")
    result = eng.move_element("shape-01", new_bbox, source="agent")
    print_result("After unlock", result)
    assert result["status"] in ("ok", "needs_decision"), f"Expected ok after unlock, got {result['status']}"
    print("  [PASS] PASSED: Unlock restores Agent access")


def test_4_transaction_conflict():
    """场景 4: Agent 事务中 -> 人插入修改 -> 事务回滚。"""
    print_separator("SCENARIO 4: 事务冲突 -- 人插入修改导致 Agent 事务回滚")

    eng = make_slide()
    rev = eng.journal.last_revision()
    print_step(1, f"Initial revision = {rev}")

    # Agent 开始事务
    print_step(2, "Agent begins transaction")
    eng.journal.begin_transaction()

    # Agent 移动 shape-01
    elem = eng.get_element("shape-01")
    eng.move_element("shape-01", BBox(50, 150, elem.bbox.w, elem.bbox.h), source="agent")
    print(f"  Agent moved shape-01 -> rev={eng.journal.last_revision()}")

    # Agent 移动 shape-02
    elem2 = eng.get_element("shape-02")
    eng.move_element("shape-02", BBox(500, 150, elem2.bbox.w, elem2.bbox.h), source="agent")
    print(f"  Agent moved shape-02 -> rev={eng.journal.last_revision()}")

    # 人插入修改
    print_step(3, "Human modifies shape-01 mid-transaction")
    eng.notify_human_edit("shape-01", BBox(200, 200, 300, 200))
    print(f"  Human edit -> rev={eng.journal.last_revision()}")

    # Agent 尝试提交 -- 但人已改过状态 -> 应回滚
    print_step(4, "Agent detects external change -> rollback")
    reversed_ops = eng.rollback()
    print(f"  Rolled back {len(reversed_ops)} operations")
    for op in reversed_ops:
        print(f"    op={op['operation_id']} element={op['element_id']} restored to {op['after_inverse']}")

    current_rev = eng.journal.last_revision()
    print(f"  After rollback -> rev={current_rev}")

    # 验证回滚后状态：
    # journal.rollback() 回滚了 agent 条目，保留了 human 条目。
    # 引擎坐标被 reflex.rollback() 逆操作恢复到人编辑后的状态。
    elem_after = eng.get_element("shape-01")
    print(f"  shape-01 position: ({elem_after.bbox.x:.0f}, {elem_after.bbox.y:.0f})")
    # 人编辑在 (200,200)，回滚 revert 了 Agent 在事务中的操作，
    # 引擎坐标应回到人编辑后的位置
    assert abs(elem_after.bbox.x - 200) < 5, f"Expected x≈200 (human edit), got {elem_after.bbox.x}"
    assert abs(elem_after.bbox.y - 200) < 5, f"Expected y≈200 (human edit), got {elem_after.bbox.y}"

    print("  [PASS] PASSED: Transaction rolled back, human edit preserved")


def test_5_human_edit_introduces_issue():
    """场景 5: 人修改后 audit -> 发现新问题。"""
    print_separator("SCENARIO 5: 感知人工编辑引入的问题")

    eng = make_slide()

    # 初始 audit
    print_step(1, "Initial audit")
    result = eng.audit()
    print_result("Before", result)
    initial_issues = len(result.get("issues", []))

    # 人把 shape-01 拖到 shape-02 上面 -> 制造碰撞
    print_step(2, "Human drags shape-01 on top of shape-02")
    eng.notify_human_edit("shape-01", BBox(480, 140, 400, 300))

    # 人把 shape-00 推到安全区外
    print_step(3, "Human pushes title past right margin")
    eng.notify_human_edit("shape-00", BBox(930, 36, 50, 80))

    # 审计
    print_step(4, "Post-human-edit audit")
    result = eng.audit()
    print_result("After", result)
    new_issues = result.get("issues", [])
    print(f"  Issues detected: {len(new_issues)} (was {initial_issues})")

    # 应该检测到新问题
    issue_codes = [i["code"] for i in new_issues]
    print(f"  Issue codes: {issue_codes}")

    assert len(new_issues) > initial_issues, "Expected new issues after human edit"

    # 检查 journal 来源标记
    entries = eng.journal.get_entries_since(0)
    human_entries = [e for e in entries if e.source == "human"]
    assert len(human_entries) >= 2, f"Expected ≥2 human entries, got {len(human_entries)}"
    print(f"  [PASS] Journal has {len(human_entries)} human entries")

    # 后面的 audit -> revision 继续递增
    print_step(5, "Agent resolves one issue (moves title back)")
    result = eng.move_element("shape-00", BBox(36, 36, 600, 80),
                              expected_revision=eng.journal.last_revision(), source="agent")
    print_result("After fix", result)
    assert result["status"] in ("ok", "needs_decision"), f"Expected ok, got {result['status']}"

    print("  [PASS] PASSED: Human edits detected + new issues surfaced + Agent fixes on top")


def test_6_full_workflow():
    """场景 6: 完整人机协同流程。"""
    print_separator("SCENARIO 6: 完整协同流程 -- 交互式模式")

    eng = make_slide()
    history = []  # simulated interaction log

    def log(action, detail):
        entry = {"step": len(history) + 1, "action": action, **detail}
        history.append(entry)
        print(f"  [{entry['step']}] {action}: {detail}")

    # Phase 1: Agent 应用布局
    print_step(1, "Phase 1: Agent applies layout template")
    rev = eng.journal.last_revision()
    result = eng.apply_layout("text_left_figure_right",
                              {"title": "shape-00", "body": "shape-01", "figure": "shape-02"},
                              expected_revision=rev)
    result_rev = result.get("revision", rev + 1)
    log("apply_layout", {"template": "text_left_figure_right", "status": result["status"],
                         "revision": result_rev})

    # Phase 2: 人在 PowerPoint 中看到，手动微调
    print_step(2, "Phase 2: Human manually adjusts in PowerPoint")
    # 人觉得图片离文字太紧，手动右移
    fig = eng.get_element("shape-02")
    eng.notify_human_edit("shape-02", BBox(fig.bbox.x + 20, fig.bbox.y, fig.bbox.w, fig.bbox.h))
    human_rev = eng.journal.last_revision()
    log("human_nudge", {"element": "shape-02", "reason": "图片与文字间距太紧",
                        "revision": human_rev})

    # 人锁定标题----不要动我的标题
    eng.lock_element("shape-00", locked_by="human")
    log("human_lock", {"element": "shape-00"})

    # Phase 3: Agent 审计 -> 发现问题
    print_step(3, "Phase 3: Agent audits after human changes")
    result = eng.audit()
    issues = result.get("issues", [])
    log("agent_audit", {"issues": len(issues), "revision": eng.journal.last_revision()})

    # Phase 4: Agent 尝试修复----碰标题被拒
    print_step(4, "Phase 4: Agent tries to fix alignment")
    title = eng.get_element("shape-00")
    # Agent 不知道人被锁了标题
    result = eng.move_element("shape-00", BBox(title.bbox.x, title.bbox.y - 10,
                                              title.bbox.w, title.bbox.h),
                              expected_revision=human_rev, source="agent")
    log("agent_move_blocked", {"element": "shape-00", "status": result["status"],
                               "reason": result.get("message", "")})

    # Phase 5: Agent 重新读取状态 -> 发现标题已锁定 -> 调整策略
    print_step(5, "Phase 5: Agent re-reads state, adapts")
    ctx = eng.local_context(["shape-00", "shape-01", "shape-02"])
    locked = [t for t in ctx["targets"] if t.get("locked")]
    unlocked = [t for t in ctx["targets"] if not t.get("locked")]
    log("agent_re_read", {"locked_elements": [l["id"] for l in locked],
                          "unlocked": [u["id"] for u in unlocked]})

    # Agent 只操作未锁定元素
    for u in unlocked:
        elem = eng.get_element(u["id"])
        result = eng.move_element(u["id"],
                                  BBox(elem.bbox.x, elem.bbox.y, elem.bbox.w, elem.bbox.h),
                                  expected_revision=eng.journal.last_revision(),
                                  source="agent")
        log(f"agent_touch_{u['id']}", {"status": result["status"]})

    # Phase 6: 终审
    print_step(6, "Phase 6: Final audit")
    final = eng.audit()
    log("final_audit", {"issues": len(final.get("issues", [])),
                        "total_revisions": eng.journal.last_revision()})

    # Verify journal consistency
    entries = eng.journal.entries
    sources = set(e.source for e in entries)
    print(f"\n  Journal: {len(entries)} entries, sources: {sources}")
    for e in entries:
        print(f"    rev={e.revision} source={e.source:<8} element={e.element_id:<12} action={e.action}")

    assert "human" in sources, "Expected human entries in journal"
    assert "agent" in sources, "Expected agent entries in journal"
    assert len(entries) >= 6, f"Expected ≥6 journal entries, got {len(entries)}"

    # Verify revision is monotonic
    revs = [e.revision for e in entries]
    assert revs == sorted(revs), f"Revisions not monotonic: {revs}"

    # Verify locked element stayed put
    title_after = eng.get_element("shape-00")
    assert title_after.locked == True
    assert title_after.locked_by == "human"

    print("  [PASS] PASSED: Full workflow complete -- human+agent collaboration verified")


# ═══════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    tests = [
        ("Normal flow", test_1_normal_flow),
        ("Revision conflict", test_2_revision_conflict),
        ("Element locking", test_3_element_locking),
        ("Transaction conflict", test_4_transaction_conflict),
        ("Human edit detection", test_5_human_edit_introduces_issue),
        ("Full collaborative workflow", test_6_full_workflow),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"\n  [FAIL] FAILED [{name}]: {e}")
        except Exception as e:
            failed += 1
            print(f"\n  [FAIL] ERROR [{name}]: {type(e).__name__}: {e}")

    print(f"\n{'='*70}")
    print(f"RESULTS: {passed}/{passed+failed} passed")
    if failed == 0:
        print(f"  [PASS] All 6 collaborative scenarios verified")
    else:
        print(f"  [FAIL] {failed} scenario(s) need fixing")
    print(f"{'='*70}")
