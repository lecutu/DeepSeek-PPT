# 文献搜索员

## 核心资产
- `ppt_reflex/` — PPT 生成引擎
- `.claude/skills/ppt-maker/SKILL.md` — ppt-maker Skill 定义
- `.claude/protocols/ai-task-protocol.md` — AI 任务协议
- `.claude/agents/` — 专用 agent 定义

## 快速开始

### PPT 生成
```
/ppt → 问卷 → 确认 → PPTBuilder 生成
from ppt_reflex.builder import PPTBuilder
builder = PPTBuilder(template="academic", style="academic_rigorous")
builder.add_slide(...)
builder.build("out.pptx")
```

### 全局可用
`pip install -e D:\文献搜索员` 后任何工作区 `from ppt_reflex.builder import PPTBuilder`。

### 测试
`python -m pytest ppt_reflex/grid/tests/ -q` — 46 个测试
