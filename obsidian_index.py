"""
Obsidian → zvec 向量索引器 (中文优化版)

使用 zvec 内置 DefaultLocalDenseEmbedding(model_source="modelscope")
→ GTE-Chinese-small (512维, 中文原生)

每 md 按 ## 标题分 chunk → 嵌入 → zvec HNSW 索引
增量更新：只重建修改时间晚于上次索引的文件

用法:
  python obsidian_index.py --vault "D:/学术" --db "D:/文献搜索员/obsidian_zvec"
  python obsidian_index.py --incremental
"""

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import zvec

VAULT_PATH = "D:/学术"
DB_PATH = "C:/Users/Lenovo/obsidian_vec"
META_PATH = os.path.join(DB_PATH, "index_meta.json")
MIN_CHUNK_LEN = 80
SKIP_DIRS = {".obsidian", ".claude", ".agents", ".trash", "_templates", ".git"}
BATCH_SIZE = 16

# 结构化声明提取的最小质量阈值
FRONTMATTER_KEEP = {"quality", "date", "tags", "title"}


def load_embedder():
    return zvec.DefaultLocalDenseEmbedding(model_source="modelscope")


def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 3:].strip()
    meta = {}
    for line in raw.split("\n"):
        line = line.strip()
        if ":" in line:
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
            meta[k] = v
    return meta, body


def chunk_markdown(text, min_len=MIN_CHUNK_LEN):
    lines = text.split("\n")
    chunks = []
    hstack = ["(top)"]  # 标题栈
    current_lines = []

    def flush():
        content = "\n".join(current_lines).strip()
        if content and len(content) >= min_len:
            chunks.append((" > ".join(hstack), content))
        elif content and chunks:
            # 合并到前一chunk
            prev_h, prev_c = chunks[-1]
            chunks[-1] = (prev_h, prev_c + "\n" + content)

    for line in lines:
        m = re.match(r"^(#{1,3})\s+(.+)", line)
        if m:
            flush()
            level = len(m.group(1))
            heading = m.group(2).strip()
            # 更新标题栈
            hstack = hstack[:level] + [heading]
            current_lines = []
        else:
            current_lines.append(line)

    flush()
    return chunks


def scan_vault(vault_path, incremental=False):
    vault = Path(vault_path)
    last_index = {}
    if incremental and os.path.exists(META_PATH):
        with open(META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
            last_index = meta.get("file_mtimes", {})

    files = []
    for md in sorted(vault.rglob("*.md")):
        parts = set(md.relative_to(vault).parts)
        if parts & SKIP_DIRS:
            continue
        if md.name == "CLAUDE.md" and md.parent == vault:
            continue

        mtime = md.stat().st_mtime
        rel = str(md.relative_to(vault)).replace("\\", "/")

        if incremental and rel in last_index and last_index[rel] >= mtime:
            continue

        files.append((md, rel, mtime))

    return files, {f[1]: f[2] for f in files}


def index_vault(vault_path, db_path, incremental=False):
    vault = Path(vault_path)
    if not vault.exists():
        raise FileNotFoundError(f"Vault not found: {vault_path}")

    parent = os.path.dirname(db_path)
    os.makedirs(parent, exist_ok=True)

    print(f"Scanning: {vault_path}")
    file_list, new_mtimes = scan_vault(vault_path, incremental)
    n = len(file_list)
    print(f"  {n} files to index" + (" (incremental)" if incremental else ""))

    if n == 0:
        print("  Nothing to index.")
        return

    print("Loading embedder (GTE-Chinese-small, modelscope)...")
    emb = load_embedder()
    dim = emb.dimension
    print(f"  dim={dim}")

    schema = zvec.CollectionSchema(
        name="obsidian_mem",
        vectors=zvec.VectorSchema("v", zvec.DataType.VECTOR_FP32, dim),
    )

    idx_exists = os.path.exists(db_path)
    if idx_exists:
        import shutil
        shutil.rmtree(db_path, ignore_errors=True)

    collection = zvec.create_and_open(path=db_path, schema=schema)

    existing_meta = {"file_mtimes": {}, "chunks": {}, "total_chunks": 0}
    if os.path.exists(META_PATH):
        with open(META_PATH, "r", encoding="utf-8") as f:
            existing_meta = json.load(f)

    # 删除本次要重建文件的旧 chunks
    for rel in new_mtimes:
        old_keys = [k for k in existing_meta["chunks"] if k.startswith(
            re.sub(r"[^a-zA-Z0-9_\-/.]", "_", rel).replace("\\", "/") + "#")]
        for k in old_keys:
            del existing_meta["chunks"][k]

    texts_batch = []
    cids_batch = []
    metas_batch = []
    total = 0

    for i, (file_path, rel, mtime) in enumerate(file_list):
        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{n}] {rel}")

        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  SKIP {rel}: {e}")
            existing_meta["file_mtimes"][rel] = mtime
            continue

        frontmatter, body = parse_frontmatter(text)
        quality = frontmatter.get("quality", "")
        date_str = frontmatter.get("date", "")
        tags = frontmatter.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        title = frontmatter.get("title", file_path.stem)

        chunks = chunk_markdown(body)
        if not chunks and len(body.strip()) >= MIN_CHUNK_LEN:
            chunks = [("", body.strip())]

        for ci, (heading, content) in enumerate(chunks):
            safe_rel = re.sub(r"[^a-zA-Z0-9_/.]", "_", rel).replace("\\", "/")
            cid = safe_rel.replace("/", "_").replace(".", "_").replace("-", "_")
            cid = re.sub(r"_{2,}", "_", cid)   # collapse multi-underscore
            cid = re.sub(r"^[_]+", "", cid)    # strip leading underscores
            cid = re.sub(r"[_]+$", "", cid)    # strip trailing underscores
            cid = f"{cid}_c{ci}"

            search_text = f"{title}\n{heading}\n{content}"

            texts_batch.append(search_text)
            cids_batch.append(cid)
            metas_batch.append({
                "file": rel,
                "title": title,
                "heading": heading,
                "quality": quality,
                "date": date_str,
                "tags": tags,
            })

            if len(texts_batch) >= BATCH_SIZE:
                total += _flush(emb, collection, texts_batch, cids_batch, metas_batch, META_PATH)
                texts_batch.clear(); cids_batch.clear(); metas_batch.clear()

        existing_meta["file_mtimes"][rel] = mtime

    if texts_batch:
        total += _flush(emb, collection, texts_batch, cids_batch, metas_batch, META_PATH)

    # 最后写一次完整的 meta（确保 file_mtimes 已更新）
    with open(META_PATH, "r", encoding="utf-8") as f:
        final_meta = json.load(f)
    final_meta["file_mtimes"] = existing_meta["file_mtimes"]
    final_meta["total_chunks"] = len(final_meta["chunks"])
    final_meta["total_files"] = len(final_meta["file_mtimes"])
    final_meta["indexed_at"] = datetime.now(timezone.utc).isoformat()
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(final_meta, f, ensure_ascii=False, indent=2)

    print(f"\nDone: {total} chunks added, {final_meta['total_chunks']} total, ")


def _flush(emb, collection, texts, cids, metas, meta_path=None):
    vecs = []
    for t in texts:
        v = emb.embed(t)
        vecs.append(v)
    docs = []
    for cid, vec, cm in zip(cids, vecs, metas):
        docs.append(zvec.Doc(id=cid, vectors={"v": vec}))
    collection.insert(docs)

    # 同步写入 meta.json（增量更新，防崩溃丢数据）
    if meta_path:
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            meta = {"file_mtimes": {}, "chunks": {}, "total_chunks": 0}

        for cid, cm in zip(cids, metas):
            meta["chunks"][cid] = cm
        meta["total_chunks"] = len(meta["chunks"])
        meta["indexed_at"] = datetime.now(timezone.utc).isoformat()

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    return len(docs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=VAULT_PATH)
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--incremental", action="store_true")
    args = parser.parse_args()
    t0 = time.time()
    index_vault(args.vault, args.db, incremental=args.incremental)
    print(f"Time: {time.time() - t0:.1f}s")
