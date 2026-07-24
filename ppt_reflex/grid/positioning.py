"""
grid/positioning.py — 定位层：地址 ↔ pt 互转（纯函数，无状态）

Agent 的"空间词汇"：Excel 风格的格子地址 (A1..P9)。
引擎用这个模块翻译 Agent 的话，不自己算坐标。
"""

from __future__ import annotations
from .types import GridConfig


def cell_name(col: int, row: int) -> str:
    """0-indexed col,row → Excel-style cell name.

    >>> cell_name(0, 0)
    'A1'
    >>> cell_name(15, 8)
    'P9'
    """
    if col < 26:
        c = chr(65 + col)
    else:
        c = chr(65 + (col // 26) - 1) + chr(65 + (col % 26))
    return f"{c}{row + 1}"


def parse_cell(cell: str) -> tuple[int, int]:
    """Excel cell name → (col, row) 0-indexed.

    >>> parse_cell("A1")
    (0, 0)
    >>> parse_cell("P9")
    (15, 8)
    """
    cell = cell.strip().upper()
    col_str = ""
    i = 0
    while i < len(cell) and cell[i].isalpha():
        col_str += cell[i]
        i += 1
    row_str = cell[i:]
    if not row_str:
        raise ValueError(f"Invalid cell: {cell}")

    if len(col_str) == 1:
        col = ord(col_str) - 65
    elif len(col_str) == 2:
        col = (ord(col_str[0]) - 64) * 26 + (ord(col_str[1]) - 65)
    else:
        raise ValueError(f"Invalid column: {col_str} (max 2 letters, e.g. ZZ)")

    row = int(row_str) - 1
    return col, row


def cells_to_bbox(cells: list[str], config: GridConfig | None = None) -> dict:
    """一组格子 → 最小包围矩形 (pt)。

    >>> cells_to_bbox(["A2", "B2", "A3", "B3"])
    {'x': 0, 'y': 60, 'w': 120, 'h': 120}
    """
    if not cells:
        raise ValueError("cells list is empty")
    cfg = config or GridConfig()
    parsed = [parse_cell(c) for c in cells]
    min_col = min(p[0] for p in parsed)
    max_col = max(p[0] for p in parsed)
    min_row = min(p[1] for p in parsed)
    max_row = max(p[1] for p in parsed)
    return {
        "x": min_col * cfg.coarse_cell_pt,
        "y": min_row * cfg.coarse_cell_pt,
        "w": (max_col - min_col + 1) * cfg.coarse_cell_pt,
        "h": (max_row - min_row + 1) * cfg.coarse_cell_pt,
    }


def bbox_to_coarse_cells(x: float, y: float, w: float, h: float,
                         config: GridConfig | None = None) -> list[str]:
    """pt bbox → 覆盖的定位层格子。

    >>> bbox_to_coarse_cells(0, 60, 120, 120)
    ['A2', 'B2', 'A3', 'B3']
    """
    cfg = config or GridConfig()
    c0 = max(0, int(x / cfg.coarse_cell_pt))
    r0 = max(0, int(y / cfg.coarse_cell_pt))
    c1 = min(cfg.coarse_cols - 1, int((x + w - 1) / cfg.coarse_cell_pt))
    r1 = min(cfg.coarse_rows - 1, int((y + h - 1) / cfg.coarse_cell_pt))
    if c0 > c1 or r0 > r1:
        return []
    cells = []
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            cells.append(cell_name(c, r))
    return cells


def bbox_to_fine_cells(x: float, y: float, w: float, h: float,
                       config: GridConfig | None = None) -> list[str]:
    """pt bbox → 覆盖的信息层格子 (32×18)。引擎内部用。"""
    cfg = config or GridConfig()
    c0 = max(0, int(x / cfg.fine_cell_pt))
    r0 = max(0, int(y / cfg.fine_cell_pt))
    c1 = min(cfg.fine_cols - 1, int((x + w - 1) / cfg.fine_cell_pt))
    r1 = min(cfg.fine_rows - 1, int((y + h - 1) / cfg.fine_cell_pt))
    if c0 > c1 or r0 > r1:
        return []
    cells = []
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            cells.append(cell_name(c, r))
    return cells


def cell_range(cells: list[str]) -> str:
    """紧凑表示: ['A1','A2','B1','B2'] → 'A1:B2'"""
    if not cells:
        return ""
    parsed = [(parse_cell(c)[0], parse_cell(c)[1]) for c in cells]
    cols = sorted(set(p[0] for p in parsed))
    rows = sorted(set(p[1] for p in parsed))
    start = cell_name(cols[0], rows[0])
    if len(cols) == 1 and len(rows) == 1:
        return start
    end = cell_name(cols[-1], rows[-1])
    return f"{start}:{end}"


def is_cell_in_bounds(cell: str, config: GridConfig | None = None) -> bool:
    """格子是否在画布内。"""
    cfg = config or GridConfig()
    try:
        col, row = parse_cell(cell)
    except ValueError:
        return False
    return 0 <= col < cfg.coarse_cols and 0 <= row < cfg.coarse_rows


def cells_to_grid_snapshot(cells: list[str]) -> dict[str, list[str]]:
    """把单元格列表组织为 行×列 的可读快照。
    {'A': ['A1','A2'], 'B': ['B1','B2'], ...}
    """
    by_col: dict[str, list[str]] = {}
    for c in sorted(cells, key=lambda c: (parse_cell(c)[1], parse_cell(c)[0])):
        try:
            col, _ = parse_cell(c)
        except ValueError:
            continue
        col_letter = cell_name(col, 0)[:-1]
        by_col.setdefault(col_letter, []).append(c)
    return by_col
