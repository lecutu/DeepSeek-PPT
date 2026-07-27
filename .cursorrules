# PPT Reflex — Use directly, don't explore

**STOP. Do NOT read ppt_reflex/ source code. Do NOT import from grid/. Do NOT explore the repo.**

Everything you need is in this doc. Use the zero-error skeleton below — it builds with 0 errors on first try.

## Zero-Error Recipe — START HERE, every time

```python
from ppt_reflex.builder import PPTBuilder

b = PPTBuilder(template="minimal", style="tech_dark")
ACCENT = (34, 211, 238)
WARN = (251, 113, 133)
DARK = (16, 26, 45)

b.add_slide("Title",
    regions=[
        ("header", 60, 30, 840, 60, 1),        # ≥60pt tall for titles
        ("main", 60, 110, 520, 380, 2),
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

### Guaranteed errors — NEVER use

| NEVER | Why | Error |
|:--|:--|:--|
| `b.text(style="Heading")` in header | 28pt bold → needs ~49pt, header is 50pt → overflow after inset | `overflow_vertical` |
| `b.text(style="Subheading")` in small region | 20pt font → box too small | `overflow_vertical` |
| `b.text(style="Emphasis")` | Bold 16pt → needs > allocated | `overflow_vertical` |
| `b.text(style="Body")` in fixed-height region | 18pt, auto-grows but may clip | `overflow_vertical` roundtrip |
| `b.image(..., caption="...")` | Caption text triggers overflow | `overflow_vertical` |
| `template="product"` + `style="creative_vibrant"` | creative_vibrant overrides bg to light | `tri_bg_fill` BLOCK |
| Any light-bg template + dark-bg style | White text on white | `invisible_text` BLOCK |

### Safe patterns — always zero errors

| Always safe | Why |
|:--|:--|
| `template="product"` + `style="tech_dark"` | Genuinely dark bg |
| `template="minimal"` + `style="tech_dark"` | Also safe |
| `b.title("...", region="header")` | Built-in ph=40 margin |
| `b.subtitle("...", region="header")` | 18pt, ph=30 |
| `b.text("...", style="Caption")` | 10pt fits anywhere |
| `b.bullet("...")` | 13pt, auto-flow |
| `b.box("...", fill_color=DARK, style="Body")` | Auto-expands height |
| `b.shape(...)` | Pure graphics, no text |
| `b.image(..., layout_mode="...", caption="")` | No caption = no text overflow |
| `b.divider(...)` | Always safe |
| `b.arrow(...)` | Always safe |

### Key rules

- **header ≥ 60pt** for titles. 50pt is too short.
- **Use `b.box()` for text content.** Not `b.text(Body)`.
- **Use `b.title()` for headings.** Not `b.text(style="Heading")`.
- **Images: no captions.** `caption=""`.
- **Dark themes: `product` ONLY with `tech_dark`.**

---

## API Reference

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

### Style presets

`academic_rigorous` | `corporate_minimal` | `tech_dark` | `editorial_magazine` | `creative_vibrant` | `government_solemn`

### add_slide — full signature

```python
b.add_slide("Slide title",
    regions=[
        ("header", 60, 30, 840, 60, 1),           # (name, x, y, w, h, z_order)
        ("main", 60, 110, 520, 380, 2),            # lower z_order = behind
        ("sidebar", 600, 110, 300, 200, 3),
    ],
    elements=[...],
    arrows=[...],
)
```

### Element API

```python
# HEADINGS
b.title("Title", region="header")                 # 28pt bold, centered, ph=40 — USE THIS, not b.text(Heading)
b.subtitle("Subtitle", region="header")           # 18pt, gray, ph=30

# TEXT — only safe style is Caption
b.text("Caption only", style="Caption", region="main")  # 10pt — fits anywhere
# ⚠ b.text(style="Body"/"Heading"/"Subheading"/"Emphasis") — GUARANTEED OVERFLOW, DO NOT USE

# LISTS — always safe
b.bullet("List item", region="main")              # 13pt, auto-flow

# CARDS — always safe
b.box("Text content", style="Body", region="card",
      fill_color=(16,26,45),                      # dark fill → white text automatic
      shape_id="rounded_rectangle")               # 20 shapes available

# SHAPES — always safe
b.shape("hexagon", region="center", fill_color=(34,211,238),
         pw=100, ph=60)                           # pw/ph REQUIRED

# IMAGES — safe without caption
b.image("path/img.jpg", region="hero",
        layout_mode="hero_top", caption="")        # NEVER add caption text

# DECORATION — always safe
b.divider(region="main", color=(34,211,238), width_pt=2.0)
b.arrow(elem_a, elem_b, "label", "below",         # elem_a/elem_b = _Spec from b.box/b.shape
        color=(34,211,238), text_font_size=9)
```

### Shape IDs

`rounded_rectangle` `rectangle` `oval` `parallelogram` `diamond` `chevron`
`pentagon` `hexagon` `up_arrow` `down_arrow` `left_arrow` `right_arrow`
`star` `triangle` `home` `cross` `pie` `wave` `donut` `plaque` `sun`

### Image layout modes

`hero_top` `hero_right` `hero_left` `center_float` `small_inline` `grid_2x2` `grid_1x3`

Or auto-infer: `b.auto_layout_mode("img.jpg")` — picks from aspect ratio:

| Aspect | Auto mode | Behavior |
|:--|:--|:--|
| >1.6 (wide) | `hero_top` | banner, contain-fit |
| <0.8 (tall) | `hero_right` | side column, contain-fit |
| 0.8–1.6 (square/screenshot) | `center_float` | centered, NEVER cropped |

**Screenshots, irregular crops, phone captures — just pass the file.** `fit_mode="fit"` is default.

### Build + diagnostics

```python
r = b.build("output.pptx")
# Returns: {"ok": bool, "summary": str, "diagnostics": list, "path": str}

for d in r["diagnostics"]:
    if d["severity"] == "error":
        print(f"S{d['slide']:02d} [{d['phase']}] {d['kind']}: {d['message']}")
        # d keys: slide, phase, kind, severity, elem_id, message
```

### Open generated file

```python
import os; os.startfile("output.pptx")
```

### Color conventions

- RGB tuples: `(34, 211, 238)` — not hex strings
- Never `(0,0,0)` or `(255,255,255)`
- Dark bg: `(26,26,46)` range
- Dark fills auto-invert text to white

### Image sources

- Unsplash: `https://images.unsplash.com/photo-{id}?w=800&q=80`
- Local files provided by user

---

## Full Example — 3 slides, 0 errors

```python
from ppt_reflex.builder import PPTBuilder

b = PPTBuilder(template="minimal", style="tech_dark")
ACCENT = (34, 211, 238); WARN = (251, 113, 133); DARK = (16, 26, 45)

b.add_slide("Cover",
    regions=[("header", 60, 30, 840, 60, 1), ("hero", 40, 120, 880, 250, 2), ("footer", 60, 400, 840, 100, 3)],
    elements=[
        b.title("Computer Science's Greatest WTFs", region="header"),
        b.shape("star", region="hero", fill_color=WARN, pw=80, ph=80),
        b.shape("hexagon", region="hero", fill_color=ACCENT, pw=60, ph=60),
        b.text("A journey through the weirdest corners of computing", style="Caption", region="footer"),
    ],
)

hub = b.shape("hexagon", region="center", fill_color=ACCENT, pw=200, ph=80)
tl = b.box("Esoteric\nLanguages", style="Body", region="top_l", fill_color=DARK)
tr = b.box("Impossible\nProblems", style="Body", region="top_r", fill_color=DARK)

b.add_slide("Overview",
    regions=[("header", 60, 30, 840, 60, 1), ("center", 350, 230, 260, 100, 2), ("top_l", 80, 120, 200, 80, 3), ("top_r", 680, 120, 200, 80, 4)],
    elements=[b.title("Five Realms of Computational Chaos", region="header"), hub, b.title("CS\nChaos", region="center"), tl, tr],
    arrows=[b.arrow(hub, tl, "brain-melting syntax", "above", color=ACCENT), b.arrow(hub, tr, "can't be solved", "above", color=ACCENT)],
)

b.add_slide("Brainfuck",
    regions=[("header", 60, 30, 840, 60, 1), ("main", 60, 100, 520, 380, 2), ("code", 620, 100, 280, 240, 3), ("tip", 620, 370, 280, 110, 4)],
    elements=[
        b.title("The Most Famous Esolang", region="header"),
        b.bullet("Operates on a 30,000-cell array of bytes — a Turing machine tape", region="main"),
        b.bullet("[ and ] form loops: \"while current cell != 0, repeat\"", region="main"),
        b.bullet("Turing-complete — you can write ANY program with 8 symbols", region="main"),
        b.bullet("\"Hello World\" in Brainfuck is 106 characters of pure punctuation", region="main"),
        b.box("++++++++[>++++[>++>+++>+++>+<<<<-]\n>+>+>->>+[<]<-]>>\n.>---.+++++++..+++.>>", style="Body", region="code", fill_color=DARK),
        b.box("Try reading it out loud.\nYour family will stage an intervention.", style="Body", region="tip", fill_color=DARK),
    ],
)

r = b.build("cs_wtf.pptx")
print(r["summary"])
# Expect: 0 errors
```

## DON'T

1. **Do NOT read ppt_reflex/ source code.** All APIs are here.
2. **Do NOT import from grid/.** Only `from ppt_reflex.builder import PPTBuilder`.
3. **Do NOT use `b.text(style="Heading"/"Subheading"/"Emphasis"/"Body")`.** Use `b.title()` + `b.box()` + `b.bullet()`.
4. **Do NOT add captions to images.** `caption=""`.
5. **Do NOT mix light-bg templates with dark-bg styles.** `product` ONLY with `tech_dark`.
6. **Do NOT use header < 60pt for titles.**
