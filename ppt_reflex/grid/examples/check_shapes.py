"""
grid/examples/check_shapes.py — Shape library + true arrow connectors.

40+ shape_id → python-pptx MSO_SHAPE presets.
CONNECTOR type draws real arrows with arrowheads between cells.
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from grid import GridCanvas, GridConfig, ContentType
from grid.types import ElementPayload

OUT = os.path.join(tempfile.gettempdir(), "shape_library_v3.pptx")

SHAPES = [
    ("rounded_rectangle", "Rounded"),
    ("diamond",      "Diamond"),
    ("ellipse",       "Ellipse"),
    ("chevron",       "Chevron"),
    ("pentagon",      "Penta"),
    ("star5",         "★5"),
    ("triangle",      "Tri"),
    ("right_arrow",   "→"),
    ("up_arrow",      "↑"),
    ("heart",         "♥"),
    ("banner",        "Banner"),
    ("flowchart_decision", "Decision"),
]
COLORS = [
    (0x1B,0x3A,0x5C), (0xC0,0x39,0x2B), (0x27,0xAE,0x60),
    (0xE6,0x7E,0x22), (0x8E,0x44,0xAD), (0x1B,0x3A,0x5C),
]


def demo():
    cfg = GridConfig()
    c = GridCanvas(cfg)

    c.try_place("title", ContentType.TEXT, ["A1","B1","C1","D1","E1","F1","G1","H1"],
        payload=ElementPayload(
            text="Shape Library + Arrow Connectors", font_size=22,
            font_color=(0x1B,0x3A,0x5C), font_bold=True,
            font_name="Microsoft YaHei", alignment="CENTER"))

    # ═══ 12 shapes: 3 rows × 4 cols, 1-coarse-cell gap ═══
    # Each shape: 4 fine cells in a 2×2 fine grid = 1 coarse cell
    # Layout grid (coarse): row 2/4/6, col A D G J (1-cell gaps B C, E F, H I)
    row_offsets = [2, 4, 6]    # coarse rows (1-indexed in fine cells)
    col_offsets = [0, 3, 6, 9]  # coarse cols mapped to fine col
    size = 2                    # fine cells per shape side

    for i, (sid, label) in enumerate(SHAPES):
        ri, ci = i // 4, i % 4
        if ri >= len(row_offsets) or ci >= len(col_offsets):
            break
        r0 = row_offsets[ri]
        c0 = col_offsets[ci]
        # Build fine cell addresses: 2×2 block
        cells = []
        for dr in range(size):
            for dc in range(size):
                col_letter = chr(ord('A') + c0 + dc)
                cells.append(f"{col_letter}{r0 + dr + 1}")

        payload = ElementPayload(
            text=label, font_size=10, font_color=(0xFF,0xFF,0xFF), font_bold=True,
            font_name="Microsoft YaHei", alignment="CENTER",
            fill_color=COLORS[ri], shape_id=sid)
        res = c.try_place(f"sh_{i}", ContentType.TEXTBOX, cells, payload=payload)
        status = res.verdict.value.upper()
        if not res.allowed:
            print(f"  {status}: {sid} @ {cells}")
        else:
            print(f"  {status}: {sid} @ {cells[0]}:{cells[-1]}")

    # ═══ True arrow connectors between shapes ═══
    # Horizontal connectors (row 1: sh_0 → sh_1 → sh_2 → sh_3)
    # These use fine-cell addresses. Shapes are at:
    #   sh_0: A3..B4, sh_1: D3..E4, sh_2: G3..H4, sh_3: J3..K4
    # Arrow from center of sh_0 right edge (C3=gap center) to sh_1 left
    for src_fine, dst_fine, color in [
        ("C3", "D3", (0x1B,0x3A,0x5C)),   # sh_0→sh_1
        ("F3", "G3", (0x1B,0x3A,0x5C)),   # sh_1→sh_2
        ("I3", "J3", (0x1B,0x3A,0x5C)),   # sh_2→sh_3
        # Vertical: sh_0→sh_4, sh_1→sh_5
        ("B4", "B5", (0xC0,0x39,0x2B)),
        ("E4", "E5", (0xC0,0x39,0x2B)),
        # Diagonal: sh_2→sh_8
        ("G4", "D8", (0x8E,0x44,0xAD)),
    ]:
        oid = f"conn_{src_fine}_{dst_fine}".replace(",","")
        payload = ElementPayload(
            connector_from=src_fine, connector_to=dst_fine,
            line_color=color, line_width_pt=2.0)
        res = c.try_place(oid, ContentType.CONNECTOR, [src_fine], payload=payload)
        print(f"  Conn {src_fine}→{dst_fine}: {res.verdict.value.upper()}")

    # ═══ Collision: TEXT over sh_0 (TEXTBOX) should ALLOW ═══
    overlap = c.try_place("bad", ContentType.TEXT, ["A3"],
        payload=ElementPayload(text="X", font_size=10))
    print(f"\nTEXT on TEXTBOX: [{overlap.verdict.value.upper()}] "
          f"(TEXT×TEXTBOX=ALLOW, shows z_hint)")

    # TEXT on TEXT: try over title
    overlap2 = c.try_place("bad2", ContentType.TEXT, ["A1"],
        payload=ElementPayload(text="X", font_size=10))
    print(f"TEXT on TEXT:    [{overlap2.verdict.value.upper()}] "
          f"({'BLOCKED: '+overlap2.conflicts[0].detail if overlap2.blocked else 'no conflict'})")

    c.checkpoint()
    r = c.commit(OUT)
    print(f"\nCommit: {r['status']} → {OUT}")
    print(f"Size: {os.path.getsize(OUT)} bytes")


if __name__ == "__main__":
    print("=" * 60)
    print("Shape Library + Arrow Connectors Demo")
    print("=" * 60)
    demo()
    print("=" * 60)
    print(f"Open: {OUT}")
    print("=" * 60)
