"""
grid/spatial.py — 空间索引预计算

信息层常驻查询集，Agent 请求时直接返回，不实时遍历。
nearest_neighbor / gap_matrix / alignment_groups / density_heatmap / orphans
"""

from __future__ import annotations
from dataclasses import dataclass, field
from .types import GridConfig, ContentType, InfoCell
from .info_grid import InformationGrid
from .positioning import parse_cell, cell_name


@dataclass
class SpatialIndex:
    """信息层预计算的空间关系数据——按需刷新，Agent 查询时零遍历。"""

    config: GridConfig = field(default_factory=GridConfig)

    # {element_id: (neighbor_id, distance_pt)}
    nearest_neighbor: dict[str, tuple[str, float]] = field(default_factory=dict)

    # 列/行上的间距数组 {row: [gap1_pt, gap2_pt, ...]}
    gap_matrix_rows: dict[int, list[float]] = field(default_factory=dict)
    gap_matrix_cols: dict[int, list[float]] = field(default_factory=dict)

    # 对齐组 {left_edge_pt: [element_ids]}
    alignment_groups: dict[float, list[str]] = field(default_factory=dict)

    # 密度热力 {coarse_cell_addr: density_0_to_1}
    density_heatmap: dict[str, float] = field(default_factory=dict)

    # 孤岛元素
    orphans: set[str] = field(default_factory=set)

    dirty: bool = True

    def rebuild(self, grid: InformationGrid) -> None:
        self.config = grid.config
        occ = grid.all_occupied()
        if not occ:
            self.dirty = False
            return

        elements: dict[str, dict] = {}  # eid → {bbox, type}

        for eid, fine_cells in occ.items():
            bbox = self._bbox_from_cells(fine_cells, grid.config)
            if bbox is None:
                continue
            cell = grid.get_cell(next(iter(fine_cells)))
            ct = cell.content_type.value if cell and cell.content_type else "unknown"
            elements[eid] = {"bbox": bbox, "type": ct,
                             "locked": cell.locked if cell else False}

        eids = list(elements.keys())

        # nearest_neighbor
        self.nearest_neighbor.clear()
        for i, eid_a in enumerate(eids):
            best_dist = float("inf")
            best_eid = ""
            for j, eid_b in enumerate(eids):
                if i == j:
                    continue
                d = self._center_distance(elements[eid_a]["bbox"],
                                          elements[eid_b]["bbox"])
                if d < best_dist:
                    best_dist = d
                    best_eid = eid_b
            if best_eid:
                self.nearest_neighbor[eid_a] = (best_eid, round(best_dist, 1))

        # gap_matrix (coarse-row based)
        self.gap_matrix_rows.clear()
        rows: dict[int, list[tuple[str, float, float]]] = {}  # row → [(eid, x_left, x_right)]
        for eid, data in elements.items():
            if data["locked"]:
                continue
            x, y, w, h = data["bbox"]
            r = int(y / grid.config.coarse_cell_pt)
            rows.setdefault(r, []).append((eid, x, x + w))
        for r, items in rows.items():
            items.sort(key=lambda t: t[1])
            gaps = [items[i+1][1] - items[i][2] for i in range(len(items) - 1)]
            gaps = [g for g in gaps if g >= 0]
            if gaps:
                self.gap_matrix_rows[r] = [round(g, 1) for g in gaps]

        # alignment groups
        self.alignment_groups.clear()
        for eid, data in elements.items():
            if data["locked"]:
                continue
            x = data["bbox"][0]
            edge = round(x, 0)
            self.alignment_groups.setdefault(edge, []).append(eid)
        self.alignment_groups = {k: v for k, v in self.alignment_groups.items() if len(v) >= 2}

        # density heatmap (coarse cells)
        occ_coarse = grid.occupied_coarse()
        total_coarse = grid.config.coarse_cols * grid.config.coarse_rows
        self.density_heatmap.clear()
        for r in range(grid.config.coarse_rows):
            for c in range(grid.config.coarse_cols):
                addr = cell_name(c, r)
                # count fine cells occupied in this coarse cell
                fc_count = 0
                for fr in range(r * 2, min((r + 1) * 2, grid.config.fine_rows)):
                    for fc in range(c * 2, min((c + 1) * 2, grid.config.fine_cols)):
                        cell = grid.get_cell(cell_name(fc, fr))
                        if cell and cell.owner_id and not cell.locked:
                            fc_count += 1
                self.density_heatmap[addr] = fc_count / 4  # 4 fine cells per coarse

        # orphans: elements with no same-type neighbor within 120pt
        self.orphans.clear()
        for eid, data in elements.items():
            if data["locked"]:
                continue
            x, y, w, h = data["bbox"]
            has_neighbor = False
            for eid2, data2 in elements.items():
                if eid == eid2 or data2["locked"]:
                    continue
                d = self._center_distance(data["bbox"], data2["bbox"])
                if d < 120 and data["type"] == data2["type"]:
                    has_neighbor = True
                    break
            if not has_neighbor:
                self.orphans.add(eid)

        self.dirty = False

    def summary(self) -> dict:
        """Agent 友好的空间关系摘要。"""
        return {
            "nearest_neighbor": {k: {"to": v[0], "dist_pt": v[1]}
                                 for k, v in self.nearest_neighbor.items()},
            "alignment_groups": {
                str(edge): ids for edge, ids in self.alignment_groups.items()
            },
            "orphans": list(self.orphans),
            "density_hotspots": sorted(
                [(addr, d) for addr, d in self.density_heatmap.items() if d > 0.7],
                key=lambda x: x[1], reverse=True
            )[:5],
        }

    @staticmethod
    def _bbox_from_cells(fine_cells, config: GridConfig) -> tuple | None:
        if not fine_cells:
            return None
        parsed = [parse_cell(c) for c in fine_cells]
        min_col = min(p[0] for p in parsed)
        max_col = max(p[0] for p in parsed)
        min_row = min(p[1] for p in parsed)
        max_row = max(p[1] for p in parsed)
        x = min_col * config.fine_cell_pt
        y = min_row * config.fine_cell_pt
        w = (max_col - min_col + 1) * config.fine_cell_pt
        h = (max_row - min_row + 1) * config.fine_cell_pt
        return (x, y, w, h)

    @staticmethod
    def _center_distance(b1, b2) -> float:
        cx1, cy1 = b1[0] + b1[2] / 2, b1[1] + b1[3] / 2
        cx2, cy2 = b2[0] + b2[2] / 2, b2[1] + b2[3] / 2
        return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5
