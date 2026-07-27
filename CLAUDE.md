# PPT Reflex — 直接用，别研究

## 唯一入口

```python
from ppt_reflex.builder import PPTBuilder
b = PPTBuilder(template="minimal", style="tech_dark")
```

## 模板 (template)

| template | bg | accent | 特点 |
|:--|:--|:--|:--|
| `academic` | white | navy+brick | 严谨、高信息密度 |
| `business` | white | blue+orange | 专业、结论优先 |
| `minimal` | white | dark gray+blue | 呼吸感、一页一个信息 |
| `data_report` | white | blue+orange | 网格感、数据密集 |
| `teaching` | warm white | vibrant blue+orange | 友好、结构清晰 |
| `product` | dark gray | indigo+violet | 高级感、暗场、居中 |

## style (AI 从 style_presets.json 选)

- `academic_rigorous` — 印刷品质感、低饱和
- `corporate_minimal` — 一页一个强调色、其余灰阶
- `tech_dark` — 暗场、1-2 处霓虹点缀
- `editorial_magazine` — 超大标题、不对称网格
- `creative_vibrant` — 大圆角、贴纸风格
- `government_solemn` — 对称构图、红色点缀线

## 元素 API (b.xxx)

```python
b.title("标题", region="header")                         # 28pt bold, 居中, ph=40
b.subtitle("副标题", region="header")                     # 18pt, 灰色, ph=30
b.text("正文内容", style="Body", region="main")           # 14pt, style: Body|Subheading|Caption|Emphasis
b.bullet("列表项内容", region="main")                     # 自动加 • 前缀, 13pt
b.box("卡片内容", style="Body", region="card1",
      fill_color=(16,26,45), shape_id="rounded_rectangle")  # 方形文本卡片
b.shape("hexagon", region="center", fill_color=(34,211,238),
         pw=100, ph=60)                                   # 装饰形状, 20种可选
b.image("path/to/img.jpg", region="hero",
        layout_mode="hero_top", caption="Figure 1.")     # 图片, 自动 contain-fit
b.arrow(from_elem, to_elem, "标注文字", "below",
         color=(34,211,238), text_font_size=9)            # 箭头, from/to 可以是 _Spec 对象
b.divider(region="main", color=(34,211,238), width_pt=2.0)  # 分割线
```

## 形状 ID (shape_id)

`rounded_rectangle` `rectangle` `oval` `parallelogram` `diamond` `chevron`
`pentagon` `hexagon` `up_arrow` `down_arrow` `left_arrow` `right_arrow`
`star` `triangle` `home` `cross` `pie` `wave` `donut` `plaque` `sun`

## 图片布局 (layout_mode)

`hero_top` — 页面顶部横幅, ≤800×280pt
`hero_right` — 右侧竖图
`hero_left` — 左侧竖图
`center_float` — 居中浮动, ≤560×360pt
`small_inline` — 小图内联
`grid_2x2` `grid_1x3` — 网格

或让引擎自动推断: `b.auto_layout_mode("img.jpg")` → 根据宽高比选模式

## 构建 + 读诊断

```python
r = b.build("output.pptx")
print(r["summary"])  # "313 issues (32 errors, 280 warnings)"

for d in r["diagnostics"]:
    if d["severity"] == "error":
        print(f"S{d['slide']:02d} [{d['phase']}] {d['kind']}: {d['message']}")
```

## 完整示例

```python
from ppt_reflex.builder import PPTBuilder

b = PPTBuilder(template="minimal", style="tech_dark")
ACCENT = (34, 211, 238)
WARN = (251, 113, 133)
DARK = (16, 26, 45)

b.add_slide("主题标题",
    regions=[
        ("header", 60, 30, 840, 50, 1),           # (name, x, y, w, h, z_order)
        ("hero", 60, 100, 500, 360, 2),            # z_order: 数字越小越底层
        ("sidebar", 600, 100, 300, 360, 3),
        ("footer", 60, 480, 840, 30, 4),
    ],
    elements=[
        b.text("页面标题", style="Heading", region="header"),
        b.bullet("第一条要点", region="hero"),
        b.bullet("第二条要点", region="hero"),
        b.bullet("第三条要点", region="hero"),
        b.box("关键结论放在卡片里", style="Body", region="sidebar",
              fill_color=DARK, shape_id="rounded_rectangle"),
        b.text("脚注信息", style="Caption", region="footer"),
    ],
)

r = b.build("demo.pptx")
print(r["summary"])
```

## 颜色约定

- 用 RGB tuple: `(34, 211, 238)` 不是 `"#22D3EE"`
- bg 不用纯黑 `(0,0,0)` 或纯白 `(255,255,255)`
- 暗场用 `(26,26,46)` 类似色
- 图片从 Unsplash: `https://images.unsplash.com/photo-{id}?w=800&q=80`

## 看结果

```powershell
Start-Process "output.pptx"
```

## DON'T

- 不读 ppt_reflex/ 源码 —— 一切 API 都在 PPTBuilder 上
- 不 import grid/ 内部模块
- 不手动改 style_presets.json —— 用 `load_style_presets()` / `save_style_presets()`
