"""
grid/composition.py — Phase 2.5: global composition check + anti-AI-template detection

Input: LayoutPlan (Phase 1+2 completed)
Output: list[dict] — aesthetics/balance/whitespace issues + anti-AI-cliché warnings
"""

from __future__ import annotations
from .plan import LayoutPlan


def global_composition_check(plan: LayoutPlan, theme: dict|None = None) -> list[dict]:
    """Global composition check — whitespace ratio, visual center of mass, density, alignment,
    font hierarchy, color ratio, anti-AI-template detection.

    Returns:
        list of dicts with keys: level ("info"|"warn"), category, message
    """
    issues: list[dict] = []

    _check_whitespace(plan, issues)
    _check_balance(plan, issues)
    _check_density(plan, issues)
    _check_alignment(plan, issues)
    _check_font_hierarchy(plan, issues)
    _check_font_size_variety(plan, issues)
    _check_color_ratio(plan, issues)
    _check_single_accent(plan, issues, theme)
    _check_visual_chunks(plan, issues)
    _check_edge_safe_zone(plan, issues)

    # Anti-AI cliché detection — uses theme's anti_ai_rules if available
    anti_rules = theme.get("anti_ai_rules", []) if theme else []
    _check_anti_ai_cliches(plan, issues, anti_rules, theme)

    return issues


# ═══════════════════════════════════════════════════════════════
# Check functions
# ═══════════════════════════════════════════════════════════════

def _check_whitespace(plan: LayoutPlan, issues: list[dict]) -> None:
    total_area = plan.page_w * plan.page_h
    if total_area <= 0:
        return

    elem_area = sum(e.w * e.h for e in plan.elements)
    deco_area = sum(
        abs(d.x2 - d.x1) * abs(d.y2 - d.y1) * 0.1
        for d in plan.decorations
        if d.deco_type == "arrow" and d.x2 != 0
    )
    occupied = elem_area + deco_area
    ratio = occupied / total_area

    if ratio < 0.08:
        issues.append({
            "level": "warn", "category": "whitespace",
            "message": f"Content occupies only {ratio:.0%} of page — too sparse.",
        })
    elif ratio > 0.80:
        issues.append({
            "level": "warn", "category": "whitespace",
            "message": f"Content occupies {ratio:.0%} of page — too dense, reduce element count or size.",
        })
    elif ratio > 0.65:
        issues.append({
            "level": "warn", "category": "whitespace",
            "message": f"Content occupies {ratio:.0%} of page — whitespace below 35%. "
                       f"Design guides recommend ≥40% whitespace (content ≤60%).",
        })
    elif ratio > 0.60:
        issues.append({
            "level": "info", "category": "whitespace",
            "message": f"Content occupies {ratio:.0%} of page — whitespace at {1-ratio:.0%}, "
                       f"approaching the ≥40% whitespace target.",
        })


def _check_balance(plan: LayoutPlan, issues: list[dict]) -> None:
    elements = plan.elements
    if not elements:
        return

    total_area = sum(e.w * e.h for e in elements)
    if total_area <= 0:
        return

    cx = sum((e.x + e.w / 2) * e.w * e.h for e in elements) / total_area
    cy = sum((e.y + e.h / 2) * e.w * e.h for e in elements) / total_area

    page_cx = plan.page_w / 2
    page_cy = plan.page_h / 2
    third_w = plan.page_w / 3
    third_h = plan.page_h / 3

    dx = abs(cx - page_cx)
    dy = abs(cy - page_cy)

    if dx > third_w or dy > third_h:
        direction = ""
        if dx > third_w:
            direction += "right-heavy" if cx > page_cx else "left-heavy"
        if dy > third_h:
            direction += "bottom-heavy" if cy > page_cy else "top-heavy"
        issues.append({
            "level": "info", "category": "balance",
            "message": f"Visual center ({cx:.0f},{cy:.0f}) deviates from page center ({page_cx:.0f},{page_cy:.0f}) — {direction}.",
        })


def _check_density(plan: LayoutPlan, issues: list[dict]) -> None:
    for region in plan.regions:
        region_area = region.w * region.h
        if region_area <= 0:
            continue
        elem_area = sum(
            e.w * e.h for e in plan.elements
            if e.elem_id in region.elements
        )
        ratio = elem_area / region_area
        if ratio > 0.90:
            issues.append({
                "level": "warn", "category": "density",
                "message": f"Region '{region.region_id}' ({region.purpose}) at {ratio:.0%} fill — "
                           f"no room for decoration or breathing space.",
            })


def _check_alignment(plan: LayoutPlan, issues: list[dict]) -> None:
    for region in plan.regions:
        region_elems = [e for e in plan.elements if e.elem_id in region.elements]
        if len(region_elems) < 2:
            continue
        left_edges = sorted(e.x for e in region_elems)
        spread = left_edges[-1] - left_edges[0]
        if spread > 10:
            issues.append({
                "level": "info", "category": "alignment",
                "message": f"Region '{region.region_id}': left edges span {spread:.0f}pt "
                           f"(from {left_edges[0]:.0f} to {left_edges[-1]:.0f}) — "
                           f"consider uniform left alignment.",
            })


def _check_font_hierarchy(plan: LayoutPlan, issues: list[dict]) -> None:
    titles = []
    bodies = []
    for e in plan.elements:
        p = e.payload
        if not p or not p.text.strip():
            continue
        # 用语义样式名判断（builder._s 注入 payload.style_name），
        # 不再读恒为 None 的 p.role（2026-08 审查：旧版因此永不触发）
        style = (getattr(p, "style_name", "") or "").lower()
        if style in ("heading", "subtitle", "subheading"):
            titles.append((e.elem_id, p.font_size))
        else:
            bodies.append((e.elem_id, p.font_size))

    if not titles or not bodies:
        return

    min_title_sz = min(sz for _, sz in titles)
    violators = [(eid, sz) for eid, sz in bodies if sz >= min_title_sz]

    if violators:
        examples = ", ".join(f"{eid}({sz:.0f}pt)" for eid, sz in violators[:3])
        issues.append({
            "level": "warn",
            "category": "font_hierarchy",
            "message": (
                f"Font hierarchy broken: {len(violators)} body elements have font_size "
                f">= smallest title ({min_title_sz:.0f}pt). "
                f"Offenders: {examples}"
                f"{'...' if len(violators) > 3 else ''}. "
                f"Shrink body text or enlarge titles to restore hierarchy."
            ),
            "violator_count": len(violators),
            "min_title_pt": min_title_sz,
        })


def _check_font_size_variety(plan: LayoutPlan, issues: list[dict]) -> None:
    """Max 4 distinct font sizes per slide (power-design #7, Refactoring UI)."""
    sizes: set[float] = set()
    for e in plan.elements:
        p = e.payload
        if p and p.text.strip() and p.font_size:
            sizes.add(round(p.font_size, 1))
    if len(sizes) > 4:
        examples = sorted(sizes, reverse=True)
        issues.append({
            "level": "info", "category": "font_variety",
            "message": (
                f"{len(sizes)} distinct font sizes on this slide: {examples}. "
                f"Design guides cap at 4 (Refactoring UI / power-design). "
                f"Merge sizes into a 2-3 tier hierarchy."
            ),
            "font_sizes": sorted(examples, reverse=True),
        })


def _check_single_accent(plan: LayoutPlan, issues: list[dict],
                         theme: dict | None) -> None:
    """One accent color per slide (power-design #13, Tufte)."""
    if not theme:
        return
    accent_hex = theme.get("color_roles", {}).get("accent", "")
    if not accent_hex:
        return
    accent = tuple(int(accent_hex.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))

    accent_shapes = 0
    accent_boxes = 0
    for e in plan.elements:
        p = e.payload
        if not p:
            continue
        fc = getattr(p, "fill_color", None)
        if isinstance(fc, tuple) and len(fc) == 3 and fc == accent:
            accent_shapes += 1
        if isinstance(fc, tuple) and len(fc) == 3 and fc != accent and fc not in ((255, 255, 255),):
            accent_boxes += 1

    # Theme accent used more than twice as pure fills → accent dilution
    if accent_shapes > 2:
        issues.append({
            "level": "info", "category": "single_accent",
            "message": (
                f"Accent color #{accent_hex} used {accent_shapes} times as pure fill. "
                f"Reserve accent for ≤2 anchoring elements; use neutral surfaces for the rest."
            ),
            "accent_fill_count": accent_shapes,
        })
    # Multiple non-accent colored boxes → palette creep
    if accent_boxes >= 3:
        issues.append({
            "level": "info", "category": "single_accent",
            "message": (
                f"{accent_boxes} elements use non-accent fill colors. "
                f"Aim for one accent per slide (Tufte) — neutral surfaces + single accent."
            ),
            "extra_color_boxes": accent_boxes,
        })


def _check_visual_chunks(plan: LayoutPlan, issues: list[dict]) -> None:
    """3-5 visual chunks ideal, max 7±2 (power-design #3, Miller 1956)."""
    n = len(plan.elements)
    if n > 8:
        issues.append({
            "level": "info", "category": "visual_chunks",
            "message": (
                f"{n} elements on this slide — above the 5-8 chunk ideal. "
                f"Too many visual blocks fragments attention; group or remove some."
            ),
            "element_count": n,
        })
    elif n > 5:
        issues.append({
            "level": "info", "category": "visual_chunks",
            "message": (
                f"{n} elements — toward the upper limit of the 3-5 chunk ideal. "
                f"Fine if they group into few visual units."
            ),
            "element_count": n,
        })


def _check_edge_safe_zone(plan: LayoutPlan, issues: list[dict]) -> None:
    """5% edge safe-zone on all sides (power-design #5)."""
    page_w = plan.page_w
    page_h = plan.page_h
    if page_w <= 0 or page_h <= 0:
        return
    safe_x = page_w * 0.05
    safe_y = page_h * 0.05

    violations = []
    for e in plan.elements:
        if e.x < safe_x or e.y < safe_y:
            side = []
            if e.x < safe_x:
                side.append("left")
            if e.y < safe_y:
                side.append("top")
            violations.append((e.elem_id, side))
            continue
        if e.x + e.w > page_w - safe_x:
            violations.append((e.elem_id, ["right"]))
        elif e.y + e.h > page_h - safe_y:
            violations.append((e.elem_id, ["bottom"]))

    if violations:
        examples = ", ".join(f"{eid}({','.join(sides)})" for eid, sides in violations[:4])
        issues.append({
            "level": "info", "category": "edge_safe_zone",
            "message": (
                f"{len(violations)} element(s) touch the 5% edge safe-zone: {examples}. "
                f"Keep content ≥5% from edges for projection/title-safe."
            ),
            "violation_count": len(violations),
        })


def _check_color_ratio(plan: LayoutPlan, issues: list[dict]) -> None:
    """60-30-10 color rule: dominant ~60%, secondary ~30%, accent ~10%.
    Detects evenly-distributed color usage (classic AI cliché)."""
    elements = plan.elements
    if len(elements) < 3:
        return

    from collections import Counter
    color_usage: dict[str, float] = {}
    for e in elements:
        p = e.payload
        if not p:
            continue
        fc = getattr(p, 'fill_color', None)
        if fc is None:
            key = "transparent"
        elif isinstance(fc, tuple):
            key = f"#{fc[0]:02X}{fc[1]:02X}{fc[2]:02X}"
        else:
            key = str(fc)
        color_usage[key] = color_usage.get(key, 0) + e.w * e.h

    total = sum(color_usage.values())
    if total <= 0:
        return

    shares = sorted(color_usage.values(), reverse=True)
    n_colors = len(shares)

    # Evenly distributed colors → AI cliché
    if n_colors >= 4:
        avg_share = 1.0 / n_colors
        is_even = all(abs(s / total - avg_share) < 0.10 for s in shares[:n_colors])
        if is_even:
            issues.append({
                "level": "warn", "category": "color_ratio",
                "message": (
                    f"{n_colors} colors evenly distributed across the page. "
                    f"Aim for 60-30-10: one dominant color (~60%), one secondary (~30%), "
                    f"one accent (~10%). Even distribution reads as 'AI-generated template'."
                ),
                "n_colors": n_colors,
            })

    # No clear dominant (>50%)
    if n_colors >= 2 and shares and shares[0] / total < 0.50:
        issues.append({
            "level": "info", "category": "color_ratio",
            "message": (
                f"No dominant color (largest is {shares[0]/total:.0%}). "
                f"Pick a dominant color occupying ≥50% of visual area."
            ),
        })


# ═══════════════════════════════════════════════════════════════
# Anti-AI-template detection
# ═══════════════════════════════════════════════════════════════

def _check_anti_ai_cliches(plan: LayoutPlan, issues: list[dict],
                           theme_rules: list[str], theme: dict | None = None) -> None:
    """Detect patterns that scream 'AI-generated'. Theme-specific rules take priority
    over global defaults."""

    elements = plan.elements

    # ── Global defaults (always checked) ──

    # Check 1: Everything centered → classic AI layout
    if _all_elements_centered(plan):
        issues.append({
            "level": "warn", "category": "anti_ai",
            "message": (
                "All elements horizontally centered — this reads as generic AI template. "
                "Vary alignment: left-align text blocks, right-align images, create asymmetry."
            ),
            "rule": "no_center_everything",
        })

    # Check 2: No shapes at all → text-only, visually flat
    if _no_shapes(plan):
        issues.append({
            "level": "info", "category": "anti_ai",
            "message": (
                "No decorative shapes (divider, accent bar, icon) on this slide — "
                "looks text-only. Add ≥1 shape for visual anchoring."
            ),
            "rule": "at_least_one_shape",
        })

    # Check 3: All cards same radius → uniform, no variation
    # 但主题契约 cards_must_have_consistent_size 是正向要求——存在时跳过本检查，
    # 否则"遵守主题"反而被惩罚（2026-08 审查发现的规则打架）
    if "cards_must_have_consistent_size" not in theme_rules and _all_cards_uniform(plan):
        issues.append({
            "level": "info", "category": "anti_ai",
            "message": (
                "All cards have identical dimensions — reads as template fill. "
                "Vary card sizes or add one visually distinct element."
            ),
            "rule": "vary_card_sizes",
        })

    # ── Theme-specific rule checks — 注册表分派 ──
    # 未注册的规则字符串不再被静默忽略：builder 在主题加载时通过
    # unimplemented_rules() 显式报告（消灭拼写漂移，如
    # no_gradients_or_glows vs no_gradients_or_shadows）
    for rule in theme_rules:
        handler = ANTI_AI_RULE_REGISTRY.get(rule)
        if handler is None or handler == "structural":
            continue
        handler(plan, issues, theme)

    # Check: text_over_images_must_have_dark_overlay — engine can't verify this
    # (image rendering is Phase 3), so this rule is reported as unimplemented


# ── taste-skill port helpers ──

_EM_DASH_CHARS = ("—", "―")

def _iter_texts(plan):
    """Yield (elem, text) for every element carrying visible text."""
    for e in plan.elements:
        p = e.payload
        if p is None:
            continue
        t = (p.text or "").strip()
        if t:
            yield e, t
        cap = (p.caption or "").strip()
        if cap:
            yield e, cap

def _check_em_dash(plan: LayoutPlan, issues: list[dict]) -> None:
    for e, t in _iter_texts(plan):
        if any(c in t for c in _EM_DASH_CHARS):
            issues.append({
                "level": "warn", "category": "anti_ai",
                "message": f"'{e.elem_id}' contains an em-dash (—) — the #1 AI tell. "
                           f"Replace with a comma, period, or colon.",
                "rule": "no_em_dash_in_copy",
                "elem_id": e.elem_id,
            })
            return  # one warning per slide is enough

def _check_section_number_eyebrow(plan: LayoutPlan, issues: list[dict]) -> None:
    import re as _re
    for e, t in _iter_texts(plan):
        if len(t) > 40:  # only eyebrow-like short labels, not body lines
            continue
        if _re.match(r"^\s*(?:0?[0-9]{1,2})\s*[\/·\\.\-–─]\s*\S", t):
            issues.append({
                "level": "info", "category": "anti_ai",
                "message": f"'{e.elem_id}' uses a section-number eyebrow '{t[:30]}…' — "
                           f"reads as production-test template. Drop the number prefix.",
                "rule": "no_section_number_eyebrow",
                "elem_id": e.elem_id,
            })
            return

def _check_version_label(plan: LayoutPlan, issues: list[dict]) -> None:
    import re as _re
    for e, t in _iter_texts(plan):
        if _re.search(r"(?:v\d+\.\d+(?:\.\d+)?|\bver(?:sion)?\.?\s*\d)", t, _re.IGNORECASE):
            issues.append({
                "level": "warn", "category": "anti_ai",
                "message": f"'{e.elem_id}' carries a version label '{t[:40]}…' — "
                           f"fake-launch tell. Remove version numbers from deck copy.",
                "rule": "no_version_label_in_hero",
                "elem_id": e.elem_id,
            })
            return

def _check_shape_family(plan: LayoutPlan, issues: list[dict]) -> None:
    shapes = [e for e in plan.elements
              if e.payload and getattr(e.payload, "shape_id", "")]
    if len(shapes) < 3:
        return
    from collections import Counter
    families = Counter()
    for e in shapes:
        sid = e.payload.shape_id or ""
        if sid in ("rectangle", "rounded_rectangle", "oval"):
            families["rect"] += 1
        elif sid in ("hexagon", "pentagon", "diamond", "triangle", "chevron"):
            families["poly"] += 1
        elif sid in ("star", "sun", "pie", "donut", "wave", "plaque", "home", "cross"):
            families["iconic"] += 1
        else:
            families["other"] += 1
    if len(families) > 1 and max(families.values()) < len(shapes) - 1:
        majority = families.most_common(1)[0][0]
        issues.append({
            "level": "info", "category": "anti_ai",
            "message": f"{len(shapes)} shapes mixed across {len(families)} families — "
                       f"pick one geometric family (keep {majority}) for a consistent look.",
            "rule": "shape_family_consistency",
            "families": dict(families),
        })

_ROUNDED_SHAPES = {"oval", "rounded_rectangle", "pie", "donut", "sun", "plaque"}
_ANGULAR_SHAPES = {"rectangle", "triangle", "diamond", "hexagon", "pentagon",
                   "chevron", "parallelogram", "star", "cross", "up_arrow",
                   "down_arrow", "left_arrow", "right_arrow", "home", "wave"}

def _check_shape_types_limit(plan: LayoutPlan, issues: list[dict]) -> None:
    """iSlide shape law #1: ≤2 distinct shape types per slide. 3+ reads as visual noise."""
    from collections import Counter
    counts = Counter()
    for e in plan.elements:
        p = e.payload
        if not p or not getattr(p, "shape_id", ""):
            continue
        sid = p.shape_id or ""
        if sid == "rectangle":
            continue  # divider bars / plain cards are background structure, not decorative shapes
        counts[sid] += 1
    if len(counts) > 2:
        top = ", ".join(f"{sid}×{n}" for sid, n in counts.most_common())
        issues.append({
            "level": "warn", "category": "anti_ai",
            "message": f"{len(counts)} distinct shapes on this slide ({top}) — "
                       f"iSlide law says ≤2. Pick one family and reuse it.",
            "rule": "shape_types_max_2",
            "shape_counts": dict(counts),
        })


def _check_shape_style_mix(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """iSlide shape law #2: rounded + angular shapes never mix on one slide.
    rectangle 视为中性衬底（divider/底色条），不计入 angular——
    否则 box()(rounded) + divider()(rectangle) 的默认用法必然误报（2026-08 审查）。"""
    rounded = [e for e in plan.elements
               if e.payload and (e.payload.shape_id or "") in _ROUNDED_SHAPES]
    angular = [e for e in plan.elements
               if e.payload and (e.payload.shape_id or "") in _ANGULAR_SHAPES
               and (e.payload.shape_id or "") != "rectangle"]
    # 忽略 rectangle 作为 divider 衬底；纯装饰形状才计入
    if rounded and angular:
        issues.append({
            "level": "warn", "category": "anti_ai",
            "message": f"Rounded ({', '.join(e.payload.shape_id for e in rounded)}) and "
                       f"angular ({', '.join(e.payload.shape_id for e in angular)}) "
                       f"shapes on the same slide — pick one geometric style.",
            "rule": "shape_style_no_mix",
        })


def _check_single_accent_lock(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """Taste-skill single-accent lock — warning fires once per slide if fills look random.
    （原名 _check_single_accent，与 :204 的主题色检查同名互相覆盖——2026-08 审查修复）"""
    fills: dict[tuple, int] = {}
    for e in plan.elements:
        p = e.payload
        if not p or not p.fill_color:
            continue
        fills[p.fill_color] = fills.get(p.fill_color, 0) + 1
    if len(fills) <= 1:
        return
    top_count = max(fills.values())
    total = sum(fills.values())
    if total >= 4 and top_count / total < 0.6:
        top = sorted(fills.items(), key=lambda kv: -kv[1])[0][0]
        issues.append({
            "level": "warn", "category": "anti_ai",
            "message": f"{len(fills)} distinct fill colors on this slide "
                       f"(dominant {top} only {top_count}/{total}) — "
                       f"single-accent rule wants one surface color + one accent. "
                       f"Recolor minor fills to the dominant surface.",
            "rule": "single_accent_color_lock",
            "fill_counts": {str(k): v for k, v in fills.items()},
        })


def _check_accent_coverage(plan: LayoutPlan, issues: list[dict],
                           theme: dict | None = None) -> None:
    """60-30-10 / gold-usage rule: accent fill must stay ≤20% of filled area.
    Research (media.io black-gold guide): gold 5-15% reads 'premium'; beyond that it's 'flashy'."""
    from collections import Counter

    if not theme:
        return
    accent_hex = theme.get("color_roles", {}).get("accent", "")
    if not accent_hex:
        return
    accent = tuple(int(accent_hex.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))

    area_by_color: dict[tuple, float] = Counter()
    for e in plan.elements:
        p = e.payload
        if not p or not p.fill_color:
            continue
        # count only shape/box visible area, exclude dividers (near-zero height)
        if e.w * e.h < 50:
            continue
        area_by_color[p.fill_color] += e.w * e.h

    total = sum(area_by_color.values())
    if total <= 0:
        return

    accent_area = sum(v for c, v in area_by_color.items() if c == accent)
    accent_share = accent_area / total
    dominant_share = area_by_color.most_common(1)[0][1] / total

    if accent_share > 0.20:
        issues.append({
            "level": "warn", "category": "anti_ai",
            "message": (
                f"Accent color #{accent_hex} covers {accent_share:.0%} of filled area — "
                f"60-30-10 rule caps accent at ~10-15%. "
                f"Oversized accent reads as flashy; shrink accent shapes or swap to surface color."
            ),
            "rule": "accent_coverage_max_20pct",
            "accent_share": round(accent_share, 2),
            "dominant_share": round(dominant_share, 2),
        })
    elif dominant_share < 0.50 and len(area_by_color) >= 2:
        issues.append({
            "level": "info", "category": "anti_ai",
            "message": (
                f"No dominant surface color (largest {dominant_share:.0%} of filled area) — "
                f"aim for one surface ≥60% per 60-30-10."
            ),
            "rule": "accent_coverage_max_20pct",
            "dominant_share": round(dominant_share, 2),
        })


def _check_shape_anchor(plan: LayoutPlan, issues: list[dict]) -> None:
    """Every slide needs ≥1 large anchoring shape (8-15% of page); no scattered fragments."""
    from .types import ContentType
    page_area = plan.page_w * plan.page_h
    shapes = [
        (e, e.w * e.h) for e in plan.elements
        if e.content_type == ContentType.SHAPE and e.w * e.h > 0
    ]
    if not shapes:
        # handled by _no_shapes — don't double-report
        return

    large = [s for s in shapes if s[1] >= page_area * 0.08]
    if not large:
        largest = max(shapes, key=lambda s: s[1])
        largest_pct = largest[1] / page_area
        issues.append({
            "level": "warn", "category": "anti_ai",
            "message": (
                f"No anchoring shape — largest shape is only {largest_pct:.0%} of page "
                f"({largest[0].elem_id}). Research: 1-2 large shapes (8-15%) anchor a slide; "
                f"scattered <5% fragments read as noise. Make one shape dominant."
            ),
            "rule": "shape_size_anchor_rule",
            "largest_shape_pct": round(largest_pct, 2),
        })
    elif len(large) > 3:
        issues.append({
            "level": "info", "category": "anti_ai",
            "message": f"{len(large)} shapes ≥8% of page — visual competition. "
                       f"Research: one or two anchors per slide; pick one protagonist.",
            "rule": "shape_size_anchor_rule",
            "large_shape_count": len(large),
        })


# ── Anti-AI helper functions ──

def _all_elements_centered(plan: LayoutPlan) -> bool:
    """True if every text-bearing element's x-center is within ±5% of page center."""
    elements = [e for e in plan.elements if e.payload and e.payload.text.strip()]
    if len(elements) < 3:
        return False
    page_cx = plan.page_w / 2
    threshold = plan.page_w * 0.05
    return all(abs(e.x + e.w / 2 - page_cx) < threshold for e in elements)


def _no_shapes(plan: LayoutPlan) -> bool:
    """True if no pure-shape elements (divider, accent bar, icon) exist."""
    from .types import ContentType
    return not any(e.content_type == ContentType.SHAPE for e in plan.elements)


def _all_cards_uniform(plan: LayoutPlan) -> bool:
    """True if all textbox elements have near-identical dimensions."""
    boxes = [e for e in plan.elements
             if getattr(e, 'content_type', None) is not None
             and str(getattr(e, 'content_type', '')).endswith('TEXTBOX')]
    if len(boxes) < 3:
        return False
    ws = [b.w for b in boxes]
    hs = [b.h for b in boxes]
    w_range = max(ws) - min(ws)
    h_range = max(hs) - min(hs)
    return w_range < 10 and h_range < 10


# ═══════════════════════════════════════════════════════════════
# CJK-aware 词数统计 + 新检查器（2026-08 审查补齐）
# ═══════════════════════════════════════════════════════════════

def _word_count(text: str) -> int:
    """中英文混合词数：CJK/全角字符每字算一词，拉丁按空白分词。
    旧版 len(text.split()) 对中文整段只算 1 "词"，词数规则对中文失明。"""
    import unicodedata
    cjk = sum(1 for ch in text if unicodedata.east_asian_width(ch) in ("W", "F"))
    latin = 0
    for tok in text.split():
        if not all(unicodedata.east_asian_width(c) in ("W", "F") for c in tok):
            latin += 1
    return cjk + latin


def _check_max_bullets(limit: int):
    def _run(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
        n = sum(1 for e in plan.elements
                if e.payload and e.payload.text.strip().startswith("•"))
        if n > limit:
            issues.append({
                "level": "warn", "category": "anti_ai",
                "message": f"{n} bullets on this slide — theme recommends ≤{limit}. "
                           f"Split into multiple slides or use visual alternatives.",
                "rule": f"max_{limit}_bullets", "bullet_count": n,
            })
    return _run


def _check_max_words_30(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    n = sum(_word_count(e.payload.text) for e in plan.elements if e.payload)
    if n > 30:
        issues.append({
            "level": "warn", "category": "anti_ai",
            "message": f"{n} words (CJK chars count individually) on this slide — "
                       f"minimalist theme recommends ≤30.",
            "rule": "max_30_words", "word_count": n,
        })


def _check_max_elements_3(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    n = len(plan.elements)
    if n > 3:
        issues.append({
            "level": "info", "category": "anti_ai",
            "message": f"{n} elements on this slide — minimalist theme prefers ≤3.",
            "rule": "max_3_elements", "element_count": n,
        })


def _check_no_pure_text_colors(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    for e in plan.elements:
        p = e.payload
        if not p or not p.text.strip():
            continue
        fc = getattr(p, 'font_color', None)
        if fc in ((0, 0, 0), (0xFF, 0xFF, 0xFF)):
            issues.append({
                "level": "info", "category": "anti_ai",
                "message": f"'{e.elem_id}' uses pure {'black' if fc == (0,0,0) else 'white'} text. "
                           f"Use near-black (#1A1A1A) or near-white (#F0F0F0) instead.",
                "rule": "no_pure_black_white", "elem_id": e.elem_id,
            })
            return


def _check_full_sentence_bullets(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    for e in plan.elements:
        p = e.payload
        if not p or not p.text.strip().startswith("•"):
            continue
        text = p.text.lstrip("• ").strip()
        wc = _word_count(text)
        if wc > 10:
            issues.append({
                "level": "info", "category": "anti_ai",
                "message": f"Bullet '{text[:40]}...' is {wc} words — "
                           f"corporate style prefers keyword bullets, not full sentences.",
                "rule": "no_full_sentence_bullets", "elem_id": e.elem_id,
            })
            return


def _check_no_bold_body(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    for e in plan.elements:
        p = e.payload
        if not p or not p.text.strip():
            continue
        style = (getattr(p, "style_name", "") or "").lower()
        if style in ("body", "listitem", "caption") and p.font_bold:
            issues.append({
                "level": "info", "category": "anti_ai",
                "message": f"'{e.elem_id}' is bold {style} text — minimalist theme forbids bold body.",
                "rule": "no_bold_body_text", "elem_id": e.elem_id,
            })
            return


def _check_never_decorative_shapes(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    from .types import ContentType
    for e in plan.elements:
        if e.content_type == ContentType.SHAPE and (not e.payload or not e.payload.text.strip()):
            issues.append({
                "level": "warn", "category": "anti_ai",
                "message": f"Decorative shape '{e.elem_id}' found — minimalist theme forbids "
                           f"decoration; keep only content.",
                "rule": "never_use_decorative_shapes", "elem_id": e.elem_id,
            })
            return


def _check_no_decorative_shapes_on_data_area(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """no_decorative_shapes_on_data_area：数据区（含 table/image/chart 的 region）不放纯装饰 shape。"""
    from .types import ContentType
    data_regions = {e.region_id for e in plan.elements
                    if e.content_type in (ContentType.TABLE, ContentType.IMAGE, ContentType.CHART)}
    if not data_regions:
        return
    for e in plan.elements:
        if e.content_type == ContentType.SHAPE and e.region_id in data_regions \
           and (not e.payload or not e.payload.text.strip()):
            issues.append({
                "level": "info", "category": "anti_ai",
                "message": f"Decorative shape '{e.elem_id}' sits in data region '{e.region_id}' — "
                           f"academic theme wants data areas free of decoration.",
                "rule": "no_decorative_shapes_on_data_area", "elem_id": e.elem_id,
            })
            return


def _check_leave_half_empty(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    total = plan.page_w * plan.page_h
    if total <= 0:
        return
    occupied = sum(e.w * e.h for e in plan.elements) / total
    if occupied > 0.5:
        issues.append({
            "level": "warn", "category": "anti_ai",
            "message": f"Content occupies {occupied:.0%} of page — minimalist theme wants "
                       f"≥50% empty. Remove elements, don't rearrange them.",
            "rule": "leave_half_page_empty", "occupied": round(occupied, 2),
        })


def _check_key_numbers(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """key_numbers_must_be_large_and_bold：纯数字/百分比文本（关键数字）应 ≥24pt 加粗。"""
    import re as _re
    for e in plan.elements:
        p = e.payload
        if not p:
            continue
        t = p.text.strip()
        if not t or not _re.fullmatch(r"[\d.,%‰x×+\-–—/]+\s*[a-zA-Z%‰]*", t):
            continue
        if len(t) > 12:  # 长串数字更可能是数据表内容而非关键数字
            continue
        if p.font_size < 24 or not p.font_bold:
            issues.append({
                "level": "info", "category": "anti_ai",
                "message": f"Key number '{t}' rendered at {p.font_size:.0f}pt"
                           f"{' non-bold' if not p.font_bold else ''} — "
                           f"corporate theme wants key numbers ≥24pt bold.",
                "rule": "key_numbers_must_be_large_and_bold", "elem_id": e.elem_id,
            })
            return


def _check_minimize_text(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """minimize_text_count_per_slide：tech 主题倾向少文字 — 每页总字符数超阈值提醒。"""
    total_chars = sum(len((e.payload.text or "").strip()) for e in plan.elements
                      if e.payload and e.payload.text.strip())
    if total_chars > 180:
        issues.append({
            "level": "info", "category": "anti_ai",
            "message": f"{total_chars} chars on this slide — tech product theme prefers "
                       f"minimal text. Split or trim.",
            "rule": "minimize_text_count_per_slide", "char_count": total_chars,
        })


def _check_one_hero(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """one_hero_element_per_slide：>15% 页面面积的视觉主体每页至多一个。"""
    page_area = plan.page_w * plan.page_h
    if page_area <= 0:
        return
    heroes = [e for e in plan.elements if e.w * e.h > page_area * 0.15]
    if len(heroes) > 1:
        issues.append({
            "level": "info", "category": "anti_ai",
            "message": f"{len(heroes)} hero elements (>15% page each) — "
                       f"tech theme wants ONE protagonist per slide.",
            "rule": "one_hero_element_per_slide",
            "hero_ids": [e.elem_id for e in heroes],
        })


def _check_no_rounded_cards(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """no_rounded_cards（圆角卡禁令，academic/tech 共用）。
    （旧版注释谎称"engine can't read shape_id"——payload.shape_id 一直可读）"""
    for e in plan.elements:
        p = e.payload
        if p and (p.shape_id or "") in ("rounded_rectangle", "oval"):
            issues.append({
                "level": "info", "category": "anti_ai",
                "message": f"'{e.elem_id}' is a rounded card ({p.shape_id}) — theme forbids them; "
                           f"use sharp rectangles (b.box() auto-applies swiss no-rounding).",
                "rule": "no_rounded_cards", "elem_id": e.elem_id,
            })
            return


def _check_captions_numbered(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """captions_must_be_numbered：图片说明应以编号开头（如 'Figure 1.' / '图1'）。"""
    import re as _re
    for e in plan.elements:
        p = e.payload
        if not p:
            continue
        cap = (p.caption or "").strip()
        if cap and not _re.match(r"^(figure|fig\.|图|表)?\s*\d+", cap, _re.IGNORECASE):
            issues.append({
                "level": "info", "category": "anti_ai",
                "message": f"Caption '{cap[:30]}' is not numbered — academic theme requires "
                           f"'Figure N.' style captions (engine auto-numbers when caption='').",
                "rule": "captions_must_be_numbered", "elem_id": e.elem_id,
            })
            return


def _check_data_sources_cited(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """data_sources_must_be_cited：含表格/图片的数据页应有来源标注。"""
    from .types import ContentType
    has_data = any(e.content_type in (ContentType.TABLE, ContentType.IMAGE, ContentType.CHART)
                   for e in plan.elements)
    if not has_data:
        return
    import re as _re
    pat = _re.compile(r"来源|出处|数据来自|source|reference|参考文献|\[\d+\]", _re.IGNORECASE)
    for e in plan.elements:
        p = e.payload
        if p and p.text.strip() and pat.search(p.text):
            return
        if p and p.caption and pat.search(p.caption):
            return
    issues.append({
        "level": "info", "category": "anti_ai",
        "message": "Data/table/image present but no source citation found — "
                   "academic theme requires '来源: ...' or [n] references.",
        "rule": "data_sources_must_be_cited",
    })


def _check_image_high_res(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """image_must_be_high_res：图片像素密度 < ~110dpi（px/pt < 1.5）→ 警告。"""
    import os
    from .types import ContentType
    for e in plan.elements:
        p = e.payload
        if e.content_type != ContentType.IMAGE or not p or not p.image_path:
            continue
        if not os.path.isfile(p.image_path):
            continue
        try:
            from PIL import Image
            iw, ih = Image.open(p.image_path).size
        except Exception:
            continue
        if e.w <= 0 or e.h <= 0:
            continue
        ppi = min(iw / e.w, ih / e.h)
        if ppi < 1.5:
            issues.append({
                "level": "warn", "category": "anti_ai",
                "message": f"Image '{e.elem_id}' is {iw}×{ih}px over {e.w:.0f}×{e.h:.0f}pt "
                           f"(~{ppi*72:.0f}dpi) — below print quality. Use higher resolution.",
                "rule": "image_must_be_high_res", "elem_id": e.elem_id,
            })
            return


def _check_grid_alignment_perfect(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """ensure_perfect_alignment_in_grid：>3 条不同的左边缘线 → 网格失控。"""
    edges = {round(e.x / 4) for e in plan.elements}  # 4pt 容差合并
    if len(edges) > 3:
        issues.append({
            "level": "info", "category": "anti_ai",
            "message": f"{len(edges)} distinct left-edge positions — corporate grid wants ≤3 "
                       f"alignment columns. Realign elements to a shared grid.",
            "rule": "ensure_perfect_alignment_in_grid", "edge_count": len(edges),
        })


def _check_no_grid_layouts(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """no_grid_layouts：minimalist 禁网格——元素高度对齐到共享网格 → 提示。"""
    if len(plan.elements) < 3:
        return
    xs = {round(e.x / 8) for e in plan.elements}
    if len(xs) <= 2:  # 元素挤在少数几条垂直线 → 网格感
        issues.append({
            "level": "info", "category": "anti_ai",
            "message": f"Elements align to {len(xs)} vertical lines — reads as a grid. "
                       f"Minimalist theme wants asymmetric, off-grid placement.",
            "rule": "no_grid_layouts", "edge_count": len(xs),
        })


def _check_allow_asymmetric(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """allow_asymmetric_placement：minimalist 允许不对称——过度对称/居中 → 提示。"""
    if len(plan.elements) < 2:
        return
    centers_x = [e.x + e.w / 2 for e in plan.elements]
    page_cx = plan.page_w / 2
    sym = sum(1 for cx in centers_x if abs(cx - page_cx) < 12)
    if sym >= max(2, len(plan.elements) * 0.7):
        issues.append({
            "level": "info", "category": "anti_ai",
            "message": f"{sym}/{len(plan.elements)} elements centered on the vertical axis — "
                       f"too symmetric for minimalist theme. Off-center for asymmetry.",
            "rule": "allow_asymmetric_placement", "centered": sym,
        })


def _check_avoid_white_bg(plan: LayoutPlan, issues: list[dict], theme: dict | None = None) -> None:
    """avoid_white_background：主题本身为浅底时被覆盖回浅色 → 提醒。"""
    if not theme:
        return
    bg_hex = (theme.get("color_roles", {}) or {}).get("bg", "")
    if not bg_hex:
        return
    try:
        from .color_utils import hex_to_rgb, luminance_L
        if luminance_L(hex_to_rgb(bg_hex)) > 90:
            issues.append({
                "level": "warn", "category": "anti_ai",
                "message": f"Slide bg {bg_hex} is near-white — tech theme requires a dark field.",
                "rule": "avoid_white_background",
            })
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 反 AI 规则注册表 — themes.json 声明的每条规则必须在此登记：
#   callable      → 每页执行的检查器 (plan, issues, theme) -> None
#   "structural"  → 引擎结构性保证（渲染器只做纯色填充/无渐变无阴影/无 deck 级执行点）
#   未登记        → builder 在主题加载时通过 unimplemented_rules() 显式报告
# ═══════════════════════════════════════════════════════════════

ANTI_AI_RULE_REGISTRY: dict[str, object] = {
    # 结构性保证（渲染器能力边界内不可能违反）
    "no_gradients_or_glows": "structural",       # 渲染器只做 solid fill，无渐变通道
    "no_gradients_or_shadows": "structural",     # 同上（修正 themes.json 的拼写漂移）
    "no_same_layout_all_slides": "structural",   # deck 级检查：builder._check_repeated_layout
    # 可执行检查器
    "no_more_than_5_bullets_per_slide": _check_max_bullets(5),
    "no_bullet_lists_over_3_items": _check_max_bullets(3),
    "text_must_be_under_30_words_per_slide": _check_max_words_30,
    "no_more_than_3_elements_per_slide": _check_max_elements_3,
    "no_pure_white_or_pure_black_text": _check_no_pure_text_colors,
    "no_pure_black_pure_white": _check_no_pure_text_colors,
    "avoid_full_sentences_in_bullets": _check_full_sentence_bullets,
    "no_em_dash_in_copy": lambda p, i, t=None: _check_em_dash(p, i),
    "no_section_number_eyebrow": lambda p, i, t=None: _check_section_number_eyebrow(p, i),
    "no_version_label_in_hero": lambda p, i, t=None: _check_version_label(p, i),
    "shape_family_consistency": lambda p, i, t=None: _check_shape_family(p, i),
    "single_accent_color_lock": _check_single_accent_lock,
    "accent_coverage_max_20pct": _check_accent_coverage,
    "shape_size_anchor_rule": lambda p, i, t=None: _check_shape_anchor(p, i),
    "shape_types_max_2": lambda p, i, t=None: _check_shape_types_limit(p, i),
    "shape_style_no_mix": _check_shape_style_mix,
    "no_bold_body_text": _check_no_bold_body,
    "never_use_decorative_shapes": _check_never_decorative_shapes,
    "leave_half_page_empty": _check_leave_half_empty,
    "key_numbers_must_be_large_and_bold": _check_key_numbers,
    "one_hero_element_per_slide": _check_one_hero,
    "no_rounded_cards": _check_no_rounded_cards,
    "no_decorative_shapes_on_data_area": _check_no_decorative_shapes_on_data_area,
    "captions_must_be_numbered": _check_captions_numbered,
    "data_sources_must_be_cited": _check_data_sources_cited,
    "image_must_be_high_res": _check_image_high_res,
    "ensure_perfect_alignment_in_grid": _check_grid_alignment_perfect,
    "avoid_white_background": _check_avoid_white_bg,
    "minimize_text_count_per_slide": _check_minimize_text,
    "no_grid_layouts": _check_no_grid_layouts,
    "allow_asymmetric_placement": _check_allow_asymmetric,
    "use_gradient_overlay_for_image_readability": "structural",  # 渲染器不做渐变遮罩
    "text_over_images_must_have_dark_overlay": "structural",     # 无图叠加渲染通道
    # cards_must_have_consistent_size 是正向契约（ suppresses vary_card_sizes），非检查器
    "cards_must_have_consistent_size": "structural",
}

def unimplemented_rules(theme_rules: list[str]) -> list[str]:
    """返回主题声明了但注册表中没有的规则——显式报告，不再静默忽略。"""
    return [r for r in theme_rules if r not in ANTI_AI_RULE_REGISTRY]
