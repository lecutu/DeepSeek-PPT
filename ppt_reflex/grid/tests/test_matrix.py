"""grid/tests/test_matrix.py"""
import sys
sys.path.insert(0, "D:/文献搜索员/ppt_reflex")
from grid.types import ContentType, Verdict, Conflict, GridConfig
from grid.matrix import InteractionMatrix


def test_block_pairs():
    m = InteractionMatrix()
    assert m.judge(ContentType.TEXT, ContentType.TEXT) == Verdict.BLOCK
    assert m.judge(ContentType.TEXT, ContentType.IMAGE) == Verdict.BLOCK
    assert m.judge(ContentType.TEXT, ContentType.TABLE) == Verdict.BLOCK
    assert m.judge(ContentType.IMAGE, ContentType.TEXT) == Verdict.BLOCK
    print("[PASS] block_pairs")


def test_allow_pairs():
    m = InteractionMatrix()
    assert m.judge(ContentType.TEXT, ContentType.TEXTBOX) == Verdict.ALLOW
    assert m.judge(ContentType.TEXT, ContentType.BACKGROUND) == Verdict.ALLOW
    assert m.judge(ContentType.IMAGE, ContentType.SHAPE) == Verdict.ALLOW
    assert m.judge(ContentType.SHAPE, ContentType.SHAPE) == Verdict.ALLOW
    print("[PASS] allow_pairs")


def test_default_policy():
    config = GridConfig(default_policy=Verdict.ALLOW)
    m = InteractionMatrix(config)
    assert m.judge(ContentType.ANNOTATION, ContentType.CHART) == Verdict.ALLOW

    config2 = GridConfig(default_policy=Verdict.BLOCK)
    m2 = InteractionMatrix(config2)
    assert m2.judge(ContentType.ANNOTATION, ContentType.CHART) == Verdict.BLOCK
    print("[PASS] default_policy")


def test_z_hints():
    m = InteractionMatrix()
    assert m.z_hint(ContentType.TEXT, ContentType.TEXTBOX) == "new_above"
    assert m.z_hint(ContentType.TEXTBOX, ContentType.TEXT) == "new_above"  # 对称
    assert m.z_hint(ContentType.TEXT, ContentType.TEXT) is None  # BLOCK 不需要 hint
    print("[PASS] z_hints")


def test_runtime_customize():
    m = InteractionMatrix()
    m.add_block_pair(ContentType.SHAPE, ContentType.SHAPE)
    assert m.judge(ContentType.SHAPE, ContentType.SHAPE) == Verdict.BLOCK
    m.remove_block_pair(ContentType.SHAPE, ContentType.SHAPE)
    assert m.judge(ContentType.SHAPE, ContentType.SHAPE) == Verdict.ALLOW
    print("[PASS] runtime_customize")


if __name__ == "__main__":
    test_block_pairs()
    test_allow_pairs()
    test_default_policy()
    test_z_hints()
    test_runtime_customize()
    print("\n✓ All matrix tests PASSED")
