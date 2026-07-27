# ppt_reflex — Blind-Proof PowerPoint. No Vision Needed.

**DeepSeek can't see images. Every LLM is blind to its own `.pptx` output — it writes code, crosses its fingers, and hopes. Other tools solve this by making the AI guess harder. ppt_reflex doesn't guess. It runs a real constraint-solving engine, returns structured diagnostics the AI can read and act on, and guarantees visual correctness before the file is written.**

The key insight: it's not a one-way pipeline. It's a **closed loop**. AI declares intent → engine computes layout → engine returns per-element diagnostics → AI reads them, decides what to fix → re-enters the pipeline. The AI doesn't need to see. It needs to read. And every LLM — DeepSeek included — can read structured JSON.

## The Agent-Engine Loop

```
┌─────────────────────────────────────────────────────────┐
│                    AI AGENT                             │
│  "title centered, image contain-fit,                     │
│   dark box for key finding, 3 bullets below"            │
│                       │                                  │
│            declares intent (PPTBuilder)                 │
│                       ▼                                  │
│  ┌─────────────────────────────────────────────┐        │
│  │              ENGINE                          │        │
│  │  Three-layer canvas / five-phase pipeline    │        │
│  │  Rendering not yet executed                 │        │
│  │                       │                      │        │
│  │  Computes: geometry · contrast · overflow    │        │
│  │  Returns: per-element diagnostics            │        │
│  │                       ▼                      │        │
│  │  { "overflow_v": 12pt, "elem": "box_3",      │        │
│  │    "fixes": ["shrink → 11pt",                │        │
│  │              "widen → +40pt"] }              │        │
│  └─────────────────────────────────────────────┘        │
│                       │                                  │
│            AI reads diagnostics                         │
│            AI decides: "widen to +40pt"                 │
│            AI re-enters pipeline                        │
│                       │                                  │
│                       ▼                                  │
│            Engine renders → .pptx                       │
│            build().ok == true → guaranteed correct      │
└─────────────────────────────────────────────────────────┘
```

**This is the DeepSeek difference.** A vision model sees the output and says "looks wrong." DeepSeek has no vision — but it doesn't need it. The engine provides machine-readable diagnostics at every phase. DeepSeek reads them like a compiler reading warnings, chooses the fix, and re-runs. The loop closes.

Claude and GPT-4o can do this too. Vision is a bonus, not a dependency.

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
| **Overflow detected, not hidden** | `text_metrics` pre-estimates rendered dimensions of every string. Reports `overflow_v` / `overflow_h` with fix options. |
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
┌───────────────────────────────────────────────────┐
│             FIVE-PHASE PIPELINE                    │
│  Phase 0   — intent → LayoutPlan                  │
│  Phase 0.5 — region validation                    │
│  Phase 1   — info layer: stack/inline placement    │
│  Phase 2   — decoration: arrow routing            │
│  Phase 2.5 — global composition: whitespace/density│
│       │                                            │
│  AestheticsEngine (10+ WCAG rules)                │
│  Pre-commit validation                            │
│       │                                            │
│       ▼                                            │
│  Structured diagnostics → AI reads, decides, loops │
│       │                                            │
│       ▼                                            │
│  _render_slide() → .pptx                          │
└───────────────────────────────────────────────────┘
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
| **DeepSeek V3 / R1** | No | ✅ Best | Reads diagnostics → decides fix → re-enters. No vision needed. |
| **Claude (Opus/Sonnet)** | Yes | ✅ Excellent | Vision adds bonus: sees the slide, correlates with diagnostics. |
| **GPT-4o / GPT-4.1** | Yes | ✅ Excellent | Same. Structured output mode maps directly to diagnostic schema. |
| **Gemini 2.5** | Yes | ✅ Excellent | Full compatibility. |
| **Qwen / Llama / Mistral** | Varies | ✅ Works | Any model that writes Python and reads JSON. |
| **Ollama / local models** | Usually no | ✅ Works | Designed for this. The loop works entirely through text. |

## Style Presets

| Preset | Mood | Image Mode | Image Ratio | Corners |
|:--|:--|:--|:--|:--|
| `academic_rigorous` | Rigorous, restrained | center_float | ≤60% | 0 |
| `corporate_minimal` | Clean, trustworthy | hero_right | ≤40% | 8pt |
| `tech_dark` | Immersive, dramatic | hero_right | ≤50% | 12pt |
| `magazine_editorial` | Bold, narrative | hero_top | 50–70% | 0 |
| `creative_vibrant` | Playful, friendly | center_float | ≤50% | 20pt |
| `government_solemn` | Authoritative, formal | hero_top | ≤45% | 4pt |

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
├── grid/
│   ├── types.py          # 30+ types: SemanticRole, ContentType...
│   ├── plan.py           # LayoutPlan, Region, ElementPayload
│   ├── canvas.py         # Three-layer canvas
│   ├── phase1.py         # Info layer: stack/inline placement
│   ├── phase2.py         # Decoration: arrow routing
│   ├── composition.py    # Global whitespace/balance/density
│   ├── aesthetics.py     # 10+ WCAG rules engine
│   ├── templates.py      # 6 TemplateProfiles + override()
│   ├── serializer.py     # Grid → python-pptx rendering
│   ├── text_metrics.py   # Pre-render text size estimation
│   ├── orchestrator.py   # Diagnostic repair loop
│   └── tests/            # 46 tests
└── .claude/skills/ppt-maker/
    └── SKILL.md
```

## Design Philosophy

> **The engine computes truth and returns options. It never silently mutates the AI's declarations.**

This is not a "generate and pray" system. It's a declarative constraint solver with a text-based diagnostics channel. AI declares what it wants. Engine computes what's possible. Diagnostics flow back as structured data. AI decides. Loop closes. Every LLM — vision or no vision — can participate.

If `build().ok` is `true`, the file is visually correct. Guaranteed. No `.pptx` renderer required.

---

MIT Licensed. Built for AI agents. Blind-proof by design.
