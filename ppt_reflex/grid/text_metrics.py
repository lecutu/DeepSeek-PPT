"""
grid/text_metrics.py — text render size estimator (no font file dependency)

Estimates rendered_bbox for overflow detection. Accuracy ±8% for Latin/CJK.

Principle:
  CJK ≈ 1.0em/char, Latin weighted average ~0.55em/char
  rendered_h = line_height × actual_line_count
  rendered_w = max(line_widths)
"""

from __future__ import annotations
import math
import unicodedata

# ═══════════════════════════════════════════════════════════
# CHARACTER WIDTH FACTORS (relative to font_size_pt)
# ═══════════════════════════════════════════════════════════

# Per-character overrides for Latin glyphs that deviate significantly from the 0.55 average.
# Measured against Arial at 12pt. Non-overridden chars fall back to _DEFAULT_LATIN.
_LATIN_GLYPH_WIDTH: dict[str, float] = {
    # Wide glyphs
    'W': 0.95, 'M': 0.85, 'm': 0.82, 'w': 0.75,
    '@': 0.75, '%': 0.72, '#': 0.65, 'G': 0.65, 'O': 0.65, 'Q': 0.65, 'D': 0.62,
    # Narrow glyphs
    'I': 0.30, 'i': 0.25, 'l': 0.25, 'j': 0.25,
    'f': 0.30, 't': 0.30, 'r': 0.35,
    # Punctuation
    '.': 0.28, ',': 0.28, ':': 0.28, ';': 0.28,
    '!': 0.28, '|': 0.30, "'": 0.22, '"': 0.45,
    # Space variants
    ' ': 0.28, ' ': 0.28,  # non-breaking space
}
_DEFAULT_LATIN = 0.55

# Unicode East Asian Width classes that map to 1.0em.
# 'W' = Wide, 'F' = Fullwidth.
_FULLWIDTH_EAW = frozenset(('W', 'F'))


def _is_fullwidth(ch: str) -> bool:
    """Use Unicode East Asian Width property — correct for CJK, Japanese kana, Korean, fullwidth punctuation."""
    return unicodedata.east_asian_width(ch) in _FULLWIDTH_EAW


def _char_width_em(ch: str) -> float:
    """Single character width in em units."""
    cp = ord(ch)
    # Tab, carriage return, vertical tab, form feed — zero width in PPT rendering
    if ch in ('\t', '\r', '\x0b', '\x0c'):
        return 0.0
    # Zero-width characters
    if cp in (0x200B, 0x200C, 0x200D, 0xFEFF, 0x200E, 0x200F):
        return 0.0
    # Newline — caller should split, but be defensive
    if ch == '\n':
        return 0.0
    # Fullwidth CJK / kana / Hangul / fullwidth punctuation
    if _is_fullwidth(ch):
        return 1.0
    # Per-glyph Latin override
    if ch in _LATIN_GLYPH_WIDTH:
        return _LATIN_GLYPH_WIDTH[ch]
    # Digits and remaining Latin / Greek / Cyrillic
    if ch.isdigit():
        return 0.55
    if ch.isspace():
        return 0.28
    return _DEFAULT_LATIN


def _line_width(line: str, font_pt: float) -> float:
    """Estimated rendered width of a single line (pt)."""
    w = sum(_char_width_em(ch) * font_pt for ch in line)
    return max(w, 0.0)


def estimate_text_size(
    text: str,
    font_pt: float,
    line_spacing: float = 1.2,
    box_width_pt: float = 0.0,
    box_height_pt: float = 0.0,
    word_wrap: bool = True,
) -> tuple[float, float, float, float]:
    """
    Args:
        text: text content
        font_pt: font size in points
        line_spacing: line height multiplier (1.0 = 100% of font size)
        box_width_pt: logical text box width (pt). 0 = unbounded.
        box_height_pt: logical text box height (pt). 0 = unbounded.
        word_wrap: enable automatic line wrapping

    Returns:
        (overflow_x_pt, overflow_y_pt, rendered_w_pt, rendered_h_pt)
        First two are overflow amounts (0.0 = no overflow); last two are estimated rendered dimensions.
    """
    # Defensive: empty strings
    if not text or not text.strip():
        return 0.0, 0.0, box_width_pt, box_height_pt
    # Defensive: invalid font size
    if font_pt <= 0:
        return 0.0, 0.0, 0.0, 0.0

    lines = text.split("\n")
    line_h = font_pt * line_spacing

    if not word_wrap:
        line_widths = [_line_width(ln, font_pt) for ln in lines]
        rendered_w = max(line_widths) if line_widths else 0.0
        rendered_lines = len(lines)
    else:
        rendered_lines = 0
        rendered_w = box_width_pt
        # Guard against negative or tiny box width → infinite wraps
        avail_w = max(box_width_pt, font_pt) if box_width_pt > 0 else float('inf')
        for ln in lines:
            lw = _line_width(ln, font_pt)
            if box_width_pt > 0 and lw > 0:
                rendered_lines += max(1, math.ceil(lw / avail_w))
            else:
                rendered_lines += 1

    rendered_h = rendered_lines * line_h

    overflow_x = max(0.0, rendered_w - box_width_pt) if box_width_pt > 0 else 0.0
    overflow_y = max(0.0, rendered_h - box_height_pt) if box_height_pt > 0 else 0.0

    return overflow_x, overflow_y, rendered_w, rendered_h


# Tolerance ratio for overflow detection — absorbs font metric estimation error (~5-10%).
# Overflow smaller than 8% of box dimension is treated as in-tolerance.
_OVERFLOW_TOLERANCE_RATIO = 0.08
# Minimum absolute tolerance (pt) — prevents tiny boxes from always being "in tolerance"
_OVERFLOW_TOLERANCE_MIN = 2.0


def check_overflow_2d(
    text: str,
    font_pt: float,
    box_w: float,
    box_h: float,
    line_spacing: float = 1.2,
    v_auto_fit: bool = False,
    h_auto_fit: bool = False,
) -> list[dict]:
    """2D overflow detection — vertical + horizontal, each dimension independently.

    Returns list of overflow issues. Empty list = no overflow detected.
    Vertical:   rendered text height > box height → overflow_vertical
    Horizontal: longest unbreakable word > box width → overflow_horizontal

    Each issue includes actionable fix options for the AI agent.
    """
    if not text or not text.strip():
        return []
    if font_pt <= 0:
        return []

    issues: list[dict] = []

    m = estimate_text_size(text, font_pt, line_spacing, box_w, box_h, word_wrap=True)
    _, ov_y, rendered_w, rendered_h = m

    # Line count for diagnostics
    text_lines_raw = text.split("\n")
    total_chars = sum(len(ln) for ln in text_lines_raw)

    # ── Vertical ──
    if not v_auto_fit and box_h > 0 and rendered_h > 0:
        overflow_v = rendered_h - box_h
        tolerance = max(box_h * _OVERFLOW_TOLERANCE_RATIO, _OVERFLOW_TOLERANCE_MIN)
        if overflow_v > tolerance:
            # Estimate how many lines to remove or how much to shrink font
            line_h = font_pt * line_spacing
            overflow_lines = math.ceil(overflow_v / line_h) if line_h > 0 else 0
            target_font_size = round(font_pt * box_h / rendered_h, 1) if rendered_h > 0 else font_pt

            issues.append({
                "kind": "overflow_vertical",
                "level": "error",  # severity decided by caller (builder downgrades TEXTBOX → warning)
                "rendered_h": round(rendered_h, 1),
                "box_h": round(box_h, 1),
                "overflow_pt": round(overflow_v, 1),
                "font_size": font_pt,
                "line_count": len(text_lines_raw),
                "overflow_lines": overflow_lines,
                "total_chars": total_chars,
                "message": (
                    f"text height {rendered_h:.1f}pt > box {box_h:.1f}pt "
                    f"({overflow_v:.1f}pt overflow, ~{overflow_lines} lines beyond box)"
                ),
                "options": [
                    f"shrink font from {font_pt}pt to {target_font_size}pt",
                    f"reduce content by ~{overflow_lines} lines (current: {len(text_lines_raw)} lines, {total_chars} chars)",
                    f"increase box height from {box_h:.0f}pt to ≥{rendered_h:.0f}pt",
                    "split content across multiple slides",
                ],
            })

    # ── Horizontal ──
    if not h_auto_fit and box_w > 0:
        # Find longest unbreakable word (split on whitespace)
        longest_word_w = 0.0
        longest_word = ""
        for line in text.split("\n"):
            for word in line.split(" "):
                ww = _line_width(word, font_pt)
                if ww > longest_word_w:
                    longest_word_w = ww
                    longest_word = word

        tolerance_w = max(box_w * _OVERFLOW_TOLERANCE_RATIO, _OVERFLOW_TOLERANCE_MIN)
        if longest_word_w > box_w + tolerance_w:
            target_font_size_w = round(font_pt * box_w / longest_word_w, 1) if longest_word_w > 0 else font_pt
            overflow_w = longest_word_w - box_w

            issues.append({
                "kind": "overflow_horizontal",
                "level": "error",
                "longest_word_w": round(longest_word_w, 1),
                "box_w": round(box_w, 1),
                "overflow_pt": round(overflow_w, 1),
                "font_size": font_pt,
                "longest_word": longest_word[:40],
                "message": (
                    f"longest word '{longest_word[:30]}' ({longest_word_w:.1f}pt) "
                    f"> box width {box_w:.1f}pt ({overflow_w:.1f}pt overflow)"
                ),
                "options": [
                    f"shrink font from {font_pt}pt to {target_font_size_w}pt",
                    f"widen box from {box_w:.0f}pt to ≥{longest_word_w:.0f}pt",
                    f"hyphenate or shorten word: '{longest_word[:40]}'",
                    "enable word_wrap / allow_wrap on this element",
                ],
            })

    return issues


def expand_bbox(
    x: float, y: float, w: float, h: float,
    overflow_x: float, overflow_y: float,
    text_align: str = "left",
) -> tuple[float, float, float, float]:
    """Merge overflow into bbox to produce effective_bbox.

    text_align:
      "left"   → overflow extends right
      "center" → overflow extends both sides equally
      "right"  → overflow extends left

    Vertical overflow always extends downward (text flows top-to-bottom).
    """
    new_w = w + overflow_x
    new_h = h + overflow_y
    new_x = x
    new_y = y

    if text_align == "center":
        new_x = x - overflow_x / 2
    elif text_align == "right":
        new_x = x - overflow_x

    return new_x, new_y, max(new_w, 0.1), max(new_h, 0.1)


# ═══════════════════════════════════════════════════════════
# OVERFLOW REPORT
# ═══════════════════════════════════════════════════════════

class OverflowReport:
    """Text overflow detection result."""

    def __init__(
        self, text: str, font_pt: float, line_spacing: float,
        box_x: float, box_y: float, box_w: float, box_h: float,
        word_wrap: bool, auto_size: str = "NONE",
        font_explicit: bool = True,
    ):
        self.overflow_x, self.overflow_y, self.rendered_w, self.rendered_h = \
            estimate_text_size(text, font_pt, line_spacing, box_w, box_h, word_wrap)

        self.has_overflow = self.overflow_x > 2 or self.overflow_y > 2
        self.is_horizontal = self.overflow_x > 2
        self.is_vertical = self.overflow_y > 2

        # effective_bbox = largest possible area this element occupies when rendered
        if self.has_overflow and auto_size == "NONE":
            ex, ey, ew, eh = expand_bbox(
                box_x, box_y, box_w, box_h,
                self.overflow_x, self.overflow_y,
            )
        elif auto_size == "SHAPE_TO_FIT_TEXT":
            ex, ey, ew, eh = expand_bbox(
                box_x, box_y,
                min(box_w, self.rendered_w),
                min(box_h, self.rendered_h),
                max(0.0, self.rendered_w - box_w),
                max(0.0, self.rendered_h - box_h),
            )
        else:
            ex, ey, ew, eh = box_x, box_y, box_w, box_h

        self.effective_x = ex
        self.effective_y = ey
        self.effective_w = ew
        self.effective_h = eh

        # Auto-scaled font size estimate (TEXT_TO_FIT_SHAPE)
        if auto_size == "TEXT_TO_FIT_SHAPE" and self.has_overflow:
            scale_x = box_w / max(self.rendered_w, 0.1)
            scale_y = box_h / max(self.rendered_h, 0.1)
            self.fitted_font_size = max(1.0, font_pt * min(scale_x, scale_y))
        else:
            self.fitted_font_size = font_pt

    def to_dict(self) -> dict:
        return {
            "has_overflow": self.has_overflow,
            "overflow_x_pt": round(self.overflow_x, 1),
            "overflow_y_pt": round(self.overflow_y, 1),
            "rendered_w_pt": round(self.rendered_w, 1),
            "rendered_h_pt": round(self.rendered_h, 1),
            "effective_bbox": (
                round(self.effective_x, 1), round(self.effective_y, 1),
                round(self.effective_w, 1), round(self.effective_h, 1),
            ),
            "fitted_font_size": round(self.fitted_font_size, 1),
        }
