"""
grid/examples/check_image.py — End-to-end image rendering demo.

Proves the engine handles real images:
  1. try_place IMAGE with image_path + fit_mode via ElementPayload
  2. File-not-found → WARN before writing
  3. Valid image → ALLOW → commit renders at target size with fit/fill/crop
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from grid import GridCanvas, GridConfig, ContentType, Supply
from grid.types import ElementPayload

OUT = os.path.join(tempfile.gettempdir(), "image_demo.pptx")


def _make_test_image(w_px, h_px, color, path):
    from PIL import Image
    img = Image.new("RGB", (w_px, h_px), color)
    img.save(path)
    return path


def demo():
    cfg = GridConfig()
    canvas = GridCanvas(cfg)

    # ── Make test images ──
    td = tempfile.gettempdir()
    img_wide = _make_test_image(800, 400, (0x1B, 0x3A, 0x5C), os.path.join(td, "_test_wide.png"))   # 2:1
    img_tall = _make_test_image(400, 600, (0xC0, 0x39, 0x2B), os.path.join(td, "_test_tall.png"))    # 2:3
    img_missing = os.path.join(td, "_does_not_exist.png")

    # ── Title ──
    r = canvas.try_place("title", ContentType.TEXT, ["A1","B1","C1","D1","E1","F1","G1","H1"],
                         payload=ElementPayload(text="Image Rendering Demo", font_size=28,
                                                font_color=(0x1B,0x3A,0x5C), font_bold=True))
    print(f"[{r.verdict.value.upper()}] title")

    # ── Test 1: missing file → WARN ──
    r = canvas.try_place("img_missing", ContentType.IMAGE, ["A3","B3","C3","D3","A4","B4","C4","D4"],
                         payload=ElementPayload(image_path=img_missing, fit_mode="fit"))
    print(f"\n[Test 1] Missing file: [{r.verdict.value.upper()}]")
    if r.warnings:
        print(f"  WARN: {r.warnings[0].detail}")

    # ── Test 2: wide image → fit ──
    r = canvas.try_place("img_wide", ContentType.IMAGE, ["A3","B3","C3","D3","A4","B4","C4","D4",
                                                          "A5","B5","C5","D5","A6","B6","C6","D6"],
                         payload=ElementPayload(image_path=img_wide, fit_mode="fit"))
    print(f"\n[Test 2] Wide 800x400 fit @ A3:D6 (4col x 4row = 240x240pt): [{r.verdict.value.upper()}]")

    # ── Test 3: tall image → crop_center ──
    r = canvas.try_place("img_tall", ContentType.IMAGE, ["F3","G3","H3","I3","F4","G4","H4","I4"],
                         payload=ElementPayload(image_path=img_tall, fit_mode="crop_center"))
    print(f"\n[Test 3] Tall 400x600 crop @ F3:I4 (4col x 2row = 240x120pt): [{r.verdict.value.upper()}]")

    # ── Commit ──
    canvas.checkpoint()
    result = canvas.commit(OUT)
    print(f"\nCommit: {result['status']} -> {OUT}")
    if os.path.exists(OUT):
        print(f"  File: {os.path.getsize(OUT)} bytes")

    print(f"\nOccupied:")
    for oid, cells in canvas.occupied_summary().items():
        print(f"  {oid}: {list(cells)[:4]}...")


if __name__ == "__main__":
    print("=" * 60)
    print("PPT Reflex Grid — Image Rendering Demo")
    print("=" * 60)
    demo()
    print("=" * 60)
    print(f"Open: {OUT}")
    print("=" * 60)
