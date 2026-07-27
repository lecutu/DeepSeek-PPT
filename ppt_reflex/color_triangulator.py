"""
ppt_reflex/color_triangulator.py — Text-Fill-Background color triangle constraint system.

Three edges, all derived from the template semantic contract:
  Edge ①  bg ↔ text:  global floor — every text element on the slide must clear
  Edge ②  bg ↔ fill:  surface cards must contrast against the slide canvas
  Edge ③  fill ↔ text: element self-contrast — text over its own fill must be readable

The triangulator is stateless — call .check(slide, template) per slide and get
back a flat list of issues. No side effects, no mutable state.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from math import sqrt
from typing import Callable

# ── WCAG luminance (same formula as aesthetics.py, standalone copy to avoid circular import) ──


def _luminance(rgb: tuple) -> float:
    def f(c):
        s = c / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2])


def _Lstar(rgb: tuple) -> float:
    r, g, b = rgb[0] / 255, rgb[1] / 255, rgb[2] / 255
    r = r / 12.92 if r <= 0.04045 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.04045 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.04045 else ((b + 0.055) / 1.055) ** 2.4
    Y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return 116 * (Y ** (1 / 3)) - 16 if Y > 0.008856 else 903.3 * Y


def _contrast_ratio(a: tuple, b: tuple) -> float:
    L1, L2 = _luminance(a), _luminance(b)
    L, D = max(L1, L2), min(L1, L2)
    return (L + 0.05) / (D + 0.05)


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


@dataclass
class TriIssue:
    """Single color constraint violation."""
    edge: str          # "bg↔text" | "bg↔fill" | "fill↔text"
    level: str         # "error" | "warning" | "info"
    elem_id: str
    fill_hex: str      # actual fill color (hex, no #)
    font_hex: str      # actual font color (hex, no #)
    ratio: float       # contrast ratio
    required: float    # minimum required ratio
    message: str


# ── Role-aware color contract ──


@dataclass
class ColorRoles:
    """Parsed color role table from template + style preset."""
    bg: tuple            # slide background RGB
    text: tuple          # body text default RGB
    title: tuple         # heading text default RGB
    accent: tuple        # decoration / highlight
    accent2: tuple       # warning / emphasis — NEVER self-text
    surface: tuple       # card / box background on dark themes
    dim: tuple           # faintest text

    bg_L: float = 0.0
    is_dark_bg: bool = False

    def __post_init__(self):
        self.bg_L = _Lstar(self.bg)
        self.is_dark_bg = self.bg_L < 30


def roles_from_template(t) -> ColorRoles:
    """Derive ColorRoles from a TemplateProfile + applied style overrides."""
    return ColorRoles(
        bg=_hex_to_rgb(t.bg_hex),
        text=_hex_to_rgb(t.text_hex),
        title=_hex_to_rgb(t.title_hex),
        accent=_hex_to_rgb(t.accent_hex),
        accent2=_hex_to_rgb(t.accent2_hex) if t.accent2_hex else _hex_to_rgb(t.accent_hex),
        surface=_hex_to_rgb(t.dim_hex) if t.dim_hex and t.dim_hex != t.gray_hex else _hex_to_rgb(t.bg_hex),
        dim=_hex_to_rgb(t.gray_hex) if t.gray_hex else _hex_to_rgb(t.text_hex),
    )


# ── Edge ①: bg ↔ text ──


def _edge_bg_text(elem_font_rgb: tuple, roles: ColorRoles, font_size: float,
                   is_bold: bool, elem_id: str) -> list[TriIssue]:
    """Every element's font must contrast against the slide background."""
    is_large = font_size >= 18 or (font_size >= 14 and is_bold)
    req = 3.0 if is_large else 4.5
    cr = _contrast_ratio(elem_font_rgb, roles.bg)

    if cr >= req:
        return []

    return [TriIssue(
        edge="bg↔text", level="error", elem_id=elem_id,
        fill_hex="", font_hex=_fmt_hex(elem_font_rgb),
        ratio=round(cr, 1), required=req,
        message=(
            f"Font #{_fmt_hex(elem_font_rgb)} L*={_Lstar(elem_font_rgb):.0f} "
            f"vs bg #{_fmt_hex(roles.bg)} L*={roles.bg_L:.0f} → "
            f"contrast {cr:.1f}:1 < {req}:1 ({'large' if is_large else 'normal'} text)"
        ),
    )]


# ── Edge ②: bg ↔ fill ──


def _edge_bg_fill(fill_rgb: tuple, roles: ColorRoles, elem_id: str) -> list[TriIssue]:
    """Card fills must contrast against the slide background.
    Only checked when fill is EXPLICIT (not None and not equal to bg)."""
    if fill_rgb == roles.bg:
        return []  # transparent / inherit — effectively no fill

    req = 3.0  # cards are large elements, 3:1 is sufficient
    cr = _contrast_ratio(fill_rgb, roles.bg)

    if cr >= req:
        return []

    return [TriIssue(
        edge="bg↔fill", level="warning", elem_id=elem_id,
        fill_hex=_fmt_hex(fill_rgb), font_hex="",
        ratio=round(cr, 1), required=req,
        message=(
            f"Fill #{_fmt_hex(fill_rgb)} vs bg #{_fmt_hex(roles.bg)} → "
            f"contrast {cr:.1f}:1 < {req}:1 — card may blend into background"
        ),
    )]


# ── Edge ③: fill ↔ text ──


def _edge_fill_text(fill_rgb: tuple | None, font_rgb: tuple, roles: ColorRoles,
                    font_size: float, is_bold: bool, elem_id: str) -> list[TriIssue]:
    """Text must contrast against its OWN fill. If no fill → effective fill is bg."""
    effective_fill = fill_rgb if fill_rgb is not None else roles.bg
    is_large = font_size >= 18 or (font_size >= 14 and is_bold)
    req = 3.0 if is_large else 4.5
    cr = _contrast_ratio(font_rgb, effective_fill)

    if cr >= req:
        return []

    # ── Role guard: accent2 IS warn — self-text → always block ──
    if effective_fill == roles.accent2 and font_rgb == roles.accent2:
        level = "error"
        extra = " — accent2=warn role forbids self-text"
    elif effective_fill == roles.accent and font_rgb == roles.accent:
        level = "warning"
        extra = " — accent self-text, ensure intent is decorative-only"
    else:
        level = "error"
        extra = ""

    return [TriIssue(
        edge="fill↔text", level=level, elem_id=elem_id,
        fill_hex=_fmt_hex(effective_fill),
        font_hex=_fmt_hex(font_rgb),
        ratio=round(cr, 1), required=req,
        message=(
            f"Font #{_fmt_hex(font_rgb)} vs fill #{_fmt_hex(effective_fill)} → "
            f"contrast {cr:.1f}:1 < {req}:1{extra}"
        ),
    )]


# ── Public API ──


def _fmt_hex(rgb: tuple) -> str:
    return f"{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def check_slide(elems: list[dict], template) -> list[TriIssue]:
    """Run all three edges on one slide's elements.

    Args:
        elems: list of {elem_id, font_size, font_bold, font_color_rgb, fill_color_rgb}
               fill_color_rgb may be None (transparent/inherit bg).
        template: TemplateProfile (with applied style overrides).

    Returns:
        Flat list of TriIssue sorted by severity (error → warning → info).
    """
    roles = roles_from_template(template)
    issues: list[TriIssue] = []

    for e in elems:
        eid = e["elem_id"]
        font_rgb = e["font_color_rgb"]
        fill_rgb = e.get("fill_color_rgb")  # None = transparent
        fs = e.get("font_size", 14)
        bold = e.get("font_bold", False)

        # Edge ① bg↔text
        issues.extend(_edge_bg_text(font_rgb, roles, fs, bold, eid))

        # Edge ② bg↔fill (only if explicit fill)
        if fill_rgb is not None:
            issues.extend(_edge_bg_fill(fill_rgb, roles, eid))

        # Edge ③ fill↔text
        issues.extend(_edge_fill_text(fill_rgb, font_rgb, roles, fs, bold, eid))

    issues.sort(key=lambda i: {"error": 0, "warning": 1, "info": 2}[i.level])
    return issues


def summary(issues: list[TriIssue]) -> dict:
    """Human-readable summary of a slide's color issues."""
    errs = [i for i in issues if i.level == "error"]
    warns = [i for i in issues if i.level == "warning"]
    return {
        "total": len(issues),
        "errors": len(errs),
        "warnings": len(warns),
        "errors_detail": [i.message for i in errs],
        "warnings_detail": [i.message for i in warns],
    }
