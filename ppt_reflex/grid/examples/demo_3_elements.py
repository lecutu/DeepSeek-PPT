"""
examples/demo_3_elements.py — 最小可运行 demo
证明架构跑通：Agent 用格子地址操作 → 引擎拦截/放行 → PPT 写入

运行: python -m ppt_reflex.grid.examples.demo_3_elements
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from grid import GridCanvas, GridConfig, ContentType, Supply


def main():
    print("="*60)
    print("PPT Reflex Grid Canvas — Demo")
    print("="*60)

    canvas = GridCanvas(GridConfig())
    supply = Supply()

    # Step 1: 放 title (纯文本)
    print("\n1. Put title on A1:B1...")
    r = canvas.try_place("s_title", ContentType.TEXT, ["A1", "B1", "C1"])
    print(f"   → {r.verdict.value.upper()}")

    # Step 2: 放 body (纯文本)
    print("\n2. Put body on A2:D6...")
    r = canvas.try_place("s_body", ContentType.TEXT,
                         ["A2","B2","C2","D2", "A3","B3","C3","D3",
                          "A4","B4","C4","D4", "A5","B5","C5","D5",
                          "A6","B6","C6","D6"])
    print(f"   → {r.verdict.value.upper()}")

    # Step 3: 放 figure 在旁边
    print("\n3. Put figure on E2:H6 (next to body)...")
    r = canvas.try_place("s_fig", ContentType.IMAGE,
                         ["E2","F2","G2","H2", "E3","F3","G3","H3",
                          "E4","F4","G4","H4", "E5","F5","G5","H5",
                          "E6","F6","G6","H6"])
    print(f"   → {r.verdict.value.upper()}")

    # Step 4: 尝在 body 上叠文字 → BLOCK
    print("\n4. TRY to put caption ON TOP of body (C6:D6) — should BLOCK...")
    r = canvas.try_place("s_caption", ContentType.TEXT, ["C6", "D6"])
    print(f"   → {r.verdict.value.upper()}")

    if r.blocked:
        report = supply.format_conflict(r)
        opps = [c["conflict_with"] for c in report["conflicts"]]
        print(f"   Conflicts with: {opps}")
        if report.get("suggestions"):
            print(f"   Suggested free: {report['suggestions'][0]}")

    # Step 5: 放到空闲区 → ALLOW
    print("\n5. Move caption to free zone (A8:C8)...")
    r = canvas.try_place("s_caption", ContentType.TEXT, ["A8", "B8", "C8"])
    print(f"   → {r.verdict.value.upper()}")

    # Step 6: 查看画布状态
    l0 = supply.level0(canvas.info_grid)
    print(f"\n6. Canvas state: {len(l0['zones'])} elements, density {l0['density']}%")
    for name, info in l0["zones"].items():
        print(f"   {name}: {info['range']}")

    # Step 7: 写入 PPT
    out = os.path.join(tempfile.gettempdir(), "demo_canvas.pptx")
    canvas.checkpoint()
    result = canvas.commit(out)
    print(f"\n7. Committed: {result['status']} ({out})")
    if os.path.exists(out):
        print(f"   File size: {os.path.getsize(out)} bytes")

    print("\n" + "="*60)
    print("Demo complete. Grid state == PPT file.")
    print("="*60)


if __name__ == "__main__":
    main()
