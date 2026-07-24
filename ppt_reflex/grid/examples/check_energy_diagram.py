"""
grid/examples/check_energy_diagram.py — Jablonski energy diagram v3.

Uses: rounded_rectangle bands (2 fine-cells high) + CONNECTOR arrows
      with anchor points (bottom/top/left/right) for proper transitions.
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from grid import GridCanvas, GridConfig, ContentType
from grid.types import ElementPayload, SemanticRole

OUT = os.path.join(tempfile.gettempdir(), "jablonski_energy_diagram.pptx")


def col_letter(ci: int) -> str:
    if ci < 26:
        return chr(ord('A') + ci)
    return chr(ord('A') + ci // 26 - 1) + chr(ord('A') + ci % 26)


def cell_range(r0: int, c0: int, r1: int, c1: int) -> list[str]:
    """Rectangle of fine cells: rows r0..r1, cols c0..c1."""
    cells = []
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            cells.append(f"{col_letter(c)}{r}")
    return cells


def demo():
    cfg = GridConfig()
    c = GridCanvas(cfg)

    # Fine-grid layout (0-indexed rows, 1-indexed display):
    #   Rows 1-2:  title
    #   Rows 3-4:  spacing
    #   Rows 5-6:  S₁  Singlet Excited  (red, 2 rows)
    #   Row  7:    gap
    #   Rows 8-9:  T₁  Triplet          (orange, 2 rows)
    #   Row  10:   gap
    #   Rows 11-12: S₀  Ground State     (blue, 2 rows)
    #   Rows 13-14: labels zone
    BAND_LEFT, BAND_RIGHT = 2, 14  # cols C(2) to O(14) → 13×30=390pt wide

    # ═══ Title (rows 1-2, cols D..N) ═══
    c.try_place("title", ContentType.TEXT, cell_range(1, 3, 2, 13),
        payload=ElementPayload(
            text="Jablonski Energy Diagram", font_size=24,
            font_color=(0x1B,0x3A,0x5C), font_bold=True,
            font_name="Microsoft YaHei", alignment="CENTER"))

    # ═══ Energy axis label ═══
    c.try_place("axis", ContentType.ANNOTATION, ["A4", "A5"],
        payload=ElementPayload(text="E\n↑", font_size=10,
            font_color=(0x1B,0x3A,0x5C),
            font_name="Microsoft YaHei", alignment="CENTER"))

    # ═══ 3 energy bands — rounded rectangles, 2 cells high ═══
    bands = [
        ("S1",  5,  6,  "S₁  Singlet Excited",  (0xC0,0x39,0x2B)),
        ("T1",  8,  9,  "T₁  Triplet",           (0xE6,0x7E,0x22)),
        ("S0", 11, 12,  "S₀  Ground State",      (0x1B,0x3A,0x5C)),
    ]
    for name, r0, r1, text, color in bands:
        res = c.try_place(name, ContentType.TEXTBOX,
            cell_range(r0, BAND_LEFT, r1, BAND_RIGHT),
            payload=ElementPayload(
                text=text, font_size=14, font_color=(0xFF,0xFF,0xFF),
                font_bold=True, font_name="Microsoft YaHei", alignment="CENTER",
                fill_color=color, shape_id="rounded_rectangle"))
        print(f"  Band {name}: [{res.verdict.value.upper()}] rows {r0}-{r1}")

    # ═══ Transition arrows with anchor points ═══
    # Each arrow connects from one band's edge to another's edge
    #
    # Absorption: S₀(top) → S₁(bottom) — up arrow
    #   Start at S₀ row=11, end at S₁ row=6
    c.try_place("c_abs", ContentType.CONNECTOR, ["D11"],
        payload=ElementPayload(
            connector_from="D11", connector_to="D6",
            connector_anchor_from="top", connector_anchor_to="bottom",
            line_color=(0x29,0x80,0xB9), line_width_pt=2.5))

    # Absorption label
    c.try_place("l_abs", ContentType.ANNOTATION, cell_range(8, 2, 8, 3),
        payload=ElementPayload(text="Absorption\nhν", font_size=9,
            font_color=(0x29,0x80,0xB9), font_name="Microsoft YaHei",
            alignment="CENTER"))

    # Fluorescence: S₁(bottom) → S₀(top) — down arrow
    c.try_place("c_fluor", ContentType.CONNECTOR, ["J6"],
        payload=ElementPayload(
            connector_from="J6", connector_to="J11",
            connector_anchor_from="bottom", connector_anchor_to="top",
            line_color=(0x27,0xAE,0x60), line_width_pt=2.5))

    c.try_place("l_fluor", ContentType.ANNOTATION, cell_range(8, 10, 8, 11),
        payload=ElementPayload(text="Fluorescence\n~10⁻⁹ s", font_size=9,
            font_color=(0x27,0xAE,0x60), font_name="Microsoft YaHei",
            alignment="CENTER"))

    # ISC: S₁(right) → T₁(top) — diagonal line
    c.try_place("c_isc", ContentType.CONNECTOR, ["O6"],
        payload=ElementPayload(
            connector_from="O6", connector_to="N8",
            connector_anchor_from="right", connector_anchor_to="top",
            line_color=(0xE6,0x7E,0x22), line_width_pt=2.0))

    c.try_place("l_isc", ContentType.ANNOTATION, ["O3", "O4"],
        payload=ElementPayload(text="ISC", font_size=9,
            font_color=(0xE6,0x7E,0x22), font_name="Microsoft YaHei",
            alignment="CENTER"))

    # Phosphorescence: T₁(bottom) → S₀(top) — down arrow
    c.try_place("c_phos", ContentType.CONNECTOR, ["H9"],
        payload=ElementPayload(
            connector_from="H9", connector_to="H11",
            connector_anchor_from="bottom", connector_anchor_to="top",
            line_color=(0x9B,0x59,0xB6), line_width_pt=2.5))

    c.try_place("l_phos", ContentType.ANNOTATION, cell_range(12, 6, 12, 7),
        payload=ElementPayload(text="Phosphorescence\n~10⁻³ s", font_size=9,
            font_color=(0x9B,0x59,0xB6), font_name="Microsoft YaHei",
            alignment="CENTER"))

    # ═══ Vibrational relaxation (wiggly arrow symbol) ═══
    for row, name in [(3, "vr1"), (14, "vr2")]:
        c.try_place(name, ContentType.ANNOTATION, cell_range(row, 15, row, 16),
            payload=ElementPayload(text="↕", font_size=12,
                font_color=(0xAA,0xAA,0xAA),
                font_name="Microsoft YaHei", alignment="CENTER"))

    # ═══ pre_commit_validation ═══
    report = c.pre_commit_validation()
    print(f"\nPre-commit: {report['summary']}")
    for w in report["warnings"]:
        print(f"  ⚠ {w['owner_id']}: {w['detail']}")
    for e in report["errors"]:
        print(f"  ❌ {e['owner_id']}: {e['detail']}")

    c.checkpoint()
    r = c.commit(OUT)
    print(f"\nCommit: {r['status']} → {OUT}")
    print(f"Size: {os.path.getsize(OUT)} bytes")


if __name__ == "__main__":
    print("=" * 60)
    print("Jablonski Energy Diagram v3 — Anchors + Clamp + Validation")
    print("=" * 60)
    demo()
    print("=" * 60)
    print(f"Open: {OUT}")
