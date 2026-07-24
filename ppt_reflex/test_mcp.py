"""End-to-end MCP Server tool call test."""
import json, sys
sys.path.insert(0, '.')
from mcp_server import PPTReflexMCPServer

s = PPTReflexMCPServer()
ok = 0
fail = 0

def test(name, fn):
    global ok, fail
    try:
        fn()
        ok += 1
        print(f"  [OK] {name}")
    except Exception as e:
        fail += 1
        print(f"  [FAIL] {name}: {e}")

def assert_eq(a, b, msg=""):
    assert a == b, f"Expected {b}, got {a}. {msg}"

def assert_in(sub, container, msg=""):
    assert sub in container, f"Expected '{sub}' in {container}. {msg}"

# 1
print("=== 1. Open Presentation ===")
test("Open pptx", lambda: (
    (r := s.call_tool('open_presentation', {'path': 'D:/文献搜索员/ppt_reflex/cases/broken.pptx'}))
    and assert_eq(r['status'], 'ok')
    and assert_eq(r['slides'], 15)
    and print(f"      {r['slides']} slides, {r['elements']} elements on slide 0")
))

# 2
print("\n=== 2. Element Summary ===")
test("Lightweight element list", lambda: (
    (r := s.call_tool('element_summary', {}))
    and (els := r['elements'])
    and assert_eq(len(els), 2)
    and assert_in('grid', els[0])
    and print(f"      Elements: {[(e['id'], e['role'], e['grid']) for e in els]}")
))

# 3
print("\n=== 3. Audit ===")
test("Detect OUT_OF_BOUNDS", lambda: (
    (r := s.call_tool('audit_slide', {}))
    and print(f"      Status: {r['status']}, issues: {len(r.get('issues',[]))}")
    and assert_eq(r['status'], 'needs_decision')
    and assert_eq(r['issues'][0]['code'], 'OUT_OF_BOUNDS')
))

# 4
print("\n=== 4. List Templates ===")
test("Template registry", lambda: (
    (r := s.call_tool('list_templates', {}))
    and (templates := r['templates'])
    and assert_eq(len(templates), 8)
    and print(f"      {', '.join(t['name'] for t in templates)}")
))

# 5
print("\n=== 5. Select Slide 2 ===")
test("Switch slide", lambda: (
    (r := s.call_tool('select_slide', {'index': 1}))
    and assert_eq(r['status'], 'ok')
    and assert_eq(r['current_slide'], 1)
    and (r2 := s.call_tool('audit_slide', {}))
    and print(f"      Status: {r2['status']}, issues: {r2['issues']}")
))

# 6
print("\n=== 6. Local Context ===")
test("Get neighbors", lambda: (
    (r := s.call_tool('local_context', {'element_ids': ['shape-00', 'shape-01']}))
    and assert_eq(r['status'], 'local_context')
    and print(f"      Targets: {[t['id'] for t in r['targets']]}, Neighbors: {[n['id'] for n in r['neighbors']]}")
))

# 7
print("\n=== 7. Set Element Role ===")
test("Assign title role", lambda: (
    (r := s.call_tool('set_element_role', {'element_id': 'shape-00', 'role': 'title'}))
    and assert_eq(r['status'], 'ok')
    and assert_eq(r['new_role'], 'title')
))

# 8
print("\n=== 8. Lock Element ===")
test("Lock shape-00", lambda: (
    (r := s.call_tool('lock_element', {'element_id': 'shape-00', 'locked_by': 'human'}))
    and assert_eq(r['status'], 'ok')
    and (r2 := s.call_tool('element_summary', {}))
    and (el := next(e for e in r2['elements'] if e['id'] == 'shape-00'))
    and assert_eq(el['locked'], True)
    and print(f"      shape-00 locked={el['locked']} by={el['locked_by']}")
))

# 9
print("\n=== 9. Move Locked → Blocked ===")
test("Blocked on locked element", lambda: (
    (r := s.call_tool('move_element', {'element_id': 'shape-00', 'x': 200, 'y': 200, 'w': 400, 'h': 100}))
    and assert_eq(r['status'], 'blocked')
    and assert_in('locked', r.get('message', ''))
))

# 10
print("\n=== 10. Unlock + Move ===")
test("Unlock then move", lambda: (
    s.call_tool('unlock_element', {'element_id': 'shape-00'})
    and (r := s.call_tool('move_element', {'element_id': 'shape-00', 'x': 100, 'y': 36, 'w': 600, 'h': 80}))
    and print(f"      Status: {r['status']}, auto_adjusted: {r.get('auto_adjusted', [])}")
    and assert_eq(r['status'], 'ok')
))

# 11
print("\n=== 11. Revision Conflict ===")
test("STATE_CHANGED after human edit", lambda: (
    (rev := s.call_tool('get_revision', {}).get('revision', 0))
    and s.call_tool('notify_human_edit', {'element_id': 'shape-01', 'x': 300, 'y': 300, 'w': 300, 'h': 200})
    and (r2 := s.call_tool('move_element', {'element_id': 'shape-01', 'x': 350, 'y': 300, 'w': 300, 'h': 200, 'expected_revision': rev}))
    and print(f"      Status: {r2['status']}, msg: {r2.get('message', '')}")
    and assert_eq(r2['status'], 'state_changed')
))

# 12
print("\n=== 12. Apply Layout ===")
test("Apply template", lambda: (
    s.call_tool('select_slide', {'index': 1})
    and s.call_tool('set_element_role', {'element_id': 'shape-00', 'role': 'title'})
    and s.call_tool('set_element_role', {'element_id': 'shape-01', 'role': 'body'})
    and (r := s.call_tool('apply_layout', {'template': 'title_body', 'role_mapping': {'title': 'shape-00', 'body': 'shape-01'}}))
    and print(f"      Status: {r['status']}, template: {r.get('applied_template')}")
    and assert_eq(r.get('applied_template'), 'title_body')
))

# 13
print("\n=== 13. Transaction + Rollback ===")
test("Rollback preserves human edits", lambda: (
    (rev := s.call_tool('get_revision', {}).get('revision', 0))
    and s.call_tool('begin_transaction', {})
    and s.call_tool('move_element', {'element_id': 'shape-01', 'x': 500, 'y': 500, 'w': 300, 'h': 200})
    and s.call_tool('notify_human_edit', {'element_id': 'shape-00', 'x': 50, 'y': 50, 'w': 600, 'h': 80})
    and (r := s.call_tool('rollback', {}))
    and print(f"      Rolled back: {r['rolled_back']} ops. {r.get('message', '')}")
    and assert_eq(r['rolled_back'], 1)  # 1 agent op in transaction
    and assert_in("Human edits preserved", r.get('message', ''))
))

# 14
print("\n=== 14. Journal ===")
test("Journal entries", lambda: (
    (r := s.call_tool('get_journal', {'since_revision': 0, 'limit': 5}))
    and (entries := r['entries'])
    and assert_eq(len(entries) <= 5, True)
    and print(f"      {len(entries)} entries: sources={set(e['source'] for e in entries)}")
    and [print(f"        rev={e['revision']} {e['source']} {e['action']} {e['element_id']}") for e in entries]
))

# 15
print("\n=== 15. Error Handling ===")
test("Unknown tool", lambda: (
    (r := s.call_tool('nonexistent', {}))
    and assert_eq(r['status'], 'error')
))
test("Invalid role", lambda: (
    (r := s.call_tool('set_element_role', {'element_id': 'shape-00', 'role': 'rocket'}))
    and assert_eq(r['status'], 'error')
))
test("Move non-existent", lambda: (
    (r := s.call_tool('move_element', {'element_id': 'shape-999', 'x': 0, 'y': 0, 'w': 100, 'h': 100}))
    and assert_eq(r['status'], 'blocked')
))

# 16: Return to slide 4 (caption+figure, should be clean)
print("\n=== 16. Slide 4 — Legal Overlap ===")
test("Caption on figure = no false positive", lambda: (
    s.call_tool('select_slide', {'index': 3})
    and s.call_tool('set_element_role', {'element_id': 'shape-00', 'role': 'figure'})
    and s.call_tool('set_element_role', {'element_id': 'shape-01', 'role': 'caption'})
    and (r := s.call_tool('audit_slide', {}))
    and print(f"      Status: {r['status']}")
    and assert_eq(r['status'], 'ok')  # Should be clean
))

# 17: Slide 13 — background + text, should be clean
print("\n=== 17. Slide 13 — Background Exemption ===")
test("Full-bleed BG = no OOB false positive", lambda: (
    s.call_tool('select_slide', {'index': 12})
    and s.call_tool('set_element_role', {'element_id': 'shape-01', 'role': 'body'})
    and (r := s.call_tool('audit_slide', {}))
    and print(f"      Status: {r['status']}")
    and assert_eq(r['status'], 'ok')
))

print(f"\n{'='*60}")
print(f"RESULTS: {ok}/{ok+fail} passed")
if fail:
    print(f"  {fail} tool(s) need fixing")
else:
    print(f"  All {ok} MCP tool interactions verified")
print(f"{'='*60}")
