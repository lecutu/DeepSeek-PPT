"""
grid/matrix.py — 交互矩阵：ContentType × ContentType → Verdict + z_hint

只判规则，不持有状态。info_grid 和 positioning 各司其职，
matrix 只回答 "X 类型叠 Y 类型 = 允许/警告/阻止"。
"""

from __future__ import annotations
from .types import (
    ContentType, Verdict, Conflict, GridConfig,
    BLOCK_PAIRS, DEFAULT_POLICY, Z_ORDER_RULES,
)
from .info_grid import InformationGrid, InfoCell


class InteractionMatrix:
    """类型×类型 → 判定。可扩展样式规则（第二版）。"""

    def __init__(self, config: GridConfig | None = None):
        self.config = config or GridConfig()
        self._block_pairs = set(BLOCK_PAIRS)       # 可运行时添加
        self._z_order_rules = dict(Z_ORDER_RULES)   # 可运行时修改

    # ── core ────────────────────────────────────────────────

    def judge(self, existing_type: ContentType, new_type: ContentType) -> Verdict:
        """两类型重叠 → ALLOW | WARN | BLOCK。

        >>> InteractionMatrix().judge(ContentType.TEXT, ContentType.TEXT)
        Verdict.BLOCK
        >>> InteractionMatrix().judge(ContentType.TEXT, ContentType.TEXTBOX)
        Verdict.ALLOW
        """
        pair = (existing_type, new_type)
        if pair in self._block_pairs:
            return Verdict.BLOCK
        return self.config.default_policy

    def z_hint(self, existing_type: ContentType, new_type: ContentType) -> str | None:
        """建议新元素的 z-order: "new_above" | "new_below" | "either" | None"""
        for (a, b), hint in self._z_order_rules.items():
            if (a == existing_type and b == new_type) or (a == new_type and b == existing_type):
                return hint
        return None

    # ── bulk check ──────────────────────────────────────────

    def check_all(self, covered_cells: list[tuple[str, InfoCell]],
                  new_type: ContentType, new_id: str) -> list[Conflict]:
        """对一组已覆盖的信息格，逐个检查冲突。

        Args:
            covered_cells: [(addr, InfoCell), ...] 来自 info_grid.cells_in_bbox()
            new_type: 新元素的内容类型
            new_id: 新元素的 ID

        Returns:
            仅返回 BLOCK 和 WARN 级别的冲突。
            跳过了同一 owner（自我重叠）、locked 格、background 格。
        """
        conflicts: list[Conflict] = []
        for addr, cell in covered_cells:
            if cell.owner_id is None:
                continue
            if cell.owner_id == new_id:
                continue                          # 自己的格子
            if cell.locked and cell.source == "template":
                continue                          # 模板装饰 — 不参与判定
            if cell.content_type == ContentType.BACKGROUND:
                continue                          # 背景 — 永远允许重叠

            existing_type = cell.content_type or ContentType.UNKNOWN
            # CONNECTOR always allowed — lines float above everything
            if existing_type == ContentType.CONNECTOR or new_type == ContentType.CONNECTOR:
                continue
            verdict = self.judge(existing_type, new_type)

            if verdict == Verdict.ALLOW:
                continue

            conflict = Conflict(
                cell_addr=addr,
                existing_id=cell.owner_id,
                new_id=new_id,
                existing_type=existing_type,
                new_type=new_type,
                verdict=verdict,
                detail=self._describe(existing_type, new_type, verdict),
            )
            conflicts.append(conflict)
        return conflicts

    # ── helpers ─────────────────────────────────────────────

    @staticmethod
    def _describe(et: ContentType, nt: ContentType, v: Verdict) -> str:
        if v == Verdict.BLOCK:
            return f"{et.value} 叠 {nt.value} → 阻止"
        if v == Verdict.WARN:
            return f"{et.value} 叠 {nt.value} → 警告"
        return f"{et.value} 叠 {nt.value} → 允许"

    # ── runtime customization ───────────────────────────────

    def add_block_pair(self, a: ContentType, b: ContentType) -> None:
        """运行时加一条 BLOCK 规则。"""
        self._block_pairs.add((a, b))
        self._block_pairs.add((b, a))

    def remove_block_pair(self, a: ContentType, b: ContentType) -> None:
        """运行时移除一条 BLOCK 规则。"""
        self._block_pairs.discard((a, b))
        self._block_pairs.discard((b, a))

    def set_z_hint(self, a: ContentType, b: ContentType, hint: str) -> None:
        self._z_order_rules[(a, b)] = hint
