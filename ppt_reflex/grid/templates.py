"""
grid/templates.py — PPT template color/font snapshot

6 color schemes, all white/warm-white backgrounds, <=4 colors, contrast >= 4.5:1 (WCAG AA)
Agent selects template -> engine validates -> auto-applies on generation
"""

from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class TemplateProfile:
    id: str
    name: str
    description: str              # one-line description, Agent's basis for template selection

    # ── Colors ──
    bg_hex: str                   # background
    text_hex: str                 # body text
    title_hex: str                # title
    accent_hex: str               # primary accent
    accent2_hex: str = ""         # secondary accent
    gray_hex: str = "7A8090"      # secondary text/lines
    dim_hex: str = "B0B5C0"       # faintest text

    # ── Fonts ──
    title_font: str = "Microsoft YaHei"
    body_font: str = "Microsoft YaHei"
    title_size: int = 28          # pt
    body_size: int = 18           # pt
    caption_size: int = 14        # pt
    page_number_size: int = 12

    # ── Spacing ──
    page_margin: int = 48         # pt four-side safe zone
    line_spacing: float = 1.35

    # ── Decor ──
    divider_color_hex: str = ""   # divider color, default=accent
    divider_width_pt: float = 3.0
    card_rounding: float = 0      # card corner radius, 0=sharp

    # ── Constraints ──
    max_colors: int = 4           # max colors per deck
    max_elements_per_slide: int = 12
    max_chars_per_slide: int = 200
    allow_dark_bg: bool = False   # allow dark backgrounds
    center_titles: bool = False   # center titles

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "bg": self.bg_hex, "text": self.text_hex, "title": self.title_hex,
            "accent": self.accent_hex, "accent2": self.accent2_hex,
            "title_font": self.title_font, "body_font": self.body_font,
            "title_sz": self.title_size, "body_sz": self.body_size,
        }

    def override(self, **kwargs) -> "TemplateProfile":
        """Return new instance with specified fields overridden. Usage: t.override(bg_hex="FAFAFA", accent_hex="E74C3C")"""
        d = {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}
        d.update(kwargs)
        for k in kwargs:
            if k not in d:
                raise KeyError(f"TemplateProfile has no field '{k}'")
        return TemplateProfile(**d)


# ═══════════════════════════════════════════════════════════
# 6 templates
# ═══════════════════════════════════════════════════════════

TEMPLATES = {
    "academic": TemplateProfile(
        id="academic", name="Academic",
        description="Restrained, trustworthy, high information density. Deep navy + brick red accent, white bg",
        bg_hex="FFFFFF", text_hex="2D2D2D", title_hex="1B3A5C",
        accent_hex="1B3A5C", accent2_hex="C0392B", gray_hex="7A8599", dim_hex="A0A8B8",
        title_font="Microsoft YaHei", body_font="Microsoft YaHei",
        title_size=28, body_size=20, caption_size=14,
        divider_color_hex="1B3A5C", divider_width_pt=3.0,
        max_chars_per_slide=250, center_titles=False,
    ),
    "business": TemplateProfile(
        id="business", name="Business",
        description="Professional, clear, conclusion-first. Corporate blue + orange alert, white bg",
        bg_hex="FFFFFF", text_hex="333333", title_hex="0052D9",
        accent_hex="0052D9", accent2_hex="ED7B2F", gray_hex="888888", dim_hex="BDBDBD",
        title_font="Microsoft YaHei", body_font="Microsoft YaHei",
        title_size=28, body_size=20, caption_size=14,
        divider_color_hex="0052D9", divider_width_pt=2.0, card_rounding=8,
        max_chars_per_slide=180, center_titles=False,
    ),
    "minimal": TemplateProfile(
        id="minimal", name="Minimal",
        description="Breathing room, one message per slide. Dark gray + single bright accent, white bg",
        bg_hex="FFFFFF", text_hex="2A2A2F", title_hex="1A1A2E",
        accent_hex="2D5BD7", accent2_hex="FF4757", gray_hex="A0A0B0", dim_hex="D0D0D8",
        title_font="Microsoft YaHei", body_font="Microsoft YaHei",
        title_size=36, body_size=20, caption_size=14,
        divider_color_hex="2D5BD7", divider_width_pt=4.0,
        max_elements_per_slide=6, max_chars_per_slide=100, center_titles=True,
    ),
    "data_report": TemplateProfile(
        id="data_report", name="Data Report",
        description="Precise, grid-feel. Dark slate + data palette, white bg",
        bg_hex="FFFFFF", text_hex="212121", title_hex="37474F",
        accent_hex="1976D2", accent2_hex="F57C00", gray_hex="757575", dim_hex="BDBDBD",
        title_font="Microsoft YaHei", body_font="Microsoft YaHei",
        title_size=26, body_size=16, caption_size=12,
        page_margin=40, line_spacing=1.25,
        max_elements_per_slide=16, max_chars_per_slide=300, center_titles=False,
    ),
    "teaching": TemplateProfile(
        id="teaching", name="Teaching",
        description="Friendly, well-structured. Vibrant blue + orange markers, warm white bg",
        bg_hex="FFFDF5", text_hex="333333", title_hex="2196F3",
        accent_hex="2196F3", accent2_hex="FF9800", gray_hex="888888", dim_hex="C0C0C0",
        title_font="Microsoft YaHei", body_font="Microsoft YaHei",
        title_size=30, body_size=22, caption_size=16,
        divider_color_hex="E3F2FD", page_margin=60, line_spacing=1.45,
        max_elements_per_slide=8, max_chars_per_slide=180, center_titles=False,
    ),
    "product": TemplateProfile(
        id="product", name="Product Launch",
        description="Premium, visual impact. Dark gray bg + white text, dark bg allowed, all centered",
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
# PPT Template Selection Guide

You are generating a PowerPoint deck. Choose one of the 6 templates below and apply the corresponding colors/fonts/spacing on the first slide.

| ID | Name | Best for | Background | Primary | Body Text |
|----|------|----------|------------|---------|-----------|
| academic | Academic | Literature review / Defense / Seminar | #FFFFFF | #1B3A5C navy | #2D2D2D |
| business | Business | Work summary / Annual report | #FFFFFF | #0052D9 corp blue | #333333 |
| minimal  | Minimal | Share-out / TED talk | #FFFFFF | #2D5BD7 blue | #2A2A2F |
| data_report | Data Report | Annual report / Analysis | #FFFFFF | #1976D2 blue | #212121 |
| teaching | Teaching | Training / Course | #FFFDF5 warm white | #2196F3 blue | #333333 |
| product  | Product Launch | Brand / Promo | #1D1D1F dark gray | #6366F1 purple | #E8E8EC |

General rules:
- <= 4 colors per deck (primary + accent + body + gray)
- Body text >= 18pt, captions >= 14pt
- No pure black (#000) / pure white (#FFF) backgrounds
- No rainbow effect (<= 5 hues per slide)
- Four-side safe zone >= 48pt

After selecting a template, the engine auto-validates aesthetics rules during generation.
"""
