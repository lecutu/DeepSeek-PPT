"""End-to-end test: generate a 3-slide deck with each theme."""
from ppt_reflex.builder import PPTBuilder

for theme_id in ["academic_research", "corporate_consulting", "tech_product", "minimalist_creative"]:
    b = PPTBuilder(theme=theme_id)
    ACCENT = (
        int(b._t.accent_hex.lstrip("#")[0:2], 16),
        int(b._t.accent_hex.lstrip("#")[2:4], 16),
        int(b._t.accent_hex.lstrip("#")[4:6], 16),
    )
    DARK = (
        int(b._t.bg_hex.lstrip("#")[0:2], 16),
        int(b._t.bg_hex.lstrip("#")[2:4], 16),
        int(b._t.bg_hex.lstrip("#")[4:6], 16),
    )

    b.add_slide("主题测试",
        regions=[
            ("header", 60, 30, 840, 100, 1),
            ("hero", 60, 140, 840, 240, 2),
            ("footer", 60, 420, 840, 80, 3),
        ],
        elements=[
            b.title(f"{theme_id} — 主题自检", region="header"),
            b.box("主题正确加载\n排版/间距/装饰/反AI规则\n全部从 themes.json 解析", style="Body",
                  region="hero", fill_color=DARK),
            b.shape("hexagon", region="hero", fill_color=ACCENT, pw=60, ph=45),
            b.text("PPT Reflex Theme System v1.0", style="Caption", region="footer"),
        ],
    )

    b.add_slide("特性展示",
        regions=[
            ("header", 60, 30, 840, 100, 1),
            ("main", 60, 120, 520, 370, 2),
            ("card", 620, 120, 280, 250, 3),
        ],
        elements=[
            b.title("约束求解器 + 语义主题", region="header"),
            b.bullet(f"模板: {b._t.id}", region="main"),
            b.bullet(f"风格: {b._style_id}", region="main"),
            b.bullet(f"装饰策略: {(b.decoration_policy or {}).get('type', 'none')}", region="main"),
            b.bullet(f"反AI规则: {len(b.anti_ai_rules)} 条", region="main"),
            b.box("模板+风格+间距+字体+装饰+反AI → 一个参数搞定", style="Body",
                  region="card", fill_color=DARK),
        ],
    )

    b.add_slide("验证通过",
        regions=[
            ("center", 120, 120, 720, 300, 1),
        ],
        elements=[
            b.title("0 Error", region="center"),
            b.box("引擎保证布局确定性\n主题保证视觉一致性\nAI 只负责内容语义", style="Body",
                  region="center", fill_color=DARK),
        ],
    )

    r = b.build(f"test_theme_{theme_id}.pptx")
    errs = [d for d in r["diagnostics"] if d["severity"] == "error"]
    warns = [d for d in r["diagnostics"] if d["severity"] == "warning"]
    print(f"{theme_id}: {r['summary']}")
    if errs:
        for e in errs:
            print(f"  ERROR S{e['slide']:02d} [{e['phase']}] {e['kind']}: {e['message']}")
    else:
        print(f"  OK 0 errors, {len(warns)} warnings")

print("\nDone")
