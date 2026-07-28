from ppt_reflex.grid.templates import _TEMPLATE_DATA, get_template
from ppt_reflex.grid.aesthetics import hex_to_rgb, contrast_ratio, luminance_L

print(f"{len(_TEMPLATE_DATA)} templates loaded\n")

for tid in sorted(_TEMPLATE_DATA):
    t = get_template(tid)
    cr = contrast_ratio(hex_to_rgb(t.text_hex), hex_to_rgb(t.bg_hex))
    bgL = luminance_L(hex_to_rgb(t.bg_hex))
    txtL = luminance_L(hex_to_rgb(t.text_hex))
    ok = cr >= 4.5
    darkOK = not (bgL < 50 and txtL < 128)
    ltOK = not (bgL > 85 and txtL > 128)
    colors = set()
    for c in [t.bg_hex, t.text_hex, t.title_hex, t.accent_hex, t.accent2_hex]:
        if c:
            colors.add(c.upper())
    flag = "+" if ok else "x"
    print(f"  {tid:12s} CR={cr:.1f}:1 {flag}  darkOK={darkOK}  ltOK={ltOK}  colors={len(colors)}")

print("\ndone")
