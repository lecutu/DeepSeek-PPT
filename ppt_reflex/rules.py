"""
L2 声明式规则引擎

规则分类：
  collision_rules  — 哪些重叠合法
  bounds_rules     — 安全区/边距
  alignment_rules  — 对齐容差
  spacing_rules    — 间距均匀性
  font_rules       — 字号下限
  density_rules    — 页面密度阈值

规则不写死——从 rules_schema 加载，支持用户自定义。
"""

from __future__ import annotations
from engine import (
    ContentRole, CollisionRole, CollisionVerdict, Issue, IssueCode, Severity,
    SlideElement, BBox,
)
from dataclasses import dataclass, field
from typing import Any
import json
from pathlib import Path


# ── rule data types ────────────────────────────────────────
@dataclass
class OverlapRule:
    a: str     # content_role or collision_role wildcard
    b: str     # symmetrical — order doesn't matter
    verdict: str  # "allow" | "warn" | "block"
    relation: str = "overlap"   # "overlap" | "over" | "under"
    max_area_pct: float | None = None
    requires_same_group: bool = False
    severity: str = "high"

@dataclass
class FontRule:
    role: str
    min_pt: float

@dataclass
class BoundsRule:
    safe_margin_pt: float = 36
    snap_max_pt: float = 5

@dataclass
class AlignmentRule:
    snap_max_pt: float = 3
    report_drift_min_pt: float = 2


# ── default rules ──────────────────────────────────────────
DEFAULT_OVERLAP_RULES: list[dict] = [
    # Block: no overlap allowed
    {"a": "title",      "b": "*",              "verdict": "block", "severity": "high"},
    {"a": "subtitle",   "b": "*",              "verdict": "block", "severity": "high"},
    {"a": "body",       "b": "body",           "verdict": "block", "severity": "high"},
    {"a": "body",       "b": "figure",         "verdict": "block", "severity": "high"},
    {"a": "figure",     "b": "figure",         "verdict": "block", "severity": "high"},
    {"a": "body",       "b": "key_metric",     "verdict": "block", "severity": "high"},
    # Allow: intentional overlap
    {"a": "caption",    "b": "figure",         "verdict": "allow", "relation": "over",
     "max_area_pct": 70},
    {"a": "caption",    "b": "key_metric",     "verdict": "allow", "relation": "over",
     "max_area_pct": 20},
    {"a": "page_number","b": "footer",         "verdict": "allow", "max_area_pct": 50},
    {"a": "page_number","b": "*",              "verdict": "allow", "max_area_pct": 10,
     "relation": "over"},
    {"a": "background", "b": "*",              "verdict": "allow"},
    {"a": "decoration", "b": "*",              "verdict": "allow", "max_area_pct": 25},
    # Warn: ambiguous — accumulate before reporting
    {"a": "key_metric", "b": "figure",         "verdict": "warn", "max_area_pct": 10},
    {"a": "citation",   "b": "body",           "verdict": "warn", "max_area_pct": 15},
]

DEFAULT_FONT_RULES: list[dict] = [
    {"role": "title",      "min_pt": 24},
    {"role": "subtitle",   "min_pt": 18},
    {"role": "body",       "min_pt": 14},
    {"role": "key_metric", "min_pt": 20},
    {"role": "caption",    "min_pt": 11},
    {"role": "citation",   "min_pt": 10},
    {"role": "footer",     "min_pt": 10},
    {"role": "unknown",    "min_pt": 12},
]

DEFAULT_BOUNDS_RULES: dict = {
    "safe_margin_pt": 36,
    "snap_max_pt": 5,
}

DEFAULT_ALIGNMENT_RULES: dict = {
    "snap_max_pt": 3,
    "report_drift_min_pt": 2,
}

DEFAULT_SPACING_RULES: dict = {
    "max_deviation_pct": 50,  # max gap deviation as % of mean gap
}

DEFAULT_DENSITY_RULES: dict = {
    "warn_threshold_pct": 70,
    "critical_threshold_pct": 85,
}


# ═══════════════════════════════════════════════════════════
# RULES ENGINE
# ═══════════════════════════════════════════════════════════
class RulesEngine:
    """Loads declarative rules and judges overlap pairs."""

    def __init__(self, rules_path: str | None = None):
        self.overlap_rules: list[OverlapRule] = []
        self.font_rules: dict[str, float] = {}
        self.bounds_rules = BoundsRule()
        self.alignment_rules = AlignmentRule()
        self.spacing_rules: dict = {}
        self.density_rules: dict = {}
        self._load(rules_path)

    def _load(self, path: str | None):
        if path:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {
                "overlap_rules": DEFAULT_OVERLAP_RULES,
                "font_rules": DEFAULT_FONT_RULES,
                "bounds_rules": DEFAULT_BOUNDS_RULES,
                "alignment_rules": DEFAULT_ALIGNMENT_RULES,
                "spacing_rules": DEFAULT_SPACING_RULES,
                "density_rules": DEFAULT_DENSITY_RULES,
            }

        # overlap rules
        self.overlap_rules = [OverlapRule(**r) for r in data.get("overlap_rules", [])]

        # font rules
        self.font_rules = {
            r["role"]: r["min_pt"]
            for r in data.get("font_rules", DEFAULT_FONT_RULES)
        }

        # bounds rules
        br = data.get("bounds_rules", DEFAULT_BOUNDS_RULES)
        self.bounds_rules = BoundsRule(**br)

        # alignment
        ar = data.get("alignment_rules", DEFAULT_ALIGNMENT_RULES)
        self.alignment_rules = AlignmentRule(**ar)

        # spacing
        self.spacing_rules = data.get("spacing_rules", DEFAULT_SPACING_RULES)

        # density
        self.density_rules = data.get("density_rules", DEFAULT_DENSITY_RULES)

    # ── overlap judgement ──────────────────────────────────
    def judge_overlap(self, a: SlideElement, b: SlideElement, overlap_pct: float) -> CollisionVerdict:
        """Match pair against rule table. Returns verdict."""
        role_a = a.content_role.value
        role_b = b.content_role.value

        for rule in self.overlap_rules:
            if self._match_pair(rule, role_a, role_b):
                # max_area check
                if rule.max_area_pct is not None and overlap_pct > rule.max_area_pct:
                    return CollisionVerdict.BLOCK
                return CollisionVerdict[rule.verdict.upper()]

        # No rule matched → block by default (conservative)
        return CollisionVerdict.BLOCK

    def _match_pair(self, rule: OverlapRule, role_a: str, role_b: str) -> bool:
        """Check if rule matches (a,b) pair, handling '*' wildcard."""
        def _match(pattern: str, role: str) -> bool:
            return pattern == "*" or pattern == role

        # Try both orders (rules are symmetric in meaning)
        if _match(rule.a, role_a) and _match(rule.b, role_b):
            return True
        if _match(rule.a, role_b) and _match(rule.b, role_a):
            return True
        return False

    # ── font minimum ───────────────────────────────────────
    def get_min_font(self, role: ContentRole) -> float:
        return self.font_rules.get(role.value, 12.0)

    # ── serialization ──────────────────────────────────────
    def export_default_rules(self, path: str):
        """Write default rules to file so user can customize."""
        data = {
            "overlap_rules": DEFAULT_OVERLAP_RULES,
            "font_rules": DEFAULT_FONT_RULES,
            "bounds_rules": DEFAULT_BOUNDS_RULES,
            "alignment_rules": DEFAULT_ALIGNMENT_RULES,
            "spacing_rules": DEFAULT_SPACING_RULES,
            "density_rules": DEFAULT_DENSITY_RULES,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
