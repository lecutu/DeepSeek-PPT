"""ppt_reflex/builder.py — 唯一 AI 入口。引擎所有功能在此暴露，纯接口无引擎概念。

from ppt_reflex.builder import PPTBuilder, load_style_presets, save_style_presets, list_style_presets

# 基础用法
builder = PPTBuilder(template="academic", style="academic_rigorous")
builder.add_slide("封面",
    regions=[("r1", 100,80,760,380)],
    elements=[builder.title("标题"), builder.text("正文", style="正文")],
)
result = builder.build("out.pptx")

# 风格预设管理
presets = load_style_presets()           # 读取当前预设
p = presets["academic_rigorous"]          # 获取一个预设
p["color_override"]["bg"] = "#FFFDF5"     # 修改背景色
save_style_presets(presets)              # 持久化

# list_style_presets() → [{id, display_name, mood, theme}, ...]
# 方便 AI 读取选择指南而不加载完整预设内容
"""

from __future__ import annotations
import os, tempfile, time, math, json
from dataclasses import dataclass, field

from ppt_reflex.grid import (
    GridCanvas, GridConfig, ContentType, ElementPayload,
    LayoutPlan, Region, Phase1Element, DecoIntent,
    execute_phase1, execute_phase2, global_composition_check,
)
from ppt_reflex.grid.templates import get_template, TemplateProfile

# ── 风格预设路径 ──
_PRESETS_PATH = os.path.join(os.path.dirname(__file__), "style_presets.json")


def load_style_presets() -> dict:
    """读取风格预设文件。返回完整 dict 含 meta + presets。可修改后调用 save_style_presets()。"""
    with open(_PRESETS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_style_presets(data: dict) -> None:
    """保存风格预设到磁盘。调用前先 load→修改→save。"""
    with open(_PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_style_presets() -> list[dict]:
    """轻量预设列表——AI 选风格用，每项仅 id+display_name+mood+theme。不含完整颜色/形状。"""
    data = load_style_presets()
    return [
        {"id": pid, "display_name": p["display_name"], "mood": p["mood"], "theme": p["theme"]}
        for pid, p in data.get("presets", {}).items()
    ]


# ── WCAG 亮度计算 ──
def _lum(rgb: tuple) -> float:
    def f(c): s = c/255.0; return s/12.92 if s <= 0.04045 else ((s+0.055)/1.055)**2.4
    return 0.2126*f(rgb[0]) + 0.7152*f(rgb[1]) + 0.0722*f(rgb[2])

def _is_dark(rgb: tuple) -> bool:
    return _lum(rgb) < 0.25

def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

# ── 风格表 ──
STYLE = {
    "标题":   dict(font_size=28, font_bold=True,  font_color=(0x1A,0x1A,0x2E), alignment="CENTER"),
    "副标题": dict(font_size=18, font_color=(0x55,0x55,0x77), alignment="CENTER"),
    "正文":   dict(font_size=14, font_color=(0x33,0x33,0x44), font_name="Microsoft YaHei"),
    "小标题": dict(font_size=16, font_bold=True,  font_color=(0x1B,0x3A,0x5C)),
    "注释":   dict(font_size=10, font_color=(0x88,0x88,0x99)),
    "页脚":   dict(font_size=8,  font_color=(0xAA,0xAA,0xBB), alignment="CENTER"),
    "列表项": dict(font_size=13, font_color=(0x33,0x33,0x44), font_name="Microsoft YaHei"),
    "强调":   dict(font_size=14, font_bold=True,  font_color=(0xC0,0x39,0x2B)),
}

# ── 内置形状库 ──
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

# ── 内部 spec ──
@dataclass
class _Spec:
    elem_id: str; style: str; text: str = ""; region: str = "main"
    ctype: str = "text"; fill_mode: str = "stack"
    pw: float|None = None; ph: float|None = None
    fill_color: tuple|None = None; shape_id: str = ""
    image_path: str = ""; margin: float = 6.0

@dataclass
class _Arrow:
    deco_id: str; from_elem: str; to_elem: str; text: str = ""
    direction: str = "below"; color: tuple = (0x66,0x66,0x66); width: float = 1.5

@dataclass
class _Slide:
    title: str = ""
    regions: list = field(default_factory=list)
    elements: list[_Spec] = field(default_factory=list)
    arrows: list[_Arrow] = field(default_factory=list)


class PPTBuilder:
    """唯一 AI 入口。add_slide → build，中间引擎+模板全透明。"""

    def __init__(self, template: str = "academic", style: str|None = None,
                 page_w: float = 960, page_h: float = 540):
        self._t: TemplateProfile = get_template(template)
        self._style_preset: dict|None = None
        self._style_id: str|None = style
        self.pw, self.ph = page_w, page_h
        self._slides: list[_Slide] = []
        self._id = 0

        if style:
            data = load_style_presets()
            self._style_preset = data.get("presets", {}).get(style)
            if self._style_preset and self._style_preset.get("theme") == "dark":
                if template != "product":
                    self._t = TemplateProfile(
                        id=template, name=self._t.name, description=self._t.description,
                        bg_hex=self._style_preset["color_override"]["bg"],
                        text_hex=self._style_preset["color_override"]["text_primary"],
                        title_hex=self._style_preset["color_override"]["text_primary"],
                        accent_hex=self._style_preset["color_override"]["accent"],
                        accent2_hex=self._style_preset["color_override"].get("warn", self._t.accent2_hex),
                        gray_hex=self._style_preset["color_override"].get("text_secondary", self._t.gray_hex),
                        dim_hex=self._style_preset["color_override"].get("surface", self._t.dim_hex),
                        title_font=self._t.title_font, body_font=self._t.body_font,
                        title_size=self._style_preset.get("font_override", {}).get("scale_h1", 28),
                        body_size=self._style_preset.get("font_override", {}).get("scale_body", 14),
                        caption_size=self._style_preset.get("font_override", {}).get("scale_h2", 14),
                        page_margin=48, line_spacing=1.35,
                        divider_color_hex=self._style_preset["color_override"]["accent"],
                    )
                else:
                    c = self._style_preset["color_override"]
                    self._t = TemplateProfile(
                        id="product", name="product", description="product",
                        bg_hex=c["bg"], text_hex=c["text_primary"], title_hex=c["text_primary"],
                        accent_hex=c["accent"], accent2_hex=c.get("warn", ""),
                        gray_hex=c.get("text_secondary", "98989E"), dim_hex=c.get("surface", "68686E"),
                        allow_dark_bg=True,
                    )

    # ── slide ──
    def add_slide(self, title: str = "", *, regions: list|None = None,
                  elements: list|None = None, arrows: list|None = None) -> int:
        if regions is None: regions = [("main", 60, 60, 840, 420, 1)]
        self._slides.append(_Slide(title, regions, elements or [], arrows or []))
        return len(self._slides) - 1

    def build(self, path: str|None = None) -> dict:
        from pptx import Presentation; from pptx.util import Pt
        if path is None:
            ts = int(time.time()); path = os.path.join(tempfile.gettempdir(), f"ppt_reflex_{ts}.pptx")
        prs = Presentation()
        prs.slide_width = Pt(self.pw); prs.slide_height = Pt(self.ph)
        all_diags: list[dict] = []

        for i, spec in enumerate(self._slides):
            plan = self._plan(spec); c = GridCanvas(GridConfig()); c.checkpoint()
            diags: list[dict] = []
            plan.validate(verbose=False)
            for d in plan.diagnostics: diags.append(_diag(i, "0.5", d))
            execute_phase1(plan, c)
            for d in plan.diagnostics: diags.append(_diag(i, "1", d))
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
            for ci in global_composition_check(plan):
                diags.append(_diag(i, "2.5", None, kind=ci.get("category","composition"),
                                   severity=ci.get("level","info"), message=ci.get("message","")))
            _render_slide(prs, c, self._t)
            all_diags.extend(diags)

        prs.save(path)
        errs = [d for d in all_diags if d.get("severity") in ("error",)]
        warns = [d for d in all_diags if d.get("severity") in ("warning","warn")]
        return {"path": path, "ok": len(errs) == 0, "diagnostics": all_diags,
                "summary": f"{len(all_diags)} issues ({len(errs)} errors, {len(warns)} warnings)",
                "template": self._t.id, "style": self._style_id}

    # ── 元素工厂 ──
    def title(self, text: str, region: str = "main") -> _Spec:
        return self._s("标题", text, region, "text", ph=40)
    def subtitle(self, text: str, region: str = "main") -> _Spec:
        return self._s("副标题", text, region, "text", ph=30)
    def text(self, text: str, style: str = "正文", region: str = "main") -> _Spec:
        return self._s(style, text, region, "text")
    def bullet(self, text: str, region: str = "main") -> _Spec:
        return self._s("列表项", f"• {text}", region, "text")
    def footer(self, text: str, region: str = "footer") -> _Spec:
        return self._s("页脚", text, region, "footer")
    def box(self, text: str, style: str = "正文", region: str = "main",
            fill_color: tuple|None = None, shape_id: str = "rounded_rectangle",
            ph: float = 30) -> _Spec:
        return self._s(style, text, region, "textbox", fill_color=fill_color, shape_id=shape_id, ph=ph)
    def shape(self, shape_id: str, region: str = "main",
              fill_color: tuple|None = None, pw: float|None = None, ph: float|None = None) -> _Spec:
        return _Spec(elem_id=self._nid("shape"), style="", text="", region=region,
                     ctype="shape", fill_color=fill_color, shape_id=shape_id, pw=pw, ph=ph)
    def image(self, path: str, region: str = "main",
              pw: float|None = None, ph: float|None = None) -> _Spec:
        return _Spec(elem_id=self._nid("img"), style="", text="", region=region,
                     ctype="image", pw=pw, ph=ph, image_path=path)
    def arrow(self, frm: str, to: str, text: str = "", direction: str = "below",
              color: tuple = (0x66,0x66,0x66), width: float = 1.5) -> _Arrow:
        return _Arrow(self._nid("arrow"), frm, to, text, direction, color, width)
    def divider(self, region: str = "main", color: tuple|None = None, width_pt: float = 3.0) -> _Spec:
        c = color or tuple(int(self._t.divider_color_hex.lstrip("#")[i:i+2],16) for i in (0,2,4))
        return _Spec(elem_id=self._nid("div"), style="", text="", region=region,
                     ctype="shape", fill_color=c, shape_id="rectangle", ph=width_pt)

    # ── private ──
    def _nid(self, pfx: str) -> str: self._id += 1; return f"{pfx}_{self._id}"

    def _s(self, style: str, text: str, region: str, ctype: str,
           fill_color=None, shape_id="", ph=None) -> _Spec:
        s = STYLE.get(style, STYLE["正文"])
        return _Spec(self._nid("e"), style, text, region, ctype, "stack",
                     fill_color=fill_color or s.get("fill_color"),
                     shape_id=shape_id, ph=ph, margin=4.0)

    def _plan(self, spec: _Slide) -> LayoutPlan:
        ctmap = {"text": ContentType.TEXT, "textbox": ContentType.TEXTBOX,
                 "shape": ContentType.SHAPE, "image": ContentType.IMAGE,
                 "annotation": ContentType.ANNOTATION, "footer": ContentType.FOOTER}
        regions = []
        for ri, d in enumerate(spec.regions):
            rid, x, y, w, h = d[0], d[1], d[2], d[3], d[4]
            ro = d[5] if len(d) > 5 else ri + 1
            regions.append(Region(rid, x, y, w, h, rid, ro, 8))
        elems = []
        for e in spec.elements:
            s = STYLE.get(e.style, STYLE["正文"])
            fc = s.get("font_color", (0x33,0x33,0x44))
            if e.fill_color and _is_dark(e.fill_color):
                fc = (0xFF, 0xFF, 0xFF)
            p = ElementPayload(text=e.text, font_size=s.get("font_size",14),
                font_color=fc, font_bold=s.get("font_bold",False),
                font_name=s.get("font_name", self._t.body_font),
                alignment=s.get("alignment","LEFT"),
                fill_color=e.fill_color or s.get("fill_color"),
                shape_id=e.shape_id, line_spacing=1.2)
            elems.append(Phase1Element(e.elem_id, e.region, ctmap.get(e.ctype,ContentType.TEXT),
                payload=p, fill_mode=e.fill_mode, margin_above=e.margin,
                preferred_width=e.pw, preferred_height=e.ph))
        decos = []
        for a in spec.arrows:
            decos.append(DecoIntent(a.deco_id, "arrow", [a.from_elem, a.to_elem],
                a.direction, style={"line_color":a.color,"line_width_pt":a.width},
                text=a.text, text_font_size=10, text_color=a.color))
        return LayoutPlan(self.pw, self.ph, title=spec.title, regions=regions,
                          phase1_elements=elems, deco_intents=decos)


def _render_slide(prs, c: GridCanvas, t: TemplateProfile):
    from pptx.util import Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.oxml.ns import qn
    from lxml import etree

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.background; fill = bg.fill; fill.solid()
    fill.fore_color.rgb = RGBColor(*_hex_to_rgb(t.bg_hex))

    rects = getattr(c, '_phase1_rects', {}) or {}
    payloads = getattr(c, '_phase1_payloads', {}) or {}
    decos = getattr(c, '_decoration_payloads', []) or []

    for eid, (x, y, w, h) in rects.items():
        ct_p = payloads.get(eid)
        if not ct_p: continue
        ct, p = ct_p
        l, t, wd, ht = Emu(int(x*12700)), Emu(int(y*12700)), Emu(int(w*12700)), Emu(int(h*12700))
        if ct == ContentType.IMAGE and p and p.image_path:
            try: slide.shapes.add_picture(p.image_path, l, t, wd, ht)
            except: pass
            continue
        mso = MSO_SHAPE.RECTANGLE
        if p and p.shape_id:
            sid = p.shape_id.upper().replace(" ", "_")
            if sid in SHAPES: sid = SHAPES[sid]
            mso = getattr(MSO_SHAPE, sid, MSO_SHAPE.RECTANGLE)
        shp = slide.shapes.add_shape(mso, l, t, wd, ht)
        if p and p.fill_color: shp.fill.solid(); shp.fill.fore_color.rgb = RGBColor(*p.fill_color)
        else: shp.fill.background()
        shp.line.fill.background()
        if p and p.text.strip():
            tf = shp.text_frame; tf.word_wrap = True
            al = PP_ALIGN.CENTER if getattr(p,'alignment','')=='CENTER' else \
                 PP_ALIGN.RIGHT  if getattr(p,'alignment','')=='RIGHT'  else PP_ALIGN.LEFT
            tf.paragraphs[0].alignment = al
            run = tf.paragraphs[0].add_run(); run.text = p.text
            if p.font_size: run.font.size = Pt(p.font_size)
            if p.font_color: run.font.color.rgb = RGBColor(*p.font_color)
            run.font.bold = getattr(p, 'font_bold', False)
            if p.font_name: run.font.name = p.font_name
        if ct == ContentType.TEXT:
            shp.fill.background()
            if p and p.text.strip():
                for m in ('margin_left','margin_right','margin_top','margin_bottom'):
                    setattr(shp.text_frame, m, Pt(0))

    for d in decos:
        if d.get("deco_type") != "arrow": continue
        x1, y1, x2, y2 = d["x1"], d["y1"], d["x2"], d["y2"]
        cn = slide.shapes.add_connector(1, Emu(int(x1*12700)), Emu(int(y1*12700)),
                                        Emu(int(x2*12700)), Emu(int(y2*12700)))
        lc = d.get("line_color", (0x66,0x66,0x66))
        cn.line.color.rgb = RGBColor(*lc); cn.line.width = Pt(d.get("line_width_pt", 1.5))
        sp = cn._element.find(qn('a:spPr'))
        if sp is not None:
            ln = sp.find(qn('a:ln'))
            if ln is None:
                ln = etree.SubElement(sp, qn('a:ln'))
                ln.set('w', str(int(d.get("line_width_pt",1.5)*12700)))
            tail = etree.SubElement(ln, qn('a:tailEnd'))
            tail.set('type','triangle'); tail.set('w','med'); tail.set('len','med')
        if d.get("text"):
            mx, my = (x1+x2)/2, (y1+y2)/2
            tb = slide.shapes.add_textbox(Emu(int(mx*12700-600000)), Emu(int(my*12700-200000)),
                                          Emu(1200000), Emu(400000))
            tb.text_frame.word_wrap = True
            tb.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
            rn = tb.text_frame.paragraphs[0].add_run()
            rn.text = d["text"]; rn.font.size = Pt(d.get("font_size",9))
            rn.font.color.rgb = RGBColor(*d.get("font_color",(0x55,0x55,0x55)))


def _diag(slide, phase, d, *, kind="", severity="", region_id="", elem_id="",
          deco_id="", message="", **kw) -> dict:
    if d is not None:
        item = {"slide": slide, "phase": phase, "kind": d.kind, "severity": d.severity,
                "region_id": d.region_id, "elem_id": d.elem_id,
                "over_by_pt": d.over_by_pt, "demand_pt": d.demand_pt, "usable_pt": d.usable_pt,
                "message": d.message, "options": getattr(d, "options", [])}
    else:
        item = {"slide": slide, "phase": phase, "kind": kind, "severity": severity,
                "region_id": region_id, "elem_id": elem_id, "deco_id": deco_id,
                "over_by_pt": 0, "demand_pt": 0, "usable_pt": 0,
                "message": message, "options": kw.get("options", [])}

    if item["kind"] in ("region_out_of_page",): item["fix_category"] = "resize_region"
    elif item["kind"] in ("inline_overflow", "text_wrap"): item["fix_category"] = "reduce_elements"
    elif item["kind"] in ("arrow_occlusion",): item["fix_category"] = "reroute_arrow"
    elif item["kind"] in ("whitespace",): item["fix_category"] = "adjust_density"
    elif item["kind"] in ("density",): item["fix_category"] = "resize_region"
    elif item["kind"] in ("balance", "alignment"): item["fix_category"] = "reposition"
    else: item["fix_category"] = "manual"

    fix_map = {
        "resize_region": "increase region width/height or move region to avoid page boundary",
        "reduce_elements": "reduce element count in region, split into two regions, or increase region height",
        "reroute_arrow": "reposition source/target elements or change arrow direction",
        "adjust_density": "increase element sizes or reduce region size to fill whitespace",
        "reposition": "shift element positions toward page center for visual balance",
        "manual": "review message and options, manually adjust add_slide() call",
    }
    item["recommended_action"] = fix_map.get(item["fix_category"], fix_map["manual"])
    return item
