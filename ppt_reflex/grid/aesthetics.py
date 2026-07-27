"""
grid/aesthetics.py — Aesthetics rule engine (ugliness floor)
Checks quantifiable violations only, never judges aesthetic quality.
All rules: quantifiable / detectable / grounded (WCAG 2.1 / typography).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from math import sqrt
from .types import Verdict, ContentType
from .text_metrics import estimate_text_size

# ═══════════════════════════ COLOR ═══════════════════════════
def hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

def relative_luminance(rgb: tuple) -> float:
    def f(c): s = c/255.0; return s/12.92 if s <= 0.04045 else ((s+0.055)/1.055)**2.4
    return 0.2126*f(rgb[0]) + 0.7152*f(rgb[1]) + 0.0722*f(rgb[2])

def contrast_ratio(c1, c2):
    L1, L2 = relative_luminance(c1), relative_luminance(c2)
    L, D = max(L1, L2), min(L1, L2)
    return (L+0.05)/(D+0.05)

def luminance_L(c):
    r, g, b = c[0]/255, c[1]/255, c[2]/255
    r = r/12.92 if r <= 0.04045 else ((r+0.055)/1.055)**2.4
    g = g/12.92 if g <= 0.04045 else ((g+0.055)/1.055)**2.4
    b = b/12.92 if b <= 0.04045 else ((b+0.055)/1.055)**2.4
    Y = 0.2126*r + 0.7152*g + 0.0722*b
    return 116*(Y**(1/3))-16 if Y > 0.008856 else 903.3*Y

def is_large_text(pt, bold): return pt >= 18 or (pt >= 14 and bold)

def _unique_hues(colors):
    if len(colors) <= 1: return colors
    rgbs = []
    for c in colors:
        try: rgbs.append(hex_to_rgb(c))
        except: pass
    if not rgbs: return colors
    buckets = set()
    for r, g, b in rgbs:
        mx, mn = max(r, g, b), min(r, g, b)
        buckets.add(0 if mx == 0 else round(((mx-mn)/mx)*12))
    return {str(b) for b in buckets}

# ═══════════════════════ TYPES ══════════════════════════════
@dataclass
class AestheticViolation:
    rule_id: str; category: str; priority: str
    verdict: Verdict; element_id: str = ""
    message: str = ""; metrics: dict = field(default_factory=dict)

@dataclass
class ElemStyle:
    id: str; content_type: ContentType = ContentType.UNKNOWN
    font_size: float = 12.0; font_bold: bool = False
    font_color: str = "000000"; fill_color: str = "FFFFFF"
    line_spacing: float = 1.2; word_wrap: bool = True
    auto_size: str = "NONE"
    text: str = ""; x: float = 0; y: float = 0; w: float = 0; h: float = 0
    z_order: int = 0; locked: bool = False

# ═══════════════════════ ENGINE ═════════════════════════════
class AestheticsEngine:
    def check(self, elements, ctx=None, timing="audit"):
        ctx = ctx or {}
        v = []
        for e in elements:
            v += self._color(e)
            v += self._style(e, elements)
            v += self._font(e)
            v += self._overflow(e)
        v += self._spacing(elements)
        v += self._density(elements)
        v += self._align(elements)
        if timing == "try_place": v = [x for x in v if x.priority == "P0"]
        elif timing == "commit": v = [x for x in v if x.priority in ("P0","P1")]
        return v

    def _violation(self, rid, cat, pri, ver, eid="", msg="", m=None):
        return AestheticViolation(rid, cat, pri, ver, eid, msg, m or {})

    # ── Contrast / invisible text / dark-on-light ──
    def _color(self, e):
        v = []
        # Skip color check for text-less elements (pure shapes like divider/filler only have fill)
        if not e.text.strip():
            return v
        try: fc, fillc = hex_to_rgb(e.font_color), hex_to_rgb(e.fill_color)
        except: return v
        ct = contrast_ratio(fc, fillc)
        mn = 3.0 if is_large_text(e.font_size, e.font_bold) else 4.5
        if ct < mn:
            lbl = "large_text" if is_large_text(e.font_size, e.font_bold) else "normal_text"
            v.append(self._violation("color_contrast", "color", "P0", Verdict.WARN, e.id,
                f"Contrast {ct:.1f}:1 < {mn}:1 ({lbl})", {"ratio": round(ct,1), "req": mn}))
        if e.font_color == e.fill_color and e.font_color not in ("FFFFFF","000000","","transparent","none"):
            v.append(self._violation("invisible_text", "color", "P0", Verdict.BLOCK, e.id,
                f"Text=fill color ({e.font_color})"))
        Lb = luminance_L(fillc); Lt = luminance_L(fc)
        # CIE L*: 0=black, 100=white
        if Lb < 40 and Lt < 40:
            v.append(self._violation("dark_bg_dark_text", "color", "P0", Verdict.WARN, e.id,
                f"Dark bg (L*={Lb:.0f}) + dark text (L*={Lt:.0f})", {"bg_L": round(Lb), "tx_L": round(Lt)}))
        if Lb > 85 and Lt > 85:
            v.append(self._violation("light_bg_light_text", "color", "P0", Verdict.WARN, e.id,
                f"Light bg (L*={Lb:.0f}) + light text (L*={Lt:.0f})", {"bg_L": round(Lb), "tx_L": round(Lt)}))
        return v

    # ── Background / font color / palette size ──
    def _style(self, e, all_elements):
        v = []
        try:
            fillc = hex_to_rgb(e.fill_color)
            Lb = luminance_L(fillc)
            # P1 WARN: extremely dark/pure bg affects readability, but doesn't block — truly invisible handled by _color() BLOCK
            if Lb < 8 and e.content_type in (ContentType.BACKGROUND, ContentType.TEXTBOX):
                v.append(self._violation("no_black_bg", "style", "P0", Verdict.WARN, e.id,
                    f"Near-black bg (L*={Lb:.0f})", {"L": round(Lb)}))
            if Lb > 92 and e.content_type in (ContentType.BACKGROUND, ContentType.TEXTBOX):
                v.append(self._violation("no_pure_white_bg", "style", "P1", Verdict.WARN, e.id,
                    f"Near-pure-white bg (L*={Lb:.0f})", {"L": round(Lb)}))
        except: pass
        # Font color check only when element has text
        if e.text.strip():
            try:
                Lt2 = luminance_L(hex_to_rgb(e.font_color))
                if Lt2 < 5:
                    v.append(self._violation("near_black_text", "style", "P1", Verdict.WARN, e.id,
                        f"Near-black text (L*={Lt2:.0f})", {"L": round(Lt2)}))
                if Lt2 > 98:
                    v.append(self._violation("pure_white_text", "style", "P1", Verdict.WARN, e.id,
                        f"Pure-white text (L*={Lt2:.0f})", {"L": round(Lt2)}))
            except: pass
        if all_elements:
            colors = set()
            for el in all_elements:
                try:
                    c = el.fill_color.lower()
                    if c not in ("ffffff","000000","","transparent","none"): colors.add(el.fill_color.upper())
                except: pass
            uq = _unique_hues(colors)
            if len(uq) > 5:
                v.append(self._violation("max_colors", "style", "P2", Verdict.WARN, "",
                    f"Single page {len(uq)} hues > 5", {"count": len(uq)}))
        return v

    # ── Font size ──
    def _font(self, e):
        v = []
        if e.content_type in (ContentType.BACKGROUND, ContentType.IMAGE, ContentType.SHAPE): return v
        if e.font_size < 10:
            v.append(self._violation("font_abs_min", "font", "P0", Verdict.BLOCK, e.id,
                f"Font size {e.font_size}pt < 10pt", {"size": e.font_size}))
        if 10 <= e.font_size < 14 and e.content_type != ContentType.FOOTER:
            v.append(self._violation("font_rec_min", "font", "P1", Verdict.WARN, e.id,
                f"Font size {e.font_size}pt < 14pt recommended", {"size": e.font_size}))
        if e.auto_size == "TEXT_TO_FIT_SHAPE":
            ox, oy, rw, rh = estimate_text_size(e.text, e.font_size, e.line_spacing, e.w, e.h, e.word_wrap)
            if (ox > 2 or oy > 2) and e.h > 0:
                fitted = e.font_size * min(e.w/max(rw,0.1), e.h/max(rh,0.1))
                if fitted < 10:
                    v.append(self._violation("autofit_tiny", "font", "P0", Verdict.BLOCK, e.id,
                        f"Auto-fitted {fitted:.0f}pt < 10pt", {"fitted": round(fitted,1)}))
        return v

    # ── Text overflow ──
    def _overflow(self, e):
        v = []
        if e.content_type not in (ContentType.TEXT, ContentType.TEXTBOX): return v
        if not e.text.strip(): return v
        ox, oy, rw, rh = estimate_text_size(e.text, e.font_size, e.line_spacing, e.w, e.h, e.word_wrap)
        if ox <= 2 and oy <= 2: return v
        if e.auto_size == "NONE":
            if not e.word_wrap and ox > 2:
                v.append(self._violation("overflow_h", "overflow", "P0", Verdict.BLOCK, e.id,
                    f"Horizontal overflow {ox:.0f}pt (no wrap)", {"ox": round(ox,1)}))
            if oy > 2:
                v.append(self._violation("overflow_v", "overflow", "P0", Verdict.WARN, e.id,
                    f"Vertical overflow {oy:.0f}pt", {"oy": round(oy,1)}))
            fixes = []
            fitted = e.font_size * min(e.w/max(rw,0.1), e.h/max(rh,0.1))
            if fitted >= 10: fixes.append(f"Enable auto-shrink -> font ~{fitted:.0f}pt")
            if not e.word_wrap and ox > 2: fixes.append("Enable word wrap")
            fixes.append("Expand box to fit content")
            fixes.append("Trim text or split to next slide")
            if v: v[-1].metrics["fix_suggestions"] = fixes
        elif e.auto_size == "SHAPE_TO_FIT_TEXT":
            v.append(self._violation("autofit_expand", "overflow", "P1", Verdict.WARN, e.id,
                f"Box will expand {ox:.0f}x{oy:.0f}pt", {"ox": round(ox,1), "oy": round(oy,1)}))
        return v

    # ── Spacing ──
    def _spacing(self, elements):
        v = []
        texts = [e for e in elements if e.content_type in (ContentType.TEXT, ContentType.TEXTBOX)]
        if len(texts) < 2: return v
        for e in elements:
            if e.locked: continue
            me = min(e.x, e.y)
            if 0 < me < 24:
                v.append(self._violation("edge_margin", "spacing", "P1", Verdict.WARN, e.id,
                    f"Edge margin {me:.0f}pt < 24pt", {"dist": round(me,1)}))
        for i in range(len(texts)-1):
            gap = texts[i+1].y - (texts[i].y + texts[i].h)
            if 0 < gap < 8:
                v.append(self._violation("tight_gap", "spacing", "P1", Verdict.WARN, texts[i].id,
                    f"Gap {gap:.0f}pt < 8pt", {"gap": round(gap,1)}))
        return v

    # ── Density ──
    def _density(self, elements):
        v = []
        occupied = sum(e.w*e.h for e in elements if not e.locked)
        density = occupied/(960*540)
        if density > 0.70:
            v.append(self._violation("density", "density", "P1", Verdict.WARN, "",
                f"Density {density*100:.0f}% > 70%", {"pct": round(density*100,1)}))
        if len(elements) > 12:
            v.append(self._violation("too_many", "density", "P1", Verdict.WARN, "",
                f"{len(elements)} elements > 12", {"count": len(elements)}))
        chars = sum(len(e.text) for e in elements)
        if chars > 300:
            v.append(self._violation("too_much_text", "density", "P1", Verdict.WARN, "",
                f"{chars} chars > 300", {"chars": chars}))
        return v

    # ── Alignment ──
    def _align(self, elements):
        v = []
        non_locked = [e for e in elements if not e.locked]
        if len(non_locked) < 2: return v
        cell = 60.0
        for e in non_locked:
            off = min(e.x % cell, cell - (e.x % cell), e.y % cell, cell - (e.y % cell))
            if off < 4: continue
            v.append(self._violation("grid_offset", "alignment", "P2", Verdict.WARN, e.id,
                f"Grid offset {off:.0f}pt", {"offset": round(off,1)}))
        return v
