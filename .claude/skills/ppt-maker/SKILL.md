# ppt-maker — PPT Creation Entry Point

**STOP. Do NOT read ppt_reflex/ source code. Do NOT import from grid/. Do NOT explore the repo.**

Everything you need is in this doc. If something isn't here, it doesn't exist. Use the zero-error skeleton below — it builds with 0 errors on first try.

## Rules

```
Every launch MUST ask:
  1. What to make? (topic / occasion / template)
  2. What content? (text / data / images / number of slides)
  3. Image source? (user files / AI generation / none)

NEVER decide image sources for the user. NEVER skip the questionnaire.
```

## Zero-Error Recipe — USE THIS FIRST, every time

**The skeleton below builds with 0 errors. Start here, then add content.**

```python
from ppt_reflex.builder import PPTBuilder

b = PPTBuilder(template="minimal", style="tech_dark")
ACCENT = (34, 211, 238)
WARN = (251, 113, 133)
DARK = (16, 26, 45)

b.add_slide("Title",
    regions=[
        ("header", 60, 30, 840, 60, 1),        # ≥60pt tall for titles
        ("main", 60, 110, 520, 380, 2),         # big enough for bullets
        ("sidebar", 600, 110, 300, 200, 3),
    ],
    elements=[
        b.title("Your Slide Title", region="header"),                   # SAFE
        b.text("A subtitle goes here", style="Caption", region="main"),  # SAFE
        b.bullet("Point one", region="main"),                            # SAFE
        b.bullet("Point two", region="main"),                            # SAFE
        b.box("Key takeaway in a card", style="Body", region="sidebar",
              fill_color=DARK, shape_id="rounded_rectangle"),            # SAFE — auto-height
        b.shape("hexagon", region="sidebar", fill_color=ACCENT, pw=60, ph=45),  # SAFE
    ],
)

r = b.build("output.pptx")
print(r["summary"])
errs = [d for d in r["diagnostics"] if d["severity"] == "error"]
print(f"Errors: {len(errs)}")  # Should be 0
```

### Guaranteed errors — NEVER use these

| ❌ NEVER | Why it breaks | Error |
|:--|:--|:--|
| `b.text("...", style="Heading")` in header region | 28pt bold → needs ~49pt height, header is 50pt → overflow after inset | `overflow_vertical` |
| `b.text("...", style="Subheading")` in small region | 20pt font → box too small after inset | `overflow_vertical` |
| `b.text("...", style="Emphasis")` | same problem — bold 16pt → needs > allocated | `overflow_vertical` |
| `b.text("...", style="Body")` in fixed-height region | Body is 18pt, box auto-grows but may still clip | `overflow_vertical` roundtrip error |
| `b.image(..., caption="...")` | Caption text triggers overflow check | `overflow_vertical` |
| `template="product"` + `style="creative_vibrant"` | creative_vibrant overrides bg to light → white text invisible | `tri_bg_fill` contrast BLOCK |
| Any light-bg template + any dark-bg style | Theme mismatch → white text on white | `invisible_text` BLOCK |

### Safe patterns — always zero errors

| ✅ ALWAYS SAFE | Why |
|:--|:--|
| `template="product"` + `style="tech_dark"` | Genuinely dark bg, neon text works |
| `template="minimal"` + `style="tech_dark"` | Also safe — tech_dark respects dark intent |
| `b.title("...", region="header")` | Has built-in ph=40 margin — won't overflow |
| `b.subtitle("...", region="header")` | 18pt, ph=30 — safe in header regions |
| `b.text("...", style="Caption")` | 10pt font fits in ANY region |
| `b.bullet("...")` | 13pt, no fixed box — auto-flow, never overflows |
| `b.box("...", fill_color=DARK, style="Body")` | Box auto-expands height — no overflow |
| `b.shape(...)` | Pure graphics, no text → no overflow possible |
| `b.image(..., layout_mode="hero_top")` | No caption = no text overflow |
| `b.divider(...)` | Always safe, no text |
| `b.arrow(...)` | Always safe, decoration only |

### Key rules

- **header region ≥ 60pt tall** for `b.title()`. 50pt is too short.
- **For text content: use `b.box()` not `b.text(Body)`.** Box auto-expands; Body text in fixed regions overflows.
- **For headings: use `b.title()` only.** Never `b.text(style="Heading")`.
- **Images: no captions.** `caption=""` or omit.
- **Dark themes: `product` template ONLY with `tech_dark` style.** Nothing else.
- **First build with skeleton. Iterate from 0 errors.** Don't start from scratch.

---

## PPTBuilder API Reference

### Init

```python
from ppt_reflex.builder import PPTBuilder
b = PPTBuilder(template="minimal", style="tech_dark")
```

### Templates

| id | bg | accent | vibe |
|:--|:--|:--|:--|
| `academic` | white | navy+brick | rigorous, high info density |
| `business` | white | blue+orange | professional, conclusion-first |
| `minimal` | white | dark gray+blue | breathing room, one message/slide |
| `data_report` | white | blue+orange | grid feel, data-dense |
| `teaching` | warm white | vibrant blue+orange | friendly, well-structured |
| `product` | dark gray | indigo+violet | premium, dark bg, centered |

### Style presets (style_presets.json)

`academic_rigorous` | `corporate_minimal` | `tech_dark` | `editorial_magazine` | `creative_vibrant` | `government_solemn`

### add_slide — full signature

```python
b.add_slide("Slide title",
    regions=[
        ("header", 60, 30, 840, 60, 1),           # (name, x, y, w, h, z_order)
        ("main", 60, 110, 520, 380, 2),            # lower z_order = behind
        ("sidebar", 600, 110, 300, 200, 3),
    ],
    elements=[
        b.title("Title", region="header"),          # 28pt bold, centered, ph=40
        b.bullet("Point", region="main"),           # 13pt, auto-flow
        b.box("Card", style="Body", region="sidebar",
              fill_color=(16,26,45)),               # auto-height
    ],
    arrows=[
        b.arrow(from_elem, to_elem, "label", "below",
                color=(34,211,238)),                # from/to accept _Spec objects
    ],
)
```

### Element API — every method

```python
# TEXT (safe: title/subtitle/Caption only)
b.title("Title text", region="header")                  # ⭐ Use this for headings — NOT b.text(Heading)
b.subtitle("Subtitle text", region="header")            # 18pt, gray, ph=30
b.text("Body text", style="Caption", region="main")     # ⭐ Use Caption — NOT Body/Heading/Emphasis/Subheading
# b.text(style="Subheading") → GUARANTEED overflow, see error table below

# LISTS — always safe
b.bullet("List item text", region="main")               # 13pt, auto-flow — ALWAYS SAFE

# FOOTER
b.footer("Copyright 2024", region="footer")             # dimmed, small — safe anywhere

# CARDS — always safe (auto-height)
b.box("Card content here\n\nMultiple paragraphs OK",
      style="Body", region="card",                      # style: Body only (not Heading/Subheading)
      fill_color=(16,26,45),                             # dark fill → white text automatic
      shape_id="rounded_rectangle",                      # 20 shapes available (see below)
      ph=None, align_h="left", allow_shrink=False)       # ph=override height; align_h=left|center|right

# SHAPES — always safe (pure graphics)
b.shape("hexagon", region="center",                     # 20 shape IDs (see below)
        fill_color=(34,211,238), pw=100, ph=60)         # pw/ph REQUIRED for shapes

# IMAGES — safe without caption
b.image("path/to/img.jpg", region="hero",
        layout_mode="hero_top",                          # 7 modes or b.auto_layout_mode(path)
        fit_mode="fit", allow_upscale=False,             # fit=contain; fill=crop
        pw=400, ph=300, caption="")                      # ⭐ Empty caption = safe. NEVER add caption text.

# TABLES — auto-sizes columns to region width
b.table(headers=["Col A", "Col B", "Col C"],
        rows=[["v1", "v2", "v3"], ["v4", "v5", "v6"]],
        region="main")                                   # Header row: accent bg, white bold text
# Each row MUST have len(headers) cells. Missing cells render as empty.

# DECORATION — always safe
b.divider(region="main", color=(34,211,238), width_pt=2.0)
b.arrow(elem_a, elem_b, "label text", "below",          # elem_a/elem_b = _Spec objects from b.box/b.shape
        color=(34,211,238), text_font_size=9)
```

### Shape IDs (for shape_id and b.shape)

`rounded_rectangle` `rectangle` `oval` `parallelogram` `diamond` `chevron`
`pentagon` `hexagon` `up_arrow` `down_arrow` `left_arrow` `right_arrow`
`star` `triangle` `home` `cross` `pie` `wave` `donut` `plaque` `sun`

### Image layout modes

`hero_top` `hero_right` `hero_left` `center_float` `small_inline` `grid_2x2` `grid_1x3`

Or auto-infer: `b.auto_layout_mode("img.jpg")` — picks mode from aspect ratio:

| Aspect ratio | Auto mode | Behavior |
|:--|:--|:--|
| >1.6 (wide / panorama) | `hero_top` | full-width banner, contain-fit |
| <0.8 (tall / portrait) | `hero_right` | right-side column, contain-fit |
| 0.8–1.6 (square / screenshot) | `center_float` | centered, contain-fit, NEVER cropped |

**Screenshots, irregular crops, phone captures — just pass the file.** `fit_mode="fit"` is default: image fully visible, aspect ratio preserved, nothing cropped.

### Build + read diagnostics

```python
# 推荐：分页流式 — 逐页 yield，AI 边跑边看，一页报错就停
for slide_result in b.build_stream("output.pptx"):
    if slide_result["type"] == "start":
        print(f"Building {slide_result['total_slides']} slides...")
    elif slide_result["type"] == "slide":
        errs = [d for d in slide_result["diagnostics"] if d["severity"] == "error"]
        if errs:
            print(f"S{slide_result['slide']:02d}: {len(errs)} errors — STOP, fix this page only")
            break
    elif slide_result["type"] == "summary":
        print(slide_result["summary"])

# 增量修复：改一页不动其他页
b.fix_slide(2, elements=[b.title("Fixed Title", region="header"), ...])
r = b.rebuild([2], "output.pptx")  # 只重跑 slide 2 的 pipeline，其余走缓存
# rebuild 返回格式同 build()，额外含 "cached_slides" 键

# 传统一次性模式
r = b.build("output.pptx")
# Returns: {"ok": bool, "summary": str, "diagnostics": list, "path": str,
#           "raw_diagnostic_count": int, "collapsed": {dedup, batch, trimmed_*}}

for d in r["diagnostics"]:
    if d["severity"] == "error":
        # d keys: slide, phase, kind, severity, elem_id, message
        print(f"S{d['slide']:02d} [{d['phase']}] {d['kind']}: {d['message']}")
```

### Diagnosis triage — FIX vs IGNORE

| severity + phase | meaning | action |
|:--|:--|:--|
| `error` + `0.5/1/pre` | Real layout/validation error | 🔧 FIX |
| `error` + `freeze` + TEXT | Text overflow in fixed box | 🔧 FIX |
| `error` + `3.0 tri_*` | Contrast/invisible text | 🔧 FIX |
| **`warning` + `freeze` + b.box()** | **Box overflow — PPTX auto-expands** | **🚫 IGNORE** |
| `warning` (any phase) | Margin, spacing, L* | 🚫 IGNORE |
| `info` (any phase) | Advisory | 🚫 IGNORE |

**Golden rule: file >100KB on disk → it's fine. Don't read diagnostics beyond `[d for d in r["diagnostics"] if d["severity"]=="error"]`.**

### Token explosion prevention — 3 IRON RULES

1. **Diagnosis ≠ crash.** `b.box()` overflow = warning. PPTX auto-expands boxes. Only `severity: "error"` counts.
2. **Batch fix.** grep all same-error → one bulk edit → ONE run. Never: fix → run → fix → run.
3. **Read fragments.** `Read(file, offset=N, limit=30)` for the broken slide only. Full file only when rewriting.

### Open generated file

```python
import os; os.startfile("output.pptx")
```

### AI Image Prompt Generation (ImagePrompter)

```python
from ppt_reflex.image_prompter import ImagePrompter
p = ImagePrompter(template="academic")
prompt = p.generate(subject="topic", image_type="scientific_diagram", provider="midjourney")
print(prompt.full_prompt)       # paste into AI image tool
print(prompt.negative_prompt)
```

6 image types (for AI GENERATION only, not user-provided files):

| Type | Use Case | Tool | Aspect |
|:--|:--|:--|:--|
| `scientific_diagram` | Mechanism / workflow / methodology | Midjourney | 16:9 |
| `experiment_photo` | Equipment / samples / lab scenes | Midjourney | 4:3 |
| `data_chart` | Data viz / comparison / infographic | Midjourney | 16:9 |
| `concept_illustration` | Abstract concepts / covers | Midjourney | 16:9 |
| `material_structure` | Crystal structure / molecular models | Midjourney | 1:1 |
| `hero_image` | Title slide / section dividers | DALL·E | 16:9 |

---

## Full Example — 3 slides, 0 errors

```python
from ppt_reflex.builder import PPTBuilder

b = PPTBuilder(template="minimal", style="tech_dark")
ACCENT = (34, 211, 238); WARN = (251, 113, 133); DARK = (16, 26, 45)

# Slide 1 — Cover
b.add_slide("Computer Science's Greatest WTFs",
    regions=[
        ("header", 60, 30, 840, 60, 1),
        ("hero", 40, 120, 880, 250, 2),
        ("footer", 60, 400, 840, 100, 3),
    ],
    elements=[
        b.title("Computer Science's Greatest WTFs", region="header"),
        b.shape("star", region="hero", fill_color=WARN, pw=80, ph=80),
        b.shape("hexagon", region="hero", fill_color=ACCENT, pw=60, ph=60),
        b.text("A journey through the weirdest corners of computing", style="Caption", region="footer"),
    ],
)

# Slide 2 — Overview with arrows
hub = b.shape("hexagon", region="center", fill_color=ACCENT, pw=200, ph=80)
tl = b.box("Esoteric\nLanguages", style="Body", region="top_l", fill_color=DARK)
tr = b.box("Impossible\nProblems", style="Body", region="top_r", fill_color=DARK)

b.add_slide("What's On The Menu",
    regions=[
        ("header", 60, 30, 840, 60, 1),
        ("center", 350, 230, 260, 100, 2),
        ("top_l", 80, 120, 200, 80, 3),
        ("top_r", 680, 120, 200, 80, 4),
    ],
    elements=[
        b.title("Five Realms of Computational Chaos", region="header"),
        hub, b.title("CS\nChaos", region="center"), tl, tr,
    ],
    arrows=[
        b.arrow(hub, tl, "brain-melting syntax", "above", color=ACCENT),
        b.arrow(hub, tr, "can't be solved", "above", color=ACCENT),
    ],
)

# Slide 3 — Content with bullet lists
b.add_slide("Brainfuck: 8 Characters of Pain",
    regions=[
        ("header", 60, 30, 840, 60, 1),
        ("main", 60, 100, 520, 380, 2),
        ("code", 620, 100, 280, 240, 3),
        ("tip", 620, 370, 280, 110, 4),
    ],
    elements=[
        b.title("The Most Famous Esolang", region="header"),
        b.bullet("Operates on a 30,000-cell array of bytes — a Turing machine tape", region="main"),
        b.bullet("[ and ] form loops: \"while current cell != 0, repeat\"", region="main"),
        b.bullet("Turing-complete — you can write ANY program with 8 symbols", region="main"),
        b.bullet("\"Hello World\" in Brainfuck is 106 characters of pure punctuation", region="main"),
        b.box("++++++++[>++++[>++>+++>+++>+<<<<-]\n>+>+>->>+[<]<-]>>\n.>---.+++++++..+++.>>",
              style="Body", region="code", fill_color=DARK),
        b.box("Try reading it out loud.\nYour family will stage an intervention.",
              style="Body", region="tip", fill_color=DARK),
    ],
)

r = b.build("cs_wtf.pptx")
print(r["summary"])
# Expect: 0 errors
```

---

## Color Conventions

- RGB tuples only: `(34, 211, 238)` — NOT `"#22D3EE"`
- Never `(0,0,0)` or `(255,255,255)`
- Dark bg range: `(26,26,46)` — `(16,26,45)`
- Dark fills auto-invert text to white — no manual color needed

## Image Sources

- Unsplash: `https://images.unsplash.com/photo-{id}?w=800&q=80`
- User provides local files → `b.image("path/to/file.jpg", ...)`
- AI generation → `ImagePrompter.generate()` → show prompts → user fetches images → resume

## Workflow — /ppt command

```
/ppt
  │
  ├─ Step 0: Questionnaire — ① Topic? ② Content? ③ Images? ④ Template?
  │
  ├─ Step 1: Show plan → user confirms
  │
  ├─ Step 2: Image processing (if needed)
  │
  ├─ Step 3: Generate using ZERO-ERROR SKELETON
  │   NEVER start from scratch. Copy skeleton, add content.
  │   b.title() for headings. b.bullet() for lists. b.box() for text cards.
  │   Header ≥ 60pt. No captions on images.
  │
  ├─ Step 3.5: COMPLETENESS GATE — self-check BEFORE build()
  │   Run: len(b._slides), count elements per slide, count shapes, count boxes
  │   If elements < slides*3 → too sparse, go back
  │   If shapes == 0 → no visual interest, go back
  │
  └─ Step 4: build() → check diagnostics → output
```

## COMPLETENESS GATE — self-check BEFORE build()

**Before calling `b.build("output.pptx")`, answer these 5 questions. If any answer is NO, go back and add content.**

```
1. Slides count ≥ what the user asked for?          [ ]
2. Every slide has ≥ 3 elements (not counting header)? [ ]
3. At least 1 b.shape() used (not just text)?        [ ]
4. At least 1 b.box() with fill_color used?          [ ]
5. Arrows used if there's a flow/diagram to show?    [ ]
```

**If ≥3 questions are NO → you're cheating. Add content, then re-check.**

Also verify mechanically:
```python
n_slides = len(b._slides)
n_elements = sum(len(s.elements) for s in b._slides)
n_shapes = sum(1 for s in b._slides for e in s.elements if e.ctype == "shape")
n_boxes = sum(1 for s in b._slides for e in s.elements if e.ctype == "textbox")
print(f"Slides: {n_slides}, Elements: {n_elements}, Shapes: {n_shapes}, Boxes: {n_boxes}")
# If n_elements < n_slides * 3 → TOO SPARSE
# If n_shapes == 0 → NO VISUAL
```

## DON'T — FINAL WARNING

1. **Do NOT read ppt_reflex/ source code.** All APIs are in this doc.
2. **Do NOT import from grid/ directly.** Only `from ppt_reflex.builder import PPTBuilder`.
3. **Do NOT use `b.text(style="Heading")`/`Subheading`/`Emphasis`/`Body`.** Use `b.title()` + `b.box()` + `b.bullet()` instead.
4. **Do NOT add captions to images.** `caption=""` or omit.
5. **Do NOT mix light-bg templates with dark-bg styles.** `product` template ONLY with `tech_dark` style.
6. **Do NOT use 50pt header regions for titles.** Minimum 60pt.
7. **Do NOT modify this SKILL.md.**
