"""
grid/info_grid.py — 信息层：状态存储 + 占用/释放/查询

32×18 细网格 (30pt/cell)，引擎内部使用。
每个 cell 记录: owner_id, content_type, z_order, locked, source。
"""

from __future__ import annotations
from copy import deepcopy
from .types import GridConfig, InfoCell, ContentType, ElementPayload, SemanticRole
from .positioning import cell_name, parse_cell, bbox_to_fine_cells


class InformationGrid:
    """有状态的空间快照——每个 30pt 格子知道被谁占用、什么类型。"""

    def __init__(self, config: GridConfig | None = None):
        self.config = config or GridConfig()
        rows = self.config.fine_rows
        cols = self.config.fine_cols
        # 二维数组: grid[row][col]
        self._grid: list[list[InfoCell]] = [
            [InfoCell() for _ in range(cols)] for _ in range(rows)
        ]
        self._checkpoints: list[list[list[InfoCell]]] = []  # 用于 rollback

    # ── copy / checkpoint ───────────────────────────────────

    def checkpoint(self) -> None:
        """保存当前状态，供 rollback 恢复。"""
        self._checkpoints.append(deepcopy(self._grid))

    def rollback(self) -> None:
        """恢复到最近一次 checkpoint。"""
        if self._checkpoints:
            self._grid = self._checkpoints.pop()

    def discard_checkpoint(self) -> None:
        """确认当前状态，丢弃最近 checkpoint。"""
        if self._checkpoints:
            self._checkpoints.pop()

    def snapshot(self) -> list[list[InfoCell]]:
        """返回只读快照（不暴露内部引用）。"""
        return deepcopy(self._grid)

    # ── cell access ─────────────────────────────────────────

    def get_cell(self, cell_addr: str) -> InfoCell | None:
        """读取单个信息格。"""
        try:
            col, row = parse_cell(cell_addr)
        except ValueError:
            return None
        if 0 <= row < self.config.fine_rows and 0 <= col < self.config.fine_cols:
            return self._grid[row][col]
        return None

    def get_cell_raw(self, col: int, row: int) -> InfoCell | None:
        """按 0-indexed (col, row) 读取。"""
        if 0 <= row < self.config.fine_rows and 0 <= col < self.config.fine_cols:
            return self._grid[row][col]
        return None

    # ── bbox → cells ────────────────────────────────────────

    def cells_in_bbox(self, x: float, y: float, w: float, h: float) -> list[tuple[str, InfoCell]]:
        """返回 bbox 覆盖的所有信息格地址 + InfoCell。"""
        addrs = bbox_to_fine_cells(x, y, w, h, self.config)
        result = []
        for addr in addrs:
            cell = self.get_cell(addr)
            if cell is not None:
                result.append((addr, cell))
        return result

    # ── occupy / release ────────────────────────────────────

    def occupy(self, cells: list[str], owner_id: str, content_type: ContentType,
               z_order: int = 0, locked: bool = False, source: str = "agent",
               payload: ElementPayload | None = None,
               role: SemanticRole = SemanticRole.ENTITY) -> None:
        """占用一组信息格。"""
        for addr in cells:
            cell = self.get_cell(addr)
            if cell is None:
                continue
            cell.owner_id = owner_id
            cell.content_type = content_type
            cell.role = role
            cell.z_order = z_order
            cell.locked = locked
            cell.source = source
            cell.payload = payload

    def occupy_bbox(self, x: float, y: float, w: float, h: float,
                    owner_id: str, content_type: ContentType,
                    z_order: int = 0, locked: bool = False, source: str = "agent") -> None:
        """按 bbox 占用。"""
        addrs = bbox_to_fine_cells(x, y, w, h, self.config)
        self.occupy(addrs, owner_id, content_type, z_order, locked, source)

    def release(self, owner_id: str) -> int:
        """释放某个 owner 占用的所有格子。返回释放数量。"""
        count = 0
        for row in self._grid:
            for cell in row:
                if cell.owner_id == owner_id and not cell.locked:
                    cell.owner_id = None
                    cell.content_type = None
                    cell.z_order = 0
                    count += 1
        return count

    def release_cells(self, cells: list[str]) -> int:
        """释放指定格子列表。返回释放数量。"""
        count = 0
        for addr in cells:
            cell = self.get_cell(addr)
            if cell is None or cell.locked:
                continue
            if cell.owner_id is not None:
                cell.owner_id = None
                cell.content_type = None
                cell.z_order = 0
                count += 1
        return count

    # ── query ───────────────────────────────────────────────

    def is_empty(self, cell_addr: str) -> bool:
        cell = self.get_cell(cell_addr)
        return cell is None or cell.owner_id is None

    def all_occupied(self) -> dict[str, set[str]]:
        """{owner_id: {cell_addrs}} 所有占用情况。"""
        result: dict[str, set[str]] = {}
        for r in range(self.config.fine_rows):
            for c in range(self.config.fine_cols):
                cell = self._grid[r][c]
                if cell.owner_id:
                    result.setdefault(cell.owner_id, set()).add(cell_name(c, r))
        return result

    def occupied_coarse(self) -> dict[str, set[str]]:
        """{owner_id: {coarse_cell_addrs}} 聚合到定位层。"""
        fine = self.all_occupied()
        result: dict[str, set[str]] = {}
        for oid, fine_cells in fine.items():
            coarse = set()
            for fc in fine_cells:
                col_f, row_f = parse_cell(fc)
                col_c = col_f // 2   # 32→16
                row_c = row_f // 2   # 18→9
                coarse.add(cell_name(col_c, row_c))
            result[oid] = coarse
        return result

    def find_free(self, needed_cols: int, needed_rows: int) -> list[list[str]]:
        """在定位层扫描完全空闲的连续区域。返回前几个候选。

        Returns: list of cell-address lists, each a continuous rectangle.
        """
        occ = self.occupied_coarse()
        occupied_coarse: set[str] = set()
        for cells in occ.values():
            occupied_coarse.update(cells)

        candidates: list[list[str]] = []
        max_col = self.config.coarse_cols
        max_row = self.config.coarse_rows

        for r in range(max_row - needed_rows + 1):
            for c in range(max_col - needed_cols + 1):
                rect = []
                free = True
                for dr in range(needed_rows):
                    for dc in range(needed_cols):
                        addr = cell_name(c + dc, r + dr)
                        if addr in occupied_coarse:
                            free = False
                            break
                        rect.append(addr)
                    if not free:
                        break
                if free:
                    candidates.append(rect)
                    if len(candidates) >= 3:
                        return candidates
        return candidates

    def density(self) -> float:
        """信息层占用率 (0~1)，排除 locked/background。"""
        total = 0
        occupied = 0
        for row in self._grid:
            for cell in row:
                if cell.locked:
                    continue
                total += 1
                if cell.owner_id is not None and cell.content_type != ContentType.BACKGROUND:
                    occupied += 1
        return occupied / total if total > 0 else 0.0
