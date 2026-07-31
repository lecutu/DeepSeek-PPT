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
        role = getattr(p, 'role', None)
        role_name = role.name if hasattr(role, 'name') else str(role or '')
        if 'TITLE' in role_name.upper() or 'HEADING' in role_name.upper():
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
    if _all_cards_uniform(plan):
        issues.append({
            "level": "info", "category": "anti_ai",
            "message": (
                "All cards have identical dimensions — reads as template fill. "
                "Vary card sizes or add one visually distinct element."
            ),
            "rule": "vary_card_sizes",
        })

    # ── Theme-specific rule checks ──
    if "no_gradients_or_glows" in theme_rules:
        pass  # Engine already enforces this — no-op at composition level

    if "no_rounded_cards" in theme_rules:
        pass  # Shape choice is AI-level decision, engine can't read shape_id here

    if "no_more_than_5_bullets_per_slide" in theme_rules:
        bullet_count = sum(1 for e in elements
                          if e.payload and e.payload.text.strip().startswith("•"))
        if bullet_count > 5:
            issues.append({
                "level": "warn", "category": "anti_ai",
                "message": f"{bullet_count} bullets on this slide — "
                           f"corporate consulting theme recommends ≤5.",
                "rule": "max_5_bullets",
                "bullet_count": bullet_count,
            })

    if "text_must_be_under_30_words_per_slide" in theme_rules:
        word_count = sum(
            len(e.payload.text.split()) if e.payload else 0
            for e in elements
        )
        if word_count > 30:
            issues.append({
                "level": "warn", "category": "anti_ai",
                "message": f"{word_count} words on this slide — "
                           f"minimalist creative theme recommends ≤30.",
                "rule": "max_30_words",
                "word_count": word_count,
            })

    if "no_more_than_3_elements_per_slide" in theme_rules:
        if len(elements) > 3:
            issues.append({
                "level": "info", "category": "anti_ai",
                "message": f"{len(elements)} elements on this slide — "
                           f"minimalist creative theme prefers ≤3.",
                "rule": "max_3_elements",
                "element_count": len(elements),
            })

    if "no_bullet_lists_over_3_items" in theme_rules:
        bullet_count = sum(1 for e in elements
                          if e.payload and e.payload.text.strip().startswith("•"))
        if bullet_count > 3:
            issues.append({
                "level": "warn", "category": "anti_ai",
                "message": f"{bullet_count} bullets — tech product theme prefers ≤3. "
                           f"Split into multiple slides or use visual alternatives.",
                "rule": "max_3_bullets",
                "bullet_count": bullet_count,
            })

    if "no_pure_white_or_pure_black_text" in theme_rules:
        for e in elements:
            p = e.payload
            if not p or not p.text.strip():
                continue
            fc = getattr(p, 'font_color', None)
            if fc in ((0, 0, 0), (0xFF, 0xFF, 0xFF)):
                issues.append({
                    "level": "info", "category": "anti_ai",
                    "message": f"'{e.elem_id}' uses pure {'black' if fc == (0,0,0) else 'white'} text. "
                               f"Use near-black (#1A1A1A) or near-white (#F0F0F0) instead.",
                    "rule": "no_pure_black_white",
                    "elem_id": e.elem_id,
                })
                break  # One warning per slide is enough

    if "no_pure_black_pure_white" in theme_rules:
        for e in elements:
            p = e.payload
            if not p:
                continue
            fc = getattr(p, 'font_color', None)
            fill = getattr(p, 'fill_color', None)
            if fc in ((0, 0, 0), (0xFF, 0xFF, 0xFF)):
                clr = "black" if fc == (0, 0, 0) else "white"
                issues.append({
                    "level": "info", "category": "anti_ai",
                    "message": f"'{e.elem_id}' uses pure {clr}. "
                               f"Minimalist theme avoids extremes — use muted tones.",
                    "rule": "no_pure_extremes",
                    "elem_id": e.elem_id,
                })
                break

    # Check: avoid_full_sentences_in_bullets
    if "avoid_full_sentences_in_bullets" in theme_rules:
        for e in elements:
            p = e.payload
            if not p or not p.text.strip().startswith("•"):
                continue
            text = p.text.lstrip("• ").strip()
            word_count = len(text.split())
            if word_count > 10:
                issues.append({
                    "level": "info", "category": "anti_ai",
                    "message": f"Bullet '{text[:40]}...' is {word_count} words — "
                               f"corporate style prefers keyword bullets, not full sentences.",
                    "rule": "no_full_sentence_bullets",
                    "elem_id": e.elem_id,
                })
                break

    # Check: text_over_images_must_have_dark_overlay — engine can't verify this
    # (image rendering is Phase 3), so this rule is advisory in CLAUDE.md only

    # ── taste-skill port: hard-coded AI tells (all themes) ──

    # Check: em-dash complete ban — the single most-cited AI tell in copy
    if "no_em_dash_in_copy" in theme_rules:
        _check_em_dash(plan, issues)

    # Check: section-number eyebrows "01 / 02 / 03" — production-test AI tell
    if "no_section_number_eyebrow" in theme_rules:
        _check_section_number_eyebrow(plan, issues)

    # Check: version labels in hero/footer ("v0.2.0 — ...") — fake-launch tell
    if "no_version_label_in_hero" in theme_rules:
        _check_version_label(plan, issues)

    # Check: shape-family consistency lock — one geometric family per deck, no odd-one-out
    if "shape_family_consistency" in theme_rules:
        _check_shape_family(plan, issues)

    # Check: single-accent lock — any fill/font outside palette breaks the 60-30-10 read
    if "single_accent_color_lock" in theme_rules:
        _check_single_accent(plan, issues, theme_rules)

    # ── research-driven additions ──

    # Check: accent coverage — accent color must be a small 5-15% accent, not 20%+ of the page
    if "accent_coverage_max_20pct" in theme_rules:
        _check_accent_coverage(plan, issues, theme)

    # Check: at least one large shape anchors the slide (no scattered fragments)
    if "shape_size_anchor_rule" in theme_rules:
        _check_shape_anchor(plan, issues)

    # Check: ≤2 distinct shape types per slide — 3+ reads as visual noise (iSlide shape law #1)
    if "shape_types_max_2" in theme_rules:
        _check_shape_types_limit(plan, issues)

    # Check: rounded + angular shapes never mix on one slide (iSlide shape law #2)
    if "shape_style_no_mix" in theme_rules:
        _check_shape_style_mix(plan, issues)


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


def _check_shape_style_mix(plan: LayoutPlan, issues: list[dict]) -> None:
    """iSlide shape law #2: rounded + angular shapes never mix on one slide."""
    rounded = [e for e in plan.elements
               if e.payload and (e.payload.shape_id or "") in _ROUNDED_SHAPES]
    angular = [e for e in plan.elements
               if e.payload and (e.payload.shape_id or "") in _ANGULAR_SHAPES]
    # 忽略 rectangle 作为 divider 衬底；纯装饰形状才计入
    if rounded and angular:
        issues.append({
            "level": "warn", "category": "anti_ai",
            "message": f"Rounded ({', '.join(e.payload.shape_id for e in rounded)}) and "
                       f"angular ({', '.join(e.payload.shape_id for e in angular)}) "
                       f"shapes on the same slide — pick one geometric style.",
            "rule": "shape_style_no_mix",
        })


def _check_single_accent(plan: LayoutPlan, issues: list[dict], theme_rules: list[str]) -> None:
    """Taste-skill single-accent lock — warning fires once per slide if fills look random."""
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
