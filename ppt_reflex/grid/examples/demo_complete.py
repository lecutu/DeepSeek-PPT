"""
examples/demo_complete.py — 完整流程演示

load broken.pptx → grid canvas → detect → Agent decision loop → commit
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from grid import GridCanvas, GridConfig, ContentType, Supply, Verdict


def main():
    print("="*70)
    print("PPT Reflex — Complete Agent Loop Demo")
    print("="*70)

    canvas = GridCanvas(GridConfig())
    supply = Supply(GridConfig())

    # ── Step 1: Load broken.pptx ──
    broken_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "cases", "broken.pptx"
    )
    if not os.path.exists(broken_path):
        print(f"\n{broken_path} not found. Creating mock scenario instead.\n")
        _run_mock(canvas, supply)
        return

    print(f"\n1. Loading: {broken_path}")
    result = canvas.load(broken_path, 0)  # slide 0
    print(f"   {result}")

    # ── Step 2: Grid snapshot (L0) ──
    print(f"\n2. Slide 0 overview:")
    profile = canvas.profile()
    l0 = supply.level0(canvas.info_grid, profile)
    import json
    print(f"   {json.dumps(l0, ensure_ascii=False, indent=2)[:300]}")

    # ── Step 3: Agent try_place decision loop ──
    print(f"\n3. Agent loop — trying placements...")
    results = _agent_loop(canvas, supply)

    print(f"\n{'-'*60}")
    print(f"4. Final canvas state:")
    l0 = supply.level0(canvas.info_grid)
    print(f"   {json.dumps(l0, ensure_ascii=False)}")

    # ── Step 5: Commit ──
    out = os.path.join(tempfile.gettempdir(), "complete_demo.pptx")
    canvas.checkpoint()
    r = canvas.commit(out)
    print(f"\n5. Committed: {r['status']} ({out})")
    if os.path.exists(out):
        print(f"   File: {os.path.getsize(out)} bytes")

    print(f"\n{'='*70}")
    print(f"Demo complete. {'✓' if results['success'] else '⚠'} "
          f"{results['placed']}/{results['tried']} placed.")
    print(f"{'='*70}")


def _agent_loop(canvas, supply) -> dict:
    """Simulate Agent: try placements, get conflicts, adapt."""
    tried = 0
    placed = 0

    # Agent tries body in left zone
    tried += 1
    r = canvas.try_place("s_body", ContentType.TEXT,
                         ["A2","B2","C2","D2","A3","B3","C3","D3",
                          "A4","B4","C4","D4","A5","B5","C5","D5"])
    if r.allowed:
        placed += 1
        print(f"   ✓ body → A2:D5")
    else:
        print(f"   ✗ body blocked: {supply.format_conflict(r).get('suggestions','?')}")

    # Agent tries figure in right zone
    tried += 1
    r = canvas.try_place("s_fig", ContentType.IMAGE,
                         ["E2","F2","G2","H2","E3","F3","G3","H3",
                          "E4","F4","G4","H4","E5","F5","G5","H5"])
    if r.allowed:
        placed += 1
        print(f"   ✓ figure → E2:H5")
    else:
        print(f"   ✗ figure blocked")

    # Agent tries title at top
    tried += 1
    r = canvas.try_place("s_title", ContentType.TEXT,
                         ["A1","B1","C1","D1","E1","F1","G1","H1"])
    if r.allowed:
        placed += 1
        print(f"   ✓ title → A1:H1")
    else:
        print(f"   ✗ title blocked")

    # Agent tries caption overlapping body → should BLOCK
    tried += 1
    r = canvas.try_place("s_cap", ContentType.TEXT, ["C3","D3"])
    if r.allowed:
        placed += 1
        print(f"   ✓ caption (unexpected — should have blocked)")
    else:
        report = supply.format_conflict(r)
        sug = report.get("suggestions", ["none"])
        print(f"   ✗ caption on body → BLOCKED. Suggestion: {sug[0]}")
        # Agent adapts: try free zone
        if sug and sug[0] != "none":
            tried += 1
            r2 = canvas.try_place("s_cap", ContentType.TEXT, ["A7","B7","C7"])
            if r2.allowed:
                placed += 1
                print(f"   ✓ caption moved to A7:C7")

    return {"success": tried == placed, "tried": tried, "placed": placed}


def _run_mock(canvas, supply):
    """Fallback when broken.pptx not available."""
    canvas.try_place("s_title", ContentType.TEXT, ["A1","B1","C1"])
    canvas.try_place("s_body", ContentType.TEXT,
                     ["A2","B2","C2","D2","A3","B3","C3","D3",
                      "A4","B4","C4","D4","A5","B5","C5","D5"])
    canvas.try_place("s_fig", ContentType.IMAGE,
                     ["E2","F2","G2","H2","E3","F3","G3","H3",
                      "E4","F4","G4","H4","E5","F5","G5","H5"])

    r = canvas.try_place("s_cap", ContentType.TEXT, ["C3","D3"])
    print(f"   Try caption on body: {r.verdict.value}")
    if r.blocked:
        print(f"   Conflict: {r.conflicts[0].detail}")
        sug = supply.format_conflict(r).get("suggestions", ["none"])
        print(f"   Suggestion: {sug[0]}")

    r = canvas.try_place("s_cap", ContentType.TEXT, ["A7","B7","C7"])
    print(f"   Move to free: {r.verdict.value}")

    out = os.path.join(tempfile.gettempdir(), "mock_demo.pptx")
    canvas.checkpoint()
    canvas.commit(out)
    print(f"   Saved: {out} ({os.path.getsize(out)} bytes)")


if __name__ == "__main__":
    main()
