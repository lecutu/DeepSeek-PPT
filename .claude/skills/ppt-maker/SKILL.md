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

## PPTBuilder API — 唯一入口，不要探索源码

### 初始化

```python
from ppt_reflex.builder import PPTBuilder
b = PPTBuilder(template="minimal", style="tech_dark")
```

### 模板 (template)

| id | bg | accent | 特点 |
|:--|:--|:--|:--|
| `academic` | white | navy+brick | 严谨、高信息密度 |
| `business` | white | blue+orange | 专业、结论优先 |
| `minimal` | white | dark gray+blue | 呼吸感、一页一个信息 |
| `data_report` | white | blue+orange | 网格感、数据密集 |
| `teaching` | warm white | vibrant blue+orange | 友好、结构清晰 |
| `product` | dark gray | indigo+violet | 高级感、暗场、居中 |

### style (style_presets.json)

`academic_rigorous` | `corporate_minimal` | `tech_dark` | `editorial_magazine` | `creative_vibrant` | `government_solemn`

### 元素 API

```python
b.title("标题", region="header")                           # 28pt bold, 居中, ph=40
b.subtitle("副标题", region="header")                       # 18pt, 灰色, ph=30
b.text("正文", style="Body", region="main")                 # style: Body|Subheading|Caption|Emphasis
b.bullet("列表项", region="main")                           # 自动加 • 前缀, 13pt
b.box("卡片内容", style="Body", region="card1",
      fill_color=(16,26,45), shape_id="rounded_rectangle")   # 方形文本卡片, ph=自动
b.shape("hexagon", region="center", fill_color=(34,211,238),
         pw=100, ph=60)                                     # 装饰形状, pw/ph 必填
b.image("path/img.jpg", region="hero",
        layout_mode="hero_top", caption="Figure 1.")         # 自动 contain-fit
b.arrow(from_elem, to_elem, "文字", "below",
         color=(34,211,238), text_font_size=9)               # from/to 传 _Spec 对象
b.divider(region="main", color=(34,211,238), width_pt=2.0)   # 分割线
```

### 形状 ID (shape_id)

`rounded_rectangle` `rectangle` `oval` `parallelogram` `diamond` `chevron`
`pentagon` `hexagon` `up_arrow` `down_arrow` `left_arrow` `right_arrow`
`star` `triangle` `home` `cross` `pie` `wave` `donut` `plaque` `sun`

### 图片布局 (layout_mode)

`hero_top` `hero_right` `hero_left` `center_float` `small_inline` `grid_2x2` `grid_1x3`

或自动推断: `b.auto_layout_mode("img.jpg")`

### add_slide 完整参数

```python
b.add_slide("幻灯片标题",
    regions=[
        ("header", 60, 30, 840, 50, 1),           # (name, x, y, w, h, z_order)
        ("main", 60, 100, 520, 380, 2),            # z_order: 小=底层
        ("sidebar", 600, 100, 300, 380, 3),
    ],
    elements=[...],
    arrows=[...],
)
```

### 构建 + 诊断

```python
r = b.build("output.pptx")
# r = {"ok": bool, "summary": str, "diagnostics": [...], "path": str}

for d in r["diagnostics"]:
    if d["severity"] == "error":
        print(f"S{d['slide']:02d} [{d['phase']}] {d['kind']}: {d['message']}")
        # d = {slide, phase, kind, severity, elem_id, message}
```

### 图片源

- Unsplash: `https://images.unsplash.com/photo-{id}?w=800&q=80`
- 本地文件: `b.image("D:/path/to/img.jpg", ...)` 用户提供

## 颜色约定

- RGB tuple: `(34, 211, 238)` 不是 hex string
- bg 不用 `(0,0,0)` 或 `(255,255,255)`
- 暗场用 `(26,26,46)` 类似色
- 暗色填充会自动翻白文字

## 完整示例

```python
from ppt_reflex.builder import PPTBuilder

b = PPTBuilder(template="minimal", style="tech_dark")
ACCENT = (34, 211, 238); DARK = (16, 26, 45)

b.add_slide("计算机科学的奇妙世界",
    regions=[
        ("header", 60, 30, 840, 50, 1),
        ("main", 60, 100, 520, 400, 2),
        ("sidebar", 620, 100, 280, 240, 3),
        ("tip", 620, 370, 280, 130, 4),
    ],
    elements=[
        b.text("欢迎来到CS的荒诞角落", style="Heading", region="header"),
        b.text("为什么程序员喜欢冷笑话", style="Subheading", region="main"),
        b.bullet("因为所有好梗都要编译通过", region="main"),
        b.bullet("Stack Overflow 上提问的第一条回复永远是重复标记", region="main"),
        b.bullet('"It works on my machine" 是软件开发史上最贵的八个单词', region="main"),
        b.shape("hexagon", region="sidebar", fill_color=ACCENT, pw=80, ph=60),
        b.text("Fun\nFact", style="Heading", region="sidebar"),
        b.box("你知道吗：npm 上 `is-odd` 包每周下载500万次，依赖 `is-number`，而 `is-number` 又依赖 `kind-of`。检查一个数是奇数需要3个包。",
              style="Body", region="tip", fill_color=DARK),
    ],
)

r = b.build("cs_intro.pptx")
print(r["summary"])
```

## Generate PPT → open it

```python
r = b.build("output.pptx")
print(r["summary"])
# Windows: os.startfile("output.pptx")
```

## DON'T

- 不读 ppt_reflex/ 源码 —— 一切 API 都在 PPTBuilder 上
- 不 import grid/ 内部模块
- 不 skip questionnaire
- 不替用户决定图片来源
