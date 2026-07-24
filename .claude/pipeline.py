#!/usr/bin/env python3
"""literature-search + literature-research pipeline helpers — 机械操作, 零科学判断."""
import json, sys, re, hashlib
from pathlib import Path
from difflib import SequenceMatcher

# ============================================================
# Phase 1: 去重
# ============================================================

def deduplicate(papers: list) -> list:
    """DOI 精确去重 + title 相似度 ≥0.85 去重."""
    seen_doi = set()
    deduped = []
    for p in sorted(papers, key=lambda x: x.get("relevance_score", 0), reverse=True):
        doi = (p.get("doi", "") or "").strip().lower()
        if doi and doi in seen_doi:
            continue
        if doi:
            seen_doi.add(doi)
        title = p.get("title", "")
        is_dup = False
        for existing in deduped:
            if not doi and not existing.get("doi"):
                sim = SequenceMatcher(None, title.lower(), existing["title"].lower()).ratio()
                if sim > 0.85:
                    is_dup = True
                    break
        if not is_dup:
            deduped.append(p)
    return deduped

# ============================================================
# 元数据核验
# ============================================================

DOI_REGEX = re.compile(r'^10\.\d{4,}/.+$')

def validate_metadata(candidates: list) -> list:
    """校验 DOI 格式 + 标题规范化 + 身份验证标记."""
    for c in candidates:
        doi = (c.get("doi", "") or "").strip()
        if DOI_REGEX.match(doi):
            c["doi"] = doi
        elif doi:
            c.setdefault("warnings", []).append(f"DOI format invalid: {doi}")
        c["title"] = (c.get("title", "") or "").strip()
    return candidates

# ============================================================
# Phase Gate
# ============================================================

def check_gate(search_mode: str, stats: dict) -> dict:
    """返回 {pass: bool, reason: str}."""
    total = stats.get("total", 0)
    thresholds = {"exact": 0, "survey": 10, "explore": 3}
    target = thresholds.get(search_mode, 3)
    return {
        "pass": total >= target,
        "reason": f"mode={search_mode}, total={total}, need≥{target}"
    }

# ============================================================
# Manifest schema 校验
# ============================================================

REQUIRED_CANDIDATE_FIELDS = [
    "candidate_id", "item_id", "title", "identity_status", "tier", "selection_status"
]
VALID_IDENTITY = {"verified", "probable_match", "unverified"}
VALID_SELECTION = {"recommended", "backup", "excluded"}

def validate_manifest(manifest: dict) -> dict:
    """校验 search-manifest.json 结构."""
    errors = []
    if "candidates" not in manifest:
        errors.append("missing 'candidates' array")
    else:
        for i, c in enumerate(manifest["candidates"]):
            for f in REQUIRED_CANDIDATE_FIELDS:
                if f not in c:
                    errors.append(f"candidates[{i}]: missing '{f}'")
            if c.get("identity_status") not in VALID_IDENTITY:
                errors.append(f"candidates[{i}]: invalid identity_status={c.get('identity_status')}")
            if c.get("selection_status") not in VALID_SELECTION:
                errors.append(f"candidates[{i}]: invalid selection_status={c.get('selection_status')}")
    return {"valid": len(errors) == 0, "errors": errors}

# ============================================================
# Handoff 生成
# ============================================================

def generate_handoff(manifest: dict) -> dict:
    """从 manifest 提取 handoff 报告."""
    recommended = [
        c["item_id"] for c in manifest.get("candidates", [])
        if c.get("selection_status") == "recommended"
    ]
    by_tier = {}
    for c in manifest.get("candidates", []):
        tier = c.get("tier", 3)
        by_tier.setdefault(tier, []).append(c["item_id"])
    return {
        "run_id": manifest.get("run_id"),
        "recommended": recommended,
        "by_tier": by_tier,
        "total": len(manifest.get("candidates", [])),
        "pdf_failures": len(manifest.get("pdf_failures", [])),
    }

# ============================================================
# evidence card 冲突检测
# ============================================================

def detect_conflicts(claims: list) -> dict:
    """合并同 topic 声明, 检测冲突."""
    from collections import defaultdict
    by_topic = defaultdict(list)
    for c in claims:
        by_topic[c.get("topic", "general")].append(c)

    merged = []
    conflicts = []
    for topic, entries in by_topic.items():
        conclusions = [e.get("conclusion") for e in entries if e.get("conclusion")]
        unique = list(set(conclusions))
        n = len(entries)
        dois = [e.get("source_doi", "") for e in entries]
        if len(unique) > 1:
            status = "⚠ Conflicting"
            conflicts.append({"topic": topic, "dois": dois, "conclusions": unique})
        elif n >= 2:
            status = f"Supported (n={n})"
        elif n == 1:
            status = "Supported (single source)"
        else:
            status = "Unverified"
        merged.append({
            "topic": topic,
            "support_status": status,
            "evidence_level": max(
                (e.get("evidence_level", "C") for e in entries),
                key=lambda x: {"A": 3, "B": 2, "C": 1}.get(x, 0)
            ),
            "source_doi": ", ".join(dois),
        })
    return {"claims": merged, "conflicts": conflicts}

# ============================================================
# Obsidian quality 预检 (仅 frontmatter, 零正文)
# ============================================================

def read_quality(obsidian_data: list[dict]) -> dict:
    """输入: manage_frontmatter(op='get', key='quality') 的结果列表."""
    return {
        entry["doi"]: entry.get("quality", "none")
        for entry in obsidian_data
        if entry.get("doi")
    }

# ============================================================
# Evidence index 生成
# ============================================================

def build_evidence_index(evidence_dir: str) -> dict:
    """扫描 evidence/*.json 生成索引."""
    import os
    index = {"papers": [], "dimensions": {}, "total_cards": 0}
    dims = [
        "synthesis", "thermal.TGA", "molecular.GPC", "structure.NMR",
        "structure.FTIR", "structure.XRD", "mechanical", "dielectric",
        "surface", "electrochemical", "application", "mechanism"
    ]
    for d in dims:
        index["dimensions"][d] = {"status": "not_reported", "paper_count": 0}

    p = Path(evidence_dir)
    if not p.exists():
        return index

    for f in sorted(p.glob("*.json")):
        try:
            card = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        paper_entry = {
            "item_id": card.get("item_id"),
            "title": card.get("title"),
            "doi": card.get("doi"),
            "reading_status": card.get("reading_status"),
            "question_count": len(card.get("questions", [])),
        }
        index["papers"].append(paper_entry)
        index["total_cards"] += 1

        for q in card.get("questions", []):
            dim = q.get("topic", "general")
            if dim in index["dimensions"]:
                index["dimensions"][dim]["status"] = "reported"
                index["dimensions"][dim]["paper_count"] += 1

    return index

# ============================================================
# CLI: 从 stdin 读 JSON, 输出结果
# ============================================================

COMMANDS = {
    "dedup": ("papers", deduplicate),
    "gate": (None, lambda d: check_gate(
        d.get("search_mode", "explore"), d.get("stats", {})
    )),
    "validate": ("manifest", lambda d: validate_manifest(d)),
    "handoff": ("manifest", lambda d: generate_handoff(d)),
    "metadata": ("candidates", validate_metadata),
    "conflicts": ("claims", detect_conflicts),
    "quality": ("obsidian", read_quality),
    "index": ("evidence_dir", lambda d: build_evidence_index(d.get("evidence_dir", "."))),
}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"usage: pipeline.py <{'|'.join(COMMANDS)}>", file=sys.stderr)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)

    raw = sys.stdin.read() if not sys.stdin.isatty() else "{}"
    data = json.loads(raw)
    wrapper_key, fn = COMMANDS[cmd]

    if wrapper_key and wrapper_key in data:
        result = fn(data[wrapper_key])
    elif wrapper_key and isinstance(data, list):
        result = fn(data)
    else:
        result = fn(data)

    print(json.dumps(result, ensure_ascii=False, indent=2))
