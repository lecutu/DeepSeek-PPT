"""
profiles.py — 版式推断：从 PPT 母版/形状推断 LayoutProfile。
"""
from .types import GridConfig, LayoutProfile, ContentType
from .info_grid import InformationGrid
from .positioning import parse_cell, cell_name


def infer_profile(grid: InformationGrid, config: GridConfig | None = None) -> LayoutProfile:
    """从已填充的 info_grid 推断版式约束。

    启发式规则：
      覆盖 >80% 画布面积 → 装饰/locked
      顶部 2 行 → title 区
      底部 1 行 → footer 区（locked）
      中部纯 SHAPE 无文字 → 装饰
    """
    cfg = config or GridConfig()
    profile = LayoutProfile(name="auto")
    occ = grid.occupied_coarse()

    total_coarse = cfg.coarse_cols * cfg.coarse_rows

    for oid, coarse_cells in occ.items():
        rows = set()
        cols = set()
        for c in coarse_cells:
            try:
                col, row = parse_cell(c)
                rows.add(row)
                cols.add(col)
            except ValueError:
                continue
        if not rows:
            continue

        min_r, max_r = min(rows), max(rows)
        cell_count = len(coarse_cells)
        coverage = cell_count / total_coarse

        # 全覆盖背景 → 装饰，锁定
        if coverage > 0.8:
            profile.locked_zones.update(coarse_cells)
            profile.decorative_elements.add(oid)
            continue

        # 底部一行 → footer zone，锁定
        if min_r >= cfg.coarse_rows - 1:
            profile.locked_zones.update(coarse_cells)
            profile.decorative_elements.add(oid)
            profile.zones.setdefault("footer", []).extend(
                c for c in coarse_cells
                if c not in profile.zones.get("footer", [])
            )
            continue

        # 顶部 2 行 → title/subtitle zone
        if max_r <= 1:
            # 小框可能是 subtitle
            if cell_count <= 3:
                profile.zones.setdefault("subtitle", []).extend(
                    c for c in coarse_cells
                    if c not in profile.zones.get("subtitle", [])
                )
            else:
                profile.zones.setdefault("title", []).extend(
                    c for c in coarse_cells
                    if c not in profile.zones.get("title", [])
                )
            continue

        # 中部 → 暂不分 zone（后续可根据 content_type 进一步分类）

    return profile
