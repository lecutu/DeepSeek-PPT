"""
Obsidian 记忆搜索 — 反噪音保护

三层裁断:
L1 意图分类 → 只有知识类查询才搜（拒绝闲聊/命令/过短查询）
L2 会话去重 → 同一问题直接返回缓存（Jaccard≥0.8）
L3 阈值过滤 → 最高分<0.35 → 拒绝，同文件只取最高分chunk
"""

import hashlib
import json
import os
import re
import sys
from typing import Optional

import zvec

VAULT_PATH = "D:/学术"
DB_PATH = "C:/Users/Lenovo/obsidian_vec"
META_PATH = os.path.join(DB_PATH, "index_meta.json")
CACHE_PATH = os.path.join(DB_PATH, "session_cache.json")

SCORE_MIN = 0.35
TOP_K = 5

# === L1: 查询意图分类 ===

SKIP_PATTERNS = [
    r"^(你好|hi|hello|谢谢|再见|bye|ok|好的|嗯|哦|知道了|明白)\b",
    r"^(帮我|给我|写|生成|创建|新建|删除|修改|保存|打开|关闭|运行|执行)\b",
    r"^(列出|显示|查看)\s*(文件|目录|文件夹)",
    r"^(今天|昨天|现在|几点|天气|时间|日期)",
    r"^(搜索|查找|找一下|搜一下)\s+文件",
]

KNOWLEDGE_PATTERNS = [
    r"(什么|为什么|如何|怎么|怎样|机制|原理|机理|原因|因素|条件|影响|关系|区别|对比|差异|分析|解释|讨论|总结|概述)",
    r"(合成|水解|缩合|缩聚|封端|固化|热解|纺丝|凝胶|沉淀|溶解|催化|交联)",
    r"(PMSQ|MTMS|SiOC|SiOH|HMDS|TMSCl|POSS|PSQ|有机硅|硅烷|硅氧烷|碳化硅|SiC)",
    r"(分子量|MW|Mn|PDI|温度|pH|浓度|时间|比率|R[₁₂₃\\d]|催化剂)",
    r"(文献|论文|专利|实验|数据|结论|证据|结果|表征|NMR|IR|GPC|DSC|TGA|SEM|TEM|XRD|XPS)",
    r"(Abe|Lee|Dong|Smith|Alam|Takamura|Yoldas|Pohl|Fujitsu|Wacker|Dow[ -]?Corning|Shin[ -]?Etsu|信越)",
    r"(润湿|接触角|表面|疏水|亲水|表面能|界面)",
    r"(阳极|负极|电池|容量|循环|库[仑伦]|倍率|SEI|电化学)",
]


def classify_query(q):
    qs = q.strip()
    if len(qs) < 4:
        return False, "too_short"

    for pat in SKIP_PATTERNS:
        if re.search(pat, qs, re.IGNORECASE):
            return False, f"skip:{pat[:40]}"

    for pat in KNOWLEDGE_PATTERNS:
        if re.search(pat, qs, re.IGNORECASE):
            return True, f"knowledge:{pat[:40]}"

    # 容忍模糊查询（10字以上 + 含关键术语）
    fuzzy_kw = ["PMSQ", "MTMS", "SiOC", "SiOH", "HMDS", "TMSCl",
                "封端", "水解", "缩合", "缩聚", "热解", "纺丝",
                "硅烷", "硅氧烷", "硅树脂", "前驱体", "阳极"]
    if len(qs) >= 10 and any(kw in qs for kw in fuzzy_kw):
        return True, "fuzzy"

    return False, "no_signal"


# === L2: 会话去重 ===

def load_cache():
    if not os.path.exists(CACHE_PATH):
        return {"queries": {}, "query_texts": {}}
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def dedup_query(query, cache):
    qhash = hashlib.md5(query.strip().encode()).hexdigest()[:12]
    if qhash in cache.get("queries", {}):
        return cache["queries"][qhash]
    for phash, presult in cache.get("queries", {}).items():
        pq = cache.get("query_texts", {}).get(phash, "")
        if pq and _jaccard(query, pq) > 0.8:
            return presult
    return None


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


# === L3: 语义搜索 ===

def load_embedder():
    return zvec.DefaultLocalDenseEmbedding(model_source="modelscope")


def search(query, top_k=TOP_K, score_min=SCORE_MIN):
    searchable, reason = classify_query(query)
    if not searchable:
        return {"rejected": True, "reason": reason, "results": []}

    cache = load_cache()
    cached = dedup_query(query, cache)
    if cached:
        return {"from_cache": True, "results": cached}

    meta = _load_meta()
    if not meta or meta.get("total_chunks", 0) == 0:
        return {"rejected": True, "reason": "no_index", "results": []}

    emb = load_embedder()
    qvec = emb.embed(query)

    schema = zvec.CollectionSchema(
        name="obsidian_mem",
        vectors=zvec.VectorSchema("v", zvec.DataType.VECTOR_FP32, meta.get("embedding_dim", 512)),
    )

    collection = zvec.open(path=DB_PATH)
    q = zvec.Query("v", vector=qvec)
    raw = collection.query(queries=q, topk=min(top_k * 4, meta.get("total_chunks", 999)))

    chunks = meta.get("chunks", {})
    formatted = []
    seen_files = set()

    for item in raw:
        score = float(item.score)
        if score < score_min:
            continue
        cm = chunks.get(item.id, {})
        f = cm.get("file", "")
        if not cm or f in seen_files:
            continue
        seen_files.add(f)
        preview = _read_chunk(item.id, cm)
        if not preview:
            continue
        formatted.append({
            "score": round(score, 3),
            "file": f,
            "title": cm.get("title", ""),
            "heading": cm.get("heading", ""),
            "quality": cm.get("quality", ""),
            "date": cm.get("date", ""),
            "tags": cm.get("tags", []),
            "preview": preview[:600],
        })
        if len(formatted) >= top_k:
            break

    if not formatted or formatted[0]["score"] < score_min:
        result = {"rejected": True, "reason": f"score<{score_min}", "results": formatted}
    else:
        result = {"results": formatted}

    qhash = hashlib.md5(query.strip().encode()).hexdigest()[:12]
    cache.setdefault("queries", {})[qhash] = formatted
    cache.setdefault("query_texts", {})[qhash] = query
    if len(cache["queries"]) > 50:
        oldest = min(cache["queries"].keys(),
                     key=lambda k: len(str(cache["queries"].get(k, ""))))
        cache["queries"].pop(oldest, None)
    save_cache(cache)

    return result


def _load_meta():
    if not os.path.exists(META_PATH):
        return None
    with open(META_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_chunk(cid, cm):
    """从 chunk_id 推导文件路径并读取对应节的内容"""
    file_rel = cm.get("file", "")
    if not file_rel:
        return ""
    fp = os.path.join(VAULT_PATH, file_rel)
    if not os.path.exists(fp):
        return ""
    try:
        with open(fp, "r", encoding="utf-8") as f:
            text = f.read()
        heading = cm.get("heading", "")
        if not heading:
            return text[:600]
        # 找对应 ## 标题的内容
        heading_parts = heading.split(" > ")
        target = heading_parts[-1]
        lines = text.split("\n")
        collecting = False
        collected = []
        for line in lines:
            if re.match(r"^#{1,3}\s+", line):
                if target in line:
                    collecting = True
                    continue
                elif collecting:
                    break
            if collecting:
                collected.append(line)
        content = "\n".join(collected).strip()
        return content[:600] if content else text[:600]
    except Exception:
        return ""


def format_agent_ctx(results, query=""):
    """Agent 上下文注入格式"""
    if results.get("rejected"):
        return None
    items = results.get("results", [])
    if not items:
        return None
    lines = [f"## Obsidian记忆检索 ({query})", ""]
    for i, r in enumerate(items):
        qual = f"quality:{r['quality']}" if r.get("quality") else ""
        date = f"[{r['date']}]" if r.get("date") else ""
        meta = " | ".join(filter(None, [qual, date]))
        lines.append(f"### [{i+1}] {r['title']} — `{r['file']}`")
        if meta:
            lines.append(f"*{meta}*")
        lines.append(f"```\n{r['preview']}\n```\n")
    return "\n".join(lines)


# CLI test
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python obsidian_search.py <query>")
        sys.exit(1)
    q = " ".join(sys.argv[1:])
    r = search(q)
    if r.get("rejected"):
        print(f"REJECTED: {r['reason']}")
        sys.exit(0)
    if r.get("from_cache"):
        print("[from session cache]")
    for item in r["results"]:
        print(f"[{item['score']:.3f}] {item['title']} ({item['file']})")
        print(f"  {item['preview'][:150]}...\n")
