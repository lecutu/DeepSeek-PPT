---
name: literature-search
description: 文献检索Skill——判断exact/survey/explore模式→本地优先→外部补搜→去重→PDF检测→OCR预判。跨工作区输出 result.json；内部管线输出 search-manifest.json。不产生科学观点。
trigger: /lit-search, /literature-search, 文献搜索, 找文献, search papers, Zotero搜索, arXiv搜索, 搜论文, 定位论文, 帮我搜索, 检索文献, 搜索文献
---

# literature-search — 文献发现与核验

## 核心约束

```
输入: task.json (观点员发给搜索员)
输出: result.json (精简, 仅 zotero_key + title + doi + year + relevance + pdf + safety)
不输出: matchedChunks, 完整元数据, 科学观点, PDF 路径
```

协议详见 `.claude/protocols/ai-task-protocol.md`。

## 搜索模式 → 自动路由

```
用户输入
  │
  ├─ DOI / 引号标题 / "这篇"/"读这篇"/"查这篇"
  │  → exact
  │
  ├─ 领域关键词 / "找文献" / "搜X方面"
  │  → survey
  │
  └─ 现象描述 / 观察 / 问句("为什么"/"怎么回事")
     → explore
```

| | exact | survey | explore |
|:---|:---|:---|:---|
| 典型输入 | `DOI:10.xxx` `找Kumar那篇` | `SiOC阳极` `POSS热性能` | `为什么SiOC首效只有50%` |
| RAG queries | 1条, topK=3 | ≤3条, topK=5 | 概念→近义词×3轮, topK=3-5 |
| P1 Gate | ≥0 | ≥10 | ≥3 |
| PDF 检测 | 有则标记无则跳过 | 全量检测 | 全量检测 |
| 排序 | 精确命中优先 | relevance_score 降序 | relevance_score 降序 |

### explore 模式专用: 现象→学术术语

```
1. 从现象描述提取核心概念 (Agent 自身, 不调 MCP):
   用户: "SiOC 负极首圈库仑效率只有 50% 怎么回事"
   提取: SiOC anode, first cycle Coulombic efficiency, low ICE
   近义词: ICE loss, initial capacity loss, SEI formation, irreversible capacity

2. 每轮 topK=5, 最多 3 轮, 前两轮累计 ≥5 篇则停止

3. search_library 兜底 (中文原文)
```

### explore 模式专用: 问题正交分解

复杂问题先拆分为互不重叠的子维度，每个子维度独立检索，最后合并去重：

```
用户问题
  │
  ├─ 反向拆解 (LLM, ≤500 token, 零 MCP):
  │   "把这个问题拆成 2-4 个互不重叠的子问题，每个子问题可被一篇论文的一个实验节回答"
  │   示例: "SiOC 首效低为什么" →
  │     Q1: SiOC 负极首效的典型值范围和测量方法
  │     Q2: SiOC 首效损失的主要机制（SEI/不可逆储锂/结构塌陷）
  │     Q3: 哪些合成/后处理参数影响 ICE
  │     Q4: 提高 SiOC 首效的文献策略（改性/掺杂/涂层）
  │
  ├─ 每个子问题 → 独立 semantic_search (1 query, topK=5)
  │
  └─ 合并: 子问题内按 relevance_score 排序 → 整体去重 → 保留 top 30
     各子问题至少保留 1 篇 (确保维度覆盖)
```

不要求每个子问题都命中等量文献。某子问题命中 0 篇 → 该维度标记为 research-gap。

## 检索流程

### Step 1 — 本地优先检索

```
1. semantic_status() → ready=true ? 语义 : 全 keyword
2. 英文概念 → semantic_search(topK, query)
   - exact: 1 query, topK=3
   - survey: ≤3 queries (材料/性能/方法), topK=5
   - explore: 概念→近义词×3轮, topK=3-5
3. 中文/DOI/标题 → search_library(limit=10, mode=preview) 兜底
   - 中文不走 semantic
   - 不用 complete mode
4. Obsidian 判 local (零正文三步):
   a. obsidian_list_notes("文献笔记", depth=3) → 文件名匹配 Author/Year
   b. obsidian_manage_frontmatter(op="get", key="doi") → DOI 匹配
   c. obsidian_search_notes(query, limit=5) → 仅前两步未命中时
5. local < 目标数 → mcp__paper-distill__search_papers 外部检索
6. 多源级联: Zotero → Obsidian → 外部 → Semantic Scholar → arXiv
```

### Step 2 — 元数据核验与去重

```
1. 元数据核验:
   - DOI 格式: ^10\.\d{4,}/.+$
   - 标题规范化: 去首尾空格, 规范化 Unicode
   - 作者/年份校验: 有就记录, 不编造

2. 去重 (pipeline.py dedup):
   - DOI 相同 → 合并, 保留最高 relevance_score
   - title 相似 >0.85 且无 DOI → 合并
   - Zotero 库内已有 DOI → 标记 library_status=already_exists

3. 身份验证:
   - DOI 可查 + 标题匹配 → verified
   - 仅标题匹配 → probable_match
   - 无 DOI 无标题匹配 → unverified
```

### Step 3 — PDF 可用性检测

```
PDF 获取尝试顺序 (仅合法来源):

1. Zotero 现有附件: get_item_details → hasFulltext
2. 发布商开放获取页面
3. Unpaywall / Crossref / OpenAlex
4. PubMed Central / arXiv / 机构仓储 / 作者主页
5. 校园网/VPN 授权访问
6. 以上全失败 → 标记 manual_action_required

D:\Zotero导入\ 目录作为用户手动导入兜底, 不作为自动下载源

不自动访问或绕过付费墙。
```

### Step 4 — OCR 需求预判

```
检测项目:
- PDF 是否存在
- 文本能否提取
- 提取文本长度
- 页面是否主要为图像
- 是否可能需要 OCR

输出标记:
{
  "pdf_status": "available|missing|manual_action_required",
  "text_status": "extractable|insufficient|image_only|not_checked",
  "needs_ocr": true|false,
  "ocr_reason": "Text extraction returned insufficient content from 12 pages."
}
```

### Step 5 — Obsidian 上下文 (仅 frontmatter)

```
obsidian_manage_frontmatter(op="get") → 读取已有笔记的质量标记

输出 (原样传递, 不改写):
{
  "obsidian_context": {
    "note_path": "文献笔记/...",
    "note_quality": "high|medium|low",
    "quality_source": "frontmatter"
  }
}

严禁: 把 "relevance_score 高" 写成 "note_quality=high"
```

### Step 6 — 排序与推荐

```
护栏预检 (Step 5.5 填充 safety_flags 后执行):
  检索结果中标记了 safety_flag 的论文:
    🚫 safety_redline/competitor → 标记 caution: 需护栏审查, 仍进入推荐但附警告
    ⚠️ risk/cost_concern → 标记 caution: 需护栏审查

tier 分配:
  tier 1: relevance_score ≥ 0.8 + pdf_status=available + identity_status=verified
  tier 2: relevance_score ≥ 0.6
  tier 3: 其余

selection_status:
  - recommended: tier 1 (含 safety_flag 论文 — 附 chemical_caution)
  - backup: tier 2
  - excluded: tier 3 (但写入 manifest 供参考)
```

### Step 5.5 — 化学护栏预检 (search 阶段)

检索完成后、排序与推荐前，对每篇论文的标题+摘要做轻量护栏扫描：

```
1. 读取 `.claude/guardrails/chemical-guardrail.json`
2. 逐篇扫描标题和摘要 (不读全文, 零额外 token):
   - 匹配 aliases 中任意别名 → 标记 safety_flag + 提取匹配到的物质名
   - 🚫 物质出现 → 不排除，但标记 chemical_caution: "含禁限物质, 研究阶段需护栏审查"
   - ⚠️ 物质出现 → 标记 chemical_caution: "含风险物质, 注意安全约束"
3. 注入 manifest candidates 字段:
   "safety_flags": [
     {"substance": "HMDS", "flag": "⚠️", "matched_in": "abstract"}
   ]
```

不因护栏预检排除论文——安全信息是观点来源的一部分。预检结果仅作为 manifest 中的标记传递，供 research 阶段使用。

## Gate 检查

| 模式 | Gate | 不过时 |
|:---|:---|:---|
| exact | total ≥ 0 | 直接报告未找到 |
| survey | total ≥ 10 | 告知不足, 是否降级为 explore |
| explore | total ≥ 3 | 告知不足, 建议扩大检索词 |

## 硬失败规则

```
- 无全文 PDF → 标记 pdf_status=missing/manual_action_required, 不编造
- 付费墙 → pdf_status=manual_action_required, reason=paywall
- 检索结果为空 → 如实报告, 不编造文献
- 身份无法验证 → identity_status=unverified, 不假装已确认
```

## pipeline.py

```
pipeline.py init     < config.json     → 创建 run 目录结构
pipeline.py dedup    < papers.json     → 去重
pipeline.py gate     < stats.json      → Phase Gate
pipeline.py validate < manifest.json   → schema 校验
pipeline.py handoff  < manifest.json   → 生成 handoff report
```

**Agent 先跑 Python → 只解析输出 → 不做手工去重/表格/计数。**

## 输出: result.json

精简 — 不给观点员传它自己能查到的：

```json
{
  "task": "search_result",
  "query": "SiOC anode first cycle Coulombic efficiency",
  "mode": "survey",
  "total": 12,
  "papers": [
    {
      "zotero_key": "ABC123",
      "title": "High-performance SiOC anode...",
      "doi": "10.xxxx/...",
      "year": 2023,
      "relevance": 0.91,
      "pdf": true,
      "safety": ["HMDS"]
    }
  ],
  "insufficient": false
}
```

| 字段 | 说明 |
|:--|:--|
| zotero_key | 唯一标识 — 观点员直接调 Zotero API |
| relevance | 排序用，不传递为证据等级 |
| safety | null 或 [物质名列表] — 仅告警，不判定 flag |
| insufficient | true → 结果不够 gate，观点员决定是否降级 |

不传: matchedChunks / 完整元数据 / PDF 路径 / Obsidian context / tier / selection_status。
观点员 Agent 自己调 semantic_search / search_fulltext / search_library 获取全文内容。

## DON'T

- ❌ 不产生 scientific claims, hypotheses, 或结论
- ❌ 不写入论文观点到 relevance_reason (只写为什么选这篇)
- ❌ 不混淆 obsidian_context.note_quality 与 relevance_score
- ❌ 不自动绕过付费墙或使用 Sci-Hub
- ❌ search_library 不用 complete mode
- ❌ 中文概念不走 semantic_search
- ❌ 不编造未检索到的文献
- ❌ 不将 matchedChunks 内容写入 manifest
```