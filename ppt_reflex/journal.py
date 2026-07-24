"""
操作日志 + revision + 回滚

每条修改记录 revision 号、before/after、来源（human/agent/reflex）。
乐观锁：expected_revision 不匹配 → 拒绝执行。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import json
import time
from pathlib import Path


@dataclass
class JournalEntry:
    operation_id: str
    revision: int
    source: str           # "human" | "agent" | "boundary_reflex" | "alignment_reflex" | "collision_nudge"
    element_id: str
    action: str           # "move" | "resize" | "set_text" | "set_font" | "delete" | "add" | "set_role"
    before: dict          # state snapshot of modified elements before
    after: dict           # after
    reason: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class OpResult:
    status: str            # "ok" | "needs_decision" | "blocked" | "state_changed" | "rolled_back"
    revision: int
    operation_id: str = ""
    issues: list = field(default_factory=list)
    auto_adjusted: list = field(default_factory=list)
    message: str = ""


class Journal:
    """
    Append-only log of all modifications. Not a DB — flat list in memory,
    serializable to JSON for persistence.
    """

    def __init__(self):
        self.entries: list[JournalEntry] = []
        self.revision: int = 0
        self._id_counter: int = 0

        # Rollback stack: each entry is (revision_before, [journal_entries_to_undo])
        self._undo_stack: list[tuple[int, list[JournalEntry]]] = []
        self._redo_stack: list[tuple[int, list[JournalEntry]]] = []

    def next_op_id(self) -> str:
        self._id_counter += 1
        return f"op-{self._id_counter:04d}"

    # ── write ──────────────────────────────────────────────
    def record(self, source: str, element_id: str, action: str,
               before: dict, after: dict, reason: str = "") -> tuple[int, str]:
        """
        Append entry, bump revision.
        Returns (new_revision, operation_id).
        """
        self.revision += 1
        op_id = self.next_op_id()
        entry = JournalEntry(
            operation_id=op_id,
            revision=self.revision,
            source=source,
            element_id=element_id,
            action=action,
            before=before,
            after=after,
            reason=reason,
        )
        self.entries.append(entry)
        return self.revision, op_id

    def record_batch(self, source: str, ops: list[dict]) -> tuple[int, list[str]]:
        """
        ops: [{"element_id": ..., "action": ..., "before": ..., "after": ..., "reason": ...}, ...]
        All share the same revision.
        """
        self.revision += 1
        op_ids = []
        for op in ops:
            op_id = self.next_op_id()
            op_ids.append(op_id)
            entry = JournalEntry(
                operation_id=op_id,
                revision=self.revision,
                source=source,
                element_id=op.get("element_id", ""),
                action=op.get("action", ""),
                before=op.get("before", {}),
                after=op.get("after", {}),
                reason=op.get("reason", ""),
            )
            self.entries.append(entry)
        return self.revision, op_ids

    # ── read ───────────────────────────────────────────────
    def get_entries_since(self, rev: int) -> list[JournalEntry]:
        return [e for e in self.entries if e.revision > rev]

    def last_revision(self) -> int:
        return self.revision

    def check_revision(self, expected: int) -> OpResult | None:
        """
        Optimistic lock check.
        Returns OpResult with state_changed if mismatch, None if OK.
        """
        if expected != self.revision:
            return OpResult(
                status="state_changed",
                revision=self.revision,
                message=f"Expected rev {expected}, actual rev {self.revision}",
            )
        return None

    # ── undo / redo ────────────────────────────────────────
    def begin_transaction(self):
        """Mark current state for potential rollback."""
        self._undo_stack.append((self.revision, list(self.entries)))
        self._redo_stack.clear()

    def commit(self):
        """Discard rollback point — transaction succeeded."""
        if self._undo_stack:
            _ = self._undo_stack.pop()

    def rollback(self, source_filter: str = "agent") -> list[dict]:
        """
        Revert to state before the most recent begin_transaction.
        Only rolls back entries matching source_filter (default: agent).
        Human edits that happened during the transaction are preserved.

        Returns list of reversed ops so caller can apply inverse operations.
        """
        if not self._undo_stack:
            return []

        rev_before, entries_before = self._undo_stack.pop()
        # Only roll back agent entries; keep human / reflex edits
        entries_to_rollback = [
            e for e in self.entries
            if e.revision > rev_before and e.source == source_filter
        ]
        # Entries to keep (human edits during transaction)
        entries_to_keep = [
            e for e in self.entries
            if e.revision > rev_before and e.source != source_filter
        ]

        # Push rolled-back entries to redo
        self._redo_stack.append((self.revision, entries_to_rollback))

        # Restore: base entries + human edits that happened during transaction
        self.entries = entries_before + entries_to_keep
        self.revision = len(self.entries)  # Revision counts total entries

        # Return reversed operations for caller to re-apply inversely
        return [
            {"operation_id": e.operation_id, "element_id": e.element_id,
             "action": e.action, "before_inverse": e.after, "after_inverse": e.before}
            for e in reversed(entries_to_rollback)
        ]

    def undo(self) -> list[dict]:
        """Undo last non-transactional operation batch."""
        if not self.entries:
            return []
        # Find last revision boundary
        last_rev = self.entries[-1].revision
        batch = [e for e in self.entries if e.revision == last_rev]
        self.entries = [e for e in self.entries if e.revision != last_rev]
        self.revision = self.entries[-1].revision if self.entries else 0
        self._redo_stack.append((last_rev, batch))
        return [
            {"operation_id": e.operation_id, "element_id": e.element_id,
             "action": e.action, "before_inverse": e.after, "after_inverse": e.before}
            for e in reversed(batch)
        ]

    # ── serialization ──────────────────────────────────────
    def to_dicts(self) -> list[dict]:
        return [
            {"operation_id": e.operation_id, "revision": e.revision,
             "source": e.source, "element_id": e.element_id,
             "action": e.action, "before": e.before, "after": e.after,
             "reason": e.reason, "timestamp": e.timestamp}
            for e in self.entries
        ]

    def save(self, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({"revision": self.revision, "entries": self.to_dicts()},
                      f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> Journal:
        j = cls()
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        j.revision = data["revision"]
        for e in data["entries"]:
            j._id_counter = max(j._id_counter, int(e["operation_id"].split("-")[1]))
            je = JournalEntry(**e)
            j.entries.append(je)
        return j
