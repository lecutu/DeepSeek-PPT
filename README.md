# 🧠 DeepSeek PPT Maker

> **DeepSeek API 驱动 AI Agent 安全制作/修复 PPT — Agent 选格子 · 引擎判冲突 · 通过才写 PPT**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-59%2F59%20passing-brightgreen.svg)](ppt_reflex/grid/tests/)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-%E2%9C%93-orange)](https://deepseek.com)
[![Claude](https://img.shields.io/badge/Claude-%E2%9C%93-blueviolet)](https://anthropic.com)

**DeepSeek PPT Maker** 是一个让 AI Agent 安全操作 PowerPoint 的开源框架。用 DeepSeek 就能做专业 PPT。

---

## 🎯 核心能力

> **Agent 说 Excel 格子坐标 → 引擎实时判冲突 → 通过才写 PPT → 原子写入，0 次文件污染**

---

## 🔥 为什么需要这个？

| | 普通 Agent PPT 方案 | DeepSeek PPT Maker |
|:--|:--|:--|
| **冲突检测** | 写完了再 audit → 事后补救 | **try_place → BLOCK 拦截 → 事前预防** |
| **Agent 计算** | Agent 自己算 pt 坐标 | **Agent 说"A2:D5"，引擎翻译** |
| **PPT 污染** | 写入 3-4 次才能调对 | **原子写入，0 次污染** |
| **美观性** | Agent 凭感觉排版 | **WCAG 2.1 对比度 + 溢出检测 + 配色校验** |
| **图片** | 没有 | **内置 ImagePrompter → Midjourney/DALL·E/SD** |
| **LLM 支持** | 只绑一个 | **DeepSeek / Claude / 任何 OpenAI-compatible** |

---

## 💰 DeepSeek 成本

DeepSeek-V3 API 极低的 token 价格（~$0.28/1M output tokens）意味着 AI 制作 PPT 几乎是零成本——单次生成约 $0.004，做一年不超 ¥20。

---

## 📦 核心模块

```
ppt_reflex/
├── grid/                     ★ 新一代感知型网格画布
│   ├── canvas.py             GridCanvas — try_place / commit / rollback
│   ├── positioning.py        地址 ↔ pt 坐标 (A1:D5 ⇄ 60,60,240,240)
│   ├── info_grid.py          32×18 有状态信息层 + checkpoint
│   ├── matrix.py             类型 × 类型 → BLOCK / ALLOW / WARN + z_hint
│   ├── serializer.py         Grid ↔ PPT 往返 (唯一碰 python-pptx 的文件)
│   ├── supply.py             Agent 输出分层: L0(50t)/L1(100t)/L2(60t)
│   ├── spatial.py            SpatialIndex — 最近邻/间隙矩阵/对齐组/密度热图
│   ├── text_metrics.py       中英混合文字溢出估算 (±15%)
│   ├── aesthetics.py         WCAG 对比度 + 风格约束 + 密度/间距/对齐
│   ├── templates.py          6 套配色模板 + .override() 自定义颜色
│   ├── profiles.py           版式推断 (标题/正文/页脚/背景)
│   ├── types.py              ContentType / Verdict / BLOCK_PAIRS / PlacementResult
│   └── tests/                34 tests — all green ✓
│
├── image_prompter.py         图片 AI 提示词生成器 (6类型 × 3工具 × 6配色)
├── mcp_server.py             22 MCP Tools → Agent (含 grid 4 工具)
├── reflex.py                 主协调器 L1-L5
├── engine.py                 几何引擎 (标记 deprecated, 迁移到 grid/)
├── validate.py               Day 1 闭环验证 (100% recall / 83% precision)
├── collab_test.py            人机协同 6 场景测试
├── test_mcp.py               19 工具端到端测试
├── llm_agent.py              LLM 决策接口 (DeepSeek/Claude/OpenAI)
├── agent_loop.py             Agent 修复循环
├── repair_planner.py         确定性修复器 + 模拟器
└── collab_agent.py           协作者 Agent 接口
```

---

## ⚡ 5 分钟上手

### 安装

```bash
pip install python-pptx
git clone https://github.com/lecutu/deepseek-ppt-maker.git
cd deepseek-ppt-maker
```

### DeepSeek 驱动 PPT 修复

```bash
export DEEPSEEK_API_KEY="sk-your-key"
python ppt_reflex/llm_agent.py cases/broken.pptx --provider deepseek --max-slides 5

# 输出：
#   PPT Reflex Agent + LLM (Provider: deepseek)
#   Slides: 5 | Max Rounds: 3
#   Slide 1: deterministic fix ✓
#   Slide 2: LLM chose: nudge_element
#   ...
#   Slides fixed: 4 | LLM successes: 3 | Token cost: ~$0.002
```

### Grid Canvas 制作新 PPT

```python
from grid import GridCanvas, GridConfig, ContentType
from grid.templates import get_template

# 选模板 (可自定义颜色)
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

### MCP Server — Agent 直接调用

```bash
python ppt_reflex/mcp_server.py             # stdio 模式
python ppt_reflex/mcp_server.py --port 8081 # HTTP 模式
```

| 工具 | 用途 |
|:--|:--|
| `element_summary` | 当前页元素一览 |
| `audit_slide` | 全量检测 (7 类规则) |
| `try_place` | **★ 事前拦截 — Agent 说格子，引擎判冲突** |
| `commit_grid` | 原子写入 PPT |
| `rollback_grid` | 回滚到 checkpoint |
| `grid_snapshot` | 分层输出 L0/L1/L2 |
| `apply_layout` | 套用 8 种布局模板 |
| `move_element` | 移动元素 (带 revision 乐观锁) |
| `local_context` | 元素 + 邻居上下文 |
| `lock_element` | 锁定模板装饰不被修改 |
| ... | 等 22 个工具 |

### 图片 AI 提示词生成

```python
from ppt_reflex.image_prompter import ImagePrompter

p = ImagePrompter(template="academic")
r = p.generate(
    "SiOC 负极材料充放电机理示意图",
    image_type="scientific_diagram",
    provider="midjourney"
)
print(r.full_prompt)
# → "SiOC 负极材料充放电机理示意图, clean scientific illustration,
#    technical diagram, white background, color scheme: deep navy blue
#    and muted brick red accents --ar 16:9 --v 6.1"
```

6 类型 × 3 工具 (Midjourney / DALL·E / SD) × 6 配色自动匹配。

---

## 🏗️ 架构理念

### 双层网格

```
┌─────────────────────────────────────────────────────┐
│ 定位层 (16×9, 60pt/cell, A1..P9)                   │
│ ★ Agent 说的语言                                    │
│ "body 放 A2:D5, figure 放 E2:H6"                    │
│ 引擎翻译 → pt 坐标, ~425 tokens/slide               │
├─────────────────────────────────────────────────────┤
│ 信息层 (32×18, 30pt/cell, 内部)                    │
│ ★ 引擎的感知地图                                     │
│ 每格 = {owner_id, content_type, z_order, locked}    │
│ try_place 时扫描 → 发现冲突 → 拦截                   │
└─────────────────────────────────────────────────────┘
```

### 交互矩阵

|  | TEXT | TEXTBOX | IMAGE | TABLE | CHART |
|:--|:--:|:--:|:--:|:--:|:--:|
| **TEXT** | ❌ BLOCK | ✅ | ❌ | ❌ | ❌ |
| **TEXTBOX** | ✅ | ❌ BLOCK | ✅ | ✅ | ✅ |
| **IMAGE** | ❌ | ✅ | ✅ | ❌ | ❌ |
| **TABLE** | ❌ | ✅ | ❌ | ❌ | ❌ |
| **CHART** | ❌ | ✅ | ❌ | ❌ | ❌ |

只拦 8 对真正冲突的组合，其余全放行。

### try_place 实时检测

```
Agent 说: "body 放 A2:D6"
  → cells_to_bbox → bbox 边界检查
  → 扫描信息层 32×18 网格
  → 交互矩阵: TEXT 叠 TEXT? → BLOCK
  → PlacementResult {verdict, conflicts, z_hint, free_suggestion}
```

### 原子写入

```
try_place → 成功 → 信息层暂存
→ commit() → 写临时文件 → os.replace() → 确认 checkpoint
→ 失败 → rollback() → 信息层恢复 → PPT 文件从未被接触
```

---

## 🎨 6 套配色模板

| 模板 | 背景 | 主色 | 强调色 | 对比度 | 适用 |
|:--|:--|:--|:--|:--|:--|
| `academic` | `#FFFFFF` 白 | `#1B3A5C` 深蓝 | `#C0392B` 砖红 | 13.8:1 | 文献汇报/开题/答辩 |
| `business` | `#FFFFFF` 白 | `#0052D9` 企业蓝 | `#ED7B2F` 橙 | 12.6:1 | 工作/年终/述职 |
| `minimal` | `#FFFFFF` 白 | `#2D5BD7` 蓝 | `#FF4757` 红 | 14.3:1 | 分享会/TED |
| `data_report` | `#FFFFFF` 白 | `#1976D2` 蓝 | `#F57C00` 橙 | 16.1:1 | 年报/数据分析 |
| `teaching` | `#FFFDF5` 暖白 | `#2196F3` 蓝 | `#FF9800` 橙 | 12.4:1 | 培训/课程 |
| `product` | `#1D1D1F` 深灰 | `#6366F1` 紫 | `#8B5CF6` 紫 | 13.8:1 | 品牌/发布 |

自定义颜色：

```python
from grid.templates import get_template
t = get_template("academic").override(bg_hex="FAFAFA", accent_hex="E74C3C")
```

---

## 🧪 测试

```bash
python -m pytest ppt_reflex/grid/tests/ -v   # 34 tests
python ppt_reflex/test_mcp.py                # 19 tools
python ppt_reflex/collab_test.py             # 6 scenarios
python ppt_reflex/validate.py                # 检测性能
```

| 测试套件 | 结果 |
|:--|:--|
| `test_positioning.py` (8) | ✅ 地址↔pt 往返一致 |
| `test_matrix.py` (5) | ✅ BLOCK/ALLOW/WARN/z_hint |
| `test_canvas.py` (8) | ✅ try_place/commit/rollback |
| `test_serializer.py` (7) | ✅ Grid↔PPT 密度 0.134 ⇄ 0.134 |
| `test_supply.py` (3) | ✅ L0/L1/L2 token 预算 |
| `test_profiles.py` (3) | ✅ 版式推断 |
| `test_aesthetics.py` (5) | ✅ WCAG + 风格约束 |
| `test_templates.py` (1) | ✅ 6 模板 CR ≥ 12.4:1 |
| `test_mcp.py` (19) | ✅ 全部 MCP 工具 |
| `collab_test.py` (6) | ✅ 人机协同 |

---

## 🔧 Agent Prompt

```
你是 PPT 布局员。你使用 Grid Canvas 操作 PPT：

可用操作:
- grid_snapshot(level=0) 获取幻灯片总览 (~50 tokens)
- try_place(element_id, content_type, cells) 尝试放置 → 引擎判冲突
- commit(ppt_path) 原子写入 PPT
- rollback() 回滚上次操作

content_type: TEXT | TEXTBOX | IMAGE | TABLE | CHART | SHAPE | ANNOTATION | TITLE

规则:
- 定位层用 Excel 命名: "A2:D5" 表示 A2 到 D5 的矩形区域
- 不可逾越 BLOCK_PAIRS
- 背景/深色色块禁止纯黑 (#000)
- 正文用 #222-#444 深灰区间，字体 ≥ 14pt
```

---

## 📐 工程参考

| 原系统 | 核心概念 | 映射 |
|:--|:--|:--|
| **Unity Physics2D** | Layer Collision Matrix | → 交互矩阵 (BLOCK_PAIRS) |
| **CSS Grid Layout** | grid-template-areas 命名 | → 定位层 A1..P9 |
| **PCB Design Rules** | online DRC + batch DRC | → try_place(实时) + audit(全局) |
| **Figma Auto Layout** | 对齐 + 间距 + 约束 | → 对齐建议 + 密度热力图 |

---

## 🗺️ Roadmap

- [x] 双层网格 (16×9 + 32×18)
- [x] 交互矩阵 (6 ContentType × 8 BLOCK_PAIRS)
- [x] try_place / commit / rollback
- [x] Agent 输出分层 (L0/L1/L2)
- [x] 图片 AI 提示词生成器 (ImagePrompter)
- [x] WCAG 2.1 美观性引擎
- [x] 6 套配色模板 + 自定义颜色
- [x] MCP Server (22 tools)
- [x] DeepSeek / Claude / OpenAI 多 LLM 支持
- [x] 原子写入 + checkpoint/rollback
- [ ] OfficeCLI 渲染集成 (截图预览)
- [ ] 多页一致性校验
- [ ] 模板反向识别 (PPT → TemplateProfile)
- [ ] 图表数据绑定 (CSV → Chart)
- [ ] PPT → Markdown 双向转换
- [ ] Web UI (React 网格画布)

---

## 🤝 贡献

MIT License — 随意使用/修改/商用。PR welcome。

---

**DeepSeek 驱动 · Agent 选格子 · 引擎判冲突 · 通过才写 PPT。**
