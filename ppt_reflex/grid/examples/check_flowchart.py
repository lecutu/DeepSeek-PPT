"""
grid/examples/check_flowchart.py — Flowchart demo using EXISTING grid engine only.

No code changes. Proves:
  1. TEXTBOX + fill → colored flowchart nodes
  2. TEXT + "↓"/"→" → directional arrows between nodes
  3. try_place prevents overlap (every node + arrow independently placed)
  4. grid_to_ppt renders real content

What's MISSING (no code change = can't have):
  - Real arrow lines (python-pptx connector shapes)
  - Auto-layout (DAG → grid positions)
  - Connection semantics ("this node feeds that one")
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from grid import GridCanvas, GridConfig, ContentType
from grid.types import ElementPayload

OUT = os.path.join(tempfile.gettempdir(), "flowchart_demo.pptx")


def node(canvas, name, cells, text, fill_color, font_size=16):
    """Place a flowchart node: colored box with text."""
    payload = ElementPayload(
        text=text,
        font_size=font_size,
        font_color=(0xFF, 0xFF, 0xFF),
        font_bold=True,
        font_name="Microsoft YaHei",
        alignment="CENTER",
        fill_color=fill_color,
        line_spacing=1.3,
    )
    return canvas.try_place(name, ContentType.TEXTBOX, cells, payload=payload)


def arrow_down(canvas, name, cells):
    """Place a downward arrow between nodes."""
    payload = ElementPayload(
        text="▼",
        font_size=22,
        font_color=(0x99, 0x99, 0x99),
        font_name="Microsoft YaHei",
        alignment="CENTER",
    )
    return canvas.try_place(name, ContentType.TEXT, cells, payload=payload)


def arrow_right(canvas, name, cells):
    """Place a rightward arrow between nodes."""
    payload = ElementPayload(
        text="▶",
        font_size=18,
        font_color=(0x99, 0x99, 0x99),
        font_name="Microsoft YaHei",
        alignment="CENTER",
    )
    return canvas.try_place(name, ContentType.TEXT, cells, payload=payload)


def label(canvas, name, cells, text, font_size=11):
    """Small annotation label."""
    payload = ElementPayload(
        text=text,
        font_size=font_size,
        font_color=(0x66, 0x66, 0x66),
        font_name="Microsoft YaHei",
        alignment="CENTER",
    )
    return canvas.try_place(name, ContentType.ANNOTATION, cells, payload=payload)


def demo():
    cfg = GridConfig()
    canvas = GridCanvas(cfg)

    # ── Title ──
    canvas.try_place("title", ContentType.TEXT, ["B1","C1","D1","E1","F1","G1"],
        payload=ElementPayload(
            text="PMSQ Synthesis Flowchart",
            font_size=28, font_color=(0x1B,0x3A,0x5C), font_bold=True,
            font_name="Microsoft YaHei", alignment="CENTER",
        ))

    # ── Step 1: Hydrolysis ──
    r = node(canvas, "step1", ["B3","C3","D3","E3","F3","G3","B4","C4","D4","E4","F4","G4"],
        "❶  Hydrolysis\nMTMS + H₂O + HCl (pH=3) → Si-OH + MeOH",
        (0x1B, 0x3A, 0x5C))   # navy blue
    print(f"[{r.verdict.value.upper()}] step1 @ B3:G4")

    arrow_down(canvas, "a1", ["D5","E5"])

    # ── Step 2: Condensation ──
    r = node(canvas, "step2", ["B6","C6","D6","E6","F6","G6","B7","C7","D7","E7","F7","G7"],
        "❷  Condensation\nSi-OH + Si-OH → Si-O-Si + H₂O",
        (0xC0, 0x39, 0x2B))   # brick red
    print(f"[{r.verdict.value.upper()}] step2 @ B6:G7")

    arrow_down(canvas, "a2", ["D8","E8"])

    # ── Step 3: Aging → PMSQ ──
    r = node(canvas, "step3", ["B8","C8","D8","E8","F8","G8","B9","C9","D9","E9","F9","G9"],
        "❸  Aging & Drying\n80°C, 24h → PMSQ Gel",
        (0x27, 0xAE, 0x60))   # green
    print(f"[{r.verdict.value.upper()}] step3 @ B8:G9")


    # ── Check: try overlapping TEXT on TEXT → should BLOCK ──
    overlap = canvas.try_place("overlap_test", ContentType.TEXT,
        ["C1","D1","E1","F1"],   # overlaps title (TEXT × TEXT = BLOCK)
        payload=ElementPayload(text="SHOULD BE BLOCKED", font_size=14))
    print(f"\n[Overlap test] title zone C1:F1 → [{overlap.verdict.value.upper()}]")
    if overlap.blocked:
        print(f"  BLOCK detail: {overlap.conflicts[0].detail}")
        print(f"  Free suggestion: {overlap.free_suggestion[0][:6]}...")
    else:
        print(f"  UNEXPECTED: {overlap.verdict.value}")

    # ── Commit ──
    canvas.checkpoint()
    result = canvas.commit(OUT)
    print(f"\nCommit: {result['status']} → {OUT}")
    if os.path.exists(OUT):
        print(f"  Size: {os.path.getsize(OUT)} bytes")

    print(f"\nOccupied elements:")
    for oid, cells in canvas.occupied_summary().items():
        print(f"  {oid}: {len(cells)} fine cells")


if __name__ == "__main__":
    print("=" * 60)
    print("PPT Reflex Grid — Flowchart Demo (no code changes)")
    print("=" * 60)
    demo()
    print("=" * 60)
    print(f"Open: {OUT}")
    print("=" * 60)
