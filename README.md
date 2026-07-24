# 🧠 DeepSeek PPT Maker

> **AI Agent safely creates/fixes PowerPoint slides — Agent picks cells · Engine checks conflicts · Commit only on pass**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-54%2F54%20passing-brightgreen.svg)](ppt_reflex/grid/tests/)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-%E2%9C%93-orange)](https://deepseek.com)
[![Claude](https://img.shields.io/badge/Claude-%E2%9C%93-blueviolet)](https://anthropic.com)

**DeepSeek PPT Maker** is an open-source framework for AI agents to safely operate PowerPoint. Build professional slides with DeepSeek.

---

## 🎯 Core Idea

> **Agent says cell addresses → Engine checks conflicts in real-time → Passes before writing → Atomic commit, zero corruption**

---

## 🔥 Problems Solved

When DeepSeek (or any LLM) generates `python-pptx` code directly, three fundamental flaws emerge:

- **Element overlap** — the LLM outputs raw coordinates without knowing which regions are already occupied. Two text boxes land on the same spot, an image buries a caption. The code "writes" fine — the result is garbage.
- **No spatial awareness** — the LLM sees `(x=120, y=240)` as numbers, not "the left body area below the title." Without a spatial vocabulary, it cannot reason about layout at all.
- **No inter-element awareness** — the LLM generates each shape independently. Slide-level state is invisible to code generation — there is no way to know "there's already a chart here, move the caption elsewhere."

**DeepSeek PPT Maker** solves these at the engine level, before any file is touched:

- **Collision detection** — overlapping/overflowing elements → `try_place` pre-emptive blocking, engine judges in real-time before writing
- **Coordinate math** — agents struggle with pt coordinates → grid-address system (e.g. `A2:D5`), engine translates to precise positions
- **Element relationship awareness** — dual-layer 32×18 info grid tracks every occupied cell by `owner_id` + `content_type` + `z_order`, so the engine knows exactly who is where before accepting a placement
- **File corruption** — agents retry and overwrite repeatedly → atomic commit with auto-rollback on failure, zero file pollution
- **Aesthetics** — agents have no visual judgment → WCAG 2.1 contrast check + text overflow detection + palette compliance
- **Images** — agents can't generate visuals → built-in ImagePrompter auto-generates Midjourney/DALL·E/SD prompts
- **Model lock-in** — tied to a single LLM → supports DeepSeek / Claude / any OpenAI-compatible API

---

## 💰 DeepSeek Pricing

DeepSeek's ultra-low token pricing makes AI-powered PPT generation nearly free — a full 10-slide deck costs a fraction of a cent.

---

## 📦 Modules

```
ppt_reflex/
├── grid/                     ★ Perceptive grid canvas
│   ├── canvas.py             GridCanvas — try_place / commit / rollback
│   ├── positioning.py        Address ↔ pt coordinates (A1:D5 ⇄ 60,60,240,240)
│   ├── info_grid.py          32×18 stateful info layer + checkpoint
│   ├── matrix.py             Type × Type → BLOCK / ALLOW / WARN + z_hint
│   ├── serializer.py         Grid ↔ PPT round-trip (only file touching python-pptx)
│   ├── supply.py             Agent output layering: L0(50t)/L1(100t)/L2(60t)
│   ├── spatial.py            SpatialIndex — nearest neighbor/gap matrix/alignment groups/density heatmap
│   ├── text_metrics.py       CJK-Latin mixed text overflow estimation (±15%)
│   ├── aesthetics.py         WCAG contrast + style constraints + density/spacing/alignment
│   ├── templates.py          6 color templates + .override() custom colors
│   ├── profiles.py           Layout inference (title/body/footer/background)
│   ├── types.py              ContentType / Verdict / BLOCK_PAIRS / PlacementResult
│   └── tests/                34 tests — all green ✓
│
├── image_prompter.py         AI image prompt generator (6 types × 3 tools × 6 palettes)
├── mcp_server.py             22 MCP Tools → Agent (includes 4 grid tools)
├── reflex.py                 Master coordinator L1-L5
├── engine.py                 Geometry engine (deprecated, migrated to grid/)
├── validate.py               Day 1 closed-loop validation (100% recall / 83% precision)
├── collab_test.py            Human-AI collaboration 6-scenario test
├── test_mcp.py               19-tool end-to-end test
├── llm_agent.py              LLM decision interface (DeepSeek/Claude/OpenAI)
├── agent_loop.py             Agent repair loop
├── repair_planner.py         Deterministic repairer + simulator
└── collab_agent.py           Collaborator agent interface
```

---

## ⚡ 5-Minute Quick Start

### Install

```bash
pip install python-pptx
git clone https://github.com/lecutu/deepseek-ppt-maker.git
cd deepseek-ppt-maker
```

### DeepSeek-Powered PPT Repair

```bash
export DEEPSEEK_API_KEY="sk-your-key"
python ppt_reflex/llm_agent.py cases/broken.pptx --provider deepseek --max-slides 5

# Output:
#   PPT Reflex Agent + LLM (Provider: deepseek)
#   Slides: 5 | Max Rounds: 3
#   Slide 1: deterministic fix ✓
#   Slide 2: LLM chose: nudge_element
#   ...
#   Slides fixed: 4 | LLM successes: 3 | Token cost: ~$0.002
```

### Grid Canvas — Build New PPTs

```python
from grid import GridCanvas, GridConfig, ContentType
from grid.templates import get_template

# Pick a template (custom colors supported)
t = get_template("academic").override(accent_hex="E74C3C")

canvas = GridCanvas(GridConfig())
canvas.load("template.pptx")

result = canvas.try_place("body-01", ContentType.TEXT, ["A2", "B2", "A3", "B3"])

if result.allowed:
    canvas.commit("output.pptx")
else:
    print(f"BLOCKED: {result.conflicts}")
    print(f"Try: {result.free_suggestion}")
```

### MCP Server — Direct Agent Access

```bash
python ppt_reflex/mcp_server.py             # stdio mode
python ppt_reflex/mcp_server.py --port 8081 # HTTP mode
```

| Tool | Purpose |
|:--|:--|
| `element_summary` | List all elements on slide |
| `audit_slide` | Full audit (7 rule categories) |
| `try_place` | **★ Pre-emptive blocking — Agent picks cells, engine judges conflicts** |
| `commit_grid` | Atomic PPT write |
| `rollback_grid` | Revert to checkpoint |
| `grid_snapshot` | Layered output L0/L1/L2 |
| `apply_layout` | Apply one of 8 layout templates |
| `move_element` | Move element (with revision optimistic lock) |
| `local_context` | Element + neighbor context |
| `lock_element` | Lock template decoration from modification |
| ... | 22 tools total |

### AI Image Prompt Generator

```python
from ppt_reflex.image_prompter import ImagePrompter

p = ImagePrompter(template="academic")
r = p.generate(
    "SiOC anode charge-discharge mechanism diagram",
    image_type="scientific_diagram",
    provider="midjourney"
)
print(r.full_prompt)
# → "SiOC anode charge-discharge mechanism diagram, clean scientific illustration,
#    technical diagram, white background, color scheme: deep navy blue
#    and muted brick red accents --ar 16:9 --v 6.1"
```

6 types × 3 tools (Midjourney / DALL·E / SD) × 6 palette auto-matching.

---

## 🏗️ Architecture

### Dual-Layer Grid

```
┌─────────────────────────────────────────────────────┐
│ Positioning Layer (16×9, 60pt/cell, A1..P9)        │
│ ★ The language agents speak                         │
│ "body at A2:D5, figure at E2:H6"                    │
│ Engine translates → pt coords, ~425 tokens/slide    │
├─────────────────────────────────────────────────────┤
│ Info Layer (32×18, 30pt/cell, internal)            │
│ ★ Engine's perception map                           │
│ Each cell = {owner_id, content_type, z, locked}     │
│ try_place scans → finds conflict → blocks           │
└─────────────────────────────────────────────────────┘
```

### Collision Matrix

|  | TEXT | TEXTBOX | IMAGE | TABLE | CHART |
|:--|:--:|:--:|:--:|:--:|:--:|
| **TEXT** | ❌ BLOCK | ✅ | ❌ | ❌ | ❌ |
| **TEXTBOX** | ✅ | ❌ BLOCK | ✅ | ✅ | ✅ |
| **IMAGE** | ❌ | ✅ | ✅ | ❌ | ❌ |
| **TABLE** | ❌ | ✅ | ❌ | ❌ | ❌ |
| **CHART** | ❌ | ✅ | ❌ | ❌ | ❌ |

Only 8 truly problematic pairs are blocked. Everything else passes.

### try_place — Real-Time Spatial Awareness

When raw LLM code runs `slide.shapes.add_textbox(x=120, y=240, ...)`, it writes blindly — no knowledge of what's already there. `try_place` gives the engine spatial awareness before any element lands:

```
Agent says: "body at A2:D6"
  → cells_to_bbox → bbox boundary check
  → scan info layer 32×18 grid (every occupied cell tracked)
  → collision matrix: TEXT on TEXT? → BLOCK
  → PlacementResult {verdict, conflicts, z_hint, free_suggestion}
```

The engine sees every element's footprint, content type, and z-order — as a real-time perceptive map. No blind writes.

### Atomic Writes

```
try_place → passes → info layer staged
→ commit() → write temp file → os.replace() → confirm checkpoint
→ fails → rollback() → info layer restored → PPT file never touched
```

---

## 🎨 6 Color Templates

| Template | BG | Primary | Accent | Contrast | Use Case |
|:--|:--|:--|:--|:--|:--|
| `academic` | `#FFFFFF` White | `#1B3A5C` Navy | `#C0392B` Brick | 13.8:1 | Papers / Defense / Seminars |
| `business` | `#FFFFFF` White | `#0052D9` Blue | `#ED7B2F` Orange | 12.6:1 | Reports / Reviews |
| `minimal` | `#FFFFFF` White | `#2D5BD7` Blue | `#FF4757` Red | 14.3:1 | Talks / Lightning |
| `data_report` | `#FFFFFF` White | `#1976D2` Blue | `#F57C00` Orange | 16.1:1 | Annual / Analytics |
| `teaching` | `#FFFDF5` Warm | `#2196F3` Blue | `#FF9800` Orange | 12.4:1 | Courses / Training |
| `product` | `#1D1D1F` Dark | `#6366F1` Indigo | `#8B5CF6` Purple | 13.8:1 | Brand / Launch |

Custom colors in one line:

```python
from grid.templates import get_template
t = get_template("academic").override(bg_hex="FAFAFA", accent_hex="E74C3C")
```

---

## 🧪 Tests

```bash
python -m pytest ppt_reflex/grid/tests/ -v   # 34 tests
python ppt_reflex/test_mcp.py                # 19 tools
python ppt_reflex/collab_test.py             # 6 scenarios
python ppt_reflex/validate.py                # detection performance
```

| Suite | Result |
|:--|:--|
| `test_positioning.py` (8) | ✅ Address ↔ pt round-trip consistent |
| `test_matrix.py` (5) | ✅ BLOCK/ALLOW/WARN/z_hint |
| `test_canvas.py` (8) | ✅ try_place/commit/rollback |
| `test_serializer.py` (7) | ✅ Grid ↔ PPT density 0.134 ⇄ 0.134 |
| `test_supply.py` (3) | ✅ L0/L1/L2 token budget |
| `test_profiles.py` (3) | ✅ Layout inference |
| `test_aesthetics.py` (5) | ✅ WCAG + style constraints |
| `test_templates.py` (1) | ✅ 6 templates CR ≥ 12.4:1 |
| `test_mcp.py` (19) | ✅ All MCP tools |
| `collab_test.py` (6) | ✅ Human-AI collaboration |

---

## 🔧 Agent Prompt

```
You are a PPT layout agent using Grid Canvas:

Available operations:
- grid_snapshot(level=0) get slide overview (~50 tokens)
- try_place(element_id, content_type, cells) attempt placement → engine judges conflicts
- commit(ppt_path) atomic PPT write
- rollback() revert last operation

content_type: TEXT | TEXTBOX | IMAGE | TABLE | CHART | SHAPE | ANNOTATION | TITLE

Rules:
- Use Excel-style cell addresses: "A2:D5" = rectangle from A2 to D5
- Never violate BLOCK_PAIRS
- Backgrounds: no pure black (#000)
- Body text: #222-#444 dark gray range, font ≥ 14pt
```

---

## 📐 Engineering References

| Source | Concept | Mapping |
|:--|:--|:--|
| **Unity Physics2D** | Layer Collision Matrix | → Collision matrix (BLOCK_PAIRS) |
| **CSS Grid Layout** | grid-template-areas naming | → Positioning layer A1..P9 |
| **PCB Design Rules** | online DRC + batch DRC | → try_place (real-time) + audit (global) |
| **Figma Auto Layout** | Alignment + spacing + constraints | → Alignment hints + density heatmap |

---

## 🗺️ Roadmap

- [x] Dual-layer grid (16×9 + 32×18)
- [x] Collision matrix (6 ContentType × 8 BLOCK_PAIRS)
- [x] try_place / commit / rollback
- [x] Agent output layering (L0/L1/L2)
- [x] AI image prompt generator (ImagePrompter)
- [x] WCAG 2.1 aesthetics engine
- [x] 6 templates + custom color override
- [x] MCP Server (22 tools)
- [x] DeepSeek / Claude / OpenAI multi-LLM support
- [x] Atomic write + checkpoint/rollback
- [ ] OfficeCLI render integration (screenshot preview)
- [ ] Multi-slide consistency validation
- [ ] Template reverse recognition (PPT → TemplateProfile)
- [ ] Chart data binding (CSV → Chart)
- [ ] PPT ↔ Markdown bidirectional conversion
- [ ] Web UI (React grid canvas)

---

## 🤝 Contribute

MIT License — use freely, modify, commercial use. PRs welcome.

---

**DeepSeek powered · Agent picks cells · Engine judges conflicts · Commit on pass.**
