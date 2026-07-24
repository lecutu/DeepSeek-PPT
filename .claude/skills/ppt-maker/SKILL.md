---
name: ppt-maker
description: PPT制作Skill — 启动必问(做什么+内容+图片需求)→用户确认→生成。集成grid/引擎+模板+ImagePrompter图片AI提示词。
trigger: /ppt, /ppt-maker, 做ppt, 做PPT, 制作ppt, 制作PPT, 生成ppt, 生成PPT, 做个汇报, 做演示, make ppt, create ppt, ppt制作, 帮我做ppt, 帮我做PPT
---

# ppt-maker — PPT 制作入口

## 铁律

```
每次启动必问 2 个问题，不跳过：
  1. 做什么 (主题/场景/模板)
  2. 内容 (文字/数据/图片/幻灯片数)

图片必须确认来源:
  用户提供文件 → 直接用
  需要 AI 生成 → ImagePrompter 出提示词 → 用户取图 → 再继续
  不需要图片 → 跳过
```

## 启动流程

```
/ppt
  │
  ├─ Step 0: 显示 MAKER_QUESTIONNAIRE (来自 image_prompter.py)
  │   问: ① 做什么? ② 内容? ③ 图片需求? ④ 模板偏好?
  │
  ├─ Step 1: 展示计划 → 用户确认
  │   幻灯片数 / 每页内容 / 图片列表 / 模板配色
  │
  ├─ Step 2: 图片处理 (有图片需求时)
  │   ├─ 用户提供文件路径 → 验证文件存在
  │   └─ 需要 AI 生成 → ImagePrompter.generate() → 展示提示词
  │       → 等待用户提供生成的图片文件路径
  │       → 提示词格式: Midjourney/DALL·E/SD 三选, 配色与模板一致
  │
  ├─ Step 3: 生成 PPT
  │   ├─ 选模板: get_template(template_id)
  │   ├─ 用户自定义颜色 → get_template(...).override(bg_hex=..., accent_hex=...)
  │   ├─ 逐页建 slide → try_place / commit (grid/ engine)
  │   └─ AestheticsEngine.check(timing="commit") 自动校验
  │
  └─ Step 4: 输出 → temp 目录 → 用户打开检查
```

## 图片 AI 提示词生成

```
from ppt_reflex.image_prompter import ImagePrompter

p = ImagePrompter(template="academic")
prompt = p.generate(
    subject="SiOC负极材料充放电机理示意图",
    image_type="scientific_diagram",      # 6种: scientific_diagram/experiment_photo/
    provider="midjourney",                #       data_chart/concept_illustration/
)                                         #       material_structure/hero_image

print(prompt.full_prompt)      # 可直接粘贴到 AI 工具
print(prompt.negative_prompt)  # 负面提示词
print(prompt.style_notes)      # 类型+色调说明
```

6 种图片类型:

| 类型 | 适用 | 建议工具 | 比例 |
|:--|:--|:--|:--|
| scientific_diagram | 机理图/流程示意图/方法图 | Midjourney | 16:9 |
| experiment_photo | 设备照片/样品图/实验场景 | Midjourney | 4:3 |
| data_chart | 数据可视化/对比图/信息图 | Midjourney | 16:9 |
| concept_illustration | 概念插图/抽象图示/封面 | Midjourney | 16:9 |
| material_structure | 晶体结构/分子模型/材料图 | Midjourney | 1:1 |
| hero_image | 封面主视觉/章节分隔图 | DALL·E | 16:9 |

图片配色自动匹配所选模板（academic→深蓝砖红/business→企业蓝橙/...）

## 模板选择

6 套模板: academic | business | minimal | data_report | teaching | product

自定义颜色:
```python
from grid.templates import get_template
t = get_template("academic").override(bg_hex="FAFAFA", accent_hex="E74C3C")
```

## 生成约束

- 背景: 严禁纯黑底(#000) / 纯白底(#FFF) — 用暖白(#FAFAFA)或深灰(#1A1A2E)
- 颜色: 全篇 ≤4 色，单页 ≤5 色调
- 正文: #222-#444 深灰区间，不用纯黑
- 字体: 正文 ≥14pt，注释 ≥12pt
- 安全区: 四边 ≥48pt

全部由 `AestheticsEngine.check(timing="commit")` 自动执行。

## DON'T

- 不跳过问卷直接生成
- 不为用户做图片选择决定 — 有图片需求必须确认来源
- 不用旧 engine.py 生成新 PPT — 走 grid/ 管线
- 不修改此 SKILL.md 文件
