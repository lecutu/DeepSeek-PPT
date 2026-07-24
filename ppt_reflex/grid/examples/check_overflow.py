"""
grid/examples/check_overflow.py — End-to-end overflow detection demo.

Proves the engine catches text overflow BEFORE writing PPT:
  1. Place elements with payload via try_place
  2. Code box with too many lines in too-small area → WARN with suggestion
  3. Fix: expand grid area → ALLOW
  4. Commit renders payload content (text/font/color/fill)
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from grid import GridCanvas, GridConfig, ContentType, Supply
from grid.types import ElementPayload

OUT = os.path.join(tempfile.gettempdir(), "overflow_demo.pptx")


def demo():
    cfg = GridConfig()
    canvas = GridCanvas(cfg)
    supply = Supply(cfg)

    # 10 lines × 11pt × 1.35 line_spacing = 148.5pt needed
    # 2 coarse rows × 60pt = 120pt box → 28.5pt overflow → WARN expected
    code_lines = [
        "def compute_statistics(data):",
        '    """Return summary statistics for a list of numbers."""',
        "    from statistics import mean, median, stdev",
        "    return {",
        '        "mean": mean(data),',
        '        "median": median(data),',
        '        "std_dev": stdev(data),',
        '        "min": min(data),',
        '        "max": max(data),',
        "    }",
    ]

    # ── Place title (with payload) ──
    title_payload = ElementPayload(
        text="Overflow Detection Demo",
        font_size=28,
        font_color=(0x1B, 0x3A, 0x5C),
        font_bold=True,
        font_name="Arial",
        alignment="CENTER",
    )
    r = canvas.try_place("title", ContentType.TEXT, ["A1","B1","C1","D1","E1","F1","G1","H1"],
                         payload=title_payload)
    print(f"[{r.verdict.value.upper()}] title @ A1:H1")

    # ── TRY placing 10-line code box in 2 rows = 120pt — too small ──
    code_payload = ElementPayload(
        text="\n".join(code_lines),
        font_size=11,
        font_color=(0xDC, 0xDF, 0xE4),
        font_name="Consolas",
        fill_color=(0x28, 0x2C, 0x34),
        line_spacing=1.35,
        line_count=len(code_lines),
    )
    r = canvas.try_place("code_box_small", ContentType.TEXTBOX,
                         ["A3","B3","C3","D3","E3","F3","G3","H3",
                          "A4","B4","C4","D4","E4","F4","G4","H4"],
                         payload=code_payload)
    print(f"[{r.verdict.value.upper()}] code_box_small @ A3:H4 (2 rows = 120pt)")
    if r.warnings:
        print(f"  WARN: {r.warnings[0].detail}")
    if r.blocked:
        print(f"  BLOCKED: {r.conflicts[0].detail}")

    # ── FIX: expand to 3 rows = 180pt → 148.5pt fits ──
    r2 = canvas.try_place("code_box_fixed", ContentType.TEXTBOX,
                          ["A3","B3","C3","D3","E3","F3","G3","H3",
                           "A4","B4","C4","D4","E4","F4","G4","H4",
                           "A5","B5","C5","D5","E5","F5","G5","H5"],
                          payload=code_payload)
    print(f"[{r2.verdict.value.upper()}] code_box_fixed @ A3:H5 (3 rows = 180pt)")
    if r2.allowed:
        print(f"  PASS: overflow resolved by expanding grid area")

    # ── Also show a tight-fit case: 3 rows barely fits ──
    long_text = ElementPayload(
        text="This is a single-line text that is way too long to fit in a narrow box and will wrap to multiple lines, eventually exceeding the box height when the box is too short.",
        font_size=14,
        font_color=(0x22, 0x22, 0x44),
        font_name="Arial",
        line_spacing=1.2,
    )
    r3 = canvas.try_place("narrow_box", ContentType.TEXT,
                          ["I1","J1"],
                          payload=long_text)
    print(f"[{r3.verdict.value.upper()}] narrow_box @ I1:J1 (1 coarse cell = 60pt × 60pt)")
    if r3.warnings:
        print(f"  WARN: {r3.warnings[0].detail}")

    # ── Commit ──
    canvas.checkpoint()
    result = canvas.commit(OUT)
    print(f"\nCommit: {result['status']} -> {OUT}")
    if os.path.exists(OUT):
        print(f"  File: {os.path.getsize(OUT)} bytes, density {canvas.info_grid.density():.0%}")

    # Summary of zones
    print(f"\nCanvas zones:")
    for oid, cells in canvas.occupied_summary().items():
        print(f"  {oid}: {cell_range_safe(cells)}")


def cell_range_safe(cells):
    from grid.positioning import cell_range
    try:
        return cell_range(sorted(cells))
    except Exception:
        return str(cells)


if __name__ == "__main__":
    print("=" * 60)
    print("PPT Reflex Grid — Overflow Detection Demo")
    print("=" * 60)
    demo()
    print("=" * 60)
    print("Done. Overflow caught BEFORE PPT write!")
    print(f"Open: {OUT}")
    print("=" * 60)
