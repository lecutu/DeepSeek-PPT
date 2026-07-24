"""
grid/examples/check_shapes.py — Shape library + connector demo.

Tests every shape_id + true arrow connectors between cells.
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from grid import GridCanvas, GridConfig, ContentType
from grid.types import ElementPayload

OUT = os.path.join(tempfile.gettempdir(), "shape_library.pptx")

# Samples from the full shape map
DEMO_SHAPES = [
    ("rounded_rectangle", "Rounded"),
    ("diamond", "Diamond"),
    ("ellipse", "Ellipse"),
    ("chevron", "Chevron"),
    ("pentagon", "Penta"),
    ("star5", "★5"),
    ("triangle", "Tri"),
    ("right_arrow", "→"),
    ("up_arrow", "↑"),
    ("moon", "Moon"),
    ("heart", "♥"),
    ("cloud", "Cloud"),
    ("banner", "Banner"),
    ("seal8", "Seal"),
    ("flowchart_decision", "Decision"),
    ("flowchart_terminator", "Start/End"),
    ("flowchart_data", "Data"),
    ("flowchart_document", "Doc"),
    ("flowchart_merge", "Merge"),
    ("flowchart_offline_storage", "Storage"),
]


def demo():
    cfg = GridConfig()
    c = GridCanvas(cfg)

    # Title
    c.try_place("title", ContentType.TEXT, ["B1","C1","D1","E1","F1","G1"],
        payload=ElementPayload(
            text="Shape Library + Connectors Demo", font_size=24,
            font_color=(0x1B,0x3A,0x5C), font_bold=True,
            font_name="Microsoft YaHei", alignment="CENTER"))

    # ═══ Full shape gallery (4 rows × 5 cols) ═══
    colors = [(0x1B,0x3A,0x5C),(0xC0,0x39,0x2B),(0x27,0xAE,0x60),
              (0xE6,0x7E,0x22),(0x8E,0x44,0xAD)]
    row_start = [3, 7, 11]   # coarse rows (3 rows × 5 cols = 15 shapes)
    col_start = [2, 3, 4, 5, 6]  # B through G

    for i, (sid, label) in enumerate(DEMO_SHAPES):
        ri = i // 5
        ci = i % 5
        if ri >= len(row_start):
            break
        r = row_start[ri]
        col_idx = col_start[ci]
        col = chr(ord('A') + col_idx)
        cells = [f"{col}{r}", f"{col}{r+1}", f"{chr(ord(col)+1)}{r}", f"{chr(ord(col)+1)}{r+1}"]

        payload = ElementPayload(
            text=label, font_size=9, font_color=(0xFF,0xFF,0xFF), font_bold=True,
            font_name="Microsoft YaHei", alignment="CENTER",
            fill_color=colors[ri], shape_id=sid)
        res = c.try_place(f"sh_{i}", ContentType.TEXTBOX, cells, payload=payload)
        if not res.allowed:
            print(f"  BLOCKED: {sid} @ {cells}: {res.conflicts[0].detail if res.conflicts else '?'}")

    # ═══ Connectors between shapes ═══
    conns = [
        ("conn_AB", "I3", "N3"),    # horizontal
        ("conn_CD", "I10", "N10"),  # horizontal
        ("conn_BD", "N3", "N10"),   # vertical
        ("conn_AC", "I3", "I10"),   # vertical
        ("conn_diag", "I3", "N10"), # diagonal
    ]
    for cid, fr, to in conns:
        payload = ElementPayload(
            connector_from=fr, connector_to=to,
            line_color=(0x1B, 0x3A, 0x5C), line_width_pt=2.0)
        res = c.try_place(cid, ContentType.CONNECTOR, [fr, to], payload=payload)
        # Note: CONNECTOR on cells won't overlap with nearby TEXTBOX — but to be safe
        # we place them in the right column area (H-O) where there's only connectors

    print(f"\nConnectors placed:")
    for cid, fr, to in conns:
        print(f"  {cid}: {fr} → {to}")

    # ═══ Collision: TEXT on TEXTBOX (ELLIPSE) should be ALLOW ═══
    overlap = c.try_place("test_overlap", ContentType.TEXT, ["C3","D3"],
        payload=ElementPayload(text="OVER", font_size=10, font_color=(0xFF,0,0)))
    print(f"\nTEXT on filled shape (should ALLOW): [{overlap.verdict.value.upper()}]")

    c.checkpoint()
    r = c.commit(OUT)
    print(f"\nCommit: {r['status']} → {OUT}")
    print(f"Size: {os.path.getsize(OUT)} bytes")


if __name__ == "__main__":
    print("=" * 60)
    print("Shape Library + Connectors")
    print("=" * 60)
    demo()
    print("=" * 60)
    print(f"Open: {OUT}")
    print("=" * 60)
