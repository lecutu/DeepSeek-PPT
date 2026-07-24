"""
grid/matrix.py — 碰撞判定：仅 entity_table 内跑排他检查。

语义角色 (SemanticRole) 决定表分配，表决定是否碰撞。
overlay 元素 (CONNECTOR/ANNOTATION/EMPHASIS/BACKDROP) 不参与碰撞。
"""

from __future__ import annotations
from .types import (
    ContentType, Verdict, Conflict, GridConfig,
    SemanticRole, ENTITY_ROLES,
)
from .info_grid import InformationGrid, InfoCell


class InteractionMatrix:
    """Entity × Entity → BLOCK/ALLOW/WARN。Overlay 元素不参与。"""

    def __init__(self, config: GridConfig | None = None):
        self.config = config or GridConfig()

    def check_all(self, covered_cells: list[tuple[str, InfoCell]],
                  new_type: ContentType, new_id: str,
                  new_role: SemanticRole = SemanticRole.ENTITY) -> list[Conflict]:
        """检查新元素与已存在元素的冲突。

        核心规则：
          1. overlay 元素永远不触发碰撞（不跟任何东西比）
          2. entity × entity → BLOCK（实体之间互斥）
          3. 同一 owner、locked、BACKGROUND → 跳过
          4. CONNECTOR ContentType 已废除碰撞豁免——role 取代了它
        """
        conflicts: list[Conflict] = []

        # Overlay elements never collide
        if new_role not in ENTITY_ROLES:
            return conflicts

        for addr, cell in covered_cells:
            if cell.owner_id is None:
                continue
            if cell.owner_id == new_id:
                continue
            if cell.locked and cell.source == "template":
                continue
            if cell.content_type == ContentType.BACKGROUND:
                continue

            # Existing overlay → never blocks a new entity
            if cell.role not in ENTITY_ROLES:
                continue

            # Entity × Entity → BLOCK
            conflict = Conflict(
                cell_addr=addr,
                existing_id=cell.owner_id,
                new_id=new_id,
                existing_type=cell.content_type or ContentType.UNKNOWN,
                new_type=new_type,
                existing_role=cell.role,
                new_role=new_role,
                verdict=Verdict.BLOCK,
                detail=(
                    f"Entity '{new_id}' ({new_type.value}) overlaps "
                    f"entity '{cell.owner_id}' ({cell.content_type.value if cell.content_type else '?'}). "
                    f"If '{new_id}' is meant to annotate/connect/highlight "
                    f"'{cell.owner_id}', change its role to CONNECTOR/ANNOTATION/EMPHASIS "
                    f"— do NOT move its coordinates."
                ),
            )
            conflicts.append(conflict)

        return conflicts

    def judge(self, existing_type: ContentType, new_type: ContentType) -> Verdict:
        """Legacy two-type → Verdict. Always ALLOW — collision is role-driven now."""
        return Verdict.ALLOW

    def z_hint(self, existing_type: ContentType, new_type: ContentType) -> str | None:
        """Legacy z-hint. Always None — z-order is role-driven now."""
        return None
