---
name: literature-research
description: 文献研究Skill——读取search-manifest→逐篇evidence card→12维index→synthesis+gaps+化学审查。输出evidence-index.json，不形成科学观点。
trigger: /lit-research, 研究这篇, 分析证据, evidence, 提取数据, research, /research
---

# literature-research — 证据提取与综合

## 核心约束

```
输入: search-manifest.json (唯一入口)
输出: evidence-index.json + synthesis.md + research-gaps.json
不输出: scientific opinions (那是观点讨论员的事)
```

## 流程

### Step 1 — 加载 manifest

```
1. 读取 search-manifest.json
2. 抽取 selection_status=recommended 的论文列表
3. 按 tier 排序: tier1 → tier2 (tier3 仅 reference)
4. 初始综合 ≤5 篇, 综合 evidence cards ≤8 张
```

### Step 2 — 逐篇处理

每篇论文独立处理，不携带上一篇的上下文：

```
1. 读 Zotero matchedChunks (semantic_search × 12 维, 每维 topK=5)
2. Chunk Rerank: 对每次 semantic_search 返回的 chunks 做 LLM 轻量打分
   → 模型只输出 relevance_judgment: "direct"|"partial"|"irrelevant"
   → 保留 "direct" + "partial" 的前 3 个 ("irrelevant" 丢弃)
   → ≤500 token/次，不读全文
3. matchedChunks 充分性检查 (6 项):
   Identity / Attribution / Completeness / Qualifiers / Consistency / Question fit
4. 强制提取实验条件 (Method/Experimental 节, 必读):
   a. 合成条件: 前驱体比例/催化剂/溶剂/温度/时间/气氛/升温速率
   b. 电化学条件: 电解液/对电极/电压窗口/电流密度/活性物质负载/扫速
   c. 每字段标记 reported: true|false — 未报告的不编造
   d. 条件缺失字段 → 标记 INSUFFICIENT_CONTEXT → 进入 research-gaps
5. 分流：
   ├─ 6 项全过 → 直接生成 evidence card
   ├─ 缺必要条件 → search_fulltext → bounded window (≤8 KB)
   ├─ 需 section → get_content(mode="standard") 定位目标小节
   └─ 仍不足 → 标记 INSUFFICIENT_CONTEXT, 进入 research-gaps
6. 逐篇落盘: $RUN/research/evidence/{zotero_key}.json
```

每篇保留 chunks ≤3, 全文关键词查询 ≤3 次。rerank 丢弃的 chunks 不进入 evidence card。

### Step 2.5 — 条件可比性预检

跨论文条件 diff 由 pipeline.py 机械完成（不交给 LLM 判断）：

```
| 判定 | 规则（机械） | 示例 |
|:---|:---|:---|
| identical | 数值/描述完全一致 | 1M LiPF6 EC:DMC = 1M LiPF6 EC:DMC |
| comparable | 同类型有差异 | 0.01-3V vs 0.01-2.5V (同 Li 体系) |
| incompatible | 根本不同体系 | LiPF6/EC:DMC vs NaPF6/PC |
| missing | 文献未报告 | — |

硬规则:
- 电解液溶剂相同 → comparable; 不同金属离子 → incompatible
- 电压窗口重叠 >50% → comparable; 否则 incompatible
- 电流密度差 <5× → comparable; 否则 ⚠large_gap
- 活性物质负载差 <3× → comparable; 否则 ⚠large_gap
```

各 evidence card 落地后 `pipeline.py condition-batch` 扫描生成 diff 矩阵 → 输出为 `condition-diff.json`。

### Step 3 — 化学护栏审查

护栏 SSOT: `.claude/guardrails/chemical-guardrail.json`。
扫描所有 evidence cards 中的试剂 → 查表匹配 → 标记 verdict + flag。
不在表中的物质 → `$RUN/research/chemical-proposals.json`。
每张 evidence card 的 chemical_audit 字段标注审查结果。

### Step 4 — 构建 evidence-index

```
pipeline.py index < evidence_dir

生成 12 维 × 论文矩阵:
  - 每维度 status: reported / not_reported
  - 跨论文冲突标记 (pipeline.py conflicts)
  - 证据等级汇总 (最高等级为准)
```

### Step 5 — 综合

```
1. pipeline.py conflicts < claims.json → 机械冲突检测
2. 逐维度写 synthesis.md (导航摘要):
   - 每维度 ≤3 句
   - 链接到 evidence card
   - 不重复 evidence card 内容
3. 输出 research-gaps.json:
   无法确认的维度 + 缺什么 + 建议获取方式
```

## 读取阶梯

```
元数据 → 摘要 → matchedChunks → search_fulltext → bounded window → bounded section
```

在第一个足以回答问题的层级停止。

| 规则 | 说明 |
|:--|:--|
| matchedChunks 能回答，就不读全文 | 默认 |
| 窗口能回答，就不读章节 | 升级 |
| get_content(mode="complete") 不直接返回 Agent | 硬限制 |
| 全文仅 pipeline 解析 | 硬限制 |

## pipeline.py 命令

```
pipeline.py dedup    < papers.json    → 去重
pipeline.py conflicts < claims.json   → 冲突检测
pipeline.py index    < evidence_dir   → evidence-index 生成
pipeline.py validate < manifest.json  → schema 校验
```

Agent 先跑 Python → 只解析输出 → 不做手工去重/计数。

## 证据等级

| 等级 | 条件 | 能否引数值 |
|:--|:--|:--:|
| A | PDF 正文/图表/SI 直接支持; 有 quote + page/section/figure | ✅ |
| B | matchedChunk 或正文局部支持; 缺页码/完整上下文 | ✅ 标注"可能有损" |
| C | 摘要、综述转述、Obsidian 旧笔记 | ❌ |
| U | 未核实，仅线索 | ❌ |

matchedChunks 默认最多 B。C 级禁引数值。OCR 不稳时关键数值不标 A。

## 证据表达

严格区分: reported_fact / author_interpretation / agent_inference

禁止把 >140° 改写为 140°。禁止把"无需后修饰"扩大为"没有任何后处理"。

## DON'T

- ❌ 不形成科学观点 (那是观点讨论员的事)
- ❌ 不继承搜索对话上下文
- ❌ get_content(mode="complete") 不直接调用
- ❌ [C] 级禁引数值 → "⚠ Unverified"
- ❌ 不从 matchedChunks 直接建综合 (先落 evidence card)
- ❌ synthesis.md 不取代 evidence cards
- ❌ 工具失败后不换多种方式反复读取同一文件
- ❌ 不混淆 relevance_score 与 evidence_level

## 输出

```
$RUN/research/evidence/{zotero_key}.json   ← 逐篇 evidence cards
$RUN/research/evidence-index.json          ← 12 维矩阵 + 冲突
$RUN/research/synthesis.md                 ← 导航摘要 (≤3句/维度)
$RUN/research/research-gaps.json           ← 无法确认的维度
```
