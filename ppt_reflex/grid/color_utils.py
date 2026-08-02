"""Shared WCAG color math. Single source of truth — was copy-pasted 3x
(builder._lum, aesthetics.relative_luminance, color_triangulator._luminance).
Pure functions, no imports from the package (so all three can use it)."""
from __future__ import annotations


def hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _srgb_lin(c: float) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple) -> float:
    return 0.2126 * _srgb_lin(rgb[0]) + 0.7152 * _srgb_lin(rgb[1]) + 0.0722 * _srgb_lin(rgb[2])


def contrast_ratio(c1, c2) -> float:
    L1, L2 = relative_luminance(c1), relative_luminance(c2)
    L, D = max(L1, L2), min(L1, L2)
    return (L + 0.05) / (D + 0.05)


def luminance_L(c) -> float:
    """L* (CIE Lab lightness, 0-100). Used for "dark/light fill → text color" heuristics."""
    Y = relative_luminance(c)
    return 116 * (Y ** (1 / 3)) - 16 if Y > 0.008856 else 903.3 * Y


def is_dark(rgb: tuple, threshold: float = 0.25) -> bool:
    """True when a fill is dark enough that white text is the right choice."""
    return relative_luminance(rgb) < threshold


def rgb_to_hex(rgb: tuple) -> str:
    return f"{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
