#!/usr/bin/env python3
"""
Marvel Rivals match screenshot parser.
Crops fixed pixel regions per player row / stat column, OCRs each box, outputs CSV.

Requirements:
    pip install pillow pytesseract
    Tesseract must be installed and on PATH:
        Windows: https://github.com/UB-Mannheim/tesseract/wiki
        Mac:     brew install tesseract
        Linux:   sudo apt install tesseract-ocr

Usage:
    python parse_rivals.py screenshot.png
    python parse_rivals.py screenshot.png match_001.csv
    python parse_rivals.py screenshot.png --calibrate
        → saves debug_calibrate.png so you can verify crop boxes visually

Coordinates assume 1920×1080 source screenshots.
If your screenshots are a different resolution, change SRC_W / SRC_H below
and the script will scale everything automatically.
"""

import sys, csv, re
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps
import pytesseract


# ── Calibration constants ─────────────────────────────────────────────────────
# Change SRC_W / SRC_H if your screenshots are not 1920×1080.
SRC_W = 1920
SRC_H = 1080

# Column x-ranges (left_px, right_px) at SRC_W resolution.
# Run --calibrate and open debug_calibrate.png to verify these visually.
COLS = {
    "name":  (316, 492),
    "k":     (490, 528),
    "d":     (526, 562),
    "a":     (560, 598),
    # Medals column is skipped — variable icon content, not needed
    "fh":    (840, 968),
    "dmg":   (955, 1068),
    "blk":   (1056, 1178),
    "heal":  (1170, 1254),
    "acc":   (1248, 1345),
}

# Y center of each player row at SRC_H resolution.
# Victory rows first (top half), Defeat rows second (bottom half).
VICTORY_ROWS = [204, 241, 277, 313, 350, 387]
DEFEAT_ROWS  = [432, 468, 504, 540, 577, 614]
ROW_HALF = 17  # crop (y_center - ROW_HALF) to (y_center + ROW_HALF)

# Region containing the Replay ID badge (bottom-right of screen)
REPLAY_REGION = (1185, 673, 1456, 712)

# Region containing map name + mode (top-right HUD)
MODE_MAP_REGION = (1040, 8, 1420, 68)


# ── Image helpers ─────────────────────────────────────────────────────────────

def load_scaled(path: Path) -> Image.Image:
    """Load image and resize to SRC_W×SRC_H if needed."""
    img = Image.open(path).convert("RGB")
    if img.width != SRC_W or img.height != SRC_H:
        print(f"  [info] resizing {img.width}×{img.height} → {SRC_W}×{SRC_H}")
        img = img.resize((SRC_W, SRC_H), Image.LANCZOS)
    return img


def preprocess(crop: Image.Image, upscale: int = 3) -> Image.Image:
    """
    Grayscale → binary threshold → upscale.
    Auto-detects dark vs light background by sampling the four corners.
    """
    g = ImageOps.grayscale(crop)
    w, h = g.size
    corners = [
        g.getpixel((0, 0)),
        g.getpixel((w - 1, 0)),
        g.getpixel((0, h - 1)),
        g.getpixel((w - 1, h - 1)),
    ]
    dark_bg = (sum(corners) / 4) < 128
    threshold = 160 if dark_bg else 100
    # For dark bg: keep pixels brighter than threshold (white text)
    # For light bg: keep pixels darker than threshold (dark text)
    lut = [255 if (i > threshold) == dark_bg else 0 for i in range(256)]
    g = g.point(lut)
    return g.resize((g.width * upscale, g.height * upscale), Image.NEAREST)


# ── OCR wrappers ──────────────────────────────────────────────────────────────

def ocr_number(img: Image.Image) -> int:
    """OCR a single numeric cell (strips commas from thousands)."""
    cfg = r"--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789,"
    text = pytesseract.image_to_string(img, config=cfg).strip()
    text = re.sub(r"[^\d]", "", text)
    return int(text) if text else 0


def ocr_name(img: Image.Image) -> str:
    """OCR a player-name cell (allow broad character set)."""
    cfg = r"--psm 7 --oem 3"
    return pytesseract.image_to_string(img, config=cfg).strip()


def ocr_line(img: Image.Image) -> str:
    """OCR a general text region."""
    cfg = r"--psm 6 --oem 3"
    return pytesseract.image_to_string(img, config=cfg).strip()


# ── Row / region croppers ─────────────────────────────────────────────────────

def row_crop(img: Image.Image, y_center: int, col: str) -> Image.Image:
    x0, x1 = COLS[col]
    y0, y1 = y_center - ROW_HALF, y_center + ROW_HALF
    return img.crop((x0, y0, x1, y1))


# ── Player parser ─────────────────────────────────────────────────────────────

def parse_player(img: Image.Image, y: int) -> dict:
    return {
        "name": ocr_name(preprocess(row_crop(img, y, "name"))),
        "k":    ocr_number(preprocess(row_crop(img, y, "k"))),
        "d":    ocr_number(preprocess(row_crop(img, y, "d"))),
        "a":    ocr_number(preprocess(row_crop(img, y, "a"))),
        "fh":   ocr_number(preprocess(row_crop(img, y, "fh"))),
        "dmg":  ocr_number(preprocess(row_crop(img, y, "dmg"))),
        "blk":  ocr_number(preprocess(row_crop(img, y, "blk"))),
        "heal": ocr_number(preprocess(row_crop(img, y, "heal"))),
        "acc":  ocr_number(preprocess(row_crop(img, y, "acc"))),
    }


# ── Full screenshot parse ─────────────────────────────────────────────────────

def parse_screenshot(path: Path) -> dict:
    print(f"Loading {path.name}…")
    img = load_scaled(path)

    # Replay ID → use as match_id
    replay_text = ocr_line(preprocess(img.crop(REPLAY_REGION), upscale=2))
    m = re.search(r"\d{7,}", replay_text)
    match_id = m.group(0) if m else path.stem

    # Mode + map from top-right HUD
    mm_text = ocr_line(preprocess(img.crop(MODE_MAP_REGION), upscale=2))
    mm_lines = [l.strip() for l in mm_text.splitlines() if l.strip()]
    map_name = mm_lines[0] if mm_lines else ""
    mode     = mm_lines[1] if len(mm_lines) > 1 else ""

    print("  Parsing Victory rows…")
    victory = [parse_player(img, y) for y in VICTORY_ROWS]

    print("  Parsing Defeat rows…")
    defeat  = [parse_player(img, y) for y in DEFEAT_ROWS]

    return {
        "match_id": match_id,
        "map":      map_name,
        "mode":     mode,
        "victory":  victory,
        "defeat":   defeat,
    }


# ── CSV writer ────────────────────────────────────────────────────────────────

FIELDNAMES = [
    "match_id", "team", "player",
    "kills", "deaths", "assists",
    "final_hits", "damage", "blocked", "healing", "accuracy",
]


def write_csv(result: dict, out_path: Path):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for team_label, players in [("Victory", result["victory"]),
                                     ("Defeat",  result["defeat"])]:
            for p in players:
                w.writerow({
                    "match_id":   result["match_id"],
                    "team":       team_label,
                    "player":     p["name"],
                    "kills":      p["k"],
                    "deaths":     p["d"],
                    "assists":    p["a"],
                    "final_hits": p["fh"],
                    "damage":     p["dmg"],
                    "blocked":    p["blk"],
                    "healing":    p["heal"],
                    "accuracy":   p["acc"],
                })
    print(f"  Wrote {out_path}")


# ── Calibration mode ──────────────────────────────────────────────────────────

def calibrate(path: Path):
    """
    Draws all crop box outlines on the image and saves debug_calibrate.png.
    Cyan  = Victory rows
    Pink  = Defeat rows
    Yellow = Replay ID region
    Lime   = Mode/Map region
    Open the file and check that boxes sit on top of the right cells.
    If they are off, adjust the COLS / ROW constants above.
    """
    img = load_scaled(path).convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    for y in VICTORY_ROWS:
        for col, (x0, x1) in COLS.items():
            draw.rectangle([x0, y - ROW_HALF, x1, y + ROW_HALF],
                           outline=(0, 255, 255, 200), width=1)

    for y in DEFEAT_ROWS:
        for col, (x0, x1) in COLS.items():
            draw.rectangle([x0, y - ROW_HALF, x1, y + ROW_HALF],
                           outline=(255, 100, 220, 200), width=1)

    draw.rectangle(REPLAY_REGION,   outline=(255, 255, 0, 220), width=2)
    draw.rectangle(MODE_MAP_REGION, outline=(0, 255, 0, 220),   width=2)

    out = path.parent / "debug_calibrate.png"
    img.save(out)
    print(f"Saved {out}")
    print("Cyan = Victory rows | Pink = Defeat rows")
    print("Yellow = Replay ID  | Lime = Mode/Map")
    print("If boxes are misaligned, adjust COLS / VICTORY_ROWS / DEFEAT_ROWS above.")


# ── Summary printer ───────────────────────────────────────────────────────────

def print_summary(result: dict):
    print()
    print(f"  Match ID : {result['match_id']}")
    print(f"  Map      : {result['map']}")
    print(f"  Mode     : {result['mode']}")
    print()
    for label, players in [("VICTORY", result["victory"]),
                            ("DEFEAT",  result["defeat"])]:
        print(f"  {label}")
        for p in players:
            print(f"    {p['name']:<22} "
                  f"K:{p['k']:>2} D:{p['d']:>2} A:{p['a']:>2}  "
                  f"DMG:{p['dmg']:>6,}  HEAL:{p['heal']:>6,}  "
                  f"ACC:{p['acc']:>3}%")
        print()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    src = Path(sys.argv[1])
    if not src.exists():
        print(f"File not found: {src}")
        sys.exit(1)

    if "--calibrate" in sys.argv:
        calibrate(src)
        sys.exit(0)

    # Determine output path
    out = (
        Path(sys.argv[2])
        if len(sys.argv) > 2 and not sys.argv[2].startswith("--")
        else src.with_suffix(".csv")
    )

    result = parse_screenshot(src)
    write_csv(result, out)
    print_summary(result)
