"""Smoke test: theme system loading + auto-expansion."""
from ppt_reflex.builder import PPTBuilder, list_themes

# 1. List themes
themes = list_themes()
print("=== Themes ===")
for t in themes:
    print(f"  {t['id']}: {t['display_name']} [{t['mood']}] density={t['density']}")

# 2. Test each theme auto-expands
for tid in ['academic_research', 'corporate_consulting', 'tech_product', 'minimalist_creative']:
    b = PPTBuilder(theme=tid)
    sp = b._theme.get('spacing', {})
    dp = b.decoration_policy or {}
    print(f"\n--- {tid} ---")
    print(f"  template={b._t.id}, style={b._style_id}")
    print(f"  margin={sp.get('page_margin_pt')}pt, line_spacing={sp.get('line_spacing')}")
    print(f"  decoration={dp.get('type', 'none')}")
    print(f"  anti_ai_rules={len(b.anti_ai_rules)} rules")

# 3. Test backward-compatible (no theme)
b2 = PPTBuilder(template="minimal", style="tech_dark")
print(f"\n--- backward-compat ---")
print(f"  template={b2._t.id}, style={b2._style_id}, theme={b2._theme}")

print("\nOK — all themes loaded")
