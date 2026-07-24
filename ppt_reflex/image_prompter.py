"""
ppt_reflex/image_prompter.py — AI image prompt generator

Usage:
  from image_prompter import ImagePrompter
  p = ImagePrompter()
  prompt = p.generate("Li-ion battery charge-discharge mechanism", style="scientific_diagram", template="academic")

Output: optimized AI image generation prompts (Midjourney / DALL·E / SD compatible)
"""

from __future__ import annotations
from dataclasses import dataclass, field

# ═══════════════════════════════════════════════════════════
# Image type × prompt template
# ═══════════════════════════════════════════════════════════

IMAGE_TYPES = {
    "scientific_diagram": {
        "label": "Scientific Diagram",
        "style_keywords": [
            "clean scientific illustration", "technical diagram",
            "white background", "vector style", "clear labels",
            "professional academic figure", "minimalist",
        ],
        "negative": [
            "photorealistic", "3D render", "shadows", "noise",
            "text", "watermark", "logo", "cluttered",
        ],
        "aspect": "16:9",
    },
    "experiment_photo": {
        "label": "Experiment Photo/Equipment",
        "style_keywords": [
            "laboratory photography", "clean lighting",
            "professional scientific equipment", "sharp focus",
            "white lab background", "product photography style",
        ],
        "negative": [
            "blurry", "dark", "cluttered background",
            "people faces", "text overlay", "watermark",
        ],
        "aspect": "4:3",
    },
    "data_chart": {
        "label": "Data Chart",
        "style_keywords": [
            "clean data visualization", "flat design",
            "minimalist chart", "information graphic",
            "professional presentation style", "consistent color palette",
        ],
        "negative": [
            "3D chart", "shadow effects", "gradient fill",
            "photo background", "text", "watermark",
        ],
        "aspect": "16:9",
    },
    "concept_illustration": {
        "label": "Concept Illustration",
        "style_keywords": [
            "abstract concept illustration", "flat vector art",
            "minimalist design", "professional presentation",
            "clean lines", "geometric shapes", "isometric view",
        ],
        "negative": [
            "photorealistic", "complex textures", "noise",
            "text", "watermark", "people faces",
        ],
        "aspect": "16:9",
    },
    "material_structure": {
        "label": "Material Structure",
        "style_keywords": [
            "molecular structure", "material science illustration",
            "atomic arrangement", "scientific visualization",
            "clean technical rendering", "crystal structure",
            "white background", "professional academic style",
        ],
        "negative": [
            "photorealistic", "text", "watermark",
            "complex background", "shadows",
        ],
        "aspect": "1:1",
    },
    "hero_image": {
        "label": "Hero Image / Cover",
        "style_keywords": [
            "professional presentation hero image", "modern design",
            "abstract technology background", "clean geometric",
            "subtle gradient", "corporate style",
        ],
        "negative": [
            "text", "watermark", "logo", "people faces",
            "cluttered", "dark background",
        ],
        "aspect": "16:9",
    },
}

# ═══════════════════════════════════════════════════════════
# Template palette → image color hints
# ═══════════════════════════════════════════════════════════

TEMPLATE_PALETTE_HINTS = {
    "academic": {
        "primary": "#1B3A5C",
        "accent": "#C0392B",
        "hint": "deep navy blue and muted brick red accents, clean white background",
    },
    "business": {
        "primary": "#0052D9",
        "accent": "#ED7B2F",
        "hint": "corporate blue with orange highlights, professional white background",
    },
    "minimal": {
        "primary": "#2D5BD7",
        "accent": "#FF4757",
        "hint": "vibrant blue with single red accent point, extreme minimalism, white space heavy",
    },
    "data_report": {
        "primary": "#1976D2",
        "accent": "#F57C00",
        "hint": "material blue and amber data tones, grid-based precision, white background",
    },
    "teaching": {
        "primary": "#2196F3",
        "accent": "#FF9800",
        "hint": "friendly light blue and warm orange, warm off-white background, approachable",
    },
    "product": {
        "primary": "#6366F1",
        "accent": "#8B5CF6",
        "hint": "indigo-purple gradient on dark charcoal, premium tech aesthetic",
    },
}

PROVIDER_SPECIFICS = {
    "midjourney": {
        "prefix": "",
        "suffix": "--ar {aspect} --style raw --no {negative}",
        "params": ["--v 6.1", "--q 2", "--s 250"],
    },
    "dalle": {
        "prefix": "A high-quality image of ",
        "suffix": ". {aspect} composition. Professional presentation quality.",
        "params": ["resolution: 1792x1024", "quality: hd"],
    },
    "sd": {
        "prefix": "masterpiece, best quality, ",
        "suffix": ". {aspect} aspect ratio. Clean professional style.",
        "params": ["steps: 30", "cfg_scale: 7", "sampler: DPM++ 2M Karras"],
    },
}


@dataclass
class ImagePrompt:
    """一条 AI 图片提示词"""
    subject: str
    type: str
    template: str
    provider: str

    full_prompt: str = ""
    negative_prompt: str = ""
    style_notes: str = ""
    suggested_provider: str = "midjourney"

    def to_dict(self):
        return {
            "subject": self.subject,
            "type": self.type,
            "template": self.template,
            "provider": self.provider,
            "full_prompt": self.full_prompt,
            "negative_prompt": self.negative_prompt,
            "style_notes": self.style_notes,
            "suggested_provider": self.suggested_provider,
        }


class ImagePrompter:
    """图片 AI 提示词生成器"""

    def __init__(self, template: str = "academic"):
        self.template = template

    # ── public API ──────────────────────────────────────

    def generate(
        self,
        subject: str,
        image_type: str = "scientific_diagram",
        provider: str = "midjourney",
    ) -> ImagePrompt:
        """生成一条 AI 图片提示词"""
        type_cfg = IMAGE_TYPES.get(image_type, IMAGE_TYPES["scientific_diagram"])
        palette = TEMPLATE_PALETTE_HINTS.get(self.template, TEMPLATE_PALETTE_HINTS["academic"])
        prov = PROVIDER_SPECIFICS.get(provider, PROVIDER_SPECIFICS["midjourney"])

        aspect = type_cfg["aspect"]
        style = ", ".join(type_cfg["style_keywords"])
        negative = ", ".join(type_cfg["negative"])
        color = palette["hint"]

        core = f"{subject}, {style}, color scheme: {color}"

        full = self._assemble(core, aspect, negative, prov)
        neg_full = self._assemble_negative(negative, prov)

        return ImagePrompt(
            subject=subject,
            type=image_type,
            template=self.template,
            provider=provider,
            full_prompt=full,
            negative_prompt=neg_full,
            style_notes=f"Type: {type_cfg['label']} | Palette: {palette['hint']}",
            suggested_provider=self._suggest_provider(image_type),
        )

    def generate_multi(
        self,
        subjects: list[dict],
        provider: str = "midjourney",
    ) -> list[ImagePrompt]:
        """Batch generate prompts. subjects=[{"subject":"...", "type":"scientific_diagram"}, ...]"""
        return [
            self.generate(
                s.get("subject", ""),
                s.get("type", "scientific_diagram"),
                provider,
            )
            for s in subjects
        ]

    def slide_images(
        self,
        slide_plan: list[dict],
        provider: str = "midjourney",
    ) -> dict[int, ImagePrompt]:
        """根据幻灯片计划批量生成图片提示词.
        slide_plan = [{"index": 0, "image_subject": "...", "image_type": "..."}, ...]"""
        result = {}
        for slide in slide_plan:
            if not slide.get("image_subject"):
                continue
            idx = slide.get("index", -1)
            result[idx] = self.generate(
                slide["image_subject"],
                slide.get("image_type", "scientific_diagram"),
                provider,
            )
        return result

    # ── internals ───────────────────────────────────────

    def _assemble(self, core: str, aspect: str, negative: str, prov: dict) -> str:
        parts = []
        if prov["prefix"]:
            parts.append(prov["prefix"].strip())
        parts.append(core)
        suffix = prov["suffix"].format(aspect=aspect, negative=negative)
        if suffix.strip():
            parts.append(suffix)
        params = ", ".join(prov["params"]) if prov["params"] else ""
        if params:
            parts.append(params)
        return " ".join(parts).strip()

    def _assemble_negative(self, negative: str, prov: dict) -> str:
        if prov.get("provider") == "dalle":
            return negative
        return f"ugly, blurry, low quality, distorted, watermark, text, logo, {negative}"

    def _suggest_provider(self, image_type: str) -> str:
        if image_type in ("scientific_diagram", "material_structure", "concept_illustration"):
            return "midjourney"
        if image_type in ("experiment_photo",):
            return "midjourney"
        if image_type in ("hero_image",):
            return "dalle"
        return "midjourney"


# ═══════════════════════════════════════════════════════════
# Mandatory pre-generation questionnaire for Agent
# ═══════════════════════════════════════════════════════════

MAKER_QUESTIONNAIRE = """
# PPT Maker — Startup Questionnaire

The following information MUST be collected before every PPT generation (no skipping):

## Required Questions

1. **What to make**: Topic / purpose / occasion?
   - Example: "Group meeting report on SiOC anode progress" / "Thesis defense" / "Annual summary"
   - Scene: academic | business | teaching | product

2. **Content**: What content do you have?
   - Text, data tables, existing images, references
   - How many slides? Expected duration?

3. **Image needs** (explicitly say "none" if not needed):
   - Which slides need images?
   - Image type for each: scientific_diagram / experiment_photo / data_chart / concept_illustration / material_structure / hero_image
   - Do you have image files to use, or need AI to generate them?

4. **Template preference**: Which color theme?
   - academic / business / minimal / data_report / teaching / product
   - Custom colors? (provide hex codes)

## Workflow

```
User answers → confirm plan → image needs?
  ├─ User provides image files → use directly
  ├─ Needs AI generation → ImagePrompter generates prompts → user fetches images
  └─ No images needed → skip

  → Generate PPT (grid/ engine) → output to temp dir → user reviews
```
"""


# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    p = ImagePrompter(template="academic")

    tests = [
        ("SiOC anode charge-discharge mechanism diagram", "scientific_diagram", "midjourney"),
        ("POSS cage structure pyrolysis to SiOC transformation", "material_structure", "midjourney"),
        ("Li-ion half-cell testing setup photo", "experiment_photo", "midjourney"),
        ("SiOC/Graphene composite aerogel 3D structure", "concept_illustration", "dalle"),
    ]

    for subject, itype, prov in tests:
        r = p.generate(subject, itype, prov)
        print(f"\n{'='*70}")
        print(f"Type: {r.type} | Template: {r.template} | Suggested: {r.suggested_provider}")
        print(f"Subject: {r.subject}")
        print(f"Full prompt:")
        print(f"  {r.full_prompt}")
        print(f"Negative: {r.negative_prompt[:120]}...")
