"""
COM Adapter — 直接用 win32com 操控 PowerPoint，不走 C# 管道。

替代之前的 ComAdapter(NamedPipe → C#)，现在 Python 直接 Dispatch。
提供与 LocalAdapter 相同接口，上层 reflex.py / mcp_server.py 无感知。

前提：
  pip install pywin32  (已安装 ✓)
  PowerPoint 2016+ 已安装 (16.0 ✓)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import time
import os
import tempfile
from pathlib import Path
import pythoncom
import win32com.client


# ═══════════════════════════════════════════════════════════
# DATA TYPES (mirrors adapter.py)
# ═══════════════════════════════════════════════════════════

@dataclass
class ElementInfo:
    id: str
    left_pt: float
    top_pt: float
    width_pt: float
    height_pt: float
    role: str = "unknown"
    text: str = ""
    font_size_pt: float = 12.0
    font_explicit: bool = False
    is_placeholder: bool = False
    placeholder_type: int = 0
    z_order: int = 0
    is_visible: bool = True
    text_overflow: Optional[bool] = None
    actual_font_size_pt: Optional[float] = None


# ═══════════════════════════════════════════════════════════
# PYTHON COM ADAPTER
# ═══════════════════════════════════════════════════════════

class PowerPointCOM:
    """
    直接通过 win32com 操控 Microsoft PowerPoint。

    注意：
    - 所有操作通过 COM 进行，需要在 Windows 桌面环境运行
    - PowerPoint 会真实打开文件并显示（可设置为可见/不可见）
    - COM 是单线程套间 STA，需要 pythoncom.CoInitialize()
    """

    def __init__(self, visible: bool = True):
        pythoncom.CoInitialize()
        self.ppt: Optional[object] = None
        self.presentation: Optional[object] = None
        self.visible = visible
        self._last_positions: dict[str, tuple] = {}

    def connect(self) -> bool:
        try:
            # Try getting a running instance first (doesn't require Visible)
            self.ppt = win32com.client.GetActiveObject("PowerPoint.Application")
            self.ppt.Visible = self.visible  # Already running, this should work
            return True
        except Exception:
            try:
                # Start a new instance — must be visible initially
                self.ppt = win32com.client.Dispatch("PowerPoint.Application")
                self.ppt.Visible = True  # New instance must be visible first
                # Wait for PowerPoint to fully initialize
                time.sleep(1.0)
                return True
            except Exception as e:
                print(f"  COM Error: {e}")
                return False

    def disconnect(self):
        if self.ppt and self.presentation:
            self.presentation.Close()
            self.presentation = None
        if self.ppt:
            self.ppt.Quit()
            self.ppt = None

    # ── File ───────────────────────────────────────────────

    def open(self, path: str) -> dict:
        abs_path = str(Path(path).resolve())
        if not Path(abs_path).exists():
            raise FileNotFoundError(f"File not found: {abs_path}")
        # Close previous
        if self.presentation:
            try:
                self.presentation.Close()
            except Exception:
                pass
        # PowerPoint COM requires absolute path
        self.presentation = self.ppt.Presentations.Open(abs_path, ReadOnly=False, WithWindow=False)
        w = self.presentation.PageSetup.SlideWidth   # COM returns points directly
        h = self.presentation.PageSetup.SlideHeight
        return {
            "slides": self.presentation.Slides.Count,
            "slide_width_pt": w,
            "slide_height_pt": h,
            "mode": "com",
        }

    def save(self) -> dict:
        if self.presentation:
            self.presentation.Save()
            return {"saved": True, "path": self.presentation.FullName}
        return {"error": "No presentation open"}

    # ── Read ───────────────────────────────────────────────

    def read_slide(self, index: int) -> list[ElementInfo]:
        """
        读取指定幻灯片的所有图形元素。
        COM 幻灯片是 1-indexed。
        """
        slide = self.presentation.Slides[index + 1]
        elements = []
        self._last_positions.clear()

        for i, shape in enumerate(slide.Shapes):
            try:
                ei = ElementInfo(
                    id=f"shape-{i:02d}",
                    left_pt=shape.Left,      # COM returns points directly
                    top_pt=shape.Top,
                    width_pt=shape.Width,
                    height_pt=shape.Height,
                    z_order=shape.ZOrderPosition,
                    is_visible=shape.Visible == -1,  # True
                )

                # Placeholder detection
                try:
                    if shape.Type == 14:  # msoPlaceholder
                        ei.is_placeholder = True
                        ei.placeholder_type = shape.PlaceholderFormat.Type
                except Exception:
                    pass

                # Text extraction + overflow detection
                if shape.HasTextFrame == -1:
                    tf = shape.TextFrame
                    tr = tf.TextRange
                    ei.text = tr.Text[:200] if tr.Text else ""

                    # Font size
                    try:
                        ei.font_size_pt = tr.Font.Size
                        ei.font_explicit = True
                    except Exception:
                        pass

                    # Text overflow detection (PowerPoint 2013+)
                    try:
                        bound_w = tr.BoundWidth
                        bound_h = tr.BoundHeight
                        margin_w = tf.MarginLeft + tf.MarginRight
                        margin_h = tf.MarginTop + tf.MarginBottom
                        ei.text_overflow = (
                            bound_w > shape.Width + margin_w + 5
                            or bound_h > shape.Height + margin_h + 5
                        )
                    except Exception:
                        ei.text_overflow = None

                    # Auto-fit detection
                    try:
                        if tf.AutoSize != 0:  # ppAutoSizeNone
                            ei.actual_font_size_pt = tr.Font.Size
                    except Exception:
                        pass

                elements.append(ei)

                # Cache for change detection
                self._last_positions[ei.id] = (
                    ei.left_pt, ei.top_pt, ei.width_pt, ei.height_pt,
                )

            except Exception as e:
                # Skip problematic shapes
                print(f"  COM Warning: skipping shape {i}: {e}")
                continue

        return elements

    def read_rendered_bounds(self, elem_id: str, slide_idx: int = 0):
        """Get actual text rendering bounds for a shape."""
        idx = self._shape_index(elem_id)
        if idx is None:
            return None
        slide = self.presentation.Slides[slide_idx + 1]
        # Shapes collection is 1-indexed in COM
        try:
            shape = slide.Shapes(idx + 1)  # Use call syntax for safer access
        except Exception:
            return None
        try:
            tf = shape.TextFrame
            tr = tf.TextRange
            return {
                "text_width_pt": tr.BoundWidth,
                "text_height_pt": tr.BoundHeight,
                "box_width_pt": shape.Width,
                "box_height_pt": shape.Height,
                "overflow": (
                    tr.BoundWidth > shape.Width + 5
                    or tr.BoundHeight > shape.Height + 5
                ),
            }
        except Exception:
            return None

    # ── Write ──────────────────────────────────────────────

    def apply_positions(self, updates: list[dict], slide_idx: int = 0) -> dict:
        """
        updates: [{"id": "shape-05", "left_pt": 36, "top_pt": 140, ...}, ...]
        NOTE: COM Shapes collection uses 1-based call syntax: slide.Shapes(idx),
        NOT slide.Shapes[idx] which triggers enumeration and is unreliable.
        """
        slide = self.presentation.Slides[slide_idx + 1]
        applied = 0
        count = slide.Shapes.Count
        for update in updates:
            idx = self._shape_index(update["id"])
            if idx is None or idx >= count:
                continue
            try:
                # Use call syntax for reliable COM shape access
                shape = slide.Shapes(idx + 1)
                shape.Left = update["left_pt"]
                shape.Top = update["top_pt"]
                shape.Width = update["width_pt"]
                shape.Height = update["height_pt"]
                applied += 1
            except Exception as e:
                print(f"  COM Warning: apply_positions failed on {update['id']}: {e}")
        return {"applied": applied, "total": len(updates), "mode": "com"}
        return {"applied": applied, "total": len(updates), "mode": "com"}

    def apply_text(self, elem_id: str, text: str, font_pt: float | None = None,
                   slide_idx: int = 0) -> dict:
        idx = self._shape_index(elem_id)
        if idx is None:
            return {"error": f"Invalid element ID: {elem_id}"}
        slide = self.presentation.Slides[slide_idx + 1]
        try:
            shape = slide.Shapes(idx + 1)
        except Exception:
            return {"error": f"Cannot access shape {idx}"}
        if shape.HasTextFrame == -1:
            shape.TextFrame.TextRange.Text = text
            if font_pt:
                shape.TextFrame.TextRange.Font.Size = font_pt
        return {"ok": True}

    def delete_element(self, elem_id: str, slide_idx: int = 0) -> dict:
        idx = self._shape_index(elem_id)
        if idx is None:
            return {"error": f"Invalid element ID: {elem_id}"}
        slide = self.presentation.Slides[slide_idx + 1]
        try:
            shape = slide.Shapes(idx + 1)
            shape.Delete()
        except Exception as e:
            return {"error": str(e)}
        return {"deleted": elem_id, "mode": "com"}

    # ── Render ─────────────────────────────────────────────

    def render_slide_png(self, slide_idx: int, dpi: int = 200) -> str:
        """
        Export slide to PNG. Returns temp file path.
        Uses Slide.Export() which requires PowerPoint 2013+.
        Note: COM Export() uses FilterName 'PNG' and ScaleWidth/ScaleHeight.
        """
        tmp = tempfile.mktemp(suffix=".png")
        slide = self.presentation.Slides[slide_idx + 1]
        # PowerPoint Export signature: Export(FileName, FilterName, ScaleWidth, ScaleHeight)
        # ScaleWidth = dpi * slide_width_in / default_dpi
        # For 16:9 at 200dpi: 13.333" * 200 = 2667
        scale = dpi / 72 * self.presentation.PageSetup.SlideWidth
        try:
            slide.Export(tmp, "PNG", dpi, dpi)
        except Exception:
            # Fallback: some versions use different Export syntax
            try:
                slide.Export(tmp, "PNG")
            except Exception as e:
                raise RuntimeError(f"Slide.Export failed: {e}")
        return tmp

    # ── Events (polling) ───────────────────────────────────

    def poll_state_change(self, slide_idx: int) -> Optional[dict]:
        """Re-read elements and compare against cached positions."""
        elements = self.read_slide(slide_idx)
        changed = []
        new_positions = {}
        for e in elements:
            old = self._last_positions.get(e.id)
            if old:
                if (abs(e.left_pt - old[0]) > 0.5
                    or abs(e.top_pt - old[1]) > 0.5
                    or abs(e.width_pt - old[2]) > 0.5
                    or abs(e.height_pt - old[3]) > 0.5):
                    changed.append(e.id)
                    new_positions[e.id] = {
                        "left_pt": e.left_pt, "top_pt": e.top_pt,
                        "width_pt": e.width_pt, "height_pt": e.height_pt,
                    }
        if changed:
            return {
                "changed": True,
                "elements_changed": changed,
                "new_positions": new_positions,
                "slide_index": slide_idx,
            }
        return None

    # ── Helper ─────────────────────────────────────────────

    @staticmethod
    def _shape_index(elem_id: str) -> int | None:
        try:
            return int(elem_id.split("-")[1])
        except (IndexError, ValueError):
            return None
