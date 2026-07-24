"""
grid/examples/check_franck_condon.py — Franck-Condon energy diagram.

Shows:
  3 electronic states (S₀, S₁, T₁) with 4 vibrational sub-levels each
  Vertical absorption (FC principle) + vibrational relaxation cascades
  Fluorescence, ISC, phosphorescence with proper anchor arrows
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from grid import GridCanvas, GridConfig, ContentType
from grid.types import ElementPayload

OUT = os.path.join(tempfile.gettempdir(), "franck_condon_diagram.pptx")


def cl(ci: int) -> str:
    """0-indexed → Excel column letter."""
    if ci < 26:
        return chr(ord('A') + ci)
    return chr(ord('A') + ci // 26 - 1) + chr(ord('A') + ci % 26)


def cr(r0: int, c0: int, r1: int, c1: int) -> list[str]:
    """Rectangle of fine cells r0..r1, c0..c1."""
    return [f"{cl(c)}{r}" for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]


def demo():
    cfg = GridConfig()
    c = GridCanvas(cfg)

    # ═══════════════════════════════════════════════
    # Layout (fine-grid rows):
    #   1-2:   title
    #   3:     header labels (S₁, T₁, S₀)
    #   4-7:   S₁ vib levels v'=0..3  (thin bars, red)
    #   8:     gap
    #   9-12:  T₁ vib levels v'=0..3  (thin bars, orange)
    #   13:    gap
    #   14-17: S₀ vib levels v=0..3   (thin bars, blue)
    # ═══════════════════════════════════════════════

    # ── Title ──
    c.try_place("title", ContentType.TEXT, cr(1, 3, 2, 18),
        payload=ElementPayload(
            text="Franck–Condon Energy Diagram", font_size=24,
            font_color=(0x1B,0x3A,0x5C), font_bold=True,
            font_name="Microsoft YaHei", alignment="CENTER"))

    # ── Energy axis ──
    c.try_place("axis", ContentType.ANNOTATION, ["A5", "A6"],
        payload=ElementPayload(text="E\n↑", font_size=10,
            font_color=(0x1B,0x3A,0x5C),
            font_name="Microsoft YaHei", alignment="CENTER"))

    # ── State labels ──
    labels = [
        (4,  "S<sub>1</sub>  Singlet Excited", (0xC0,0x39,0x2B)),
        (9,  "T<sub>1</sub>  Triplet",          (0xE6,0x7E,0x22)),
        (14, "S<sub>0</sub>  Ground State",     (0x1B,0x3A,0x5C)),
    ]
    for row, text, color in labels:
        c.try_place(f"lbl_{row}", ContentType.ANNOTATION, cr(row, 1, row, 2),
            payload=ElementPayload(text="", font_size=9,
                font_color=color, font_name="Microsoft YaHei",
                alignment="CENTER"))
        # State name as textbox banner
        c.try_place(f"state_{row}", ContentType.TEXTBOX, cr(row, 3, row, 4),
            payload=ElementPayload(text="", font_size=10,
                font_color=(0xFF,0xFF,0xFF), font_bold=True,
                font_name="Microsoft YaHei", alignment="CENTER",
                fill_color=color, shape_id="rounded_rectangle"))

    # ── Vibrational levels — thin rounded rectangles, 1 cell high ──
    # Each state: 4 levels, gradually lighter (higher v)
    reds   = [(0xC0,0x39,0x2B), (0xD4,0x5D,0x4F), (0xE8,0x81,0x73), (0xF5,0xB7,0xB1)]
    oranges = [(0xE6,0x7E,0x22), (0xEB,0x98,0x45), (0xF0,0xB2,0x68), (0xF8,0xD7,0x98)]
    blues  = [(0x1B,0x3A,0x5C), (0x2E,0x5C,0x8A), (0x41,0x7E,0xB8), (0x7F,0xAE,0xDC)]

    vib_levels = [
        # (state, start_row, colors, vib_labels)
        ("S1",  4, reds,    ["v'=0", "v'=1", "v'=2", "v'=3"]),
        ("T1",  9, oranges, ["v'=0", "v'=1", "v'=2", "v'=3"]),
        ("S0", 14, blues,   ["v=0",  "v=1",  "v=2",  "v=3"]),
    ]

    for state, srow, colors, vlabels in vib_levels:
        for i, (color, vlab) in enumerate(zip(colors, vlabels)):
            row = srow + i
            c.try_place(f"vib_{state}_{i}", ContentType.TEXTBOX,
                cr(row, 6, row, 18),
                payload=ElementPayload(
                    text=vlab, font_size=9, font_color=(0xFF,0xFF,0xFF),
                    font_bold=True, font_name="Microsoft YaHei",
                    alignment="LEFT", fill_color=color,
                    shape_id="rounded_rectangle"))

    # ── State label banners (overlay on left side of first vib level) ──
    # Redo with actual text — overlay TEXT on the first vib bar
    state_names = {
        "S1": (4, "S₁  Excited Singlet"),
        "T1": (9, "T₁  Triplet"),
        "S0": (14, "S₀  Ground"),
    }
    for sid, (row, txt) in state_names.items():
        c.try_place(f"name_{sid}", ContentType.TEXT, cr(row, 6, row, 7),
            payload=ElementPayload(text=txt, font_size=10,
                font_color=(0xFF,0xFF,0xFF), font_bold=True,
                font_name="Microsoft YaHei", alignment="LEFT"))

    # ═══════════════════════════════════════════════
    # TRANSITIONS
    # ═══════════════════════════════════════════════

    # --- Absorption: S₀ v=0 → S₁ v'=2 (Franck-Condon maximum) ---
    # S₀ v=0 is at row 14, S₁ v'=2 is at row 6
    c.try_place("c_abs", ContentType.CONNECTOR, ["F14"],
        payload=ElementPayload(
            connector_from="F14", connector_to="F6",
            connector_anchor_from="top", connector_anchor_to="bottom",
            line_color=(0x29,0x80,0xB9), line_width_pt=2.5))

    c.try_place("l_abs", ContentType.ANNOTATION, cr(9, 3, 9, 5),
        payload=ElementPayload(text="Absorption\n(S₀ v=0 → S₁ v'=2)", font_size=8,
            font_color=(0x29,0x80,0xB9), font_name="Microsoft YaHei",
            alignment="CENTER"))

    # --- Vibrational relaxation: S₁ v'=3→2, v'=2→1, v'=1→0 ---
    vr_paths = [
        ("vr1", 7, "G", "Vibr.\nrelax"),
        ("vr2", 6, "I", ""),
        ("vr3", 5, "K", ""),
    ]
    for vid, row, col_letter, txt in vr_paths:
        cell1 = f"{col_letter}{row}"
        cell2 = f"{col_letter}{row+1}"
        c.try_place(f"c_{vid}", ContentType.CONNECTOR, [cell1],
            payload=ElementPayload(
                connector_from=cell1, connector_to=cell2,
                connector_anchor_from="top", connector_anchor_to="bottom",
                line_color=(0xAA,0xAA,0xAA), line_width_pt=1.5))
        if txt:
            c.try_place(f"l_{vid}", ContentType.ANNOTATION, cr(row, 0, row+1, 0),
                payload=ElementPayload(text="", font_size=7,
                    font_color=(0xAA,0xAA,0xAA),
                    font_name="Microsoft YaHei", alignment="CENTER"))

    # --- VR label ---
    c.try_place("vr_label", ContentType.ANNOTATION, cr(4, 0, 7, 0),
        payload=ElementPayload(text="VR\n↓", font_size=7,
            font_color=(0xAA,0xAA,0xAA),
            font_name="Microsoft YaHei", alignment="CENTER"))

    # --- Fluorescence: S₁ v'=0 → S₀ v=3 ---
    c.try_place("c_fluor", ContentType.CONNECTOR, ["L4"],
        payload=ElementPayload(
            connector_from="L4", connector_to="L17",
            connector_anchor_from="bottom", connector_anchor_to="top",
            line_color=(0x27,0xAE,0x60), line_width_pt=2.5))

    c.try_place("l_fluor", ContentType.ANNOTATION, cr(9, 10, 10, 14),
        payload=ElementPayload(
            text="Fluorescence\n(S₁ v'=0 → S₀ v=3)", font_size=8,
            font_color=(0x27,0xAE,0x60), font_name="Microsoft YaHei",
            alignment="CENTER"))

    # --- ISC: S₁ v'=0 → T₁ v'=2 ---
    c.try_place("c_isc", ContentType.CONNECTOR, ["R4"],
        payload=ElementPayload(
            connector_from="R4", connector_to="O11",
            connector_anchor_from="right", connector_anchor_to="top",
            line_color=(0xE6,0x7E,0x22), line_width_pt=2.0))

    c.try_place("l_isc", ContentType.ANNOTATION, ["O2", "O3"],
        payload=ElementPayload(text="ISC", font_size=9,
            font_color=(0xE6,0x7E,0x22), font_name="Microsoft YaHei",
            alignment="CENTER"))

    # --- T₁ vibrational relaxation ---
    for row in [10, 11, 12]:
        col = "J"
        c.try_place(f"c_vrt_{row}", ContentType.CONNECTOR, [f"{col}{row}"],
            payload=ElementPayload(
                connector_from=f"{col}{row}", connector_to=f"{col}{row+1}",
                connector_anchor_from="bottom", connector_anchor_to="top",
                line_color=(0xCC,0xCC,0xCC), line_width_pt=1.2))

    # --- Phosphorescence: T₁ v'=0 → S₀ v=2 ---
    c.try_place("c_phos", ContentType.CONNECTOR, ["N9"],
        payload=ElementPayload(
            connector_from="N9", connector_to="N16",
            connector_anchor_from="bottom", connector_anchor_to="top",
            line_color=(0x9B,0x59,0xB6), line_width_pt=2.5))

    c.try_place("l_phos", ContentType.ANNOTATION, cr(12, 13, 12, 15),
        payload=ElementPayload(
            text="Phosphorescence\n(T₁ v'=0 → S₀ v=2)", font_size=8,
            font_color=(0x9B,0x59,0xB6), font_name="Microsoft YaHei",
            alignment="CENTER"))

    # ═══════════════════════════════════════════════
    # FC Principle annotation
    # ═══════════════════════════════════════════════
    c.try_place("fc_note", ContentType.ANNOTATION, ["G12", "H12", "G13", "H13"],
        payload=ElementPayload(
            text="← Vertical transitions\n  (Franck–Condon principle)", font_size=8,
            font_color=(0x55,0x55,0x55), font_name="Microsoft YaHei",
            alignment="LEFT"))

    # ═══════════════════════════════════════════════
    # Pre-commit validation
    # ═══════════════════════════════════════════════
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
    print("Franck–Condon Diagram — 3 States × 4 Vib Levels")
    print("=" * 60)
    demo()
    print("=" * 60)
    print(f"Open: {OUT}")
