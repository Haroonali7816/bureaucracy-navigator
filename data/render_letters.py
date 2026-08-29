"""
Renders the 16 plain-text sample letters as page images (PNG), so classify_and_extract()
can be built as a real Gemini multimodal call (image in, JSON out) instead of a text-only
stand-in. Data-prep utility, not pipeline logic -- lives in data/, not backend/app/.

Deliberately plain: white page, one sans-serif font, left-aligned, no rotation/noise/scan
artifacts. The goal is a realistic "printed letter photographed or scanned flat" page, not
a stress test for OCR robustness -- that's a reasonable stretch goal for later, not Day 2.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "data" / "sample_letters"
OUT_DIR = REPO_ROOT / "data" / "sample_letters_images"

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_SIZE = 20
LINE_HEIGHT = 28
PAGE_WIDTH = 1240
PAGE_HEIGHT = 1754
MARGIN = 90


def render_letter(txt_path: Path, out_path: Path, font: ImageFont.FreeTypeFont) -> None:
    text = txt_path.read_text(encoding="utf-8")
    img = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), "white")
    draw = ImageDraw.Draw(img)

    y = MARGIN
    for line in text.split("\n"):
        draw.text((MARGIN, y), line, font=font, fill="black")
        y += LINE_HEIGHT

    img.save(out_path)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

    txt_files = sorted(SRC_DIR.glob("*.txt"))
    if not txt_files:
        raise SystemExit(f"no .txt letters found in {SRC_DIR}")

    for txt_path in txt_files:
        out_path = OUT_DIR / (txt_path.stem + ".png")
        render_letter(txt_path, out_path, font)
        print(f"rendered {out_path.relative_to(REPO_ROOT)}")

    print(f"\ndone: {len(txt_files)} letters rendered to {OUT_DIR.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
