"""quick test for aesthetics + text_metrics"""
import sys; sys.path.insert(0, "D:/文献搜索员/ppt_reflex")
from grid.aesthetics import AestheticsEngine, ElemStyle
from grid.types import ContentType

eng = AestheticsEngine()

# good contrast
e1 = ElemStyle("s01", ContentType.TEXT, font_size=14, font_color="222222", fill_color="FFFFFF")
v = eng.check([e1], timing="try_place")
print(f"Good contrast: {len(v)} violations (expect 0)")

# bad contrast
e2 = ElemStyle("s02", ContentType.TEXT, font_size=12, font_color="999999", fill_color="AAAAAA")
v = eng.check([e2], timing="try_place")
for vv in v:
    print(f"  [{vv.priority}] {vv.rule_id}: {vv.message}")

# font too small
e3 = ElemStyle("s03", ContentType.TEXT, font_size=8)
v = eng.check([e3], timing="try_place")
for vv in v:
    print(f"  [{vv.priority}] {vv.rule_id}: {vv.message}")

# overflow
e4 = ElemStyle("s04", ContentType.TEXT, font_size=24, text="区域详情这是一行很长的字",
               word_wrap=False, auto_size="NONE", w=100, h=50,
               font_color="FFFFFF", fill_color="1A1A2E")
v = eng.check([e4], timing="try_place")
for vv in v:
    print(f"  [{vv.priority}] {vv.rule_id}: {vv.message}")
    if "fix_suggestions" in vv.metrics:
        for s in vv.metrics["fix_suggestions"]:
            print(f"    fix: {s}")

# timing filter
all_elems = [e1, e2, e3, e4]
v_try = eng.check(all_elems, timing="try_place")
v_commit = eng.check(all_elems, timing="commit")
v_audit = eng.check(all_elems, timing="audit")
print(f"Timing: try_place={len(v_try)} commit={len(v_commit)} audit={len(v_audit)}")
print("All aesthetics OK")
