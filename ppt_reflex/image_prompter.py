"""
ppt_reflex/image_prompter.py — 图片 AI 提示词生成器

用法:
  from image_prompter import ImagePrompter
  p = ImagePrompter()
  prompt = p.generate("锂离子电池充放电原理示意图", style="scientific_diagram", template="academic")

输出: 优化过的 AI 图片生成提示词 (Midjourney / DALL·E / SD 通用)
"""

from __future__ import annotations
from dataclasses import dataclass, field

# ═══════════════════════════════════════════════════════════
# 图片类型 × 提示词模板
# ═══════════════════════════════════════════════════════════

IMAGE_TYPES = {
    "scientific_diagram": {
        "label": "科学示意图",
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
        "label": "实验照片/设备",
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
        "label": "数据图表",
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
        "label": "概念插图",
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
        "label": "材料结构图",
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
        "label": "封面/主视觉",
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
# 模板配色 → 图片色调建议
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
            style_notes=f"类型: {type_cfg['label']} | 色调: {palette['hint']}",
            suggested_provider=self._suggest_provider(image_type),
        )

    def generate_multi(
        self,
        subjects: list[dict],
        provider: str = "midjourney",
    ) -> list[ImagePrompt]:
        """批量生成提示词. subjects=[{"subject":"...", "type":"scientific_diagram"}, ...]"""
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
# Agent 用的引导问卷
# ═══════════════════════════════════════════════════════════

MAKER_QUESTIONNAIRE = """
# PPT 制作 — 启动问卷

每次制作 PPT 前必须收集以下信息（不得跳过）：

## 必答问题

1. **做什么**: PPT 的主题/目的/场合?
   - 示例: "组会汇报 SiOC 阳极进展" / "开题答辩" / "年终总结"
   - 场景: academic | business | teaching | product

2. **内容**: 有哪些内容?
   - 文字内容、数据表格、已有图片、参考文献
   - 需要几张幻灯片? 预期时长?

3. **图片需求** (如果不需要图片，明确说明):
   - 哪些幻灯片需要图片?
   - 每张图类型: 科学示意图/实验照片/数据图表/概念插图/材料结构/封面主视觉
   - 自己提供图片文件? 还是需要 AI 生成?

4. **模板偏好**: 用哪套配色?
   - academic(学术) / business(商务) / minimal(极简) / data_report(数据) / teaching(教学) / product(产品)
   - 自定义颜色? (需要提供 hex)

## 处理流程

```
用户回答 → 确认计划 → 有图片需求?
  ├─ 用户提供图片文件 → 直接使用
  ├─ 需要 AI 生成 → ImagePrompter 生成提示词 → 用户去生成
  └─ 无图片需求 → 跳过

  → 生成 PPT (grid/ engine) → 输出到 temp 目录 → 用户检查
```
"""


# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    p = ImagePrompter(template="academic")

    tests = [
        ("SiOC 负极材料充放电机理示意图", "scientific_diagram", "midjourney"),
        ("POSS 笼状结构热解 SiOC 转变过程", "material_structure", "midjourney"),
        ("锂离子电池半电池测试装置照片", "experiment_photo", "midjourney"),
        ("SiOC/Graphene 复合气凝胶 3D 结构", "concept_illustration", "dalle"),
    ]

    for subject, itype, prov in tests:
        r = p.generate(subject, itype, prov)
        print(f"\n{'='*70}")
        print(f"类型: {r.type} | 模板: {r.template} | 建议工具: {r.suggested_provider}")
        print(f"主体: {r.subject}")
        print(f"完整提示词:")
        print(f"  {r.full_prompt}")
        print(f"负面提示词: {r.negative_prompt[:120]}...")
