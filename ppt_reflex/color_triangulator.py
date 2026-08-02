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

from ppt_reflex.grid.color_utils import (hex_to_rgb, relative_luminance,
                                         luminance_L, contrast_ratio, rgb_to_hex)


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
        self.bg_L = luminance_L(self.bg)
        self.is_dark_bg = self.bg_L < 30


def roles_from_template(t) -> ColorRoles:
    """Derive ColorRoles from a TemplateProfile + applied style overrides."""
    return ColorRoles(
        bg=hex_to_rgb(t.bg_hex),
        text=hex_to_rgb(t.text_hex),
        title=hex_to_rgb(t.title_hex),
        accent=hex_to_rgb(t.accent_hex),
        accent2=hex_to_rgb(t.accent2_hex) if t.accent2_hex else hex_to_rgb(t.accent_hex),
        surface=hex_to_rgb(t.dim_hex) if t.dim_hex and t.dim_hex != t.gray_hex else hex_to_rgb(t.bg_hex),
        dim=hex_to_rgb(t.gray_hex) if t.gray_hex else hex_to_rgb(t.text_hex),
    )


# ── Edge ①: bg ↔ text ──


def _edge_bg_text(elem_font_rgb: tuple, roles: ColorRoles, font_size: float,
                   is_bold: bool, elem_id: str) -> list[TriIssue]:
    """Every element's font must contrast against the slide background."""
    is_large = font_size >= 18 or (font_size >= 14 and is_bold)
    req = 3.0 if is_large else 4.5
    cr = contrast_ratio(elem_font_rgb, roles.bg)

    if cr >= req:
        return []

    return [TriIssue(
        edge="bg↔text", level="error", elem_id=elem_id,
        fill_hex="", font_hex=_fmt_hex(elem_font_rgb),
        ratio=round(cr, 1), required=req,
        message=(
            f"Font #{_fmt_hex(elem_font_rgb)} L*={luminance_L(elem_font_rgb):.0f} "
            f"vs bg #{_fmt_hex(roles.bg)} L*={roles.bg_L:.0f} → "
            f"contrast {cr:.1f}:1 < {req}:1 ({'large' if is_large else 'normal'} text)"
        ),
    )]


# ── Edge ②: bg ↔ fill ──


def _is_surface_family(fill_rgb: tuple, roles: ColorRoles) -> bool:
    """Layered surface panel: a fill that sits near the canvas on the luminance
    axis (closer to bg than to text) is a deliberate card tone, not a readability
    failure. Bright accents (far from bg) are still checked by Edge ②.
    """
    if fill_rgb == roles.bg or fill_rgb == roles.surface:
        return True
    l_fill = luminance_L(fill_rgb)
    l_bg = roles.bg_L
    l_text = luminance_L(roles.text)
    if not (l_bg < l_fill < l_text) and not (l_text < l_fill < l_bg):
        return False  # not between bg and text on luminance
    return abs(l_fill - l_bg) < abs(l_text - l_fill)


def _edge_bg_fill(fill_rgb: tuple, roles: ColorRoles, elem_id: str) -> list[TriIssue]:
    """Card fills must contrast against the slide background.
    Only checked when fill is EXPLICIT (not None and not equal to bg)."""
    if fill_rgb == roles.bg:
        return []  # transparent / inherit — effectively no fill
    if _is_surface_family(fill_rgb, roles):
        return []  # layered dark card — intentional, not a contrast failure

    req = 3.0  # cards are large elements, 3:1 is sufficient
    cr = contrast_ratio(fill_rgb, roles.bg)

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
    cr = contrast_ratio(font_rgb, effective_fill)

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
    return rgb_to_hex(rgb)


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

        if fill_rgb is None:
            # 无显式填充 → 文字实际背景就是幻灯片 bg。
            # Edge① 与 Edge③ 此时等价（effective_fill = bg），只跑 Edge①，避免同一问题双报。
            issues.extend(_edge_bg_text(font_rgb, roles, fs, bold, eid))
        else:
            # 有显式填充 → 文字的实际背景是它的 fill，不是幻灯片 bg。
            # （2026-08 审查：旧版无条件跑 Edge①，深色卡片+白字被误报
            #  "白字 vs 白底 1.0:1" error —— 卡片才是文字的真实背景。）
            issues.extend(_edge_bg_fill(fill_rgb, roles, eid))
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
