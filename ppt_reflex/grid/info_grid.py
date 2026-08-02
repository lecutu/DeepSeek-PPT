"""
grid/info_grid.py — Information layer: state storage + occupy/release/query

32x18 fine grid (30pt/cell), engine-internal use.
Each cell records: owner_id, content_type, z_order, locked, source.
"""

from __future__ import annotations
from copy import deepcopy
from .types import GridConfig, InfoCell, ContentType, ElementPayload, SemanticRole, ROLE_Z_BASE
from .positioning import cell_name, parse_cell, bbox_to_fine_cells

# ROLE_Z_BASE 单一事实源在 types.py（旧版本地副本数值已分叉：ANNOTATION 300 vs 210）


class InformationGrid:
    """Fine-grained information layer grid: assign/release/query."""

    def __init__(self, config: GridConfig | None = None):
        self.config = config or GridConfig()
        self._cells: dict[str, InfoCell] = {}

    # ── Cell CRUD ──
    def occupy(self, addrs: list[str], owner_id: str, content_type: ContentType,
               role: SemanticRole = SemanticRole.ENTITY,
               source: str = "agent", locked: bool = False,
               payload = None):
        for a in addrs:
            cell = self._cells.get(a)
            z = (cell.z_order + 1) if cell else ROLE_Z_BASE.get(role, 100)
            self._cells[a] = InfoCell(
                owner_id=owner_id, content_type=content_type,
                role=role, z_order=z, locked=locked, source=source,
                payload=payload,
            )

    # ── bbox -> cells ──
    def cells_in_bbox(self, x: float, y: float, w: float, h: float) -> list[tuple[str, InfoCell]]:
        """Return all fine-grid cell addresses + InfoCells covered by bbox."""
        addrs = bbox_to_fine_cells(x, y, w, h, self.config)
        return [(a, self._cells.get(a, InfoCell())) for a in addrs]

    def occupy_bbox(self, x: float, y: float, w: float, h: float,
                    owner_id: str, content_type: ContentType,
                    role: SemanticRole = SemanticRole.ENTITY,
                    source: str = "agent", locked: bool = False):
        """Occupy by bbox."""
        addrs = bbox_to_fine_cells(x, y, w, h, self.config)
        self.occupy(addrs, owner_id, content_type, role, source, locked)

    def release(self, owner_id: str):
        remove = [a for a, c in self._cells.items() if c.owner_id == owner_id]
        for a in remove:
            del self._cells[a]

    def occupied_by(self, owner_id: str) -> list[str]:
        return [a for a, c in self._cells.items() if c.owner_id == owner_id]

    def occupied_by_all(self) -> dict[str, list[str]]:
        result = {}
        for a, c in self._cells.items():
            if c.owner_id:
                result.setdefault(c.owner_id, []).append(a)
        return result


    # ── Legacy compatibility aliases ──
    all_occupied = occupied_by_all

    def occupied_coarse(self) -> dict[str, list[str]]:
        """Legacy: return occupied cells grouped by owner (coarse alias)."""
        return self.occupied_by_all()

    def get_cell(self, addr: str):
        """Legacy: direct cell access."""
        return self._cells.get(addr)

    def cell_type(self, owner_id: str) -> ContentType | None:
        for c in self._cells.values():
            if c.owner_id == owner_id:
                return c.content_type
        return None

    def density(self) -> float:
        """Legacy: coarse occupancy ratio."""
        total_coarse = self.config.coarse_cols * self.config.coarse_rows
        if total_coarse == 0:
            return 0.0
        unique_owners = len(set(c.owner_id for c in self._cells.values() if c.owner_id))
        return min(1.0, unique_owners / max(total_coarse, 1))

    def _free_cells_suggestion(self, n_cells: int) -> list[str]:
        """Return a list of free cell addresses (for free_suggestion in PlacementResult)."""
        all_cells = []
        for r in range(self.config.coarse_rows):
            for c in range(self.config.coarse_cols):
                addr = f"{chr(ord('A')+c)}{r+1}"
                if addr not in self._cells or self._cells[addr].owner_id is None:
                    all_cells.append(addr)
        return all_cells[:max(n_cells, 4)]
