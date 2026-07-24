"""
PPT Reflex Engine — MCP Server

基于 Day 1 + Day 1.5 验证结果，定义了 14 个 MCP Tool。
Agent 只需要高层意图，引擎处理所有几何推理。

协议：
  normal → {status: "ok", revision: N}
  auto-adjusted → {status: "ok", revision: N, auto_adjusted: [...]}
  needs_decision → {status: "needs_decision", issues: [...], options: [...]}
  blocked → {status: "blocked"|"state_changed", message: ...}
  local_context → {status: "local_context", targets: [...], neighbors: [...]}

运行：
  python mcp_server.py              # 启动 MCP Server (stdio)
  python mcp_server.py --port 8081  # 启动 HTTP Streamable
"""

from __future__ import annotations
from pathlib import Path
import json
import sys

from reflex import ReflexEngine
from engine import SlideElement, BBox, ContentRole, CollisionRole
from bridge import (
    parse_slide_to_elements, apply_element_positions,
    open_presentation, read_slide, save_presentation,
)
from layout import TEMPLATES
from grid import GridCanvas, GridConfig, ContentType, Supply, Verdict


def _expand_range(cell_range: str) -> list[str]:
    """Expand 'A1:D3' → ['A1','A2','A3','B1','B2','B3','C1','C2','C3','D1','D2','D3']"""
    from grid.positioning import parse_cell, cell_name
    start, end = cell_range.split(":")
    c0, r0 = parse_cell(start)
    c1, r1 = parse_cell(end)
    cells = []
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            cells.append(cell_name(c, r))
    return cells


# ═══════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════
class Session:
    """Holds presentation + engine + grid canvas across tool calls."""

    def __init__(self):
        self.prs = None
        self.path: str = ""
        self.engine: ReflexEngine | None = None
        self.current_slide_idx: int = 0
        self.slide_elements: list[SlideElement] = []
        self.grid = GridCanvas(GridConfig())
        self.supply = Supply(GridConfig())

    def load(self, path: str):
        self.prs = open_presentation(path)
        self.path = path
        self._load_slide(0)
        # Also load into grid canvas
        try:
            self.grid.load(path, 0)
        except Exception:
            pass  # Grid load is optional

    def _load_slide(self, idx: int):
        self.current_slide_idx = idx
        slide, elements = read_slide(self.prs, idx)
        self.slide_elements = elements
        self.engine = ReflexEngine()
        self.engine.load_slide(elements)
        # Sync grid
        try:
            self.grid.load(self.path, idx)
        except Exception:
            pass

    def save(self, output_path: str | None = None):
        target = output_path or self.path
        # Write element positions back before saving
        slide = self.prs.slides[self.current_slide_idx]
        apply_element_positions(slide, self.slide_elements)
        save_presentation(self.prs, target)


# ═══════════════════════════════════════════════════════════
# MCP TOOL DEFINITIONS
# ═══════════════════════════════════════════════════════════

TOOLS = {
    # ── Presentation lifecycle ────────────────────────────
    "open_presentation": {
        "description": "Open a .pptx file and load the first slide.",
        "parameters": {
            "path": {"type": "string", "description": "Absolute path to the .pptx file"},
        },
    },
    "save_presentation": {
        "description": "Save the current presentation. Writes element positions back to pptx.",
        "parameters": {
            "output_path": {"type": "string", "description": "Optional output path. Defaults to input path."},
        },
    },
    "select_slide": {
        "description": "Switch to a different slide in the presentation.",
        "parameters": {
            "index": {"type": "integer", "description": "0-based slide index"},
        },
    },

    # ── Full audit ────────────────────────────────────────
    "audit_slide": {
        "description": (
            "Run complete geometry QA on the current slide. "
            "Returns ok if no problems, needs_decision with issues+options if problems found. "
            "Auto-fixes small boundary/alignment violations silently."
        ),
        "parameters": {},
    },

    # ── Layout template ───────────────────────────────────
    "list_templates": {
        "description": "List all available layout templates with their regions and descriptions.",
        "parameters": {},
    },
    "apply_layout": {
        "description": (
            "Move elements to positions defined by a named layout template. "
            "Agent specifies which elements fill which roles (e.g. body=shape-05, figure=shape-07). "
            "Engine computes coordinates, validates, and returns audit result."
        ),
        "parameters": {
            "template": {
                "type": "string",
                "description": "Layout template name, e.g. 'text_left_figure_right'",
            },
            "role_mapping": {
                "type": "object",
                "description": "Mapping of roles to element IDs: {'body': 'shape-05', 'figure': 'shape-07', 'title': 'shape-01'}",
            },
            "expected_revision": {
                "type": "integer",
                "description": "Optional: only apply if slide hasn't changed since this revision",
            },
        },
    },

    # ── Element operations ────────────────────────────────
    "move_element": {
        "description": (
            "Move or resize a single element. "
            "Checks revision lock, element lock, physics safety. "
            "Post-move audit detects any new issues introduced."
        ),
        "parameters": {
            "element_id": {"type": "string", "description": "Element ID, e.g. 'shape-05'"},
            "x": {"type": "number", "description": "New left position in pt"},
            "y": {"type": "number", "description": "New top position in pt"},
            "w": {"type": "number", "description": "New width in pt"},
            "h": {"type": "number", "description": "New height in pt"},
            "expected_revision": {
                "type": "integer",
                "description": "Optional: only apply if slide hasn't changed since this revision",
            },
        },
    },
    "set_element_role": {
        "description": "Assign or change the semantic role of an element (title, body, figure, etc).",
        "parameters": {
            "element_id": {"type": "string"},
            "role": {"type": "string", "description": "Content role: title|subtitle|body|figure|caption|footer|background|decoration"},
        },
    },
    "delete_element": {
        "description": "Remove an element from the slide.",
        "parameters": {
            "element_id": {"type": "string"},
        },
    },

    # ── Local context ─────────────────────────────────────
    "local_context": {
        "description": (
            "Get detailed information about specific elements and their immediate neighbors. "
            "Use after receiving needs_decision to inspect the problem area before making a choice."
        ),
        "parameters": {
            "element_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "IDs of elements to inspect",
            },
        },
    },
    "element_summary": {
        "description": "Lightweight summary of all elements on the current slide (role + grid address only, no bbox).",
        "parameters": {},
    },

    # ── Human collaboration ───────────────────────────────
    "lock_element": {
        "description": "Lock an element so it cannot be moved by automated operations.",
        "parameters": {
            "element_id": {"type": "string"},
            "locked_by": {"type": "string", "description": "Typically 'human'"},
        },
    },
    "unlock_element": {
        "description": "Unlock a previously locked element.",
        "parameters": {
            "element_id": {"type": "string"},
        },
    },
    "notify_human_edit": {
        "description": (
            "Notify the engine that a human manually edited an element in PowerPoint. "
            "Updates internal state, bumps revision, clears auto-fix state."
        ),
        "parameters": {
            "element_id": {"type": "string"},
            "x": {"type": "number"},
            "y": {"type": "number"},
            "w": {"type": "number"},
            "h": {"type": "number"},
        },
    },

    # ── Transaction control ──────────────────────────────
    "begin_transaction": {
        "description": "Start a transaction group. Subsequent operations can be rolled back atomically.",
        "parameters": {},
    },
    "commit": {
        "description": "Commit the current transaction. Changes become permanent.",
        "parameters": {},
    },
    "rollback": {
        "description": "Roll back the current transaction. Only agent operations are reverted; human edits are preserved.",
        "parameters": {},
    },
    "undo": {
        "description": "Undo the last non-transactional operation.",
        "parameters": {},
    },

    # ── Grid Canvas (new) ────────────────────────────────
    "try_place": {
        "description": (
            "Try to place an element on the grid canvas BEFORE writing to PPT. "
            "Returns ALLOW if placement is safe, BLOCK with conflicts if not. "
            "Agent provides content_role (title/body/figure/caption/textbox/etc) "
            "and target cells (e.g. ['A2','B2','A3','B3'])."
        ),
        "parameters": {
            "element_id": {"type": "string", "description": "Element ID, e.g. 'shape-07'"},
            "content_type": {"type": "string", "description": "Content type: text|textbox|image|table|chart|shape|annotation|background"},
            "target_cells": {"type": "array", "items": {"type": "string"}, "description": "Target grid cells, e.g. ['A2','A3','B2','B3']"},
        },
    },
    "commit_grid": {
        "description": "Commit grid canvas state to the PPT file. Only call after try_place returns ALLOW.",
        "parameters": {
            "output_path": {"type": "string", "description": "Output .pptx path"},
        },
    },
    "rollback_grid": {
        "description": "Roll back grid to last checkpoint. PPT file unchanged.",
        "parameters": {},
    },
    "grid_snapshot": {
        "description": (
            "Get Agent-friendly grid state summary. Level 0 = full slide overview (~50 tokens). "
            "Level 1 = zone detail (~100 tokens). Level 2 = single element detail (~60 tokens)."
        ),
        "parameters": {
            "level": {"type": "integer", "description": "0=overview, 1=zone detail, 2=element detail"},
            "target": {"type": "string", "description": "For level=1: cell range. For level=2: element ID."},
        },
    },

    # ── Info ──────────────────────────────────────────────
    "get_revision": {
        "description": "Get the current revision number of the slide.",
        "parameters": {},
    },
    "get_journal": {
        "description": "Get recent journal entries (operation history).",
        "parameters": {
            "since_revision": {"type": "integer", "description": "Only return entries after this revision"},
            "limit": {"type": "integer", "description": "Max entries to return", "default": 20},
        },
    },
}


# ═══════════════════════════════════════════════════════════
# MCP DISPATCHER
# ═══════════════════════════════════════════════════════════
class PPTReflexMCPServer:
    """Stateless dispatch layer. Session holds state."""

    def __init__(self):
        self.session = Session()
        self.handlers = {
            # Lifecycle
            "open_presentation": self._open_presentation,
            "save_presentation": self._save_presentation,
            "select_slide": self._select_slide,
            # Audit
            "audit_slide": self._audit_slide,
            # Layout
            "list_templates": self._list_templates,
            "apply_layout": self._apply_layout,
            # Element ops
            "move_element": self._move_element,
            "set_element_role": self._set_element_role,
            "delete_element": self._delete_element,
            # Context
            "local_context": self._local_context,
            "element_summary": self._element_summary,
            # Grid Canvas (new)
            "try_place": self._try_place,
            "commit_grid": self._commit_grid,
            "rollback_grid": self._rollback_grid,
            "grid_snapshot": self._grid_snapshot,
            # Human collab
            "lock_element": self._lock_element,
            "unlock_element": self._unlock_element,
            "notify_human_edit": self._notify_human_edit,
            # Transactions
            "begin_transaction": self._begin_transaction,
            "commit": self._commit,
            "rollback": self._rollback,
            "undo": self._undo,
            # Info
            "get_revision": self._get_revision,
            "get_journal": self._get_journal,
        }

    def call_tool(self, name: str, arguments: dict) -> dict:
        if name not in self.handlers:
            return {"status": "error", "message": f"Unknown tool: {name}"}
        try:
            return self.handlers[name](arguments)
        except Exception as e:
            return {"status": "error", "message": f"{type(e).__name__}: {e}"}

    # ── Lifeycle ──────────────────────────────────────────
    def _open_presentation(self, args: dict) -> dict:
        path = args["path"]
        if not Path(path).exists():
            return {"status": "error", "message": f"File not found: {path}"}
        self.session.load(path)
        return {
            "status": "ok",
            "path": path,
            "slides": len(self.session.prs.slides),
            "current_slide": 0,
            "elements": len(self.session.slide_elements),
            "revision": self.session.engine.journal.last_revision(),
            "templates_available": [k for k in TEMPLATES],
        }

    def _save_presentation(self, args: dict) -> dict:
        self.session.save(args.get("output_path"))
        return {"status": "ok", "saved_to": args.get("output_path") or self.session.path}

    def _select_slide(self, args: dict) -> dict:
        idx = args["index"]
        if idx < 0 or idx >= len(self.session.prs.slides):
            return {"status": "error", "message": f"Slide index {idx} out of range"}
        self.session._load_slide(idx)
        return {
            "status": "ok",
            "current_slide": idx,
            "elements": len(self.session.slide_elements),
            "revision": self.session.engine.journal.last_revision(),
        }

    # ── Audit ─────────────────────────────────────────────
    def _audit_slide(self, args: dict) -> dict:
        return self.session.engine.audit()

    # ── Layout ────────────────────────────────────────────
    def _list_templates(self, args: dict) -> dict:
        return {
            "status": "ok",
            "templates": [
                {
                    "name": name,
                    "description": t.description,
                    "regions": [
                        {"name": r.name, "grid": r.grid_range, "roles": r.allowed_roles}
                        for r in t.regions
                    ],
                }
                for name, t in TEMPLATES.items()
            ],
        }

    def _apply_layout(self, args: dict) -> dict:
        template = args["template"]
        role_mapping = args["role_mapping"]
        expected_rev = args.get("expected_revision")
        return self.session.engine.apply_layout(template, role_mapping, expected_rev)

    # ── Element ops ───────────────────────────────────────
    def _move_element(self, args: dict) -> dict:
        elem_id = args["element_id"]
        new_bbox = BBox(
            x=args["x"], y=args["y"],
            w=args["w"], h=args["h"],
        )
        expected_rev = args.get("expected_revision")
        result = self.session.engine.move_element(elem_id, new_bbox, expected_rev)
        # Update bridge elements to reflect engine state
        for e in self.session.slide_elements:
            engine_elem = self.session.engine.get_element(e.id)
            if engine_elem:
                e.bbox = engine_elem.bbox
                e.content_role = engine_elem.content_role
        return result

    def _set_element_role(self, args: dict) -> dict:
        elem_id = args["element_id"]
        role_str = args["role"]
        try:
            role = ContentRole(role_str)
        except ValueError:
            return {"status": "error", "message": f"Unknown role: {role_str}. Valid: {[r.value for r in ContentRole]}"}

        elem = self.session.engine.get_element(elem_id)
        if not elem:
            return {"status": "error", "message": f"Element not found: {elem_id}"}

        old_role = elem.content_role.value
        elem.content_role = role
        # Re-register to update collision indexing
        self.session.engine.geo.remove(elem)
        self.session.engine.geo.register(elem)

        self.session.engine.journal.record(
            "agent", elem_id, "set_role",
            {"role": old_role}, {"role": role_str},
        )
        return {"status": "ok", "element_id": elem_id, "old_role": old_role, "new_role": role_str}

    def _delete_element(self, args: dict) -> dict:
        elem_id = args["element_id"]
        elem = self.session.engine.get_element(elem_id)
        if not elem:
            return {"status": "error", "message": f"Element not found: {elem_id}"}
        if elem.locked:
            return {"status": "blocked", "message": f"Element '{elem_id}' locked by {elem.locked_by}"}

        before = {"x": round(elem.bbox.x, 1), "y": round(elem.bbox.y, 1),
                  "w": round(elem.bbox.w, 1), "h": round(elem.bbox.h, 1)}
        self.session.engine.geo.remove(elem)
        self.session.engine.journal.record("agent", elem_id, "delete", before, {})

        # Remove from bridge elements too
        self.session.slide_elements = [e for e in self.session.slide_elements if e.id != elem_id]

        return {"status": "ok", "deleted": elem_id}

    # ── Context ───────────────────────────────────────────
    def _local_context(self, args: dict) -> dict:
        elem_ids = args.get("element_ids", [])
        return self.session.engine.local_context(elem_ids)

    def _element_summary(self, args: dict) -> dict:
        """Lightweight: role + grid cells only, no bbox."""
        elements = []
        for e in self.session.engine.geo.elements.values():
            from engine import _grid_range
            elements.append({
                "id": e.id,
                "role": e.content_role.value,
                "grid": _grid_range(e.coarse_cells),
                "text_preview": e.text[:40] if e.text else "",
                "locked": e.locked,
                "locked_by": e.locked_by,
            })
        return {
            "status": "ok",
            "slide_id": f"slide-{self.session.current_slide_idx:02d}",
            "revision": self.session.engine.journal.last_revision(),
            "elements": elements,
        }

    # ── Grid Canvas ───────────────────────────────────────
    def _try_place(self, args: dict) -> dict:
        eid = args["element_id"]
        ct_str = args["content_type"]
        target_cells = args["target_cells"]

        try:
            ct = ContentType(ct_str)
        except ValueError:
            return {"status": "error", "message": f"Unknown ContentType: {ct_str}. Valid: {[c.value for c in ContentType]}"}

        result = self.session.grid.try_place(eid, ct, target_cells)
        report = self.session.supply.format_conflict(result)

        if result.allowed:
            report["status"] = "placed"
        return report

    def _commit_grid(self, args: dict) -> dict:
        path = args.get("output_path") or self.session.path
        self.session.grid.checkpoint()
        return self.session.grid.commit(path)

    def _rollback_grid(self, args: dict) -> dict:
        return self.session.grid.rollback()

    def _grid_snapshot(self, args: dict) -> dict:
        level = args.get("level", 0)
        target = args.get("target", "")

        if level == 0:
            profile = self.session.grid.profile()
            data = self.session.supply.level0(self.session.grid.info_grid, profile)
        elif level == 1 and target:
            from grid.positioning import cell_range, parse_cell
            try:
                cells = [target] if ":" not in target else _expand_range(target)
            except Exception:
                return {"status": "error", "message": f"Invalid cell range: {target}"}
            data = self.session.supply.level1(self.session.grid.info_grid, cells)
        elif level == 2 and target:
            data = self.session.supply.level2(self.session.grid.info_grid, target)
            if data is None:
                return {"status": "error", "message": f"Element not found: {target}"}
        else:
            return {"status": "error", "message": f"Invalid level/target: {level}/{target}"}

        data["status"] = "ok"
        return data

    # ── Human collab ──────────────────────────────────────
    def _lock_element(self, args: dict) -> dict:
        elem_id = args["element_id"]
        locked_by = args.get("locked_by", "human")
        elem = self.session.engine.get_element(elem_id)
        if not elem:
            return {"status": "error", "message": f"Element not found: {elem_id}"}
        self.session.engine.lock_element(elem_id, locked_by)
        return {"status": "ok", "element_id": elem_id, "locked_by": locked_by}

    def _unlock_element(self, args: dict) -> dict:
        elem_id = args["element_id"]
        self.session.engine.unlock_element(elem_id)
        return {"status": "ok", "element_id": elem_id, "unlocked": True}

    def _notify_human_edit(self, args: dict) -> dict:
        elem_id = args["element_id"]
        new_bbox = BBox(
            x=args["x"], y=args["y"],
            w=args["w"], h=args["h"],
        )
        self.session.engine.notify_human_edit(elem_id, new_bbox)
        return {
            "status": "ok",
            "element_id": elem_id,
            "revision": self.session.engine.journal.last_revision(),
            "message": f"Element '{elem_id}' updated. Agent should re-audit before next operation.",
        }

    # ── Transactions ──────────────────────────────────────
    def _begin_transaction(self, args: dict) -> dict:
        self.session.engine.journal.begin_transaction()
        return {"status": "ok", "message": "Transaction started"}

    def _commit(self, args: dict) -> dict:
        self.session.engine.journal.commit()
        return {"status": "ok", "message": "Transaction committed"}

    def _rollback(self, args: dict) -> dict:
        reversed_ops = self.session.engine.rollback()
        return {
            "status": "ok",
            "rolled_back": len(reversed_ops),
            "operations": [
                {"operation_id": op["operation_id"], "element_id": op["element_id"],
                 "restored_to": op["after_inverse"]}
                for op in reversed_ops
            ],
            "message": f"Rolled back {len(reversed_ops)} agent operations. Human edits preserved.",
        }

    def _undo(self, args: dict) -> dict:
        reversed_ops = self.session.engine.journal.undo()
        return {
            "status": "ok",
            "undone": len(reversed_ops),
        }

    # ── Info ──────────────────────────────────────────────
    def _get_revision(self, args: dict) -> dict:
        rev = self.session.engine.journal.last_revision()
        return {"status": "ok", "revision": rev}

    def _get_journal(self, args: dict) -> dict:
        since = args.get("since_revision", 0)
        limit = args.get("limit", 20)
        entries = self.session.engine.journal.get_entries_since(since)
        return {
            "status": "ok",
            "entries": [
                {
                    "operation_id": e.operation_id,
                    "revision": e.revision,
                    "source": e.source,
                    "element_id": e.element_id,
                    "action": e.action,
                    "reason": e.reason,
                    "timestamp": e.timestamp,
                }
                for e in entries[-limit:]
            ],
        }


# ═══════════════════════════════════════════════════════════
# MCP PROTOCOL LAYER (stdio JSON-RPC)
# ═══════════════════════════════════════════════════════════
def _run_stdio():
    """Run as stdio MCP server (compatible with Claude Desktop, VS Code, etc.)"""
    import sys
    server = PPTReflexMCPServer()

    # Initialize
    init_req = json.loads(sys.stdin.readline())
    print(json.dumps({
        "jsonrpc": "2.0",
        "id": init_req.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "ppt-reflex-engine",
                "version": "0.1.0",
            },
        },
    }))
    sys.stdout.flush()

    # Send tool list
    print(json.dumps({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }))
    sys.stdout.flush()

    # Respond to tools/list
    list_req = json.loads(sys.stdin.readline())
    tools_list = [
        {
            "name": name,
            "description": defn["description"],
            "inputSchema": {
                "type": "object",
                "properties": {
                    k: {
                        "type": v.get("type", "string"),
                        "description": v.get("description", ""),
                    }
                    for k, v in defn.get("parameters", {}).items()
                },
                "required": list(defn.get("parameters", {}).keys()),
            },
        }
        for name, defn in TOOLS.items()
    ]
    print(json.dumps({
        "jsonrpc": "2.0",
        "id": list_req.get("id"),
        "result": {"tools": tools_list},
    }))
    sys.stdout.flush()

    # Tool call loop
    for line in sys.stdin:
        try:
            req = json.loads(line)
            if req.get("method") == "tools/call":
                tool_name = req["params"]["name"]
                arguments = req["params"].get("arguments", {})
                result = server.call_tool(tool_name, arguments)
                response = {
                    "jsonrpc": "2.0",
                    "id": req["id"],
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)},
                        ],
                    },
                }
            elif req.get("method") == "tools/list":
                tools_list_2 = [
                    {
                        "name": name,
                        "description": defn["description"],
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                k: {
                                    "type": v.get("type", "string"),
                                    "description": v.get("description", ""),
                                }
                                for k, v in defn.get("parameters", {}).items()
                            },
                        },
                    }
                    for name, defn in TOOLS.items()
                ]
                response = {
                    "jsonrpc": "2.0",
                    "id": req["id"],
                    "result": {"tools": tools_list_2},
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": req.get("id"),
                    "result": {},
                }
            print(json.dumps(response, ensure_ascii=False))
            sys.stdout.flush()
        except Exception as e:
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": req.get("id") if 'req' in dir() else None,
                "error": {"code": -32603, "message": str(e)},
            }, ensure_ascii=False))
            sys.stdout.flush()


# ═══════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="PPT Reflex Engine MCP Server")
    ap.add_argument("--port", type=int, help="Run as HTTP on given port")
    ap.add_argument("--test", type=str, help="Run a single tool call from CLI for testing")
    ap.add_argument("--test-args", type=str, default="{}", help="JSON arguments for --test")
    args = ap.parse_args()

    if args.test:
        server = PPTReflexMCPServer()
        test_name = os.path.basename(args.test)
        if test_name in server.handlers:
            # Tool name: open file first if --file flag provided, then call
            result = server.call_tool(test_name, json.loads(args.test_args))
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif Path(args.test).suffix == ".pptx" and Path(args.test).exists():
            server._open_presentation({"path": args.test})
            # Print summary
            summary = server._element_summary({})
            audit = server._audit_slide({})
            print("=== ELEMENTS ===")
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            print("=== AUDIT ===")
            print(json.dumps(audit, ensure_ascii=False, indent=2))
        else:
            # Try opening it
            from pathlib import Path
            if Path(args.test).exists():
                server._open_presentation({"path": args.test})
                audit = server._audit_slide({})
                print(json.dumps(audit, ensure_ascii=False, indent=2))
            else:
                print(json.dumps({"status": "error", "message": f"Unknown tool or file: {args.test}"},
                                 ensure_ascii=False, indent=2))
    elif args.port:
        # HTTP mode (simplified — production should use FastMCP)
        from http.server import HTTPServer, BaseHTTPRequestHandler
        server = PPTReflexMCPServer()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                req = json.loads(body)
                name = req.get("method", "").replace("tools/call/", "")
                result = server.call_tool(name, req.get("params", {}))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode())

        httpd = HTTPServer(("0.0.0.0", args.port), Handler)
        print(f"MCP Server listening on http://0.0.0.0:{args.port}/mcp")
        httpd.serve_forever()
    else:
        _run_stdio()
