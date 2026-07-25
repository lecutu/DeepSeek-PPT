# PPT Reflex

## 核心资产
- `ppt_reflex/` — PPT 生成引擎
- `.claude/skills/ppt-maker/SKILL.md` — ppt-maker Skill 定义
- `pyproject.toml` — 包配置 (`pip install -e .`)

## 快速开始

### PPT 生成
```
from ppt_reflex.builder import PPTBuilder
builder = PPTBuilder(template="academic", style="academic_rigorous")
builder.add_slide(...)
builder.build("out.pptx")
```

### 全局可用
`pip install -e <REPO_ROOT>` 后任何工作区 `from ppt_reflex.builder import PPTBuilder`。

### 测试
`python -m pytest ppt_reflex/grid/tests/ -q` — 46 个测试
