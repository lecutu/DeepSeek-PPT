# PPT Reflex Engine — Architecture

## 定义

> 确定性执行层：几何 + 规则 + 模板 + 有限自动修复 + 可追溯 + 可回滚。
> Agent 负责布局意图和多方案决策，不计算坐标。
> 人随时介入，PPT 是唯一事实源。

## 架构分层

```
L0 · PowerPoint 事实源              revision、元素 ID、精确 bbox、锁定状态
─────────────────────────────────────────────────────────────────────
L1 · 几何引擎（engine.py）           双层网格 + 四阶段碰撞 + 7 类检测
L2 · 规则引擎（rules.py）            声明式规则：碰撞/字体/边界/对齐/间距/密度
L3 · 布局引擎（layout.py）           8 种固定页面模板
─────────────────────────────────────────────────────────────────────
L4 · 修复器（nudge.py）              ≤3次  ≤5pt  ≤3元素  全部可追溯可回滚
L5 · 日志（journal.py）              revision 乐观锁 + 事务 + 按源回滚
─────────────────────────────────────────────────────────────────────
L6 · 桥接（bridge.py）               python-pptx ↔ 引擎数据模型
─────────────────────────────────────────────────────────────────────
L7 · MCP Server（mcp_server.py）     19 个工具→Agent（stdio/HTTP）
L8 · Agent                         内容语义 + 版式意图 + 多方案决策
L9 · 人                             实时查看 + 锁定 + 手动编辑 + 断点确认
```

## 项目文件

```
ppt_reflex/
  engine.py            L1 几何引擎 — 双层网格 + 四阶段碰撞 + 7类检测
  rules.py             L2 声明式规则引擎 — 碰撞/字体/边界/对齐/间距/密度
  layout.py            L3 布局引擎 — 8种固定页面模板
  nudge.py             有限自动修复器 — ≤3次, ≤5pt, ≤3元素, 全部可追溯
  journal.py           操作日志 — revision乐观锁 + 事务 + 按源回滚
  reflex.py            主协调器 — audit/apply_layout/move_element/rollback
  bridge.py            python-pptx桥接 — 解析+回写+角色推断
  mcp_server.py        MCP Server — 19个工具, stdio/HTTP
  mcp-config.json      Claude Desktop 配置
  generate_test.py     15页测试PPT生成器
  validate.py          Day 1 检测验证
  collab_test.py       Day 1.5 人机协同验证
  test_mcp.py          MCP Server 端到端测试
  cases/
    broken.pptx        测试输入（15页）
    fixed-output.pptx  修复后输出
```

## 验证结果

### Day 1 — 检测引擎
| 指标 | 值 | 目标 |
|------|-----|------|
| 检出率 (Recall) | 100% | ≥90% |
| 精确率 (Precision) | 83.3% | ≥80% |
| Token/页 | 425 | ≤1500 |
| 漏检 | 0 | — |

### Day 1.5 — 人机协同
| 场景 | 结果 |
|------|------|
| Revision 乐观锁 | ✓ |
| 元素锁定 | ✓ |
| 事务冲突回滚（保留人编辑） | ✓ |
| 人工编辑感知 | ✓ |
| 解锁恢复 | ✓ |
| 完整协同流程 | ✓ |

### MCP Server
| 指标 | 值 |
|------|-----|
| 工具数 | 19 |
| 端到端测试 | 19/19 通过 |

## MCP Tool Schema

### 生命周期
- `open_presentation` — 打开 pptx 文件
- `save_presentation` — 保存当前演示文稿
- `select_slide` — 切换幻灯片

### 审计
- `audit_slide` — 完整几何 QA（7 类检测）

### 布局
- `list_templates` — 列出 8 种布局模板
- `apply_layout` — 按模板放置元素

### 元素操作
- `move_element` — 移动/缩放（含 revision 锁+锁定检查）
- `set_element_role` — 分配语义角色
- `delete_element` — 删除元素

### 上下文
- `local_context` — 目标元素+邻居的详细状态
- `element_summary` — 轻量级摘要（角色+网格地址）

### 人机协同
- `lock_element` / `unlock_element` — 人工锁定/解锁
- `notify_human_edit` — 感知人工编辑
- `begin_transaction` / `commit` / `rollback` / `undo` — 事务控制
- `get_revision` / `get_journal` — 状态查询

## Agent 交互模式

### 问题驱动的三级输出
```
ok            → {status: "ok", revision: N}
auto-adjusted → {status: "ok", revision: N, auto_adjusted: [...]}
needs_decision → {status: "needs_decision", issues: [...], budget: ...}
blocked       → {status: "blocked"|"state_changed", message: ...}
```

### 典型 Agent 循环
```
1. open_presentation
2. element_summary                → 轻量级画布感知
3. set_element_role × N           → 标注语义角色
4. audit_slide                    → 发现问题
5. 选择策略:
   a. apply_layout                → 模板化布局
   b. move_element × N            → 逐个修正
6. audit_slide                    → 验证修复
7. save_presentation              → 持久化
```

### 人介入点
```
observe 模式  → Agent 连续操作，人通过 journal 追溯
checkpoint 模式 → audit 后暂停，人确认后继续
interactive 模式 → 每次操作后人可在 PowerPoint 中手动编辑
    → notify_human_edit → Agent 收到 STATE_CHANGED → 重读再决策
```

## 核心设计原则

1. **不把所有状态传给 Agent** — 默认返回 ok/needs_decision，需要时才下钻
2. **不让 Agent 判断可代码化的几何问题** — 越界/碰撞/对齐全部在引擎中判定
3. **不把网格粗粒度误当成真实几何** — 粗网格(16×9)语义表达，精确 bbox 判决
4. **不让用户和 Agent 基于过期状态同时修改** — revision 乐观锁
5. **不把"无重叠"误认为"美观"** — 几何 QA → 规则 QA → 视觉 QA 三层独立
6. **Agent 负责布局意图，不负责手算坐标** — 选模板和策略，不写 pt 值
7. **人可以随时介入，PPT 是唯一事实源** — PowerPoint → 引擎 → Agent → 引擎 → PowerPoint
8. **所有修改可追溯、可回滚、可关闭** — journal 记录每条操作的 before/after/source

## 局限（Day 1-1.5 明确标记）

| 能力 | 状态 | 备注 |
|------|------|------|
| 文本溢出精确检测 | ✗ | 需要字体度量（fonttools） |
| 图片比例失真 | ✗ | 需要原始尺寸参照 |
| 色彩协调 | ✗ | 需要多模态模型或设计 Tokens |
| 视觉审美 | ✗ | 需要渲染 PNG + 视觉检查 |
| COM/VSTO 实时操作 | ✗ | python-pptx 文件级操作，非进程间 |
| 跨页一致性 | ✗ | 模板复用机制已设计，未实现 |
| 从 Agent 学习 | ✗ | 四级策略晋升框架已设计，未实现 |
