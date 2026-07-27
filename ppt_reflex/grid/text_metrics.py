"""
grid/text_metrics.py — 文字渲染尺寸估算器（不依赖字体文件）

估算 rendered_bbox 供溢出检测用。精度 ±15%，够做碰撞判断。

原理:
  中文 ≈ 1.0em/字, 英文 ≈ 0.55em/字, 混合取加权
  rendered_h = 行高 × 实际行数
  rendered_w = max(每行宽度)
"""

from __future__ import annotations
import math

# ═══════════════════════════════════════════════════════════
# CHARACTER WIDTH FACTORS (relative to font_size_pt)
# ═══════════════════════════════════════════════════════════

CHAR_WIDTH_FACTOR = {
    "cjk":   1.00,    # 全角中日韩
    "latin": 0.55,    # 半角平均
    "digit": 0.55,
    "space": 0.28,
    "punct": 0.35,    # 英文标点
    "cjk_punct": 1.00, # 中文标点
}

def _char_class(ch: str) -> str:
    cp = ord(ch)
    # CJK 区
    if (0x2E80 <= cp <= 0x9FFF) or (0xF900 <= cp <= 0xFAFF) or (0xFF00 <= cp <= 0xFFEF):
        if 0xFF00 <= cp <= 0xFF0F or 0xFF1A <= cp <= 0xFF20 or 0xFF3B <= cp <= 0xFF40 or 0xFF5B <= cp <= 0xFF65:
            return "cjk_punct"
        return "cjk"
    if ch.isdigit():
        return "digit"
    if ch.isspace():
        return "space"
    if ch in ',.;:!?-\'"()[]{}':
        return "punct"
    return "latin"


def _line_width(line: str, font_pt: float) -> float:
    """单行文字的估算渲染宽度 (pt)。"""
    w = 0.0
    for ch in line:
        w += CHAR_WIDTH_FACTOR.get(_char_class(ch), 0.55) * font_pt
    return max(w, 0.0)


def estimate_text_size(text: str, font_pt: float,
                       line_spacing: float = 1.2,
                       box_width_pt: float = 0.0,
                       box_height_pt: float = 0.0,
                       word_wrap: bool = True) -> tuple[float, float, float, float]:
    """
    Args:
        text: 文字内容
        font_pt: 字号 (pt)
        line_spacing: 行高倍数 (1.0 = 100% 字号)
        box_width_pt: 文本框逻辑宽度 (pt)
        box_height_pt: 文本框逻辑高度 (pt)
        word_wrap: 是否自动换行

    Returns:
        (overflow_x_pt, overflow_y_pt, rendered_w_pt, rendered_h_pt)
        前两个是溢出量 (0 = 无溢出), 后两个是估算渲染尺寸
    """
    if not text.strip():
        return 0.0, 0.0, box_width_pt, box_height_pt

    lines = text.split("\n")
    line_h = font_pt * line_spacing

    if not word_wrap:
        # 不折行：每行宽度 = 字符累加
        line_widths = [_line_width(ln, font_pt) for ln in lines]
        rendered_w = max(line_widths) if line_widths else 0.0
        rendered_lines = len(lines)
    else:
        # 折行：按 box_width 估算每行折成几行
        rendered_lines = 0
        rendered_w = box_width_pt  # 折行后宽度 = 框宽度
        for ln in lines:
            lw = _line_width(ln, font_pt)
            if box_width_pt > 0:
                rendered_lines += max(1, math.ceil(lw / box_width_pt))
            else:
                rendered_lines += 1

    rendered_h = rendered_lines * line_h

    overflow_x = max(0.0, rendered_w - box_width_pt) if box_width_pt > 0 else 0.0
    overflow_y = max(0.0, rendered_h - box_height_pt) if box_height_pt > 0 else 0.0

    return overflow_x, overflow_y, rendered_w, rendered_h


def check_overflow_2d(text: str, font_pt: float, box_w: float, box_h: float,
                       line_spacing: float = 1.2,
                       v_auto_fit: bool = False,
                       h_auto_fit: bool = False) -> list[dict]:
    """P0-口③: 二维溢出检测。vertical + horizontal，每个维度独立判定是否豁免。

    Returns list of overflow issues — empty means no overflow detected.
    垂直：文字渲染高度 > 框高 → overflow_vertical
    水平：最长不可断词 > 框宽 → overflow_horizontal（会顶破或强制多换行）
    """
    if not text.strip():
        return []

    issues: list[dict] = []
    m = estimate_text_size(text, font_pt, line_spacing, box_w, box_h, word_wrap=True)
    _, ov_y, rendered_w, rendered_h = m

    # ═══ 垂直 ═══
    if not v_auto_fit and rendered_h > box_h + 2:
        issues.append({
            "kind": "overflow_vertical",
            "level": "error",
            "rendered_h": round(rendered_h, 1),
            "box_h": round(box_h, 1),
            "font_size": font_pt,
            "message": (f"text height {rendered_h:.1f}pt > box {box_h:.1f}pt — "
                        f"vertical overflow, box is locked"),
        })

    # ═══ 水平 ═══
    if not h_auto_fit:
        # 找最长不可断词（line split on space, max word width）
        longest_word_w = 0.0
        for line in text.split("\n"):
            for word in line.split(" "):
                ww = _line_width(word, font_pt)
                if ww > longest_word_w:
                    longest_word_w = ww
        if box_w > 0 and longest_word_w > box_w + 1:
            issues.append({
                "kind": "overflow_horizontal",
                "level": "error",
                "longest_word_w": round(longest_word_w, 1),
                "box_w": round(box_w, 1),
                "font_size": font_pt,
                "message": (f"longest word {longest_word_w:.1f}pt > box {box_w:.1f}pt — "
                            f"word breaks through right edge"),
            })

    return issues


def expand_bbox(x: float, y: float, w: float, h: float,
                overflow_x: float, overflow_y: float,
                text_align: str = "left") -> tuple[float, float, float, float]:
    """
    将溢出量合并到 bbox 中，产生 effective_bbox。

    text_align:
      "left"   → 向右溢出
      "center" → 左右均分
      "right"  → 向左溢出
      竖直方向默认向下溢出（一行文字天然从上到下）
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
    """文字溢出检测结果。"""
    def __init__(self, text: str, font_pt: float, line_spacing: float,
                 box_x: float, box_y: float, box_w: float, box_h: float,
                 word_wrap: bool, auto_size: str = "NONE",
                 font_explicit: bool = True):
        self.overflow_x, self.overflow_y, self.rendered_w, self.rendered_h = \
            estimate_text_size(text, font_pt, line_spacing, box_w, box_h, word_wrap)

        self.has_overflow = self.overflow_x > 2 or self.overflow_y > 2  # 2pt 容差
        self.is_horizontal = self.overflow_x > 2
        self.is_vertical = self.overflow_y > 2

        # effective_bbox = 该元素在放映时可能占据的最大区域
        if self.has_overflow and auto_size == "NONE":
            ex, ey, ew, eh = expand_bbox(box_x, box_y, box_w, box_h,
                                         self.overflow_x, self.overflow_y)
        elif auto_size == "SHAPE_TO_FIT_TEXT":
            ex, ey, ew, eh = expand_bbox(box_x, box_y, min(box_w, self.rendered_w),
                                         min(box_h, self.rendered_h),
                                         max(0.0, self.rendered_w - box_w),
                                         max(0.0, self.rendered_h - box_h))
        else:
            ex, ey, ew, eh = box_x, box_y, box_w, box_h

        self.effective_x = ex
        self.effective_y = ey
        self.effective_w = ew
        self.effective_h = eh

        # 自动缩放后估算字号 (TEXT_TO_FIT_SHAPE)
        if auto_size == "TEXT_TO_FIT_SHAPE" and self.has_overflow:
            # 估算缩放因子
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
            "effective_bbox": (round(self.effective_x, 1), round(self.effective_y, 1),
                               round(self.effective_w, 1), round(self.effective_h, 1)),
            "fitted_font_size": round(self.fitted_font_size, 1),
        }
