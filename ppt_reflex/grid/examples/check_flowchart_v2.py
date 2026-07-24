"""
grid/examples/check_flowchart_v2.py — Slightly more complex flowchart.

3-branch parallel step + merge. Pushes against engine limits.
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from grid import GridCanvas, GridConfig, ContentType
from grid.types import ElementPayload

OUT = os.path.join(tempfile.gettempdir(), "flowchart_v2.pptx")

def node(canvas, name, cells, text, fill_color, fc=(0xFF,0xFF,0xFF), fs=14):
    p = ElementPayload(text=text, font_size=fs, font_color=fc, font_bold=True,
                       font_name="Microsoft YaHei", alignment="CENTER",
                       fill_color=fill_color, line_spacing=1.3)
    return canvas.try_place(name, ContentType.TEXTBOX, cells, payload=p)

def arrow(canvas, name, cells, direction="▼"):
    p = ElementPayload(text=direction, font_size=18, font_color=(0x99,0x99,0x99),
                       font_name="Microsoft YaHei", alignment="CENTER")
    return canvas.try_place(name, ContentType.TEXT, cells, payload=p)

def label(canvas, name, cells, text):
    p = ElementPayload(text=text, font_size=10, font_color=(0x77,0x77,0x77),
                       font_name="Microsoft YaHei", alignment="CENTER")
    return canvas.try_place(name, ContentType.ANNOTATION, cells, payload=p)


def demo():
    cfg = GridConfig()
    canvas = GridCanvas(cfg)

    # Title
    canvas.try_place("title", ContentType.TEXT, ["C1","D1","E1","F1","G1","H1"],
        payload=ElementPayload(
            text="PMSQ Synthesis: Routes Comparison",
            font_size=24, font_color=(0x1B,0x3A,0x5C), font_bold=True,
            font_name="Microsoft YaHei", alignment="CENTER"))

    # ── Common precursor ──
    node(canvas, "precursor", ["E2","F2","G2","H2","E3","F3","G3","H3"],
        "MTMS\n(common precursor)", (0x42,0x46,0x52))
    arrow(canvas, "a0", ["F4","G4"], "▼")
    label(canvas, "l0", ["F5","G5"], "H₂O / HCl / pH control")

    # ── 3 parallel routes ──
    # Route A: traditional sol-gel (left)
    node(canvas, "routeA", ["A6","B6","C6","A7","B7","C7"],
        "Route A\nSol-Gel", (0x1B,0x3A,0x5C), fs=12)
    arrow(canvas, "aa", ["B8"], "▼")

    # Route B: urea method (center) — highlighted
    node(canvas, "routeB", ["E6","F6","G6","H6","E7","F7","G7","H7"],
        "Route B ★\nUrea Method", (0xE7,0x4C,0x3C), fs=12)
    label(canvas, "lb", ["E8","F8","G8","H8"], "Gao 2025 Nat Commun\npH dual-regulation")

    arrow(canvas, "ab", ["G8"], "▼")

    # Route C: DMDMS modification (right)
    node(canvas, "routeC", ["J6","K6","L6","J7","K7","L7"],
        "Route C\nDMDMS", (0x1B,0x3A,0x5C), fs=12)
    arrow(canvas, "ac", ["K8"], "▼")

    # ── Merge to product ──
    node(canvas, "product", ["D9","E9","F9","G9","H9","I9","D10","E10","F10","G10","H10","I10"],
        "PMSQ Gel @ 80°C, 24h", (0x27,0xAE,0x60))

    # ── Overlap check: TEXT on TEXT ──
    overlap = canvas.try_place("bad", ContentType.TEXT, ["C1","D1"],  # on title zone
        payload=ElementPayload(text="X", font_size=14))
    print(f"Overlap on routeB: [{overlap.verdict.value.upper()}]")

    canvas.checkpoint()
    result = canvas.commit(OUT)
    print(f"Commit: {result['status']} → {OUT}")
    print(f"Size: {os.path.getsize(OUT)} bytes")


if __name__ == "__main__":
    print("=" * 60)
    print("Flowchart v2: 3 routes + merge")
    print("=" * 60)
    demo()
    print("=" * 60)
    print(f"Open: {OUT}")
    print("=" * 60)
