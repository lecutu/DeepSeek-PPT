"""Design-level policy engine — prevents AI fix-loops by analyzing diagnostic patterns
and producing actionable design hints, not just bug lists.

P0-①: Hard circuit breaker — same fix direction attempted ≥2 times → BLOCK
P0-②: Fix fingerprinting — (slide, kind, elem_id, direction) quad dedup
P1-①: Progressive escalation — L1 hint → L2 warn → L3 block
P1-②: Entropy management — detect mechanical micro-adjustments → force design rethink
"""

from __future__ import annotations
from dataclasses import dataclass, field
from collections import Counter, defaultdict
from enum import IntEnum
from typing import NamedTuple


# ═══════════════════════════════════════════════════════════════
# Fix direction — AI declares what strategy it's trying
# ═══════════════════════════════════════════════════════════════

# Reserved direction tags — AI picks one per fix attempt
FIX_DIRECTIONS: dict[str, str] = {
    # Size tweaks (mechanical — flagged aggressively)
    "increase_box_height":   "加大盒子高度",
    "increase_box_width":    "加大盒子宽度",
    "decrease_font_size":    "缩小字号",
    "increase_region":       "扩大区域",
    "rearrange_regions":     "重新分配区域布局",

    # Content reduction (better — but still a direction to track)
    "reduce_text":           "减少文字量",
    "split_text":            "拆分成多块文字",
    "shorter_lines":         "缩短每行字数",
    "remove_elements":       "删除元素",

    # Layout change (design-level)
    "split_slide":           "拆成两页",
    "switch_layout":         "换布局方案",
    "switch_region_order":   "调整区域叠放顺序",

    # Color change
    "change_text_color":     "改文字颜色",
    "change_fill_color":     "改填充色",
    "switch_template":       "换模板",
    "switch_style":          "换配色风格",
    "dark_to_light":         "深色背景→浅色",
    "light_to_dark":         "浅色背景→深色",

    # Unknown
    "unknown":               "未声明方向",
}

MECHANICAL_DIRECTIONS = {
    "increase_box_height", "increase_box_width", "decrease_font_size",
    "increase_region", "rearrange_regions",
}

DESIGN_DIRECTIONS = {
    "split_slide", "switch_layout", "switch_template", "switch_style",
    "dark_to_light", "light_to_dark", "reduce_text", "remove_elements",
}


# ═══════════════════════════════════════════════════════════════
# Escalation ladder
# ═══════════════════════════════════════════════════════════════

class Escalation(IntEnum):
    HINT = 1
    WARN = 2
    BLOCK = 3


# ═══════════════════════════════════════════════════════════════
# Fix fingerprint — (slide, kind, elem_id, direction)
# ═══════════════════════════════════════════════════════════════

class FixFingerprint(NamedTuple):
    slide: int
    kind: str
    elem_id: str
    direction: str = "unknown"


@dataclass
class DirectionRecord:
    """Per-direction attempt count for one (slide, kind, elem_id) triple."""
    direction: str
    attempts: int = 1


@dataclass
class EscalationRecord:
    fingerprint_base: tuple   # (slide, kind, elem_id) — direction agnostic key
    directions: dict[str, DirectionRecord] = field(default_factory=dict)
    seen_count: int = 0       # total attempts across all directions
    current_level: Escalation = Escalation.HINT


@dataclass
class CircuitBreaker:
    """Per-builder state that persists across build()/rebuild() calls.

    AI declares a fix direction before each build:
        b.declare_direction("reduce_text")
        b.declare_direction("split_slide")

    Breaker tracks (slide, kind, elem_id, direction) and escalates:
    - same direction 2+ times on same error → WARN
    - same direction 3+ times on same error → BLOCK
    - 3+ different mechanical directions on same error → BLOCK (thrashing)
    """

    fingerprints: dict[tuple, EscalationRecord] = field(default_factory=dict)

    error_trend: list[int] = field(default_factory=list)
    _max_trend_len: int = 5

    build_count: int = 0

    # Active direction for this build (set by declare_direction)
    _active_direction: str | None = None

    allow_same_direction_until: int = 2  # WARN at 2, BLOCK at 3
    entropy_stall_threshold: float = 0.20

    # ── public API ──

    def declare_direction(self, direction: str) -> str | None:
        """Set the fix direction for the upcoming build. Validates against known directions.

        Returns error string if invalid, None if OK.
        """
        if direction not in FIX_DIRECTIONS:
            valid = ", ".join(sorted(FIX_DIRECTIONS.keys()))
            return f"Unknown direction '{direction}'. Valid: {valid}"
        self._active_direction = direction
        return None

    @property
    def active_direction(self) -> str:
        return self._active_direction or "unknown"

    def record_build(self, errors: list[dict]) -> list[dict]:
        self.build_count += 1
        direction = self.active_direction
        escalated: list[dict] = []

        for d in errors:
            base_key = (
                d.get("slide", -1),
                d.get("kind", ""),
                d.get("elem_id", ""),
            )
            if not base_key[1]:
                continue

            if base_key not in self.fingerprints:
                self.fingerprints[base_key] = EscalationRecord(
                    fingerprint_base=base_key,
                )
            rec = self.fingerprints[base_key]
            rec.seen_count += 1

            # Track per-direction
            if direction not in rec.directions:
                rec.directions[direction] = DirectionRecord(direction=direction, attempts=1)
            else:
                rec.directions[direction].attempts += 1

            dr = rec.directions[direction]
            n_mech = sum(1 for dd in rec.directions.values()
                        if dd.direction in MECHANICAL_DIRECTIONS)

            # Escalation rules
            if dr.attempts >= 3:
                rec.current_level = Escalation.BLOCK
            elif dr.attempts >= 2:
                rec.current_level = max(rec.current_level, Escalation.WARN)
            # Thrashing: 3+ different mechanical directions on same error
            if n_mech >= 3:
                rec.current_level = Escalation.BLOCK

            if rec.current_level >= Escalation.WARN:
                escalated.append({
                    "base": {"slide": base_key[0], "kind": base_key[1],
                             "elem_id": base_key[2]},
                    "direction": direction,
                    "direction_attempts": dr.attempts,
                    "total_attempts": rec.seen_count,
                    "level": rec.current_level.name,
                    "int_level": int(rec.current_level),
                    "n_mech_directions": n_mech,
                })

        self.error_trend.append(len(errors))
        if len(self.error_trend) > self._max_trend_len:
            self.error_trend.pop(0)

        self._active_direction = None
        return escalated

    @property
    def is_stalled(self) -> bool:
        if len(self.error_trend) < 3:
            return False
        recent = self.error_trend[-3:]
        min_e, max_e = min(recent), max(recent)
        if max_e == 0:
            return False
        return (max_e - min_e) / max_e < self.entropy_stall_threshold

    def blocked_fingerprints(self) -> list[dict]:
        result = []
        for base_key, rec in self.fingerprints.items():
            if rec.current_level >= Escalation.BLOCK:
                result.append({
                    "slide": base_key[0],
                    "kind": base_key[1],
                    "elem_id": base_key[2],
                    "blocked_directions": [
                        {"direction": dr.direction, "attempts": dr.attempts}
                        for dr in rec.directions.values() if dr.attempts >= 2
                    ],
                    "total_attempts": rec.seen_count,
                })
        return result

    def escalate_message(self, escalated: list[dict]) -> str:
        if not escalated:
            return ""
        blocks = [e for e in escalated if e["int_level"] >= Escalation.BLOCK]
        warns = [e for e in escalated if e["int_level"] == Escalation.WARN]

        parts = []
        if blocks:
            details = []
            for b in blocks[:3]:
                d = b["direction"]
                label = FIX_DIRECTIONS.get(d, d)
                details.append(
                    f"S{b['base']['slide']+1}/{b['base']['elem_id']}: "
                    f"'{label}' ×{b['direction_attempts']}次"
                )
            parts.append(
                f"⛔ BLOCKED ({len(blocks)}): " + "; ".join(details) + "。"
                f"这些方向已彻底无效，必须换其他方案。"
            )
        if warns:
            details = []
            for w in warns[:3]:
                d = w["direction"]
                label = FIX_DIRECTIONS.get(d, d)
                details.append(
                    f"S{w['base']['slide']+1}/{w['base']['elem_id']}: "
                    f"'{label}' ×{w['direction_attempts']}次"
                )
            parts.append(
                f"⚠ WARN ({len(warns)}): " + "; ".join(details) + "。"
                f"同一方向重复尝试，效果不明显——考虑换策略。"
            )
        if self.is_stalled:
            parts.append(
                f"🔁 熵停滞: 最近{len(self.error_trend)}次 build 错误数 "
                f"{self.error_trend}，波动<{self.entropy_stall_threshold:.0%}，无效微调。"
            )
        return " | ".join(parts)

    def reset(self):
        self.fingerprints.clear()
        self.error_trend.clear()
        self.build_count = 0
        self._active_direction = None


# ═══════════════════════════════════════════════════════════════
# DesignHint
# ═══════════════════════════════════════════════════════════════

@dataclass
class DesignHint:
    level: str
    category: str
    message: str
    affected_slides: list[int] = field(default_factory=list)
    fix_strategy: str = ""


# ═══════════════════════════════════════════════════════════════
# Main analysis entry point
# ═══════════════════════════════════════════════════════════════

def analyze_design_issues(aggregated_diags: list[dict],
                          all_raw_diags: list[dict],
                          slides_data: list[dict],
                          breaker: CircuitBreaker | None = None) -> list[DesignHint]:
    hints: list[DesignHint] = []

    hints.extend(_check_content_density(slides_data, all_raw_diags))
    hints.extend(_check_repeated_errors(all_raw_diags))
    hints.extend(_check_color_scheme(all_raw_diags))
    hints.extend(_check_text_volume(all_raw_diags, slides_data))
    hints.extend(_check_element_count(slides_data))

    if breaker is not None:
        errs = [d for d in aggregated_diags if d.get("severity") in ("error",)]
        escalated = breaker.record_build(errs)
        escalation_msg = breaker.escalate_message(escalated)
        if escalation_msg:
            hints.append(DesignHint(
                level="critical",
                category="meta",
                message=escalation_msg,
                fix_strategy=_escalation_fix_strategy(escalated, breaker),
            ))

    return hints


def _escalation_fix_strategy(escalated: list[dict], breaker: CircuitBreaker) -> str:
    blocked = [e for e in escalated if e["int_level"] >= Escalation.BLOCK]
    if blocked:
        dead_dirs = set(e["direction"] for e in blocked)
        dead_labels = [FIX_DIRECTIONS.get(d, d) for d in dead_dirs]
        return (
            f"以下方向已死亡: {', '.join(dead_labels)}。"
            f"必须从从未尝试的方向中选一个: "
            f"split_slide / reduce_text / switch_template / switch_layout / remove_elements。"
            f"选好后调用 b.declare_direction('方向名') 声明，再 build。"
        )
    if breaker.is_stalled:
        return "误差在阈值内 3 次 build ——当前修复不改变结果。换设计级方案。"
    return "改方案，别微调。"


# ═══════════════════════════════════════════════════════════════
# Checkers
# ═══════════════════════════════════════════════════════════════

def _check_content_density(slides_data, raw_diags) -> list[DesignHint]:
    hints = []
    overflow_by_slide: dict[int, list[dict]] = {}
    for d in raw_diags:
        if d.get("severity") == "error" and "overflow" in d.get("kind", ""):
            slide = d.get("slide", -1)
            overflow_by_slide.setdefault(slide, []).append(d)

    for slide, errs in overflow_by_slide.items():
        sd = slides_data[slide] if slide < len(slides_data) else {}
        n_elems = sd.get("element_count", 0)
        n_regions = sd.get("region_count", 0)

        if len(errs) >= 2 and n_elems > 0:
            hints.append(DesignHint(
                level="critical", category="content",
                message=(
                    f"Slide {slide + 1}: {len(errs)} overflow errors on a single slide "
                    f"({n_elems} elements in {n_regions} regions). "
                    f"Content density is too high — the layout cannot fit what you're asking."
                ),
                affected_slides=[slide],
                fix_strategy=(
                    f"Split slide {slide + 1} into 2 slides, OR reduce content to "
                    f"≤{max(4, n_elems // 2)} elements, OR reduce text per element."
                ),
            ))
        elif len(errs) == 1:
            hints.append(DesignHint(
                level="warning", category="content",
                message=f"Slide {slide + 1}: single overflow on '{errs[0].get('elem_id', '?')}'.",
                affected_slides=[slide],
                fix_strategy=next((o for o in errs[0].get("options", []) if "reduce" in o.lower()),
                                  errs[0].get("options", ["Reduce content or font size"])[0]),
            ))
    return hints


def _check_repeated_errors(raw_diags: list[dict]) -> list[DesignHint]:
    hints = []
    errors = [d for d in raw_diags if d.get("severity") == "error"]
    if len(errors) < 3:
        return hints

    by_kind: dict[str, list[dict]] = {}
    for e in errors:
        by_kind.setdefault(e.get("kind", ""), []).append(e)

    for kind, errs in by_kind.items():
        slides = sorted(set(e.get("slide", -1) for e in errs))

        if kind == "tri_bg_text" and len(errs) >= 3:
            hints.append(DesignHint(
                level="critical", category="color",
                message=(
                    f"{len(errs)} elements across {len(slides)} slides have "
                    f"white text on near-white background (contrast < 1.1:1). "
                    f"DARK BOX TRAP: white text in dark boxes on cream bg. "
                    f"→ Switch to dark bg, or use dark text in light boxes."
                ),
                affected_slides=slides,
                fix_strategy=(
                    "Option A: Switch to template='product'+style='tech_dark'. "
                    "Option B: Keep cream bg, use dark text (#1E293B) in light boxes."
                ),
            ))

        elif kind == "overflow_vertical" and len(errs) >= 3:
            hints.append(DesignHint(
                level="critical", category="layout",
                message=(
                    f"{len(errs)} vertical overflow errors across {len(slides)} slides. "
                    f"Text boxes consistently too small. Do NOT add 5pt — rethink content."
                ),
                affected_slides=slides,
                fix_strategy=(
                    "Reduce text to ≤3 lines per element. Split dense slides. "
                    "Use b.box() in larger regions."
                ),
            ))

    return hints


def _check_color_scheme(raw_diags: list[dict]) -> list[DesignHint]:
    hints = []
    tri_diags = [d for d in raw_diags
                 if d.get("kind", "").startswith("tri_") and d.get("severity") == "error"]
    slides = sorted(set(d.get("slide", -1) for d in tri_diags))

    if len(tri_diags) >= 2:
        hints.append(DesignHint(
            level="critical", category="color",
            message=(
                f"{len(tri_diags)} color contrast violations across {len(slides)} slides. "
                f"The current color scheme has fundamental visibility problems."
            ),
            affected_slides=slides,
            fix_strategy=(
                "Change template/style combo. Light bg → dark text. "
                "Dark bg → white text. Don't fix individual colors — fix the scheme."
            ),
        ))
    return hints


def _check_text_volume(raw_diags, slides_data) -> list[DesignHint]:
    hints = []
    overflow_diags = [d for d in raw_diags
                      if d.get("kind") == "overflow_vertical" and d.get("severity") == "error"]

    for d in overflow_diags:
        overflow_pt = d.get("overflow_pt", 0)
        box_h = d.get("box_h", 1)
        if box_h <= 0:
            continue

        ratio = overflow_pt / box_h
        slide = d.get("slide", -1)
        elem_id = d.get("elem_id", "")

        if ratio > 0.3:
            hints.append(DesignHint(
                level="critical", category="typography",
                message=(
                    f"Slide {slide + 1}, '{elem_id}': text overflows by "
                    f"{overflow_pt:.0f}pt ({ratio:.0%} of box). "
                    f"Do NOT increase box — REDUCE text."
                ),
                affected_slides=[slide],
                fix_strategy=(
                    f"Reduce to ≤{d.get('line_count', 99) - d.get('overflow_lines', 99)} lines "
                    f"(now {d.get('line_count', '?')} lines). Or split into multiple boxes."
                ),
            ))
    return hints


def _check_element_count(slides_data: list[dict]) -> list[DesignHint]:
    hints = []
    for i, sd in enumerate(slides_data):
        n = sd.get("element_count", 0)
        if n >= 8:
            hints.append(DesignHint(
                level="warning", category="structure",
                message=(
                    f"Slide {i + 1} has {n} elements. "
                    f"Professional slides use 4-7. High count = clutter + noise."
                ),
                affected_slides=[i],
                fix_strategy="Merge similar elements, remove decorative shapes, or split into 2 slides.",
            ))
    return hints


def gather_slides_data(builder) -> list[dict]:
    data = []
    for i, s in enumerate(builder._slides):
        elem_count = len(s.elements)
        region_count = len(s.regions)
        text_chars = sum(len(e.text) for e in s.elements if hasattr(e, 'text') and e.text)
        data.append({
            "index": i,
            "title": getattr(s, 'title', f"Slide {i + 1}"),
            "element_count": elem_count,
            "region_count": region_count,
            "total_text_chars": text_chars,
        })
    return data
