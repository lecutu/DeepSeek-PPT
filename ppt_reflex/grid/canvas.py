"""
grid/canvas.py — 主控制器：try_place / commit / rollback

编排定位层 + 信息层 + 交互矩阵 + serializer。
不直接碰 python-pptx，IO 全部委托给 serializer。
不直接做格式化输出，委托给 supply。
"""

from __future__ import annotations
from copy import deepcopy

from .types import (
    GridConfig, ContentType, Verdict, InfoCell,
    Conflict, PlacementResult, LayoutProfile,
    ElementPayload,
)
from .positioning import cells_to_bbox, is_cell_in_bounds, bbox_to_coarse_cells, bbox_to_fine_cells
from .info_grid import InformationGrid
from .matrix import InteractionMatrix


class GridCanvas:
    """PPT 画布的感知型网格。

    用法:
        canvas = GridCanvas(GridConfig())
        result = canvas.try_place("shape-01", ContentType.TEXT, ["A1","B1","C1"])
        if result.allowed:
            canvas.commit("output.pptx")
    """

    def __init__(self, config: GridConfig | None = None):
        self.config = config or GridConfig()
        self.info_grid = InformationGrid(self.config)
        self.matrix = InteractionMatrix(self.config)
        self._profiles: dict[str, LayoutProfile] = {}  # slide_id → profile
        self._serializer = None  # lazy import to avoid coupling
        self._supply = None

    # ═══════════════════════════════════════════════════════════
    # CORE: try_place
    # ═══════════════════════════════════════════════════════════

    def try_place(self, element_id: str, content_type: ContentType,
                  target_cells: list[str], payload: ElementPayload | None = None) -> PlacementResult:
        """Try to place an element on target_cells.

        1. cells → bbox
        2. boundary check
        3. text overflow estimation (if payload provided): expand cells if text overflows
        4. scan info layer 32×18 grid for occupied cells
        5. collision matrix: Type × Type → BLOCK / ALLOW / WARN
        6. aggregate + free-zone suggestion
        7. if ALLOW: occupy info layer WITH payload stored
        """
        if not target_cells:
            return PlacementResult(
                verdict=Verdict.BLOCK,
                conflicts=[Conflict(
                    cell_addr="",
                    existing_id="",
                    new_id=element_id,
                    existing_type=ContentType.UNKNOWN,
                    new_type=content_type,
                    verdict=Verdict.BLOCK,
                    detail="空目标区域",
                )],
            )

        # ① 定位层
        bbox = cells_to_bbox(target_cells, self.config)
        x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]

        # ② 边界检查
        margin = self.config.safe_margin_pt
        oob_cells = []
        for cell in target_cells:
            if not is_cell_in_bounds(cell, self.config):
                oob_cells.append(cell)
        if oob_cells:
            return PlacementResult(
                verdict=Verdict.BLOCK,
                conflicts=[Conflict(
                    cell_addr=oob_cells[0],
                    existing_id="",
                    new_id=element_id,
                    existing_type=ContentType.UNKNOWN,
                    new_type=content_type,
                    verdict=Verdict.BLOCK,
                    detail=f"out of bounds: {', '.join(oob_cells[:5])}",
                )],
            )

        # ②.⑤ 文字溢出预检（有 payload 时）
        if payload is not None and payload.text.strip():
            from .text_metrics import estimate_text_size
            overflow_x, overflow_y, rendered_w, rendered_h = estimate_text_size(
                payload.text,
                font_pt=payload.font_size,
                line_spacing=payload.line_spacing,
                box_width_pt=w,
                box_height_pt=h,
                word_wrap=True,
            )
            if overflow_y > 2:  # >2pt tolerance
                # Text overflows vertically — return WARN with suggestion
                excess_lines = int(overflow_y / (payload.font_size * payload.line_spacing)) + 1
                total_lines = payload.text.count("\n") + 1
                max_fit = max(1, total_lines - excess_lines)
                return PlacementResult(
                    verdict=Verdict.WARN,
                    warnings=[Conflict(
                        cell_addr=target_cells[0],
                        existing_id="",
                        new_id=element_id,
                        existing_type=ContentType.UNKNOWN,
                        new_type=content_type,
                        verdict=Verdict.WARN,
                        detail=(
                            f"text overflow: needs {rendered_h:.0f}pt, box is {h:.0f}pt, "
                            f"excess {overflow_y:.0f}pt. "
                            f"Fix: reduce to {max_fit} lines, "
                            f"or decrease font, "
                            f"or expand grid area."
                        ),
                    )],
                )

        # ③ 信息层
        covered = self.info_grid.cells_in_bbox(x, y, w, h)

        # ④ 交互矩阵
        conflicts = self.matrix.check_all(covered, content_type, element_id)

        # ⑤ 汇总
        if not conflicts:
            # 通过 — 占用信息层（不写 PPT，等 commit）
            fine_addrs = [addr for addr, _ in covered]
            z = self._next_z()
            self.info_grid.occupy(
                fine_addrs, element_id, content_type,
                z_order=z,
                source="agent",
                payload=payload,   # store content for commit-time rendering
            )
            # z_hint — 即使是 ALLOW，也可能有建议
            z_hint = self._compute_z_hint(covered, content_type)
            return PlacementResult(verdict=Verdict.ALLOW, z_hint=z_hint)

        # 有冲突 → 汇总
        blocks = [c for c in conflicts if c.verdict == Verdict.BLOCK]
        warns = [c for c in conflicts if c.verdict == Verdict.WARN]

        verdict = Verdict.BLOCK if blocks else Verdict.WARN

        # z_hint
        z_hint = None
        if verdict != Verdict.BLOCK:
            existing_types = set(c.existing_type for c in conflicts)
            for et in existing_types:
                hint = self.matrix.z_hint(et, content_type)
                if hint:
                    z_hint = hint
                    break

        # 空闲建议
        needed_cols = max(1, int(w / self.config.coarse_cell_pt))
        needed_rows = max(1, int(h / self.config.coarse_cell_pt))
        free_candidates = self.info_grid.find_free(needed_cols, needed_rows)

        return PlacementResult(
            verdict=verdict,
            conflicts=blocks,
            warnings=warns,
            z_hint=z_hint,
            free_suggestion=free_candidates,
        )

    # ═══════════════════════════════════════════════════════════
    # COMMIT / ROLLBACK
    # ═══════════════════════════════════════════════════════════

    def checkpoint(self) -> None:
        """保存快照，commit 前调用。"""
        self.info_grid.checkpoint()

    def commit(self, ppt_path: str) -> dict:
        """写入 PPT 文件。信息层状态 → 物理文件。

        原子性：先写临时文件，成功后才替换 + 确认 checkpoint。
        """
        import os
        from .serializer import grid_to_ppt

        tmp_path = ppt_path + ".tmp"
        try:
            grid_to_ppt(self.info_grid, self.config, tmp_path)
            os.replace(tmp_path, ppt_path)
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return {"status": "error", "message": str(e)}

        self.info_grid.discard_checkpoint()
        return {"status": "ok", "path": ppt_path}

    def rollback(self) -> dict:
        """回滚到上一次 checkpoint。信息层恢复，PPT 不变。"""
        self.info_grid.rollback()
        return {"status": "rolled_back"}

    # ═══════════════════════════════════════════════════════════
    # LOAD / PROFILE
    # ═══════════════════════════════════════════════════════════

    def load(self, ppt_path: str, slide_index: int = 0) -> dict:
        """从 PPT 文件加载幻灯片，重建信息层 + 版式推断。"""
        from .serializer import ppt_to_grid

        self.info_grid = ppt_to_grid(ppt_path, slide_index, self.config)
        slide_id = f"{ppt_path}:{slide_index}"
        self._profiles[slide_id] = self._infer_profile(slide_id)
        return {
            "status": "ok",
            "slide_index": slide_index,
            "elements": len(self.info_grid.all_occupied()),
            "density": round(self.info_grid.density() * 100, 1),
        }

    def unload(self, element_id: str) -> int:
        """从画布上移除一个元素（释放其信息格），不写 PPT。"""
        return self.info_grid.release(element_id)

    # ═══════════════════════════════════════════════════════════
    # QUERY
    # ═══════════════════════════════════════════════════════════

    def occupied_summary(self) -> dict:
        """Agent 友好摘要 — '哪些格子被什么类型占据'。"""
        occ = self.info_grid.occupied_coarse()
        summary = {}
        for oid, coarse_cells in occ.items():
            summary[oid] = list(coarse_cells)
        return summary

    def density(self) -> float:
        return self.info_grid.density()

    def profile(self, slide_id: str | None = None) -> LayoutProfile | None:
        """获取版式约束。"""
        if slide_id:
            return self._profiles.get(slide_id)
        # return first
        for p in self._profiles.values():
            return p
        return None

    # ═══════════════════════════════════════════════════════════
    # INTERNAL
    # ═══════════════════════════════════════════════════════════

    _z_counter: int = 0

    def _next_z(self) -> int:
        self._z_counter += 1
        return self._z_counter

    def _compute_z_hint(self, covered: list, new_type: ContentType) -> str | None:
        """遍历被覆盖区域中已存在的元素，取第一个 z_hint。"""
        types_seen: set[ContentType] = set()
        for _, cell in covered:
            if cell.owner_id and cell.content_type and cell.content_type != new_type:
                types_seen.add(cell.content_type)
        for et in types_seen:
            hint = self.matrix.z_hint(et, new_type)
            if hint:
                return hint
        return None

    def _infer_profile(self, slide_id: str) -> LayoutProfile:
        """从当前 info_grid 推断版式约束。

        第二版会从母版读取；第一版用启发式：
        - 覆盖 >85% 的 SHAPE → 装饰/locked
        - 顶部 2 行的 TEXT → title zone
        - 底部 1 行的 TEXT → footer zone
        """
        profile = LayoutProfile(name="auto")
        occ = self.info_grid.occupied_coarse()

        for oid, coarse_cells in occ.items():
            rows = set()
            for c in coarse_cells:
                from .positioning import parse_cell
                try:
                    _, r = parse_cell(c)
                    rows.add(r)
                except ValueError:
                    continue
            if not rows:
                continue
            min_r, max_r = min(rows), max(rows)

            # 底部一行 → footer, locked
            if min_r >= self.config.coarse_rows - 1:
                profile.locked_zones.update(coarse_cells)
                profile.decorative_elements.add(oid)

            # 顶部一行 → title zone
            elif max_r <= 1:
                profile.zones.setdefault("title", []).extend(
                    c for c in coarse_cells if c not in profile.zones.get("title", [])
                )

            # 中部大面积 SHAPE → 装饰
            # （粗略判断——第二版用 info_grid 的 content_type 精确分类）

        return profile
