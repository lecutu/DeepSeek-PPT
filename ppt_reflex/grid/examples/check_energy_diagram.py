"""
grid/examples/check_energy_diagram.py — Energy-level diagram approximation.

Tests what the grid CAN and CAN'T do for scientific energy diagrams:
  CAN:  horizontal energy bands (TEXTBOX), labels, collision detection
  EDGE: transitions via Unicode arrows (barely passable for teaching slides)
  CAN'T: proper lines, arrows, curves, electron spin markers
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from grid import GridCanvas, GridConfig, ContentType
from grid.types import ElementPayload

OUT = os.path.join(tempfile.gettempdir(), "energy_diagram_demo.pptx")


def band(canvas, name, cells, text, fill_color, fs=12):
    """Energy level as a colored horizontal band."""
    p = ElementPayload(
        text=text, font_size=fs, font_color=(0xFF,0xFF,0xFF), font_bold=True,
        font_name="Microsoft YaHei", alignment="LEFT", fill_color=fill_color)
    return canvas.try_place(name, ContentType.TEXTBOX, cells, payload=p)


def arrow(canvas, name, cells, symbol, color):
    """Transition arrow (crude Unicode)."""
    p = ElementPayload(text=symbol, font_size=22, font_color=color,
                       font_name="Arial", alignment="CENTER")
    return canvas.try_place(name, ContentType.TEXT, cells, payload=p)


def note(canvas, name, cells, text, fs=9):
    p = ElementPayload(text=text, font_size=fs, font_color=(0x55,0x55,0x55),
                       font_name="Microsoft YaHei", alignment="CENTER")
    return canvas.try_place(name, ContentType.ANNOTATION, cells, payload=p)


def demo():
    cfg = GridConfig()
    c = GridCanvas(cfg)

    c.try_place("title", ContentType.TEXT, ["B1","C1","D1","E1","F1","G1"],
        payload=ElementPayload(
            text="Jablonski Energy Diagram", font_size=24,
            font_color=(0x1B,0x3A,0x5C), font_bold=True,
            font_name="Microsoft YaHei", alignment="CENTER"))

    # ═══ Energy levels = three horizontal bands ═══
    # S₀ — ground state (bottom, strongest color)
    band(c, "S0", ["A8","B8","C8","D8","E8","F8","G8"],   "S₀  Ground State",
         (0x1B,0x3A,0x5C))

    # S₁ — excited singlet (middle)
    band(c, "S1", ["A5","B5","C5","D5","E5","F5","G5"],   "S₁  Excited Singlet",
         (0xC0,0x39,0x2B))

    # T₁ — triplet (between S₀ and S₁)
    band(c, "T1", ["A6","B6","C6","D6","E6","F6","G6"],   "T₁  Triplet",
         (0xE6,0x7E,0x22))

    # ═══ Transitions ═══
    # Absorption: S₀ → S₁ (up arrow, blue)
    arrow(c, "abs", ["B6"], "⇡", (0x29,0x80,0xB9))
    note(c, "abs_label", ["B7"], "Absorption\nhν")

    # Fluorescence: S₁ → S₀ (down arrow, green)
    arrow(c, "fluor", ["C6"], "⇣", (0x27,0xAE,0x60))
    note(c, "fluor_label", ["C7"], "Fluorescence\n~10⁻⁹ s")

    # ISC: S₁ → T₁ (curved arrow, orange) — can't do curves, use diagonal symbol
    arrow(c, "isc", ["H6"], "↘", (0xE6,0x7E,0x22))
    note(c, "isc_label", ["H7"], "ISC")

    # Phosphorescence: T₁ → S₀ (down arrow, red)
    arrow(c, "phos", ["F6"], "⇣", (0x9B,0x59,0xB6))
    note(c, "phos_label", ["F7"], "Phospho-\nrescence\n~10⁻³ s")

    # ═══ Collision check ═══
    bad = c.try_place("bad_overlap", ContentType.TEXT, ["C5"],
        payload=ElementPayload(text="!", font_size=14))
    print(f"Overlap on S1 band: [{bad.verdict.value.upper()}]")
    if bad.blocked:
        print(f"  {bad.conflicts[0].detail}")

    c.checkpoint()
    r = c.commit(OUT)
    print(f"Commit: {r['status']} → {OUT}")
    print(f"Size: {os.path.getsize(OUT)} bytes")


if __name__ == "__main__":
    print("=" * 60)
    print("Energy Diagram Test — Jablonski")
    print("=" * 60)
    demo()
    print("=" * 60)
    print(f"Open: {OUT}")
