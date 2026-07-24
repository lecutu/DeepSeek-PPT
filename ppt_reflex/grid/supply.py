"""
grid/supply.py — Agent 输出格式化

把 info_grid 的状态格式化为 Agent 友好的分层 JSON。
不碰判定逻辑，不做 IO — 只做格式化。
"""

from __future__ import annotations
from .types import (
    GridConfig, ContentType, Conflict, PlacementResult, LayoutProfile,
)
from .info_grid import InformationGrid
from .positioning import cell_range


class Supply:
    """从 info_grid 生成 Agent 视图。"""

    def __init__(self, config: GridConfig | None = None):
        self.config = config or GridConfig()

    # ═══════════════════════════════════════════════════════════
    # LEVEL 0 — 幻灯片总览 (~30-50 tokens)
    # ═══════════════════════════════════════════════════════════

    def level0(self, grid: InformationGrid, profile: LayoutProfile | None = None) -> dict:
        """幻灯片总览 — Agent 看到的第一眼。"""
        occ = grid.occupied_coarse()

        zones = {}
        for oid, cells in occ.items():
            is_locked = profile and oid in profile.decorative_elements
            label = _clean_id(oid)
            rng = cell_range(list(cells))
            tag = "locked" if is_locked else ""
            zones[label] = {"range": rng, "tag": tag}

        free_rects = self._free_rectangles(grid)
        density = round(grid.density() * 100, 1)

        result = {
            "slide": len(zones),
            "zones": zones,
            "free": free_rects[:3],  # 最多 3 个空闲区
            "density": density,
        }

        if profile and profile.page_constraints:
            result["constraints"] = profile.page_constraints

        return result

    # ═══════════════════════════════════════════════════════════
    # LEVEL 1 — 单区域详情 (~80-100 tokens, 按需)
    # ═══════════════════════════════════════════════════════════

    def level1(self, grid: InformationGrid, zone_cells: list[str]) -> dict:
        """指定区域的详细信息 — Agent 请求 L1 时给出。"""
        result = {"zone": cell_range(zone_cells)}

        covered = []
        owners_in_zone: set[str] = set()
        for addr in zone_cells:
            cell = grid.get_cell(addr)
            if cell and cell.owner_id:
                covered.append({
                    "addr": addr,
                    "owner": _clean_id(cell.owner_id),
                    "type": cell.content_type.value if cell.content_type else "unknown",
                })
                owners_in_zone.add(cell.owner_id)

        result["elements"] = covered
        result["element_count"] = len(owners_in_zone)

        # 邻居
        neighbors = self._find_neighbors(grid, zone_cells)
        result["neighbors"] = neighbors

        return result

    # ═══════════════════════════════════════════════════════════
    # LEVEL 2 — 单元素全貌 (~50-60 tokens, 按需)
    # ═══════════════════════════════════════════════════════════

    def level2(self, grid: InformationGrid, element_id: str) -> dict | None:
        """单个元素的完整信息。"""
        occ = grid.all_occupied()
        cells = occ.get(element_id)
        if not cells:
            return None

        coarse = set()
        content_types: set[ContentType] = set()
        for addr in cells:
            cell = grid.get_cell(addr)
            if cell and cell.content_type:
                content_types.add(cell.content_type)
            from .positioning import parse_cell
            try:
                col_f, row_f = parse_cell(addr)
                coarse_c = col_f // 2
                coarse_r = row_f // 2
                from .positioning import cell_name
                coarse.add(cell_name(coarse_c, coarse_r))
            except ValueError:
                pass

        return {
            "id": element_id,
            "type": content_types.pop().value if content_types else "unknown",
            "cells": cell_range(list(coarse)),
            "fine_cells": len(cells),
        }

    # ═══════════════════════════════════════════════════════════
    # CONFLICT — 聚合冲突报告
    # ═══════════════════════════════════════════════════════════

    def format_conflict(self, result: PlacementResult) -> dict:
        """把 raw conflicts 聚合成 Agent 友好的报告。"""
        if result.allowed:
            return {"status": "clean"}

        # 按对方元素聚合
        by_opponent: dict[str, list[Conflict]] = {}
        for c in result.conflicts:
            by_opponent.setdefault(c.existing_id, []).append(c)

        summary = []
        for opponent_id, conflicts in by_opponent.items():
            types_seen = set((c.existing_type, c.new_type) for c in conflicts)
            detail = "; ".join(
                f"{et.value}∩{nt.value}" for et, nt in types_seen
            )
            summary.append({
                "conflict_with": _clean_id(opponent_id),
                "cells": list(set(c.cell_addr for c in conflicts)),
                "type": detail,
                "verdict": "BLOCK",
            })

        report = {
            "status": "blocked" if result.verdict.name == "BLOCK" else "warning",
            "conflicts": summary,
            "conflict_count": len(summary),
        }

        if result.free_suggestion:
            report["suggestions"] = [
                cell_range(free_rect) for free_rect in result.free_suggestion
            ]

        if result.z_hint:
            report["z_order"] = result.z_hint

        if result.warnings:
            report["warnings"] = [
                {"cell": w.cell_addr, "detail": w.detail}
                for w in result.warnings[:3]
            ]

        return report

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _free_rectangles(self, grid: InformationGrid) -> list[dict]:
        """扫描定位层的空闲连续区域。"""
        occ = grid.occupied_coarse()
        occupied: set[str] = set()
        for cells in occ.values():
            occupied.update(cells)

        rects = []
        max_col = self.config.coarse_cols
        max_row = self.config.coarse_rows
        seen: set[str] = set()

        for r in range(max_row):
            for c in range(max_col):
                from .positioning import cell_name
                addr = cell_name(c, r)
                if addr in seen or addr in occupied:
                    continue
                # 向右扩展
                ec = c
                while ec < max_col:
                    next_cell = cell_name(ec, r)
                    if next_cell in occupied or next_cell in seen:
                        break
                    ec += 1
                # 往下扩展
                er = r
                while er < max_row:
                    row_clear = True
                    for cc in range(c, ec):
                        if cell_name(cc, er) in occupied:
                            row_clear = False
                            break
                    if not row_clear:
                        break
                    er += 1
                # 收集
                cells_in_rect = []
                for rr in range(r, er):
                    for cc in range(c, ec):
                        ca = cell_name(cc, rr)
                        cells_in_rect.append(ca)
                        seen.add(ca)
                if cells_in_rect:
                    rects.append({
                        "range": cell_range(cells_in_rect),
                        "cols": ec - c,
                        "rows": er - r,
                    })

        # 按面积降序
        rects.sort(key=lambda x: x["cols"] * x["rows"], reverse=True)
        return rects

    def _find_neighbors(self, grid: InformationGrid, zone_cells: list[str]) -> list[dict]:
        """找到接触区域的邻居元素。"""
        from .positioning import parse_cell, cell_name

        zone_set = set(zone_cells)
        neighbors: dict[str, list[str]] = {}

        for addr in zone_cells:
            try:
                col, row = parse_cell(addr)
            except ValueError:
                continue
            for dc, dr in [(-1,0), (1,0), (0,-1), (0,1)]:
                nc, nr = col + dc, row + dr
                na = cell_name(nc, nr)
                if na in zone_set:
                    continue
                cell = grid.get_cell(na)
                if cell and cell.owner_id and not cell.locked:
                    neighbors.setdefault(cell.owner_id, []).append(na)

        return [
            {"id": _clean_id(oid), "touching_cells": list(set(cells)[:3])}
            for oid, cells in neighbors.items()
        ]


def _clean_id(element_id: str) -> str:
    """简化 ID 显示: 'shape-01' → 's01'"""
    return element_id.replace("shape-", "s")
