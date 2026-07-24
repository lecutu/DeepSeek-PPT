"""
grid/templates.py — PPT 模板配色/字体快照

6 套配色方案, 全白/暖白底, ≤4 色, 对比度 ≥ 4.5:1 (WCAG AA)
Agent 选择模板 → engine 验证 → 生成时自动应用
"""

from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class TemplateProfile:
    id: str
    name: str
    description: str              # 一行描述，Agent 选模板时的依据

    # ── 颜色 ──
    bg_hex: str                   # 背景色
    text_hex: str                 # 正文色
    title_hex: str                # 标题色
    accent_hex: str               # 主强调色
    accent2_hex: str = ""         # 辅强调色
    gray_hex: str = "7A8090"      # 次要文字/线条
    dim_hex: str = "B0B5C0"       # 最淡文字

    # ── 字体 ──
    title_font: str = "Microsoft YaHei"
    body_font: str = "Microsoft YaHei"
    title_size: int = 28          # pt
    body_size: int = 18           # pt
    caption_size: int = 14        # pt
    page_number_size: int = 12

    # ── 间距 ──
    page_margin: int = 48         # pt 四边安全区
    line_spacing: float = 1.35    # 中文推荐 1.35~1.5

    # ── 装饰 ──
    divider_color_hex: str = ""   # 分割线颜色，默认=accent
    divider_width_pt: float = 3.0
    card_rounding: float = 0      # 卡片圆角, 0=直角

    # ── 约束 ──
    max_colors: int = 4           # 全篇颜色数上限
    max_elements_per_slide: int = 12
    max_chars_per_slide: int = 200
    allow_dark_bg: bool = False   # 是否允许深色底
    center_titles: bool = False   # 标题是否居中

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "bg": self.bg_hex, "text": self.text_hex, "title": self.title_hex,
            "accent": self.accent_hex, "accent2": self.accent2_hex,
            "title_font": self.title_font, "body_font": self.body_font,
            "title_sz": self.title_size, "body_sz": self.body_size,
        }

    def override(self, **kwargs) -> "TemplateProfile":
        """返回新实例, 覆盖指定字段. 用法: t.override(bg_hex="FAFAFA", accent_hex="E74C3C")"""
        d = {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}
        d.update(kwargs)
        for k in kwargs:
            if k not in d:
                raise KeyError(f"TemplateProfile has no field '{k}'")
        return TemplateProfile(**d)


# ═══════════════════════════════════════════════════════════
# 6 套模板
# ═══════════════════════════════════════════════════════════

TEMPLATES = {
    "academic": TemplateProfile(
        id="academic", name="学术汇报",
        description="克制、可信、信息密度高。深蓝+砖红强调，白底，宋体正文",
        bg_hex="FFFFFF", text_hex="2D2D2D", title_hex="1B3A5C",
        accent_hex="1B3A5C", accent2_hex="C0392B", gray_hex="7A8599", dim_hex="A0A8B8",
        title_font="Microsoft YaHei", body_font="Microsoft YaHei",
        title_size=28, body_size=20, caption_size=14,
        divider_color_hex="1B3A5C", divider_width_pt=3.0,
        max_chars_per_slide=250, center_titles=False,
    ),
    "business": TemplateProfile(
        id="business", name="商务汇报",
        description="专业、清晰、结论先行。企业蓝+橙色警示，白底，雅黑",
        bg_hex="FFFFFF", text_hex="333333", title_hex="0052D9",
        accent_hex="0052D9", accent2_hex="ED7B2F", gray_hex="888888", dim_hex="BDBDBD",
        title_font="Microsoft YaHei", body_font="Microsoft YaHei",
        title_size=28, body_size=20, caption_size=14,
        divider_color_hex="0052D9", divider_width_pt=2.0, card_rounding=8,
        max_chars_per_slide=180, center_titles=False,
    ),
    "minimal": TemplateProfile(
        id="minimal", name="极简演讲",
        description="呼吸感、一屏一意。深灰+单一亮色，白底，极少先",
        bg_hex="FFFFFF", text_hex="2A2A2F", title_hex="1A1A2E",
        accent_hex="2D5BD7", accent2_hex="FF4757", gray_hex="A0A0B0", dim_hex="D0D0D8",
        title_font="Microsoft YaHei", body_font="Microsoft YaHei",
        title_size=36, body_size=20, caption_size=14,
        divider_color_hex="2D5BD7", divider_width_pt=4.0,
        max_elements_per_slide=6, max_chars_per_slide=100, center_titles=True,
    ),
    "data_report": TemplateProfile(
        id="data_report", name="数据报告",
        description="精确、网格感。深灰蓝+数据色板，白底，DIN数字",
        bg_hex="FFFFFF", text_hex="212121", title_hex="37474F",
        accent_hex="1976D2", accent2_hex="F57C00", gray_hex="757575", dim_hex="BDBDBD",
        title_font="Microsoft YaHei", body_font="Microsoft YaHei",
        title_size=26, body_size=16, caption_size=12,
        page_margin=40, line_spacing=1.25,
        max_elements_per_slide=16, max_chars_per_slide=300, center_titles=False,
    ),
    "teaching": TemplateProfile(
        id="teaching", name="教学课件",
        description="友好、层次分明。活力蓝+橙色标记，暖白底",
        bg_hex="FFFDF5", text_hex="333333", title_hex="2196F3",
        accent_hex="2196F3", accent2_hex="FF9800", gray_hex="888888", dim_hex="C0C0C0",
        title_font="Microsoft YaHei", body_font="Microsoft YaHei",
        title_size=30, body_size=22, caption_size=16,
        divider_color_hex="E3F2FD", page_margin=60, line_spacing=1.45,
        max_elements_per_slide=8, max_chars_per_slide=180, center_titles=False,
    ),
    "product": TemplateProfile(
        id="product", name="产品发布",
        description="高级感、视觉冲击。深灰底+白字，深底允许，全居中",
        bg_hex="1D1D1F", text_hex="E8E8EC", title_hex="FFFFFF",
        accent_hex="6366F1", accent2_hex="8B5CF6", gray_hex="98989E", dim_hex="68686E",
        title_font="Microsoft YaHei", body_font="Microsoft YaHei",
        title_size=40, body_size=20, caption_size=14,
        divider_color_hex="6366F1", divider_width_pt=2.0,
        max_elements_per_slide=4, max_chars_per_slide=60,
        allow_dark_bg=True, center_titles=True,
    ),
}


def get_template(template_id: str) -> TemplateProfile:
    if template_id not in TEMPLATES:
        raise KeyError(f"Unknown template: {template_id}. Valid: {list(TEMPLATES.keys())}")
    return TEMPLATES[template_id]


AGENT_PROMPT = """
# PPT 模板选择提示

你正在生成 PPT。请从以下 6 套模板中选择一个，并在 PPT 的第一页使用对应的配色/字体/间距。

| 模板 ID | 名称 | 适用场景 | 背景 | 主色 | 正文色 |
|---------|------|---------|------|------|--------|
| academic | 学术汇报 | 文献汇报/开题/答辩 | #FFFFFF | #1B3A5C 深蓝 | #2D2D2D |
| business | 商务汇报 | 工作总结/年终汇报 | #FFFFFF | #0052D9 企业蓝 | #333333 |
| minimal  | 极简演讲 | 分享会/TED | #FFFFFF | #2D5BD7 蓝 | #2A2A2F |
| data_report | 数据报告 | 年报/分析 | #FFFFFF | #1976D2 蓝 | #212121 |
| teaching | 教学课件 | 培训/课程 | #FFFDF5 暖白 | #2196F3 蓝 | #333333 |
| product  | 产品发布 | 品牌宣传 | #1D1D1F 深灰 | #6366F1 紫 | #E8E8EC |

通用规则:
- 全篇 ≤ 4 种颜色 (主色+强调色+正文+灰色)
- 正文 ≥ 18pt, 注释 ≥ 14pt
- 禁止纯黑底 (#000) / 纯白底 (#FFF)
- 禁止五颜六色 (单页 > 5 色调)
- 四边安全区 ≥ 48pt

选择模板后，引擎会在生成时自动校验美观性规则。
"""
