---
name: ppt-maker
description: PPT Maker Skill — mandatory questionnaire on launch (topic + content + image needs) → user confirmation → generate. Integrates grid/engine + templates + ImagePrompter for AI image prompts.
trigger: /ppt, /ppt-maker, make ppt, create ppt, generate ppt, ppt maker, build ppt, presentation maker
---

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
  ├─ Step 0: Display MAKER_QUESTIONNAIRE (from image_prompter.py)
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
  │   ├─ Pick template: get_template(template_id)
  │   ├─ Custom colors → get_template(...).override(bg_hex=..., accent_hex=...)
  │   ├─ Slide-by-slide → try_place / commit (grid/ engine)
  │   └─ AestheticsEngine.check(timing="commit") auto-validation
  │
  └─ Step 4: Output → temp dir → user opens and reviews
```

## AI Image Prompt Generation

```
from ppt_reflex.image_prompter import ImagePrompter

p = ImagePrompter(template="academic")
prompt = p.generate(
    subject="SiOC anode charge-discharge mechanism diagram",
    image_type="scientific_diagram",       # 6 types: scientific_diagram / experiment_photo /
    provider="midjourney",                 #          data_chart / concept_illustration /
)                                          #          material_structure / hero_image

print(prompt.full_prompt)      # paste directly into AI tool
print(prompt.negative_prompt)  # negative prompt
print(prompt.style_notes)      # type + color hints
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

## Template Selection

6 templates: academic | business | minimal | data_report | teaching | product

Custom colors:
```python
from grid.templates import get_template
t = get_template("academic").override(bg_hex="FAFAFA", accent_hex="E74C3C")
```

## Generation Constraints

- Background: no pure black (#000) / no pure white (#FFF) — use warm white (#FAFAFA) or dark gray (#1A1A2E)
- Colors: ≤4 total, ≤5 shades per slide
- Body text: #222-#444 dark gray range, no pure black
- Font sizes: body ≥14pt, annotations ≥12pt
- Safe margins: ≥48pt on all four sides

All enforced by `AestheticsEngine.check(timing="commit")`.

## DON'T

- Don't skip the questionnaire
- Don't make image decisions for the user — image needs must be confirmed
- Don't use the old engine.py to generate new PPTs — go through grid/ pipeline
- Don't modify this SKILL.md
