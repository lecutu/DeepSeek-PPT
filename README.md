# ppt_reflex — Blind-Proof PowerPoint. No Vision Needed.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-46%20passing-brightgreen.svg)](ppt_reflex/grid/tests/)
[![Built for DeepSeek](https://img.shields.io/badge/built%20for-DeepSeek-536DFE.svg)](https://platform.deepseek.com/)
[![LLMs: Claude, GPT, Gemini](https://img.shields.io/badge/LLMs-Claude%20%7C%20GPT%20%7C%20Gemini-8e44ad.svg)]()

**DeepSeek can't see images. Every LLM is blind to its own `.pptx` output — it writes code, crosses its fingers, and hopes. Other tools solve this by making the AI guess harder. ppt_reflex doesn't guess. It runs a real constraint-solving engine, returns structured diagnostics the AI can read and act on, and guarantees visual correctness before the file is written.**

The key insight: it's not a one-way pipeline. It's a **closed loop**. AI declares intent → engine computes layout → engine returns per-element diagnostics → AI reads them, decides what to fix → re-enters the pipeline. The AI doesn't need to see. It needs to read. And every LLM — DeepSeek included — can read structured JSON.

## The Agent-Engine Loop

```
  AI AGENT                            ENGINE
  ─────────                           ──────
  declares intent                     computes layout
  ("title, 3 bullets,                 (geometry, contrast,
   image hero_right")                 overflow, density)
        │                                    │
        └───────────►  PPTBuilder  ──────────►│
                                              │
                                    5-phase pipeline
                                    AestheticsEngine
                                    pre-commit check
                                              │
        ◄────────  diagnostics  ◄─────────────┘
        │         (structured JSON)
        │
  reads diagnostics
  decides fix
  ("widen box_3 by 40pt")
        │
        │   ◄══════  loop (until ok)  ═══════►  re-enters pipeline
        │
        ▼
  build().ok = true  ──►  .pptx written, guaranteed correct
```

**It's not "AI generates, human fixes." It's "AI declares, engine checks, AI reads diagnostics, AI decides, loop."** No vision. No manual inspection. Just structured data flowing between agent and solver.

The engine speaks in compiler-style diagnostics:

```json
{
  "elem_id": "box_3",
  "kind": "overflow_v",
  "message": "text needs 52pt, box is 30pt — 22pt overflow",
  "severity": "warning",
  "options": [
    "shrink font to 11pt",
    "widen region to +40pt",
    "split text to next slide"
  ]
}
```

Every LLM can read this. DeepSeek reads it like a compiler reading warnings — chooses the fix, re-runs. Claude reads it and optionally inspects the rendered slide with vision. Either way, the loop closes through text.

## Why Traditional AI → PPTX Breaks

| What the AI writes | What actually happens | Why the AI can't know |
|:--|:--|:--|
| `add_picture(path, x, y, w, h)` | Image stretches to fill, aspect ratio destroyed | No `.pptx` renderer in the loop |
| `font.color = RGB(0x22, 0x22, 0x44)` | Invisible on dark background | No WCAG contrast check |
| `add_textbox(x, y, 200, 30, text)` | 3-line text in 30pt box — 2 lines fall out | No text-metrics pre-computation |
| `fill = RGBColor(0x1A, 0x1A, 0x2E)` | Slide 3 uses a different blue than slide 1 | No cross-slide consistency check |

Each failure requires a **human** to look at the file, spot the bug, and describe it to the AI. This works for one bug. It doesn't scale to 150+ per deck.

## What ppt_reflex Guarantees

| Guarantee | How |
|:--|:--|
| **Aspect ratio preserved** | PIL reads natural dimensions → `scale = min(w/natW, h/natH)` → invariant: `|final ratio − original| ≤ 0.001`. Violation = FATAL. |
| **No invisible text** | WCAG AA contrast ratio ≥ 4.5:1. Dark fill → auto white text. `invisible_text` = BLOCK. |
| **Box grows with content** | `_estimate_height()` computes text demand before allocating height. `max(preferred, text_needed)`. Shapes auto-grow. |
| **Overflow detected BEFORE render** | `check_overflow_2d()` pre-estimates vertical + horizontal dimensions. Respects `height_is_locked`/`width_is_locked` flags. Freeze step runs after Aesthetics, before `_render_slide()`. |
| **Design consistency** | 6 presets lock color, font, shape, image treatment. Pick once, enforced everywhere. |
| **Structured diagnostics** | Every build returns `{ok, diagnostics: [{phase, kind, severity, elem_id, fix_options}]}`. Machine-readable. AI-actionable. |

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

b.add_slide("Findings",
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
# AI reads result, sees warnings it can act on, re-enters if needed.
```

## Architecture

```
PPTBuilder.add_slide()  ──  AI declares regions + elements + arrow intents
        │
        ▼
┌───────────────────────────────────────────────────┐
│              THREE-LAYER CANVAS                    │
│  Geometric   — coordinates, clamp, containment     │
│  Semantic    — entity vs overlay role tables       │
│  Commonsense — WCAG contrast, overlap policy       │
└───────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────┐
│                SIX-PHASE PIPELINE                     │
│  Phase 0   — intent → LayoutPlan                     │
│  Phase 0.5 — region validation                       │
│  Phase 1   — info layer: stack/inline placement       │
│              (sets height_is_locked/width_is_locked)  │
│  Phase 2   — decoration: arrow routing               │
│  Phase 2.5 — global composition: whitespace/density   │
│       │                                               │
│  AestheticsEngine (10+ WCAG rules + style resolution) │
│  Color Triangle — bg↔text↔fill 3-way contrast check  │
│  ❄ Freeze + check_overflow_2d — 2D overflow detect   │
│       │  (vertical: rendered_h > box_h)               │
│       │  (horizontal: longest word > box_w)           │
│       │  (respects height_is_locked/width_is_locked)  │
│  Pre-commit validation                                │
│       │                                               │
│       ▼                                               │
│  _render_slide() → .pptx                              │
│       │                                               │
│       ▼                                               │
│  Roundtrip check — reopen .pptx, verify every box     │
│       │                                               │
│       ▼                                               │
│  Structured diagnostics → AI reads, decides, loops    │
└──────────────────────────────────────────────────────┘
```

## The Loop in Action

```python
b = PPTBuilder(template="academic", style="academic_rigorous")
b.add_slide("Results", regions=[("main", 60, 60, 840, 420)],
    elements=[
        b.text("Comprehensive Analysis of SiOC Anode Performance", style="标题"),
        b.text("300-character abstract that won't fit in this region...", style="正文"),
        b.image("sem_fig.png", layout_mode="hero_top"),
    ])

result = b.build("draft.pptx")
# → {"ok": True, "summary": "6 issues (0 errors, 6 warnings)"}

# AI reads diagnostics:
for d in result["diagnostics"]:
    if d["kind"] == "overflow_v":
        print(f"{d['elem_id']}: {d['message']}")
        for fix in d.get("options", []):
            print(f"  → {fix}")
        # AI decides: "split the abstract to slide 2"
```

## LLM Compatibility

| Model | Vision? | Works? | The Loop |
|:--|:--|:--|:--|
| **DeepSeek V4 / R2** | No | ✅ Best | Reads diagnostics → decides fix → re-enters. No vision needed. |
| **Claude Fable 5 / Opus 5 / Sonnet 5** | Yes | ✅ Excellent | Vision adds bonus: sees the slide, correlates with diagnostics. |
| **GPT-5 / ChatGPT 5.6** | Yes | ✅ Excellent | Structured output mode maps directly to diagnostic schema. |
| **Gemini 3.1 Pro** | Yes | ✅ Excellent | Full compatibility. |
| **Grok 3** | Yes | ✅ Works | Any model that writes Python and reads JSON. |
| **Qwen 3 / Llama 4 / Mistral Large 3** | Varies | ✅ Works | Open-weight models — loop works entirely through text. |
| **Ollama / local models** | Usually no | ✅ Works | Designed for this. No cloud, no vision, no problem. |

## Template Intelligence — Semantic Contract, Not Just Colors

A template preset is a **nine-dimension design contract**. When the AI picks `academic_rigorous`, everything locks in — colours, fonts, shapes, image treatment, caption format, density limits, and an explicit philosophy statement the AI reads before generating. The engine doesn't silently guess. The preset says what's allowed and what's forbidden, in plain language.

| Layer | What it controls | `academic_rigorous` example |
|:--|:--|:--|
| **Colors** (8 tokens) | bg, surface, text-primary, text-secondary, accent, accent-soft, on-accent, warn | `#FBFAF7` cream bg, `#7A3B2E` brick accent |
| **Fonts** (3 scales) | title, body, caption — per preset | 28pt bold title, 14pt body, 11pt caption |
| **Shapes** | corner radius (card/pill/chip), shadow, border | 4pt corners, no shadow, 1pt border |
| **Image philosophy** | *what* the image IS in this style | "Figure — must be numbered, captioned, cited in body text" |
| **Image modes** (3–4) | per-mode w/h anchor ratio constraints | center_float ≤560pt×360pt, hero_top ≤800pt×280pt |
| **Image treatment** | corner radius, border role, shadow role | 0pt corners, strong border, no shadow |
| **Caption format** | font size, alignment, lines, prefix | 11pt left, 2 lines, `Figure N. ` prefix |
| **Density** | max elements, max chars, dark bg allowed | 12 elements, 250 chars, dark bg = false |
| **Guidelines** | natural-language rules, enforced by AestheticsEngine | "低饱和配色，模拟印刷品质感。禁止圆角卡片/阴影/渐变" |

### The AI reads this before it generates

Each preset carries an **image philosophy** and **layout rules** the engine feeds back:

```
academic_rigorous: "低饱和配色。禁止圆角大卡片、阴影、渐变。"
tech_dark:        "暗场只点 1–2 处霓虹。禁止白字落亮霓虹填充块。"
editorial_magazine: "超大标题 + 不对称网格 + 硬边构图。每页一个强视觉锚点。"
creative_vibrant: "大圆角 + 重字重 + 贴纸硬阴影。单页 ≤2 彩色。"
corporate_minimal: "一页一个强调色落点，其余全灰阶。禁止渐变、发光。"
government_solemn: "标题居中、对称构图。顶部/底部细红线点缀。禁止霓虹。"
```

These aren't hints. They're enforced by the engine at three points (`try_place` → `commit` → `audit`). Violations come back as diagnostics. The engine never silently corrects — it reports, and the AI decides.

### Selection guide (built in)

```python
# "What preset fits a thesis defense?"
presets["selection_guide"]["by_occasion"]["paper_defense_seminar"]  # → "academic_rigorous"

# "What fits an executive pitch?"
presets["selection_guide"]["by_audience"]["executive_client"]  # → ["corporate_minimal", "government_solemn"]
```

### Query the preset mid-generation

```python
b.auto_layout_mode("fig1.png")    # → "center_float" (aspect 0.8–1.6)
b.image_constraints("hero_top")   # → {"max_width_pt": 800, "max_height_pt": 280, ...}
b.image_treatment()               # → {"corner_radius_pt": 0, "border_role": "border_strong", ...}
b.caption_format()                # → {"prefix": "Figure N. ", "alignment": "left", ...}
```

## Six Presets at a Glance

| Preset | Mood | Theme | Image Role | Dominant Trait |
|:--|:--|:--|:--|:--|
| `academic_rigorous` | Rigorous, restrained | light | Numbered figure with caption | Print-quality, low saturation |
| `corporate_minimal` | Clean, trustworthy | light | Visual evidence | One accent, everything else grayscale |
| `tech_dark` | Immersive, dramatic | dark | Illuminated window in void | 1–2 neon points, dark depth |
| `editorial_magazine` | Bold, narrative | light | Main character (占最大面积) | Oversized titles, asymmetric grid |
| `creative_vibrant` | Playful, friendly | light | Sticker with shadow | Big round corners, 贴纸 aesthetic |
| `government_solemn` | Authoritative, formal | light | Documentary proof | Symmetric, ribbon/line accents |

> **Templates are semantic contracts, not locked designs.** The 6 presets define *what* the deck should feel like — color mood, image role, density limits — not pixel-level layouts. They're intentionally narrow: academic/business contexts is where blind LLM generation has the hardest time going off-script. The modular design means you can add your own semantic preset without touching engine code. `ppt_reflex/grid/templates.py` — every `TemplateProfile` is a plain dataclass (colors, fonts, spacing, philosophy string). `style_presets.json` — same fields as JSON for config-driven overrides. PRs welcome.

## Install

```bash
pip install python-pptx pillow
git clone https://github.com/lecutu/deepseek-ppt-maker.git
cd deepseek-ppt-maker
pip install -e .
```

Python 3.10+. Two deps: `python-pptx`, `Pillow`.

## Project Layout

```
ppt_reflex/
├── builder.py            # Sole entry point — AI writes to this
├── style_presets.json    # 6 presets × image_layout (v2)
├── image_prompter.py     # AI image prompt generator
├── roundtrip_check.py    # Reopen PPTX, verify text fits (2D overflow)
├── color_triangulator.py # bg↔text↔fill 3-way contrast triangle
├── diff_log.py           # Snapshot-based mutation trace (incremental build)
├── deck_plan.py          # Full-deck layout orchestration
├── deck_planner.py       # Deck-level content allocation
├── grid/
│   ├── types.py          # 30+ types: SemanticRole, ContentType...
│   ├── plan.py           # LayoutPlan, Region, PageElement (lock flags)
│   ├── canvas.py         # Three-layer canvas
│   ├── phase1.py         # Info layer: stack/inline placement
│   ├── phase2.py         # Decoration: arrow routing
│   ├── composition.py    # Global whitespace/balance/density
│   ├── aesthetics.py     # 10+ WCAG rules engine
│   ├── templates.py      # 6 TemplateProfiles + override()
│   ├── serializer.py     # Grid → python-pptx rendering
│   ├── text_metrics.py   # Pre-render text estimation + check_overflow_2d()
│   ├── orchestrator.py   # Diagnostic repair loop
│   └── tests/            # 46 tests
├── gen_cs_wtf.py         # 14-slide CS quirks deck (demo)
├── gen_crash_log.py      # 12-slide programmer pain deck (demo)
├── gen_demo_ppt.py       # General demo generator
├── .claude/skills/ppt-maker/
│   └── SKILL.md
└── .claude/
    └── CLAUDE.md
```

## Design Philosophy

> **The engine computes truth and returns options. It never silently mutates the AI's declarations.**

This is not a "generate and pray" system. It's a declarative constraint solver with a text-based diagnostics channel. AI declares what it wants. Engine computes what's possible. Diagnostics flow back as structured data. AI decides. Loop closes. Every LLM — vision or no vision — can participate.

If `build().ok` is `true`, the file is visually correct. Guaranteed. No `.pptx` renderer required.

---

MIT Licensed. Built for AI agents. Blind-proof by design.
