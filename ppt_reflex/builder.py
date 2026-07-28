"""
ppt_reflex/builder.py — Sole AI entry point. All engine capabilities exposed here, pure interface zero engine concepts.

from ppt_reflex.builder import PPTBuilder, load_style_presets, save_style_presets, list_style_presets, list_archetypes, get_archetype
from ppt_reflex.grid.templates import list_templates

# Agent workflow: browse lightweight catalogs → user picks → builder loads only what's needed

print(list_templates())       # [{id, name, description, bg_hex, accent_hex, ...}, ...] — 6 entries
print(list_style_presets())   # [{id, display_name, mood, theme}, ...]                   — 6 entries
print(list_archetypes())      # [{id, name, description, guide}, ...]                    — 12 entries

# User picks → builder instantiates ONLY the chosen template + style:
builder = PPTBuilder(template="academic", style="academic_rigorous")
# ^ get_template("academic") instantiates ONE TemplateProfile (cached after first access)
# ^ _load_single_style_preset("academic_rigorous") reads JSON but discards other 5 presets

builder.add_slide("Cover",
    regions=[("r1", 100,80,760,380)],
    elements=[builder.title("Title"), builder.text("Body", style="Body")],
)
result = builder.build("out.pptx")

# Style preset management (for config editing, not for generation)
presets = load_style_presets()           # read full config — use this to edit
p = presets["academic_rigorous"]         # get one preset
p["color_override"]["bg"] = "#FFFDF5"    # change background
save_style_presets(presets)              # persist
"""

from __future__ import annotations
import os, tempfile, time, math, json, hashlib
from dataclasses import dataclass, field

from ppt_reflex.grid import (
    GridCanvas, GridConfig, ContentType, ElementPayload, Verdict,
    LayoutPlan, Region, Phase1Element, DecoIntent,
    execute_phase1, execute_phase2, global_composition_check,
)
from ppt_reflex.grid.templates import get_template, TemplateProfile
from ppt_reflex.grid.aesthetics import AestheticsEngine, AestheticViolation, ElemStyle
from ppt_reflex.grid.archetypes import get_archetype, list_archetypes, get_layout_policy, LayoutPolicy
from ppt_reflex.grid.serializer import _render_image, _render_payload  # contain-fit rendering
from ppt_reflex.diff_log import DiffLog  # snapshot-based mutation trace, session lifetime
from ppt_reflex.roundtrip_check import check_overflow  # reopen saved PPTX and verify text fits
from ppt_reflex.color_triangulator import check_slide as tri_check_slide  # bg↔text↔fill color triangle

# ── Style presets path ──
_PRESETS_PATH = os.path.join(os.path.dirname(__file__), "style_presets.json")


def load_style_presets() -> dict:
    """Read style presets from disk. Returns full dict with meta + presets. Modify then call save_style_presets()."""
    with open(_PRESETS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_style_presets(data: dict) -> None:
    """Save style presets to disk. Call load->modify->save."""
    with open(_PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_style_presets() -> list[dict]:
    """Lightweight preset list for AI style selection. Each entry: id+display_name+mood+theme. No full color/shape data."""
    data = load_style_presets()
    return [
        {"id": pid, "display_name": p["display_name"], "mood": p["mood"], "theme": p["theme"]}
        for pid, p in data.get("presets", {}).items()
    ]


def _load_single_style_preset(style_id: str) -> dict | None:
    """Load ONLY one style preset from JSON — reads the file but discards all other presets.

    Avoids loading full 6-preset JSON into LLM context. Returns the single preset dict or None.
    """
    data = load_style_presets()
    return data.get("presets", {}).get(style_id)


# ── WCAG luminance ──
def _lum(rgb: tuple) -> float:
    def f(c): s = c/255.0; return s/12.92 if s <= 0.04045 else ((s+0.055)/1.055)**2.4
    return 0.2126*f(rgb[0]) + 0.7152*f(rgb[1]) + 0.0722*f(rgb[2])

def _is_dark(rgb: tuple) -> bool:
    return _lum(rgb) < 0.25

def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

def _rgb_to_hex(rgb: tuple) -> str:
    """RGB tuple -> hex string (no # prefix), for AestheticsEngine."""
    return f"{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"

# ── Style table ──
STYLE = {
    "Heading":    dict(font_size=28, font_bold=True,  font_color=(0x1A,0x1A,0x2E), alignment="CENTER"),
    "Subtitle":   dict(font_size=18, font_color=(0x55,0x55,0x77), alignment="CENTER"),
    "Body":       dict(font_size=14, font_color=(0x33,0x33,0x44), font_name="Microsoft YaHei"),
    "Subheading": dict(font_size=16, font_bold=True,  font_color=(0x1B,0x3A,0x5C)),
    "Caption":    dict(font_size=10, font_color=(0x88,0x88,0x99)),
    "Footer":     dict(font_size=8,  font_color=(0xAA,0xAA,0xBB), alignment="CENTER"),
    "ListItem":   dict(font_size=13, font_color=(0x33,0x33,0x44), font_name="Microsoft YaHei"),
    "Emphasis":   dict(font_size=14, font_bold=True,  font_color=(0xC0,0x39,0x2B)),
}

# ── Built-in shape library ──
SHAPES = {
    "rounded_rectangle": "ROUNDED_RECTANGLE", "rectangle": "RECTANGLE",
    "oval": "OVAL", "parallelogram": "PARALLELOGRAM",
    "diamond": "DIAMOND", "chevron": "CHEVRON",
    "pentagon": "PENTAGON", "hexagon": "HEXAGON",
    "up_arrow": "UP_ARROW", "down_arrow": "DOWN_ARROW",
    "left_arrow": "LEFT_ARROW", "right_arrow": "RIGHT_ARROW",
    "star": "STAR_5_POINT", "triangle": "ISOSCELES_TRIANGLE",
    "home": "HOME_PLATE", "cross": "PLUS",
    "pie": "PIE", "wave": "WAVE", "donut": "DONUT",
    "plaque": "PLAQUE", "sun": "SUN",
}

# ── P0-①: diagnostic aggregation constants ──
_PHASE_ORDER = ["0.5", "1", "2", "2.5", "aesthetics", "3.0", "freeze", "pre", "rt"]
_KIND_BATCH_THRESHOLD = 5   # collapse when >=5 warnings share same kind
_WARN_CAP = 15              # max warnings in aggregated output
_INFO_CAP = 5               # max info diagnostics in aggregated output


# ── Internal spec ──
@dataclass
class _Spec:
    elem_id: str; style: str; text: str = ""; region: str = "main"
    ctype: str = "text"; fill_mode: str = "stack"
    pw: float|None = None; ph: float|None = None
    fill_color: tuple|None = None; shape_id: str = ""
    image_path: str = ""; margin: float = 6.0
    fit_mode: str = "fit"      # fit | fill | crop_center — fit=contain, no crop
    allow_upscale: bool = False # small images stay original size
    layout_mode: str = ""      # hero_top | hero_right | hero_left | center_float | small_inline | grid_2x2 | grid_1x3
    caption: str = ""          # Figure caption text
    # Phase1Element extended params (Fix #6)
    align_h: str = "left"
    allow_shrink: bool = False
    allow_wrap: bool = False
    arrow_slot: float = 48.0
    # P1-② table data — passed through _Spec → Phase1Element → render
    table_headers: list[str] = field(default_factory=list)
    table_rows: list[list[str]] = field(default_factory=list)

@dataclass
class _Arrow:
    deco_id: str; from_elem: str; to_elem: str; text: str = ""
    direction: str = "below"; color: tuple = (0x66,0x66,0x66); width: float = 1.5
    # Fix #8: full DecoIntent params
    margin_pt: float = 8.0
    text_font_size: float = 10.0
    text_color: tuple = (0x55,0x55,0x55)
    occlusion_check: bool = True

@dataclass
class _Slide:
    title: str = ""
    regions: list = field(default_factory=list)
    elements: list[_Spec] = field(default_factory=list)
    arrows: list[_Arrow] = field(default_factory=list)
    archetype_id: str = ""  # resolved archetype id for this slide (empty = manual)


class PPTBuilder:
    """Sole AI entry point. add_slide -> build. Engine + templates fully transparent."""

    def __init__(self, template: str = "academic", style: str|None = None,
                 page_w: float = 960, page_h: float = 540,
                 template_pptx: str|None = None):
        # Template: lazy — only this one gets instantiated
        self._t: TemplateProfile = get_template(template)
        self._style_preset: dict|None = None
        self._style_id: str|None = style
        self.pw, self.ph = page_w, page_h
        self._slides: list[_Slide] = []
        self._id = 0
        self._template_pptx = template_pptx
        self._style_body_font: str|None = None
        self._image_layout: dict|None = None
        self._layout_policy: LayoutPolicy = get_layout_policy(template)
        self.diff_log = DiffLog()
        self._pipeline_cache: dict[int, tuple] = {}

        if style:
            self._apply_style(style)

    def set_intent_scope(self, scope: dict):
        """Agent-declared intent scope: {"slide_ids":[2,3], "elem_ids":["box_3"]}.
        Used by DiffLog.scope_alert() to catch say-vs-do mismatch."""
        self.diff_log.set_intent_scope(scope)

    def _apply_style(self, style_id: str) -> None:
        """Load and apply a single style preset — only this one is loaded from JSON into memory."""
        preset = _load_single_style_preset(style_id)
        if not preset:
            return
        self._style_preset = preset
        c = preset["color_override"]
        fo = preset.get("font_override", {})
        overrides = dict(
            bg_hex=c.get("bg", self._t.bg_hex),
            text_hex=c.get("text_primary", self._t.text_hex),
            title_hex=c.get("text_primary", self._t.title_hex),
            accent_hex=c.get("accent", self._t.accent_hex),
            accent2_hex=c.get("warn", self._t.accent2_hex),
            gray_hex=c.get("text_secondary", self._t.gray_hex),
            dim_hex=c.get("surface", self._t.dim_hex),
            title_size=fo.get("scale_h1", self._t.title_size),
            body_size=fo.get("scale_body", self._t.body_size),
            caption_size=fo.get("scale_h2", self._t.caption_size),
            divider_color_hex=c.get("accent", self._t.divider_color_hex),
        )
        self._t = self._t.override(**overrides)
        self._style_body_font = fo.get("body_font")
        self._image_layout = preset.get("image_layout", None)

    # ── slide ──
    def add_slide(self, title: str = "", *, archetype: str|None = None,
                  regions: list|None = None,
                  elements: list|None = None, arrows: list|None = None) -> int:
        """Add a slide. If archetype is given, auto-resolve regions + auto-route elements via zone_map.

        Manual regions override archetype. Auto-routing only applies to elements without explicit region.
        """
        arch = None
        resolved_regions = regions

        if archetype:
            try:
                arch = get_archetype(archetype)
            except KeyError:
                # Unknown archetype — fall through to manual mode
                pass

        if arch and resolved_regions is None:
            # Apply LayoutPolicy insets to archetype regions
            inset = getattr(self._layout_policy, 'content_inset', 12)
            resolved_regions = []
            for r in arch.regions:
                name, x, y, w, h, z = r
                # Apply inset: shrink region by content_inset on all sides
                resolved_regions.append(
                    (name, x + inset, y + inset, w - 2*inset, h - 2*inset, z)
                )

        if resolved_regions is None:
            resolved_regions = [("main", 60, 60, 840, 420, 1)]

        # Auto-route elements via archetype zone_map
        routed_elements = []
        if arch and arch.zone_map and elements:
            for e in elements:
                if e.region and e.region != "main":
                    routed_elements.append(e)  # explicit region — skip auto-route
                    continue
                # Determine element type from _Spec fields
                etype = self._elem_type(e)
                target_zone = arch.zone_map.get(etype)
                if target_zone:
                    # Check if zone exists in resolved regions
                    zone_names = [r[0] for r in resolved_regions]
                    if target_zone in zone_names:
                        e.region = target_zone
                routed_elements.append(e)
        elif elements:
            routed_elements = list(elements)

        self._slides.append(_Slide(title, resolved_regions, routed_elements, arrows or [],
                                   archetype_id=arch.id if arch else ""))
        self._pipeline_cache.pop(len(self._slides) - 1, None)  # invalidate new slide slot
        return len(self._slides) - 1

    @staticmethod
    def _elem_type(e: _Spec) -> str:
        """Map _Spec → zone_map key. Uses ctype + style for accurate routing.

        Priority: ctype (deterministic) > style (hint). b.title()/bullet()/etc.
        all return ctype="text" — their style distinguishes them."""
        # ctype-first: these are unambiguous
        if e.ctype == "textbox":   return "box"
        if e.ctype == "shape":     return "shape"
        if e.ctype == "image":     return "image"
        if e.ctype == "table":     return "table"
        if e.ctype == "footer":    return "footer"

        # ctype="text" + style disambiguation
        if e.style == "Heading":   return "title"
        if e.style == "Subtitle":  return "subtitle"
        if e.style == "ListItem":  return "bullet"
        if e.style == "Caption":   return "text"
        # "Body"/"Emphasis"/"Subheading" → treated as generic text
        return "text"

    def fix_slide(self, slide_idx: int, title: str|None = None, *,
                  archetype: str|None = None,
                  regions: list|None = None,
                  elements: list|None = None,
                  arrows: list|None = None) -> int:
        """P1-①: modify an existing slide in-place. Returns slide_idx on success, -1 on bad index.

        Only the passed keyword arguments are changed — omitted args keep current values.
        If archetype is passed, auto-resolves regions + auto-routes elements (like add_slide)."""
        if slide_idx < 0 or slide_idx >= len(self._slides):
            return -1
        s = self._slides[slide_idx]
        if title is not None:
            s.title = title
        if archetype is not None:
            arch = get_archetype(archetype)
            s.archetype_id = arch.id
            s.regions = [(r[0], r[1], r[2], r[3], r[4],
                          r[5] if len(r) > 5 else slide_idx + 1)
                         for r in arch.regions]
            if elements is not None:
                for e in elements:
                    if e.region and e.region != "main":
                        continue
                    etype = PPTBuilder._elem_type(e)
                    target = arch.zone_map.get(etype)
                    if target and target in [r[0] for r in s.regions]:
                        e.region = target
        if regions is not None:
            s.regions = [(r[0], r[1], r[2], r[3], r[4],
                          r[5] if len(r) > 5 else slide_idx + 1)
                         for r in regions]
        if elements is not None:
            s.elements = elements
        if arrows is not None:
            s.arrows = arrows
        self._pipeline_cache.pop(slide_idx, None)
        return slide_idx

    def _spec_hash(self, spec: _Slide) -> str:
        """P1-①: structural fingerprint — same content → same hash, regardless of elem_id."""
        data = {"title": spec.title, "regions": spec.regions, "n_arrows": len(spec.arrows)}
        els = []
        for e in spec.elements:
            d = {"ctype": e.ctype, "text": e.text, "style": e.style, "region": e.region,
                 "pw": e.pw, "ph": e.ph, "fill_color": e.fill_color, "shape_id": e.shape_id,
                 "image_path": e.image_path, "layout_mode": e.layout_mode,
                 "table_headers": e.table_headers, "table_rows_len": len(e.table_rows) if e.table_rows else 0,
                 "align_h": e.align_h, "fill_mode": e.fill_mode}
            els.append(d)
        data["elements"] = els
        return hashlib.md5(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()

    def build_single_slide(self, slide_idx: int, prs=None) -> dict:
        """Build exactly one slide (for DeckPlanner harness). Returns per-slide diagnostics."""
        if slide_idx < 0 or slide_idx >= len(self._slides):
            return {"ok": False, "diagnostics": [{"kind": "invalid_index", "severity": "error",
                     "message": f"slide_idx {slide_idx} out of range [0, {len(self._slides)})"}]}
        spec = self._slides[slide_idx]
        plan = self._plan(spec)
        c = GridCanvas(GridConfig())
        c.checkpoint()

        self.diff_log.snap_before(plan, slide_idx)
        diags: list[dict] = []

        plan.validate(verbose=False)
        for d in plan.diagnostics:
            diags.append(_diag(slide_idx, "0.5", d))

        execute_phase1(plan, c)
        for d in plan.diagnostics:
            diags.append(_diag(slide_idx, "1", d))

        decos = execute_phase2(plan, c)
        for d in decos:
            if d.deco_type == "arrow" and d.x2:
                c.register_decoration(d.deco_id, "arrow", d.x1, d.y1, d.x2, d.y2,
                    line_color=d.style.get("line_color", (0x66,0x66,0x66)),
                    line_width_pt=d.style.get("line_width_pt", 1.5),
                    text=d.text, font_size=d.text_font_size, font_color=d.text_color)
            for w in d.occlusion_warnings:
                diags.append(_diag(slide_idx, "2", None, kind="arrow_occlusion",
                                   severity="warning", deco_id=d.deco_id, message=w))

        for ci in global_composition_check(plan):
            diags.append(_diag(slide_idx, "2.5", None, kind=ci.get("category","composition"),
                               severity=ci.get("level","info"), message=ci.get("message","")))

        ae_diags = self._run_aesthetics(c, plan)
        diags.extend(ae_diags)

        # P0-口②④: freeze → overflow check before render (single-slide path)
        from ppt_reflex.grid.text_metrics import check_overflow_2d
        for pe in plan.elements:
            p = pe.payload
            if not p or not p.text.strip():
                continue
            if pe.content_type not in (ContentType.TEXT, ContentType.TEXTBOX):
                continue
            v_auto_fit = not pe.height_is_locked
            h_auto_fit = not pe.width_is_locked
            issues = check_overflow_2d(
                p.text, p.font_size,
                box_w=pe.w, box_h=pe.h,
                line_spacing=p.line_spacing,
                v_auto_fit=v_auto_fit,
                h_auto_fit=h_auto_fit,
            )
            for iss in issues:
                severity = "warning" if pe.content_type == ContentType.TEXTBOX else iss["level"]
                diags.append({
                    "slide": slide_idx, "phase": "freeze",
                    "kind": iss["kind"],
                    "severity": severity,
                    "elem_id": pe.elem_id,
                    "message": iss["message"],
                })

        pv = c.pre_commit_validation()
        for err in pv.get("errors", []):
            diags.append(_diag(slide_idx, "pre", None, kind="validation_error", severity="error",
                               elem_id=err.get("owner_id",""), message=err.get("detail","")))
        for warn in pv.get("warnings", []):
            diags.append(_diag(slide_idx, "pre", None, kind="validation_warning", severity="warning",
                               elem_id=warn.get("owner_id",""), message=warn.get("detail","")))
        for adv in pv.get("advisories", []):
            diags.append(_diag(slide_idx, "pre", None, kind="advisory", severity="info",
                               elem_id=adv.get("owner_id",""), message=adv.get("detail","")))

        if prs is not None:
            _render_slide(prs, c, self._t, slide_index=slide_idx, total_slides=len(self._slides))
        self.diff_log.snap_after(plan, slide_idx)

        errs = [d for d in diags if d.get("severity") in ("error",)]
        warns = [d for d in diags if d.get("severity") in ("warning","warn")]
        return {"ok": len(errs) == 0, "diagnostics": diags,
                "summary": f"slide {slide_idx}: {len(diags)} issues ({len(errs)} errors, {len(warns)} warnings)",
                "roundtrip_ok": True}  # single-slide mode defers roundtrip to deck-level build()

    def build_stream(self, path: str|None = None):
        """分页流式构建 — 逐页 yield 诊断，AI 可以立即看到每页结果。

        用法：
            for slide_result in b.build_stream("out.pptx"):
                ok = slide_result["ok"]
                errs = [d for d in slide_result["diagnostics"] if d["severity"] == "error"]
                print(f"S{slide_result['slide']:02d}: {len(errs)} errors")
                if errs:
                    break  # 中断构建，只修这一页

        与 build() 的区别：
        - build() 一次性完成所有页 + roundtrip，返回 dict
        - build_stream() 逐页 yield，不阻塞等待全部完成
        - 第一个返回的是 {'type': 'start', ...} 元信息
        - 之后每个是 {'type': 'slide', ...} 单页诊断
        - 最后是 {'type': 'summary', ...} 总汇 (含 roundtrip)
        """
        from pptx import Presentation; from pptx.util import Pt
        if path is None:
            ts = int(time.time()); path = os.path.join(tempfile.gettempdir(), f"ppt_reflex_{ts}.pptx")

        if self._template_pptx and os.path.exists(self._template_pptx):
            prs = Presentation(self._template_pptx)
            while len(prs.slides) > 0:
                rId = prs.slides._sldIdLst[0].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                prs.part.drop_rel(rId)
                prs.slides._sldIdLst.remove(prs.slides._sldIdLst[0])
        else:
            prs = Presentation()
        prs.slide_width = Pt(self.pw); prs.slide_height = Pt(self.ph)
        total_slides = len(self._slides)

        yield {"type": "start", "total_slides": total_slides, "template": self._t.id, "style": self._style_id}

        all_diags: list[dict] = []
        for i, spec in enumerate(self._slides):
            slide_result = self.build_single_slide(i, prs=prs)
            all_diags.extend(slide_result.get("diagnostics", []))
            yield {**slide_result, "type": "slide", "slide": i, "slide_total": total_slides}

        prs.save(path)

        # P0-①: aggregate noisy diagnostics before returning
        aggregated_diags, agg_stats = _aggregate_diagnostics(all_diags)
        errs = [d for d in aggregated_diags if d.get("severity") in ("error",)]

        rt_results = check_overflow(path)
        for rt in rt_results:
            aggregated_diags.append(_diag(rt["slide"], "rt", None,
                                   kind=rt["kind"], severity=rt["severity"],
                                   message=rt["message"]))
        rt_errors = [rt for rt in rt_results if rt["severity"] == "error"]
        rt_warns = [rt for rt in rt_results if rt["severity"] == "warning"]

        diff_report = self.diff_log.diff()
        scope = self.diff_log.scope_alert()
        yield {
            "type": "summary",
            "path": path, "ok": len(errs) == 0 and len(rt_errors) == 0,
            "diagnostics": aggregated_diags,
            "raw_diagnostic_count": agg_stats["raw_count"],
            "collapsed": {"dedup": agg_stats["dedup"],
                          "batch": agg_stats["batch"],
                          "trimmed_warnings": agg_stats["trimmed_warnings"],
                          "trimmed_info": agg_stats["trimmed_info"]},
            "summary": f"{agg_stats['final_count']} issues ({agg_stats['errors']} errors, "
                       f"{agg_stats['warnings']} warnings) — "
                       f"({agg_stats['raw_count']} raw, "
                       f"-{agg_stats['dedup']} dedup, "
                       f"{agg_stats['batch']} batch-collapsed)",
            "template": self._t.id, "style": self._style_id,
            "diff": {
                "entries": len(diff_report.entries) if diff_report else 0,
                "changed_elem_ids": list(diff_report.changed_elem_ids) if diff_report else [],
            },
            "scope_alert": scope,
        }

    def build(self, path: str|None = None) -> dict:
        from pptx import Presentation; from pptx.util import Pt
        if path is None:
            ts = int(time.time()); path = os.path.join(tempfile.gettempdir(), f"ppt_reflex_{ts}.pptx")

        # Use external template PPTX as base if provided (inherits master/layouts)
        if self._template_pptx and os.path.exists(self._template_pptx):
            prs = Presentation(self._template_pptx)
            while len(prs.slides) > 0:
                rId = prs.slides._sldIdLst[0].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                prs.part.drop_rel(rId)
                prs.slides._sldIdLst.remove(prs.slides._sldIdLst[0])
        else:
            prs = Presentation()
        prs.slide_width = Pt(self.pw); prs.slide_height = Pt(self.ph)
        all_diags: list[dict] = []
        total_slides = len(self._slides)

        for i, spec in enumerate(self._slides):
            plan = self._plan(spec); c = GridCanvas(GridConfig()); c.checkpoint()

            # DiffLog: snap_before (entry — net change computed vs this baseline)
            self.diff_log.snap_before(plan, i)

            diags: list[dict] = []

            # Phase 0.5: region boundary validation
            plan.validate(verbose=False)
            for d in plan.diagnostics:
                diags.append(_diag(i, "0.5", d))

            # Phase 1: information layer layout
            execute_phase1(plan, c)
            for d in plan.diagnostics:
                diags.append(_diag(i, "1", d))

            # Phase 2: decoration layer resolution
            decos = execute_phase2(plan, c)
            for d in decos:
                if d.deco_type == "arrow" and d.x2:
                    c.register_decoration(d.deco_id, "arrow", d.x1, d.y1, d.x2, d.y2,
                        line_color=d.style.get("line_color", (0x66,0x66,0x66)),
                        line_width_pt=d.style.get("line_width_pt", 1.5),
                        text=d.text, font_size=d.text_font_size, font_color=d.text_color)
                for w in d.occlusion_warnings:
                    diags.append(_diag(i, "2", None, kind="arrow_occlusion", severity="warning",
                                       deco_id=d.deco_id, message=w))

            # Phase 2.5: global composition check
            for ci in global_composition_check(plan):
                diags.append(_diag(i, "2.5", None, kind=ci.get("category","composition"),
                                   severity=ci.get("level","info"), message=ci.get("message","")))

            ae_diags = self._run_aesthetics(c, plan)
            diags.extend(ae_diags)

            # Color triangle: bg ↔ text ↔ fill constraint system (Phase 3.0)
            tri_elems = []
            for pe in plan.elements:
                p = pe.payload
                if not p or not p.text.strip():
                    continue
                fc = p.font_color if p else (0xFF, 0xFF, 0xFF)
                fill = p.fill_color  # None → transparent
                tri_elems.append({
                    "elem_id": pe.elem_id,
                    "font_size": p.font_size if p else 14,
                    "font_bold": p.font_bold if p else False,
                    "font_color_rgb": fc,
                    "fill_color_rgb": fill,
                })
            tri_issues = tri_check_slide(tri_elems, self._t)
            for ti in tri_issues:
                diags.append({
                    "slide": i, "phase": "3.0", "kind": f"tri_{ti.edge.replace('↔','_')}",
                    "severity": ti.level, "elem_id": ti.elem_id,
                    "message": ti.message,
                })

            # P0-口②④: freeze → overflow check before render
            # Phase 1 locked coordinates (height_is_locked=True for stack/inline elements).
            # Aesthetics resolved final font_size. Freeze snapshots both, then 2D overflow
            # check reads the frozen state — same data renderer will use.
            # SHAPE_TO_FIT_TEXT cannot rescue overflow when layout has fixed the box dims.
            from ppt_reflex.grid.text_metrics import check_overflow_2d
            for pe in plan.elements:
                p = pe.payload
                if not p or not p.text.strip():
                    continue
                if pe.content_type not in (ContentType.TEXT, ContentType.TEXTBOX):
                    continue
                # v_auto_fit: SHAPE_TO_FIT_TEXT only actually grows if layout didn't lock height
                v_auto_fit = not pe.height_is_locked
                h_auto_fit = not pe.width_is_locked
                issues = check_overflow_2d(
                    p.text, p.font_size,
                    box_w=pe.w, box_h=pe.h,
                    line_spacing=p.line_spacing,
                    v_auto_fit=v_auto_fit,
                    h_auto_fit=h_auto_fit,
                )
                for iss in issues:
                    severity = "warning" if pe.content_type == ContentType.TEXTBOX else iss["level"]
                    diags.append({
                        "slide": i, "phase": "freeze",
                        "kind": iss["kind"],
                        "severity": severity,
                        "elem_id": pe.elem_id,
                        "message": iss["message"],
                    })

            # Fix #9: pre_commit_validation — bounds/overflow/role conflicts
            pv = c.pre_commit_validation()
            for err in pv.get("errors", []):
                diags.append(_diag(i, "pre", None, kind="validation_error", severity="error",
                                   elem_id=err.get("owner_id",""), message=err.get("detail","")))
            for warn in pv.get("warnings", []):
                diags.append(_diag(i, "pre", None, kind="validation_warning", severity="warning",
                                   elem_id=warn.get("owner_id",""), message=warn.get("detail","")))
            for adv in pv.get("advisories", []):
                diags.append(_diag(i, "pre", None, kind="advisory", severity="info",
                                   elem_id=adv.get("owner_id",""), message=adv.get("detail","")))

            # Fix #2: Render with smart layout selection
            _render_slide(prs, c, self._t, slide_index=i, total_slides=total_slides)

            # DiffLog: snap_after (exit — diff sees only net change, engine loop noise folded away)
            self.diff_log.snap_after(plan, i)

            all_diags.extend(diags)

        prs.save(path)
        errs = [d for d in all_diags if d.get("severity") in ("error",)]
        warns = [d for d in all_diags if d.get("severity") in ("warning","warn")]

        # Post-render roundtrip: reopen saved PPTX and verify every text box fits
        rt_results = check_overflow(path)
        for rt in rt_results:
            all_diags.append(_diag(rt["slide"], "rt", None,
                                   kind=rt["kind"], severity=rt["severity"],
                                   message=rt["message"]))
        rt_errors = [rt for rt in rt_results if rt["severity"] == "error"]
        rt_warns = [rt for rt in rt_results if rt["severity"] == "warning"]

        diff_report = self.diff_log.diff()
        scope = self.diff_log.scope_alert()

        # P0-①: aggregate noisy diagnostics before returning
        aggregated_diags, agg_stats = _aggregate_diagnostics(all_diags)
        errs = [d for d in aggregated_diags if d.get("severity") in ("error",)]

        return {"path": path, "ok": len(errs) == 0 and len(rt_errors) == 0,
                "diagnostics": aggregated_diags,
                "raw_diagnostic_count": agg_stats["raw_count"],
                "collapsed": {"dedup": agg_stats["dedup"],
                              "batch": agg_stats["batch"],
                              "trimmed_warnings": agg_stats["trimmed_warnings"],
                              "trimmed_info": agg_stats["trimmed_info"]},
                "summary": f"{agg_stats['final_count']} issues ({agg_stats['errors']} errors, "
                           f"{agg_stats['warnings']} warnings) — "
                           f"({agg_stats['raw_count']} raw, "
                           f"-{agg_stats['dedup']} dedup, "
                           f"{agg_stats['batch']} batch-collapsed, "
                           f"-{agg_stats['trimmed_warnings']} warn / -{agg_stats['trimmed_info']} info trimmed)",
                "template": self._t.id, "style": self._style_id,
                "diff": {
                    "entries": len(diff_report.entries) if diff_report else 0,
                    "changed_elem_ids": list(diff_report.changed_elem_ids) if diff_report else [],
                },
                "scope_alert": scope}

    def clear_diff_log(self):
        """User confirmed deck is done — wipe mutation trace."""
        self.diff_log.clear()

    # ── P1-①: incremental rebuild ──

    def rebuild(self, changed_slides: list[int], path: str|None = None) -> dict:
        """Only re-run pipeline for the given slide indices; others reuse pipelined plan+canvas.

        Call this after fix_slide() — much faster than build() for 1-2 slide edits.
        Uses _pipeline_cache which stores (hash, LayoutPlan, GridCanvas, diags) per slide.
        """
        from pptx import Presentation
        from pptx.util import Pt

        if path is None:
            ts = int(time.time())
            path = os.path.join(tempfile.gettempdir(), f"ppt_reflex_{ts}.pptx")

        changed: set[int] = set(changed_slides)
        total_slides = len(self._slides)
        all_diags: list[dict] = []

        if self._template_pptx and os.path.exists(self._template_pptx):
            prs = Presentation(self._template_pptx)
            while len(prs.slides) > 0:
                rId = prs.slides._sldIdLst[0].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                prs.part.drop_rel(rId)
                prs.slides._sldIdLst.remove(prs.slides._sldIdLst[0])
        else:
            prs = Presentation()
        prs.slide_width = Pt(self.pw)
        prs.slide_height = Pt(self.ph)

        for i, spec in enumerate(self._slides):
            h = self._spec_hash(spec)

            if i not in changed:
                cached_h, cached_plan, cached_canvas, cached_diags = self._pipeline_cache.get(i, (None, None, None, None))
                if cached_h == h and cached_plan is not None and cached_canvas is not None:
                    # Cache hit: reuse pipeline results, just re-render
                    _render_slide(prs, cached_canvas, self._t, slide_index=i, total_slides=total_slides)
                    all_diags.extend(cached_diags or [])
                    # Update cache with fresh slide XML
                    self._pipeline_cache[i] = (h, cached_plan, cached_canvas, cached_diags)
                    continue

            # Cache miss or changed slide → run full pipeline
            plan = self._plan(spec)
            c = GridCanvas(GridConfig())
            c.checkpoint()
            self.diff_log.snap_before(plan, i)

            diags: list[dict] = []

            plan.validate(verbose=False)
            for d in plan.diagnostics:
                diags.append(_diag(i, "0.5", d))

            execute_phase1(plan, c)
            for d in plan.diagnostics:
                diags.append(_diag(i, "1", d))

            decos = execute_phase2(plan, c)
            for d in decos:
                if d.deco_type == "arrow" and d.x2:
                    c.register_decoration(d.deco_id, "arrow", d.x1, d.y1, d.x2, d.y2,
                        line_color=d.style.get("line_color", (0x66, 0x66, 0x66)),
                        line_width_pt=d.style.get("line_width_pt", 1.5),
                        text=d.text, font_size=d.text_font_size, font_color=d.text_color)
                for w in d.occlusion_warnings:
                    diags.append(_diag(i, "2", None, kind="arrow_occlusion", severity="warning",
                                       deco_id=d.deco_id, message=w))

            for ci in global_composition_check(plan):
                diags.append(_diag(i, "2.5", None, kind=ci.get("category", "composition"),
                                   severity=ci.get("level", "info"), message=ci.get("message", "")))

            ae_diags = self._run_aesthetics(c, plan)
            diags.extend(ae_diags)

            tri_elems = []
            for pe in plan.elements:
                p = pe.payload
                if not p or not p.text.strip():
                    continue
                fc = p.font_color if p else (0xFF, 0xFF, 0xFF)
                fill = p.fill_color
                tri_elems.append({
                    "elem_id": pe.elem_id,
                    "font_size": p.font_size if p else 14,
                    "font_bold": p.font_bold if p else False,
                    "font_color_rgb": fc,
                    "fill_color_rgb": fill,
                })
            tri_issues = tri_check_slide(tri_elems, self._t)
            for ti in tri_issues:
                diags.append({
                    "slide": i, "phase": "3.0", "kind": f"tri_{ti.edge.replace('↔', '_')}",
                    "severity": ti.level, "elem_id": ti.elem_id,
                    "message": ti.message,
                })

            from ppt_reflex.grid.text_metrics import check_overflow_2d
            for pe in plan.elements:
                p = pe.payload
                if not p or not p.text.strip():
                    continue
                if pe.content_type not in (ContentType.TEXT, ContentType.TEXTBOX):
                    continue
                v_auto_fit = not pe.height_is_locked
                h_auto_fit = not pe.width_is_locked
                issues = check_overflow_2d(
                    p.text, p.font_size,
                    box_w=pe.w, box_h=pe.h,
                    line_spacing=p.line_spacing,
                    v_auto_fit=v_auto_fit,
                    h_auto_fit=h_auto_fit,
                )
                for iss in issues:
                    severity = "warning" if pe.content_type == ContentType.TEXTBOX else iss["level"]
                    diags.append({
                        "slide": i, "phase": "freeze",
                        "kind": iss["kind"],
                        "severity": severity,
                        "elem_id": pe.elem_id,
                        "message": iss["message"],
                    })

            pv = c.pre_commit_validation()
            for err in pv.get("errors", []):
                diags.append(_diag(i, "pre", None, kind="validation_error", severity="error",
                                   elem_id=err.get("owner_id", ""), message=err.get("detail", "")))
            for warn in pv.get("warnings", []):
                diags.append(_diag(i, "pre", None, kind="validation_warning", severity="warning",
                                   elem_id=warn.get("owner_id", ""), message=warn.get("detail", "")))
            for adv in pv.get("advisories", []):
                diags.append(_diag(i, "pre", None, kind="advisory", severity="info",
                                   elem_id=adv.get("owner_id", ""), message=adv.get("detail", "")))

            _render_slide(prs, c, self._t, slide_index=i, total_slides=total_slides)
            self.diff_log.snap_after(plan, i)

            # Cache pipeline results
            self._pipeline_cache[i] = (h, plan, c, diags)
            all_diags.extend(diags)

        prs.save(path)
        rt_results = check_overflow(path)
        for rt in rt_results:
            all_diags.append(_diag(rt["slide"], "rt", None,
                                   kind=rt["kind"], severity=rt["severity"],
                                   message=rt["message"]))
        rt_errors = [rt for rt in rt_results if rt["severity"] == "error"]

        diff_report = self.diff_log.diff()
        scope = self.diff_log.scope_alert()

        aggregated_diags, agg_stats = _aggregate_diagnostics(all_diags)
        errs = [d for d in aggregated_diags if d.get("severity") in ("error",)]

        return {
            "path": path,
            "ok": len(errs) == 0 and len(rt_errors) == 0,
            "diagnostics": aggregated_diags,
            "raw_diagnostic_count": agg_stats["raw_count"],
            "collapsed": {"dedup": agg_stats["dedup"],
                          "batch": agg_stats["batch"],
                          "trimmed_warnings": agg_stats["trimmed_warnings"],
                          "trimmed_info": agg_stats["trimmed_info"]},
            "summary": f"{agg_stats['final_count']} issues ({agg_stats['errors']} errors) — "
                       f"{len(changed)} slides rebuilt, "
                       f"{total_slides - len(changed)} from cache",
            "template": self._t.id,
            "style": self._style_id,
            "diff": {
                "entries": len(diff_report.entries) if diff_report else 0,
                "changed_elem_ids": list(diff_report.changed_elem_ids) if diff_report else [],
            },
            "scope_alert": scope,
        }

    def clear_cache(self):
        """Drop incremental rebuild cache (e.g. after template switch)."""
        self._pipeline_cache.clear()


    def title(self, text: str, region: str = "main") -> _Spec:
        return self._s("Heading", text, region, "text", ph=40)
    def subtitle(self, text: str, region: str = "main") -> _Spec:
        return self._s("Subtitle", text, region, "text", ph=30)
    def text(self, text: str, style: str = "Body", region: str = "main") -> _Spec:
        return self._s(style, text, region, "text")
    def bullet(self, text: str, region: str = "main") -> _Spec:
        return self._s("ListItem", f"• {text}", region, "text")
    def footer(self, text: str, region: str = "footer") -> _Spec:
        return self._s("Footer", text, region, "footer")
    def box(self, text: str, style: str = "Body", region: str = "main",
            fill_color: tuple|None = None, shape_id: str = "rounded_rectangle",
            ph: float|None = None, align_h: str = "left", allow_shrink: bool = False) -> _Spec:
        return self._s(style, text, region, "textbox", fill_color=fill_color,
                       shape_id=shape_id, ph=ph, align_h=align_h, allow_shrink=allow_shrink)
    def shape(self, shape_id: str, region: str = "main",
              fill_color: tuple|None = None, pw: float|None = None, ph: float|None = None) -> _Spec:
        return _Spec(elem_id=self._nid("shape"), style="", text="", region=region,
                     ctype="shape", fill_color=fill_color, shape_id=shape_id, pw=pw, ph=ph)
    def image(self, path: str, region: str = "main",
              pw: float|None = None, ph: float|None = None,
              fit_mode: str = "fit", allow_upscale: bool = False,
              layout_mode: str = "", caption: str = "") -> _Spec:
        # Fix #10: validate path exists
        if not os.path.isfile(path):
            print(f"[PPTBuilder] WARNING: image path not found: {path}")
        return _Spec(elem_id=self._nid("img"), style="", text="", region=region,
                     ctype="image", pw=pw, ph=ph, image_path=path,
                     fit_mode=fit_mode, allow_upscale=allow_upscale,
                     layout_mode=layout_mode, caption=caption)
    def table(self, headers: list[str], rows: list[list[str]],
              region: str = "main", font_size: float = 12.0,
              header_bg: tuple|None = None) -> _Spec:
        """Add a table element. headers=column names, rows=row data.

        Each row must have len(headers) cells. The engine auto-sizes columns
        to fit region width and auto-sizes rows by content.
        """
        return _Spec(elem_id=self._nid("tbl"), style="Table", text="", region=region,
                     ctype="table", ph=None,
                     table_headers=list(headers), table_rows=[list(r) for r in rows])
    def arrow(self, frm: str, to: str, text: str = "", direction: str = "below",
              color: tuple = (0x66,0x66,0x66), width: float = 1.5,
              margin_pt: float = 8.0, text_font_size: float = 10.0,
              text_color: tuple = (0x55,0x55,0x55),
              occlusion_check: bool = True) -> _Arrow:
        # Allow passing _Spec objects directly — resolve to elem_id
        from_eid = frm.elem_id if hasattr(frm, 'elem_id') else frm
        to_eid = to.elem_id if hasattr(to, 'elem_id') else to
        return _Arrow(self._nid("arrow"), from_eid, to_eid, text, direction, color, width,
                      margin_pt, text_font_size, text_color, occlusion_check)
    def divider(self, region: str = "main", color: tuple|None = None, width_pt: float = 3.0) -> _Spec:
        dh = self._t.divider_color_hex
        if dh:
            c = color or tuple(int(dh.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
        else:
            c = color or (0x44, 0x44, 0x55)
        return _Spec(elem_id=self._nid("div"), style="", text="", region=region,
                     ctype="shape", fill_color=c, shape_id="rectangle", ph=width_pt)

    # ── Image layout auto-inference ──
    def auto_layout_mode(self, image_path: str) -> str:
        """Select layout mode from image aspect ratio + preset constraints. Decision tree:
        aspect > 1.6 -> hero_top (landscape)
        aspect < 0.8 -> hero_right (portrait)
        aspect 0.8-1.6 -> center_float (square)
        Falls back to preset's preferred_modes[0] if decision mode not in allowed set."""
        from PIL import Image
        try:
            img = Image.open(image_path)
            w, h = img.size
            aspect = w / h if h > 0 else 1.0
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[PPTBuilder] auto_layout_mode PIL error for {image_path}: {e}")
            return "center_float"

        # Decide by aspect ratio
        if aspect > 1.6:
            mode = "hero_top"
        elif aspect < 0.8:
            mode = "hero_right"
        else:
            mode = "center_float"

        # If preset constrains preferred_modes and decision mode is not in it, fall back to preferred_modes[0]
        if self._image_layout:
            preferred = self._image_layout.get("preferred_modes", [])
            if preferred and mode not in preferred:
                mode = preferred[0]
        return mode

    def image_constraints(self, layout_mode: str) -> dict:
        """Return max_w/max_h/anchor/ratio constraints for the given layout_mode from current preset."""
        mc = self._image_layout.get("mode_constraints", {}) if self._image_layout else {}
        return mc.get(layout_mode, {})

    def image_treatment(self) -> dict:
        """Return image rendering treatment (corner_radius/border/shadow) from current preset."""
        defaults = {"corner_radius_pt": 0, "border_role": "none", "shadow_role": "none"}
        if self._image_layout:
            defaults.update(self._image_layout.get("treatment", {}))
        return defaults

    def caption_format(self) -> dict:
        """Return caption format convention from current preset."""
        defaults = {"font_size": 11, "alignment": "left", "max_lines": 1, "prefix": ""}
        if self._image_layout:
            defaults.update(self._image_layout.get("caption", {}))
        return defaults

    # ── Internals ──
    def _nid(self, pfx: str) -> str:
        self._id += 1; return f"{pfx}_{self._id}"

    def _s(self, style: str, text: str, region: str, ctype: str,
           fill_color=None, shape_id="", ph=None,
           align_h="left", allow_shrink=False, allow_wrap=False) -> _Spec:
        s = STYLE.get(style, STYLE["Body"])
        return _Spec(self._nid("e"), style, text, region, ctype, "stack",
                     fill_color=fill_color or s.get("fill_color"),
                     shape_id=shape_id, ph=ph, margin=4.0,
                     align_h=align_h, allow_shrink=allow_shrink, allow_wrap=allow_wrap)

    # Fix #1: resolve style colors + font sizes from template profile
    def _resolve_style(self, style_name: str, fill_color=None) -> dict:
        """Merge STYLE defaults with template/style-preset colors AND font sizes."""
        s = dict(STYLE.get(style_name, STYLE["Body"]))
        t = self._t

        # Map style -> template color field
        if style_name in ("Heading", "Subheading"):
            s["font_color"] = _hex_to_rgb(t.title_hex)
        elif style_name == "Subtitle":
            s["font_color"] = _hex_to_rgb(t.gray_hex) if t.gray_hex else _hex_to_rgb(t.text_hex)
        elif style_name == "Emphasis":
            s["font_color"] = _hex_to_rgb(t.accent2_hex) if t.accent2_hex else _hex_to_rgb(t.accent_hex)
        elif style_name == "Caption":
            s["font_color"] = _hex_to_rgb(t.gray_hex) if t.gray_hex else _hex_to_rgb(t.text_hex)
        elif style_name == "Footer":
            s["font_color"] = _hex_to_rgb(t.dim_hex) if t.dim_hex else _hex_to_rgb(t.gray_hex)
        else:  # "Body", "ListItem"
            s["font_color"] = _hex_to_rgb(t.text_hex)

        # Map style -> template font size (was dead code — STYLE dict always won)
        if style_name in ("Heading",):
            s["font_size"] = t.title_size
        elif style_name in ("Subtitle",):
            s["font_size"] = t.caption_size
        elif style_name in ("Body", "ListItem", "Emphasis"):
            s["font_size"] = t.body_size
        elif style_name == "Caption":
            s["font_size"] = t.caption_size
        elif style_name == "Footer":
            s["font_size"] = t.page_number_size

        # Fix #13: font_name fallback
        if "font_name" not in s or not s["font_name"]:
            s["font_name"] = self._style_body_font or t.body_font

        # Dark fill -> white text
        if fill_color and _is_dark(fill_color):
            s["font_color"] = (0xFF, 0xFF, 0xFF)

        return s

    def _plan(self, spec: _Slide) -> LayoutPlan:
        ctmap = {"text": ContentType.TEXT, "textbox": ContentType.TEXTBOX,
                 "shape": ContentType.SHAPE, "image": ContentType.IMAGE,
                 "table": ContentType.TABLE,
                 "annotation": ContentType.ANNOTATION, "footer": ContentType.FOOTER}
        regions = []
        for ri, d in enumerate(spec.regions):
            rid, x, y, w, h = d[0], d[1], d[2], d[3], d[4]
            ro = d[5] if len(d) > 5 else ri + 1
            # Fix #5: optional 6th field for content_inset
            inset = d[6] if len(d) > 6 else 8.0
            regions.append(Region(rid, x, y, w, h, rid, ro, inset))

        elems = []
        for e in spec.elements:
            # Fix #1: resolve style from template colors
            s = self._resolve_style(e.style, e.fill_color)
            ctyp = ctmap.get(e.ctype, ContentType.TEXT)

            # Fix #4: set ElementPayload.role based on content_type
            role = None
            if e.ctype == "text":
                role = None  # handrail: TEXT -> ENTITY
            elif e.ctype == "textbox":
                role = None  # handrail: BAND -> ENTITY
            elif e.ctype == "shape":
                role = None  # handrail: BAND -> ENTITY (shape like divider)

            p = ElementPayload(
                role=role,
                text=e.text,
                font_size=s.get("font_size", 14),
                font_color=s.get("font_color", (0x33, 0x33, 0x44)),
                font_bold=s.get("font_bold", False),
                font_name=s.get("font_name", self._t.body_font),
                alignment=s.get("alignment", "LEFT"),
                fill_color=e.fill_color or s.get("fill_color"),
                shape_id=e.shape_id,
                line_spacing=self._t.line_spacing,
                image_path=e.image_path,
                fit_mode=e.fit_mode,
                allow_upscale=e.allow_upscale,
                layout_mode=e.layout_mode,
                caption=e.caption,
                table_headers=e.table_headers if e.table_headers else None,
                table_rows=e.table_rows if e.table_rows else None,
            )
            # Fix #6: expose Phase1Element params
            elems.append(Phase1Element(
                e.elem_id, e.region, ctyp,
                payload=p, fill_mode=e.fill_mode, margin_above=e.margin,
                preferred_width=e.pw, preferred_height=e.ph,
                align_h=e.align_h,
                allow_shrink=e.allow_shrink,
                allow_wrap=e.allow_wrap,
                ARROW_SLOT=e.arrow_slot,
            ))

        decos = []
        for a in spec.arrows:
            # Fix #8: pass all DecoIntent params
            decos.append(DecoIntent(
                a.deco_id, "arrow", [a.from_elem, a.to_elem],
                a.direction,
                margin_pt=a.margin_pt,
                style={"line_color": a.color, "line_width_pt": a.width},
                text=a.text,
                text_font_size=a.text_font_size,
                text_color=a.text_color,
                occlusion_check=a.occlusion_check,
            ))

        # Fix #7: use template page_margin for page_safe_inset
        plan = LayoutPlan(
            page_w=self.pw, page_h=self.ph,
            page_safe_inset=max(12.0, self._t.page_margin),
            title=spec.title,
            regions=regions,
            phase1_elements=elems,
            deco_intents=decos,
        )
        return plan

    def _run_aesthetics(self, canvas, plan) -> list[dict]:
        """Run AestheticsEngine and return structured diagnostics."""
        engine = AestheticsEngine()
        elems = []
        for pe in plan.elements:
            p = pe.payload
            fill_hex = _rgb_to_hex(p.fill_color) if p and p.fill_color else self._t.bg_hex.lstrip("#")
            font_hex = _rgb_to_hex(p.font_color) if p and p.font_color else "000000"
            es = ElemStyle(
                id=pe.elem_id, content_type=pe.content_type,
                font_size=p.font_size if p else 12,
                font_bold=p.font_bold if p else False,
                font_color=font_hex, fill_color=fill_hex,
                line_spacing=p.line_spacing if p else 1.2,
                text=p.text if p else "",
                x=pe.x, y=pe.y, w=pe.w, h=pe.h,
                auto_size="SHAPE_TO_FIT_TEXT",
                canvas_w=self.pw, canvas_h=self.ph,
            )
            # No fill -> inherit slide background (avoids false contrast errors when text over slide bg)
            if p and not p.fill_color and not p.shape_id:
                es.fill_color = self._t.bg_hex
            if p and p.fill_color:
                es.fill_color = _rgb_to_hex(p.fill_color)
            elems.append(es)

        violations = engine.check(elems, timing="audit")
        return [_ae_violation_to_diag(v) for v in violations]


def _aggregate_diagnostics(diags: list[dict]) -> tuple[list[dict], dict]:
    """P0-①: collapse noisy diagnostics into a clean actionable feed.

    Rules (priority order):
      1. ALL errors pass through untouched — never deduped, batched, or trimmed.
      2. Dedup warnings: same (elem_id, kind) → keep latest phase only.
      3. Batch-collapse: >=5 warnings of same kind → one summary with elem_ids list.
      4. Cap warnings at 15, info at 5. Surplus tracked in `trimmed_*` keys.

    Returns (aggregated, stats) — caller MUST use aggregated as the final diagnostics list.
    """
    if not diags:
        return [], {"raw_count": 0, "errors": 0, "warnings": 0, "info": 0,
                    "dedup": 0, "batch": 0, "trimmed_warnings": 0, "trimmed_info": 0}

    errors = [d for d in diags if d.get("severity") in ("error",)]
    warns  = [d for d in diags if d.get("severity") in ("warning", "warn")]
    infos  = [d for d in diags if d.get("severity") == "info"]

    raw_counts = {"raw_count": len(diags), "errors": len(errors),
                  "warnings": len(warns), "info": len(infos)}

    # ── Rule 2: dedup warnings by (elem_id, kind), keep latest phase ──
    seen: dict[tuple, dict] = {}
    dedup_count = 0
    for w in warns:
        eid = w.get("elem_id", "") or ""
        kind = w.get("kind", "")
        key = (eid, kind)
        if key in seen:
            dedup_count += 1
            # Keep the one from the later phase
            existing_phase = seen[key].get("phase", "0")
            current_phase = w.get("phase", "0")
            if _phase_rank(current_phase) >= _phase_rank(existing_phase):
                seen[key] = w
        else:
            seen[key] = w
    warns = list(seen.values())

    # ── Rule 3: batch-collapse same-kind warnings (≥ threshold) ──
    by_kind: dict[str, list[dict]] = {}
    for w in warns:
        by_kind.setdefault(w.get("kind", "unknown"), []).append(w)

    batched = 0
    result_warns: list[dict] = []
    for kind, items in by_kind.items():
        if len(items) >= _KIND_BATCH_THRESHOLD:
            batched += 1
            elem_ids = sorted(set(
                i.get("elem_id", "") for i in items if i.get("elem_id")
            ))
            sample = items[0]
            result_warns.append({
                "kind": f"{kind}_batch",
                "severity": "warning",
                "phase": "aggregate",
                "batch_kind": kind,
                "count": len(items),
                "elem_ids": elem_ids,
                "sample_message": sample.get("message", ""),
                "options": sample.get("options", []),
                "message": (
                    f"{len(items)} elements share '{kind}' — "
                    f"affected: {', '.join(elem_ids[:6])}"
                    f"{'...' if len(elem_ids) > 6 else ''}"
                ),
            })
        else:
            result_warns.extend(items)

    # ── Rule 4: cap warnings and info ──
    trimmed_w = max(0, len(result_warns) - _WARN_CAP)
    result_warns = result_warns[:_WARN_CAP]

    trimmed_i = max(0, len(infos) - _INFO_CAP)
    result_infos = infos[:_INFO_CAP]

    aggregated = errors + result_warns + result_infos
    stats = {
        **raw_counts,
        "dedup": dedup_count,
        "batch": batched,
        "trimmed_warnings": trimmed_w,
        "trimmed_info": trimmed_i,
        "final_count": len(aggregated),
    }
    return aggregated, stats


def _phase_rank(phase: str) -> int:
    """Order phases so 'keep latest phase' dedup picks the most downstream result."""
    try:
        return _PHASE_ORDER.index(phase)
    except ValueError:
        return 99  # unknown phases rank last (most recent)


def _diag(slide_idx, phase, d, kind="", severity="", deco_id="", elem_id="", message=""):
    """Normalize diagnostics from various sources into a uniform format."""
    if isinstance(d, dict):
        return {"slide": slide_idx, "phase": phase, **d}
    if hasattr(d, 'kind'):
        return {
            "slide": slide_idx, "phase": phase,
            "kind": d.kind, "severity": d.severity,
            "region_id": getattr(d, 'region_id', ''),
            "elem_id": getattr(d, 'elem_id', ''),
            "demand_pt": getattr(d, 'demand_pt', 0),
            "usable_pt": getattr(d, 'usable_pt', 0),
            "message": getattr(d, 'message', ''),
            "options": getattr(d, 'options', []),
        }
    if kind:
        return {"slide": slide_idx, "phase": phase, "kind": kind, "severity": severity,
                "deco_id": deco_id, "elem_id": elem_id, "message": message}
    return {"slide": slide_idx, "phase": phase, "message": str(d)}


def _ae_violation_to_diag(v) -> dict:
    """Convert AestheticViolation to a flat dict.

    Severity mapping: Verdict.BLOCK → "error", WARN → "warning", ALLOW → "info".
    This is canonical — BLOCK means the build must fail or the agent must explain.
    """
    severity_map = {Verdict.BLOCK: "error", Verdict.WARN: "warning", Verdict.ALLOW: "info"}
    sv = severity_map.get(v.verdict, v.verdict.name.lower() if hasattr(v.verdict, 'name') else str(v.verdict))
    return {
        "kind": v.rule_id,
        "category": v.category,
        "severity": sv,
        "priority": v.priority,
        "elem_id": v.element_id,
        "message": v.message,
        "metrics": v.metrics,
    }


def _render_slide(prs, canvas, template, slide_index=0, total_slides=1):
    """Grid-to-PPT full slide render: background + info layer + decorations + page number."""
    from pptx.util import Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN

    layout_idx = 0
    try:
        layout_count = len(prs.slide_layouts)
        if layout_count > 0:
            layout_idx = min(slide_index, layout_count - 1)
    except Exception as e:
        print(f"[PPTBuilder] slide_layouts error (template PPTX): {e}")
    slide = prs.slides.add_slide(prs.slide_layouts[layout_idx])
    # Delete all placeholder shapes from the base layout — engine adds its own shapes.
    # Default slide layouts carry title/content placeholders that the grid engine never
    # populates, leaving ghost empty boxes in the output.
    shapes_to_delete = [s for s in slide.shapes if s.is_placeholder]
    for s in shapes_to_delete:
        sp = s._element
        sp.getparent().remove(sp)

    # Background fill
    bg_hex = template.bg_hex.lstrip("#")
    bg_rgb = RGBColor(int(bg_hex[0:2], 16), int(bg_hex[2:4], 16), int(bg_hex[4:6], 16))
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = bg_rgb

    page_w_pt = canvas.config.canvas_w_pt
    page_h_pt = canvas.config.canvas_h_pt

    # Phase 1: information layer elements
    for pe in canvas._phase1_rects if hasattr(canvas, '_phase1_rects') else {}:
        x, y, w, h = canvas._phase1_rects.get(pe, (0, 0, 0, 0))
        ct, payload = canvas._phase1_payloads.get(pe, (ContentType.UNKNOWN, None))
        if w <= 0 or h <= 0:
            continue

        if ct == ContentType.TABLE and payload:
            _render_table(slide, x, y, w, h, payload, template)
        elif ct == ContentType.IMAGE and payload and payload.image_path:
            # Contain-fit image rendering: PIL natural size -> contain -> no crop, no stretch
            _render_image(slide, x, y, w, h, payload)
            # Optional caption
            if payload.caption:
                cap_x = Emu(int(x * 12700))
                cap_y = Emu(int((y + h - 6) * 12700))
                cap_w = Emu(int(w * 12700))
                cap_h = Emu(int(18 * 12700))
                tb = slide.shapes.add_textbox(cap_x, cap_y, cap_w, cap_h)
                tb.text_frame.word_wrap = True
                p = tb.text_frame.paragraphs[0]
                run = p.add_run()
                run.text = payload.caption
                run.font.size = Pt(template.caption_size)
                run.font.color.rgb = RGBColor(*_hex_to_rgb(template.gray_hex) if template.gray_hex else (0x66, 0x66, 0x66))
        else:
            _render_payload(slide, x, y, w, h, ct, payload,
                {"LEFT": PP_ALIGN.LEFT, "CENTER": PP_ALIGN.CENTER, "RIGHT": PP_ALIGN.RIGHT})

    # Phase 2: decorations
    for dec in (canvas._decoration_payloads if hasattr(canvas, '_decoration_payloads') else []):
        if dec.get("type") == "arrow":
            from pptx.enum.shapes import MSO_CONNECTOR_TYPE
            connector = slide.shapes.add_connector(
                MSO_CONNECTOR_TYPE.STRAIGHT,
                Pt(dec["x1"]), Pt(dec["y1"]),
                Pt(dec["x2"]), Pt(dec["y2"]))
            connector.line.color.rgb = RGBColor(*dec.get("line_color", (0x66, 0x66, 0x66)))
            connector.line.width = Pt(dec.get("line_width_pt", 1.5))
            if dec.get("text"):
                tx = (dec["x1"] + dec["x2"]) / 2
                ty = (dec["y1"] + dec["y2"]) / 2
                from pptx.enum.text import MSO_AUTO_SIZE
                label = slide.shapes.add_textbox(Pt(tx - 55), Pt(ty - 16), Pt(110), Pt(32))
                label.text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
                label.text_frame.word_wrap = True
                label.text_frame.paragraphs[0].text = dec["text"]
                label.text_frame.paragraphs[0].font.size = Pt(dec.get("font_size", 10))
                label.text_frame.paragraphs[0].font.color.rgb = RGBColor(*dec.get("font_color", (0x55, 0x55, 0x55)))

    # Page number
    fn = f"{slide_index + 1}/{total_slides}"
    pn = slide.shapes.add_textbox(Pt(page_w_pt - 60), Pt(page_h_pt - 28), Pt(48), Pt(20))
    pn.text_frame.paragraphs[0].text = fn
    pn.text_frame.paragraphs[0].font.size = Pt(template.page_number_size)
    pn.text_frame.paragraphs[0].font.color.rgb = RGBColor(*_hex_to_rgb(template.dim_hex)) if template.dim_hex else RGBColor(0x88, 0x88, 0x99)
    pn.text_frame.paragraphs[0].alignment = PP_ALIGN.RIGHT


# ── P1-② Table rendering ──

def _render_table(slide, x: float, y: float, w: float, h: float,
                  payload, template) -> None:
    """Render a table shape into the slide. Columns auto-sized; header row styled."""
    from pptx.util import Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.oxml.ns import qn

    headers = payload.table_headers or []
    rows = payload.table_rows or []
    if not headers and not rows:
        return

    n_cols = len(headers) if headers else (len(rows[0]) if rows else 1)
    n_rows = 1 + len(rows)  # header + data

    # Clamp — don't crash on bad input
    n_cols = max(1, n_cols)
    n_rows = max(1, n_rows)

    col_w = w / n_cols
    row_h = min(h / n_rows, 36.0)  # cap individual row height at 36pt

    tbl_shape = slide.shapes.add_table(
        n_rows, n_cols,
        Emu(int(x * 12700)), Emu(int(y * 12700)),
        Emu(int(w * 12700)), Emu(int(h * 12700)),
    )
    tbl = tbl_shape.table

    # Column widths — equal distribution
    col_emu = Emu(int(col_w * 12700))
    for ci in range(n_cols):
        tbl.columns[ci].width = col_emu

    # Font config
    font_sz = payload.font_size if payload and payload.font_size else 12.0
    font_color = payload.font_color if payload else (0x33, 0x33, 0x44)
    header_bg = _hex_to_rgb(template.accent_hex) if template.accent_hex else (0x1A, 0x1A, 0x2E)
    if _is_dark(header_bg):
        header_font_color = (0xFF, 0xFF, 0xFF)
    else:
        header_font_color = (0xFF, 0xFF, 0xFF) if _is_dark(header_bg) else (0x33, 0x33, 0x44)

    for ri in range(n_rows):
        data = headers if ri == 0 else rows[ri - 1]
        is_header = (ri == 0)

        for ci in range(n_cols):
            cell = tbl.cell(ri, ci)
            cell_text = str(data[ci]) if ci < len(data) else ""

            # Cell fill
            cell_fill = cell.fill
            cell_fill.solid()
            if is_header:
                cell_fill.fore_color.rgb = RGBColor(*header_bg)
            else:
                bg_rgb = _hex_to_rgb(template.bg_hex) if template.bg_hex else (0xFF, 0xFF, 0xFF)
                cell_fill.fore_color.rgb = RGBColor(*bg_rgb)

            # Cell text
            tf = cell.text_frame
            tf.word_wrap = True
            tf.margin_left = Pt(4)
            tf.margin_right = Pt(4)
            tf.margin_top = Pt(2)
            tf.margin_bottom = Pt(2)

            p = tf.paragraphs[0]
            p.text = cell_text
            p.font.size = Pt(font_sz)
            p.font.bold = is_header
            p.font.color.rgb = RGBColor(*header_font_color) if is_header else RGBColor(*font_color)

            # Vertical center
            tcPr = cell._tc.get_or_add_tcPr()
            tcPr.set('anchor', 'ctr')
