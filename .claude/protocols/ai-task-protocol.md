# AI 间交接协议 — task.json / result.json

## 原则

- 搜索员和观点员之间的 JSON 尽可能小 — 只传任务参数和结果摘要
- 不传 matchedChunks、不传完整元数据（都在 Zotero 里，观点员自己查）
- 观点员有自己的 Zotero 工具，可以直接搜索/读全文/入库

## 请求: task.json

由观点员发给搜索员：

```json
{
  "task": "search",
  "query": "SiOC anode first cycle Coulombic efficiency",
  "mode": "survey",
  "max_results": 15,
  "filters": {
    "year_from": 2020,
    "must_have_abstract": true
  }
}
```

| 字段 | 必需 | 说明 |
|:--|:--|:--|
| task | ✅ | 固定 "search" |
| query | ✅ | 搜索词 (英文) |
| mode | ✅ | exact / survey / explore |
| max_results | 否 | 默认 15 |
| filters | 否 | year_from / must_have_abstract |

## 响应: result.json

由搜索员返回给观点员：

```json
{
  "task": "search_result",
  "query": "SiOC anode first cycle Coulombic efficiency",
  "total": 12,
  "papers": [
    {
      "zotero_key": "ABC123",
      "title": "High-performance SiOC anode...",
      "doi": "10.xxxx/...",
      "year": 2023,
      "relevance": 0.91,
      "pdf": true,
      "safety": null
    }
  ],
  "insufficient": false
}
```

| 字段 | 说明 |
|:--|:--|
| zotero_key | 唯一标识 — 观点员直接用它调 Zotero API |
| doi | 去重用 |
| year | 排序用 |
| relevance | 排序用，不传递为证据等级 |
| pdf | PDF 是否可用 |
| safety | null / `["HMDS"]` — 仅标匹配到什么，不标 flag（flag 观点员自己从护栏表查） |
| insufficient | 结果数不够 gate → 观点员决定是否降级 |

## 不传的内容

- ❌ matchedChunks (观点员自己调 semantic_search)
- ❌ fulltext (不存在这里)
- ❌ 全文元数据 (authors/venue/abstract — Zotero 里有)
- ❌ PDF 路径/tier/selection_status/Obsidian context (本地机器信息)
- ❌ evidence card / chemical_audit (那是 research 阶段的输出，不是 search)
