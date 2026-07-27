# ppt-maker — PPT Creation Entry Point

## Rules

```
Every launch MUST ask these questions, no skipping:
  1. What to make? (topic / occasion / template)
  2. What content? (text / data / images / number of slides)

Images MUST confirm source:
  User provides files → use directly
  Needs AI generation → ImagePrompter outputs prompts → user fetches images → resume
  No images needed → skip
```

## Workflow

```
/ppt
  │
  ├─ Step 0: Display questionnaire
  │   Ask: ① What? ② Content? ③ Image needs? ④ Template preference?
  │
  ├─ Step 1: Show plan → user confirms
  │   Slide count / content per slide / image list / template & colors
  │
  ├─ Step 2: Image processing (if images needed)
  │   ├─ User provides file paths → verify files exist
  │   └─ Needs AI generation → ImagePrompter.generate() → show prompts
  │       → wait for user to provide generated image file paths
  │       → prompt format: Midjourney/DALL·E/SD, colors match template
  │
  ├─ Step 3: Generate PPT
  │   ├─ PPTBuilder(template="minimal", style="tech_dark")
  │   ├─ Slide-by-slide → add_slide(regions, elements, arrows)
  │   └─ build("output.pptx") → read r["diagnostics"] → fix if needed
  │
  └─ Step 4: Output → temp dir → user opens and reviews
```

## PPTBuilder API — Single entry point, do NOT explore source

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

### Element API

```python
b.title("Title", region="header")                           # 28pt bold, centered, ph=40
b.subtitle("Subtitle", region="header")                     # 18pt, gray, ph=30
b.text("Body text", style="Body", region="main")            # style: Body|Subheading|Caption|Emphasis
b.bullet("List item", region="main")                        # auto-prefixed with •
b.box("Card content", style="Body", region="card1",
      fill_color=(16,26,45), shape_id="rounded_rectangle")   # text card, auto-height
b.shape("hexagon", region="center", fill_color=(34,211,238),
         pw=100, ph=60)                                     # decorative shape, pw/ph required
b.image("path/img.jpg", region="hero",
        layout_mode="hero_top", caption="Figure 1.")         # auto contain-fit
b.arrow(from_elem, to_elem, "label", "below",
         color=(34,211,238), text_font_size=9)               # from/to accept _Spec objects
b.divider(region="main", color=(34,211,238), width_pt=2.0)   # horizontal rule
```

### Shape IDs

`rounded_rectangle` `rectangle` `oval` `parallelogram` `diamond` `chevron`
`pentagon` `hexagon` `up_arrow` `down_arrow` `left_arrow` `right_arrow`
`star` `triangle` `home` `cross` `pie` `wave` `donut` `plaque` `sun`

### Image layout modes

`hero_top` `hero_right` `hero_left` `center_float` `small_inline` `grid_2x2` `grid_1x3`

Or let the engine infer: `b.auto_layout_mode("img.jpg")` — picks mode from aspect ratio:

| Aspect ratio | Auto mode | What happens |
|:--|:--|:--|
| >1.6 (wide / panorama) | `hero_top` | full-width banner |
| <0.8 (tall / portrait) | `hero_right` | right-side column |
| 0.8–1.6 (square / screenshot) | `center_float` | centered, contain-fit, never cropped |

**Screenshots, irregular crops, phone captures — just pass the file.** `fit_mode="fit"` is default: image is always fully visible, aspect ratio preserved, nothing cropped. The 6 `image_type` values below are for AI *generation* only (ImagePrompter), not for user-provided files.

### add_slide — full signature

```python
b.add_slide("Slide title",
    regions=[
        ("header", 60, 30, 840, 50, 1),           # (name, x, y, w, h, z_order)
        ("main", 60, 100, 520, 380, 2),            # lower z_order = behind
        ("sidebar", 600, 100, 300, 380, 3),
    ],
    elements=[...],
    arrows=[...],
)
```

### Build + diagnostics

```python
r = b.build("output.pptx")
# r = {"ok": bool, "summary": str, "diagnostics": [...], "path": str}

for d in r["diagnostics"]:
    if d["severity"] == "error":
        print(f"S{d['slide']:02d} [{d['phase']}] {d['kind']}: {d['message']}")
```

### AI Image Prompt Generation

```python
from ppt_reflex.image_prompter import ImagePrompter

p = ImagePrompter(template="academic")
prompt = p.generate(
    subject="SiOC anode charge-discharge mechanism diagram",
    image_type="scientific_diagram",
    provider="midjourney",
)
print(prompt.full_prompt)
print(prompt.negative_prompt)
print(prompt.style_notes)
```

6 image types:

| Type | Use Case | Recommended Tool | Aspect |
|:--|:--|:--|:--|
| scientific_diagram | Mechanism / workflow / methodology | Midjourney | 16:9 |
| experiment_photo | Equipment / samples / lab scenes | Midjourney | 4:3 |
| data_chart | Data viz / comparison / infographic | Midjourney | 16:9 |
| concept_illustration | Abstract concepts / covers | Midjourney | 16:9 |
| material_structure | Crystal structure / molecular models | Midjourney | 1:1 |
| hero_image | Title slide / section dividers | DALL·E | 16:9 |

Image colors auto-match the selected template.

## Color conventions

- RGB tuples: `(34, 211, 238)` — not hex strings
- Never pure black `(0,0,0)` or pure white `(255,255,255)`
- Dark fills auto-invert text to white

## Image sources

- Unsplash: `https://images.unsplash.com/photo-{id}?w=800&q=80`
- Local files provided by user

## Full example

```python
from ppt_reflex.builder import PPTBuilder

b = PPTBuilder(template="minimal", style="tech_dark")
ACCENT = (34, 211, 238); DARK = (16, 26, 45)

b.add_slide("The Weird World of CS",
    regions=[
        ("header", 60, 30, 840, 50, 1),
        ("main", 60, 100, 520, 400, 2),
        ("sidebar", 620, 100, 280, 240, 3),
        ("tip", 620, 370, 280, 130, 4),
    ],
    elements=[
        b.text("Welcome to CS Absurdity", style="Heading", region="header"),
        b.text("Why Programmers Love Bad Jokes", style="Subheading", region="main"),
        b.bullet("Because the best ones compile without warnings", region="main"),
        b.bullet("The first reply on Stack Overflow is always a duplicate flag", region="main"),
        b.bullet("'It works on my machine' — the 8 most expensive words in software", region="main"),
        b.shape("hexagon", region="sidebar", fill_color=ACCENT, pw=80, ph=60),
        b.text("Fun\nFact", style="Heading", region="sidebar"),
        b.box("Did you know: the npm package `is-odd` gets 5M weekly downloads, depends on `is-number`, which depends on `kind-of`. Checking if a number is odd takes 3 packages.",
              style="Body", region="tip", fill_color=DARK),
    ],
)

r = b.build("cs_intro.pptx")
print(r["summary"])
```

## DON'T

- Don't read ppt_reflex/ source code — all APIs are on PPTBuilder
- Don't import from grid/ directly
- Don't skip the questionnaire
- Don't decide image sources for the user
- Don't modify this SKILL.md
