# ppt_reflex — The PowerPoint Engine for AI Code Generation

**When an LLM writes `python-pptx` code, your slides end up with stretched images, invisible text, overlapping boxes, and zero design consistency. ppt_reflex fixes that.**

A spatially-aware, aesthetics-enforcing presentation engine. Instead of AI writing raw `slide.shapes.add_picture(...)` and hoping it looks right, AI declares *intent* — and the grid engine computes, validates, and renders safe, beautiful layouts.

## The Problem It Solves

| LLM-generated `python-pptx` code | ppt_reflex |
|:--|:--|
| `add_picture(path, x, y, w, h)` — stretches to fill, destroys aspect ratio | **Contain-fit by default**: PIL reads natural dimensions → `scale = min(w/natW, h/natH)` → invariant check `±0.001` |
| Hardcoded `RGBColor(0,0,0)` on `#1A1A2E` background — invisible text | **AestheticsEngine**: WCAG 2.1 contrast ratio ≥4.5:1 enforced, `invisible_text` = BLOCK |
| 14pt body text in a 200pt box with 300 words — overflow, no warning | **text_metrics**: estimates rendered size → overflow detection → per-element diagnostic with fix suggestions |
| 6 slides, 6 different color schemes — no consistency | **6 style presets** lock color/font/shape/image-treatment per deck. Pick one, it propagates everywhere. |
| Zero feedback loop — "looks wrong" is all you get | **124 diagnostics per build**: every overflow, contrast violation, alignment drift, density warning catalogued |

## Architecture

```
AI declares intent (PPTBuilder)
        │
        ▼
┌───────────────────────────────────────┐
│           THREE-LAYER CANVAS          │
│                                       │
│  Geometric  — coordinates / clamp     │
│  Semantic   — SemanticRole / 2 tables │
│  Commonsense— OverlapPolicy / WCAG    │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│          FIVE-PHASE PIPELINE          │
│                                       │
│  Phase 0   — declare → LayoutPlan     │
│  Phase 0.5 — validate regions         │
│  Phase 1   — information layer layout │
│  Phase 2   — decoration (arrows etc.) │
│  Phase 2.5 — global composition check │
│        │                              │
│  AestheticsEngine (10+ rules)         │
│  Pre-commit validation                │
│        │                              │
│        ▼                              │
│  _render_slide() → .pptx             │
└───────────────────────────────────────┘
```

### Two-Layer Slide Model

- **Information Layer** (Phase 1): text, boxes, images — `stack` or `inline` fill modes, collision detection
- **Decoration Layer** (Phase 2): arrows, connectors — auto-routed with occlusion warnings

### AestheticsEngine

Checks every element across 10+ quantifiable rules:

| Priority | Rules | Verdict |
|:--|:--|:--|
| P0 | color contrast (WCAG AA), invisible text, dark-on-dark, light-on-light, overflow-h, font < 10pt | WARN / only `invisible_text` = BLOCK |
| P1 | tight gaps, edge margin, density, near-black/white extremes | WARN |
| P2 | grid alignment, color palette size | WARN |

Runs at three timings: `try_place` (P0 only), `commit` (P0+P1), `audit` (full).

### Image Rendering

```
1. PIL opens file → natural_w, natural_h, aspect_ratio
2. Preset constraints → max_w, max_h per layout_mode
3. contain-fit: scale = min(max_w/nat_w, max_h/nat_h)
4. no-upscale guard: if scale > 1.0 and allow_upscale=false → scale=1.0
5. invariant check: |final_w/final_h - aspect_ratio| ≤ 0.001
6. center placement within region
7. ASPECT_RATIO_BROKEN → FATAL, refuse render
```

## Quick Start

```python
from ppt_reflex.builder import PPTBuilder

# One entry point. Zero engine concepts exposed.
b = PPTBuilder(template="academic", style="academic_rigorous")

b.add_slide("Cover",
    regions=[
        ("hero",  80, 80, 800, 260, 1),   # (id, x, y, w, h, reading_order)
        ("meta",  120, 360, 720, 100, 2),
    ],
    elements=[
        b.title("Transition from Aerogels to Hierarchical Monoliths"),
        b.text("Kanamori et al. (2011) J. Colloid Interface Sci.", style="小标题"),
        b.text("DOI: 10.1016/j.jcis.2011.02.027", style="注释"),
    ])

b.add_slide("Background",
    regions=[
        ("hdr",   60, 30, 840, 40, 1),
        ("left",  60, 90, 450, 400, 2),
        ("right", 540, 90, 360, 200, 3),
    ],
    elements=[
        b.text("Why Hierarchical Porosity in PMSQ?", style="小标题", region="hdr"),
        b.divider(region="div", color=(194,65,12)),
        b.bullet("PMSQ = CH₃SiO₁.₅ — dual amphiphilic surface", region="left"),
        b.bullet("Trifunctional silane → POSS cages → gelation challenge", region="left"),
        b.box("Key Innovation: F127 controls both\nphase separation AND mesopore formation",
              style="小标题", region="right", fill_color=(20,30,50)),
        b.image("fig1_sem.png", region="right",
                layout_mode="hero_right", caption="Figure 1. SEM macropore evolution"),
    ])

result = b.build("output.pptx")
# → 128 issues (0 errors, 127 warnings), 1.3MB .pptx with aspect-locked images
```

## Style Presets (v2)

Six presets with integrated image layout strategies. Pick one, everything locks in.

| Preset | Mood | Preferred Image Mode | Image Ratio | Corners | Shadow | Caption |
|:--|:--|:--|:--|:--|:--|:--|
| `academic_rigorous` | Rigorous, restrained | center_float | ≤60% | 0 | none | `Figure N. Title (bold) + note` |
| `corporate_minimal` | Clean, trustworthy | hero_right | ≤40% | 8pt | soft | `Fig N: short` |
| `tech_dark` | Immersive, dramatic | hero_right | ≤50% | 12pt | glow | `// Figure N` |
| `magazine_editorial` | Bold, narrative | hero_top | 50-70% | 0 | none | minimal / optional |
| `creative_vibrant` | Playful, friendly | center_float | ≤50% | 20pt | sticker | centric, optional emoji |
| `government_solemn` | Authoritative, formal | hero_top | ≤45% | 4pt | none | time/place descriptive |

API for image intelligence:

```python
b.auto_layout_mode("fig1.png")   # → "hero_top" (aspect>1.6) / "hero_right" (aspect<0.8) / "center_float"
b.image_constraints("hero_top")  # → {"max_width_pt": 800, "max_height_pt": 280, "anchor": "top_center"}
b.image_treatment()              # → {"corner_radius_pt": 0, "border_role": "border_strong", "shadow_role": "none"}
b.caption_format()               # → {"prefix": "Figure N. ", "alignment": "left", "max_lines": 2}
```

## Element Factory

```python
b.title("...")           # 标题 — 28pt, bold, centered
b.subtitle("...")        # 副标题 — 18pt, centered
b.text("...", style=)    # 正文/小标题/注释/页脚/强调/列表项
b.bullet("...")          # • prefixed list item
b.box("...", fill_color=) # Rounded textbox with fill
b.divider(color=, width=) # Horizontal rule
b.shape("star", ...)     # 20+ built-in shapes
b.image("path", layout_mode=, caption=) # Aspect-locked contain-fit
b.arrow(from, to, ...)   # Auto-routed connector with occlusion check
```

## How It Prevents Common LLM PPT Failures

### 1. Stretched / distorted images
**LLM pattern**: `slide.shapes.add_picture("img.png", Pt(x), Pt(y), Pt(w), Pt(h))` — fills the box, ignores aspect ratio.
**ppt_reflex**: PIL reads 1920×1080 → contain-fit computes `min(w/1920, h/1080)` → invariant check. **Non-uniform scale = FATAL, refused.**

### 2. Invisible text on dark backgrounds
**LLM pattern**: `font.color.rgb = RGBColor(0x22, 0x22, 0x44)` on `fill = RGBColor(0x1A, 0x1A, 0x2E)` — both dark, zero contrast.
**ppt_reflex**: `_resolve_style()` detects dark fill → auto-switches to white text. `AestheticsEngine._color()` flags `dark_bg_dark_text` if L*<40 for both.

### 3. Text overflow without detection
**LLM pattern**: 300 chars in 14pt font in a 200pt-wide box → silently clipped.
**ppt_reflex**: `text_metrics.estimate_text_size()` computes true rendered dimensions → `overflow_v` / `overflow_h` diagnostics with fix suggestions (shrink font, expand box, split to next slide).

### 4. Hardcoded colors that don't match
**LLM pattern**: `RGBColor(0, 0, 255)` on every slide regardless of theme.
**ppt_reflex**: `_resolve_style()` reads from `TemplateProfile` + `style_presets.json` → dark fills get auto-white text → one preset, consistent everywhere.

### 5. No diagnostic feedback
**LLM pattern**: "It looks wrong." That's the entire error message.
**ppt_reflex**: Every `build()` returns structured diagnostics: `{"ok": True/False, "diagnostics": [{phase, kind, severity, options, recommended_action}, ...], "summary": "128 issues (0 errors, 127 warnings)"}`.

## Install

```bash
pip install python-pptx pillow
git clone https://github.com/your-org/ppt_reflex.git
```

Python 3.10+. Zero system dependencies beyond `python-pptx` and `Pillow`.

## Project Layout

```
ppt_reflex/
├── builder.py            # Sole AI entry point — PPTBuilder class
├── style_presets.json    # 6 presets × image_layout strategies (v2)
├── image_prompter.py     # AI image prompt generator for Midjourney/DALL·E/SD
├── grid/
│   ├── types.py          # 30+ types: SemanticRole, ContentType, ElementPayload...
│   ├── plan.py           # LayoutPlan, Region, Phase1Element, DecoIntent, diagnostics
│   ├── canvas.py         # Three-layer canvas: geometric → semantic → commonsense
│   ├── phase1.py         # Information layer: stack/inline placement with collision
│   ├── phase2.py         # Decoration layer: arrow routing + occlusion detection
│   ├── composition.py    # Phase 2.5: global whitespace/balance/density/alignment
│   ├── aesthetics.py     # 10+ WCAG rules: contrast, font, overflow, density, spacing
│   ├── templates.py      # 6 base TemplateProfiles + override() chain
│   ├── serializer.py     # grid_to_ppt rendering: text/shape/image/connector
│   ├── text_metrics.py   # True text size estimation for overflow prediction
│   ├── orchestrator.py   # layout_loop diagnostic repair (P2 integration)
│   └── tests/            # 9 test files covering all phases
└── .claude/skills/ppt-maker/
    └── SKILL.md          # 3-step intake flow for Claude Code
```

## The Design Philosophy

> **The engine computes truth and gives menus. It never silently mutates AI's declarations.**

Every phase produces diagnostics, not silent fixes. `allow_shrink=False` by default — if text doesn't fit, the engine reports it with concrete fix options (shrink to X pt, expand box, split). The AI decides which fix to apply, then re-enters the pipeline.

This is the core insight: **layout is a constraint-solving problem, not a one-shot rendering problem.** The engine is the solver; the AI is the decision-maker. They talk through structured diagnostics.

---

Built for AI agents. Used in production with Claude Code. MIT licensed.
