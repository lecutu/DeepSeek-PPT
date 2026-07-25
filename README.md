# ppt_reflex — Blind-Proof PowerPoint. No Vision Required.

**DeepSeek can't see images. GPT-4o can't preview `.pptx`. Every LLM is blind to its own PowerPoint output — it writes `python-pptx` code, crosses its fingers, and hopes. ppt_reflex removes the hope. The engine is a deterministic constraint solver: AI declares intent, engine guarantees correctness. You don't need to see the output to know it's right.**

Works with any LLM. Works *especially* well with DeepSeek, because the engine does the seeing for you.

## Why This Exists

Traditional AI → PowerPoint workflow:

```
AI writes python-pptx code → opens .pptx → "why is the image stretched?"
                                            → "why is that text invisible?"
                                            → "why is the box only 30pt tall?"
                                            → edit code, regenerate, repeat
```

Every iteration requires **human eyes** to spot the problem. If you're using DeepSeek (no vision), you're stuck. Even Claude/GPT users waste 3–5 rounds fixing layout bugs the AI can't detect because it has no `.pptx` renderer.

**ppt_reflex flips this**: the engine validates everything *before* the file is written. AI says what to put where. Engine computes safe geometry, checks contrast, enforces aspect ratios. Diagnostics come back as structured data — no eyes needed.

## The Blind-Model Problem (and Solution)

| What LLMs can't see | What ppt_reflex guarantees |
|:--|:--|
| Image stretched 2× horizontally — aspect ratio destroyed | **Contain-fit invariant**: `\|final_w/final_h − aspect\| ≤ 0.001`. Any violation = FATAL, refused. |
| Dark blue text on dark gray background — invisible | **WCAG AA enforced**: contrast ratio ≥ 4.5:1. `invisible_text` = BLOCK. Dark fill → auto white text. |
| 300 characters in a 200pt-wide box — silently clipped | **text_metrics**: pre-renders every string, estimates real pixel dimensions, reports overflow with fix options. |
| Multi-line callout box assigned `h=30pt` — text leaks out | **min-height semantics**: `_estimate_height()` computes text demand first, then `max(ph, text_h)`. Shapes auto-grow. |
| 6 slides, 6 different color palettes — no one noticed | **6 presets lock everything**: colors, fonts, shapes, image treatments. Pick once, enforced everywhere. |
| "Something looks wrong" — no diagnostic | **Structured diagnostics per build**: phase, kind, severity, element ID, fix suggestions. Machine-readable. |

**Result**: if `build()` returns `ok: true`, the PPTX is visually correct. Guaranteed. No visual inspection required.

## Quick Start

```python
from ppt_reflex.builder import PPTBuilder

b = PPTBuilder(template="academic", style="academic_rigorous")

b.add_slide("Cover",
    regions=[("hero", 80, 80, 800, 260, 1), ("meta", 120, 360, 720, 100, 2)],
    elements=[
        b.title("Transition from Aerogels to Hierarchical Monoliths"),
        b.text("Kanamori et al. (2011) DOI: 10.1016/j.jcis.2011.02.027", style="注释"),
    ])

b.add_slide("Background",
    regions=[("hdr", 60, 30, 840, 40, 1), ("left", 60, 90, 450, 400, 2), ("right", 540, 90, 360, 200, 3)],
    elements=[
        b.text("Why Hierarchical Porosity?", style="小标题", region="hdr"),
        b.bullet("PMSQ = CH₃SiO₁.₅ — dual amphiphilic surface", region="left"),
        b.box("Key Finding: F127 controls both\nphase separation AND mesopore formation",
              style="小标题", region="right", fill_color=(20, 30, 50)),
        b.image("fig1_sem.png", region="right", layout_mode="hero_right", caption="Figure 1. SEM"),
    ])

result = b.build("output.pptx")
# → {"ok": True, "summary": "128 issues (0 errors, 127 warnings)"}
```

One entry point. Zero engine concepts exposed. Any LLM that can write Python can use this.

## Architecture

```
AI declares intent (PPTBuilder)
        │
        ▼
┌──────────────────────────────────────────┐
│            THREE-LAYER CANVAS             │
│  Geometric   — coordinates / clamp       │
│  Semantic    — role / entity vs overlay  │
│  Commonsense — overlap policy / WCAG     │
└──────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────┐
│           FIVE-PHASE PIPELINE             │
│  Phase 0   — declare → LayoutPlan        │
│  Phase 0.5 — validate regions            │
│  Phase 1   — info layer (stack/inline)   │
│  Phase 2   — decoration (arrows)         │
│  Phase 2.5 — global composition          │
│       │                                   │
│  AestheticsEngine (10+ WCAG rules)       │
│  Pre-commit validation                   │
│  Structured diagnostics → AI reads them  │
│       │                                   │
│       ▼                                   │
│  _render_slide() → .pptx                 │
└──────────────────────────────────────────┘
```

## How It Prevents Common LLM Failures

### 1. Aspect ratio destroyed
LLM: `add_picture(path, x, y, w, h)` — fills the box, ignores 1920×1080 becoming 400×400.
ppt_reflex: PIL reads natural dimensions → `scale = min(w/natW, h/natH)` → invariant check. **Non-uniform scale → FATAL.**

### 2. Invisible text
LLM: `font.color = RGBColor(0x22, 0x22, 0x44)` on `fill = RGBColor(0x1A, 0x1A, 0x2E)`. Both dark, zero contrast.
ppt_reflex: `_resolve_style()` auto-switches to white on dark fills. AestheticsEngine flags `dark_bg_dark_text`.

### 3. Box too short for text
LLM: "wrote a 3-line warning in a 30pt box, second line fell out."
ppt_reflex: `_estimate_height()` computes text demand before allocating height. `max(preferred, text_needed)`. Shapes auto-grow with `SHAPE_TO_FIT_TEXT`.

### 4. Overflow = silent data loss
LLM: 300 chars at 14pt in a 200pt box — PowerPoint clips it. No error. Content gone.
ppt_reflex: `text_metrics` pre-estimates every string. `overflow_v` diagnostic with fix: shrink font / widen box / split slide.

### 5. Six slides, six palettes
LLM: picks `RGBColor(...)` ad-hoc per slide. Deck has no design identity.
ppt_reflex: 6 presets lock color/font/shape. Pick one. Everything inherits.

### 6. Zero diagnostics
LLM: "It looks wrong." That's it. That's the error message.
ppt_reflex: `build()` returns `{ok, diagnostics: [{phase, kind, severity, element_id, fix_options}]}`. Structure, not hand-waving.

## Style Presets

| Preset | Mood | Image Mode | Image Ratio | Corners | Shadow |
|:--|:--|:--|:--|:--|:--|
| `academic_rigorous` | Rigorous, restrained | center_float | ≤60% | 0 | none |
| `corporate_minimal` | Clean, trustworthy | hero_right | ≤40% | 8pt | soft |
| `tech_dark` | Immersive, dramatic | hero_right | ≤50% | 12pt | glow |
| `magazine_editorial` | Bold, narrative | hero_top | 50-70% | 0 | none |
| `creative_vibrant` | Playful, friendly | center_float | ≤50% | 20pt | sticker |
| `government_solemn` | Authoritative, formal | hero_top | ≤45% | 4pt | none |

## LLM Compatibility

| Model | Vision? | Works with ppt_reflex? | Notes |
|:--|:--|:--|:--|
| **DeepSeek V3 / R1** | No | ✅ Best fit | Engine provides the visual feedback DeepSeek lacks. Zero blind spots. |
| **Claude (Opus/Sonnet)** | Yes | ✅ Excellent | Vision adds bonus: Claude can review diagnostics + suggest layout tweaks. |
| **GPT-4o / GPT-4.1** | Yes | ✅ Excellent | Same as Claude. Vision is a complement, not a requirement. |
| **Gemini 2.5** | Yes | ✅ Excellent | Full compatibility. |
| **Qwen / Llama / Mistral** | Varies | ✅ Works | Any model that writes valid Python. |
| **Local models (Ollama)** | Usually no | ✅ Works | ppt_reflex was designed for this case. |

## Install

```bash
pip install python-pptx pillow
git clone https://github.com/lecutu/deepseek-ppt-maker.git
cd deepseek-ppt-maker
pip install -e .
```

Python 3.10+. Two dependencies: `python-pptx`, `Pillow`.

## Project Layout

```
ppt_reflex/
├── builder.py            # Sole AI entry point
├── style_presets.json    # 6 presets × image_layout (v2)
├── image_prompter.py     # AI image prompt generator
├── grid/
│   ├── types.py          # SemanticRole, ContentType, ElementPayload...
│   ├── plan.py           # LayoutPlan, Region, Phase1Element, DecoIntent
│   ├── canvas.py         # Three-layer canvas
│   ├── phase1.py         # Information layer layout
│   ├── phase2.py         # Decoration layer layout
│   ├── composition.py    # Global whitespace/balance/density
│   ├── aesthetics.py     # 10+ WCAG rules engine
│   ├── templates.py      # TemplateProfile + override()
│   ├── serializer.py     # Grid → python-pptx rendering
│   ├── text_metrics.py   # Pre-render text size estimation
│   └── tests/            # 46 tests
└── .claude/skills/ppt-maker/
    └── SKILL.md
```

## Design Philosophy

> **Layout is a constraint-solving problem, not a one-shot rendering problem.**

Every phase produces diagnostics, not silent mutations. The engine is the solver; the AI is the decision-maker. They communicate through structured data — no visual inspection required. This is the difference between "generate and pray" and "declare and verify."

If `build().ok` is `true`, the file is correct. Guaranteed.

---

MIT Licensed. Built for AI agents. Blind-proof by design.
