"""
Generate an animated ASCII/typographic portrait SVG from assets/input/portrait.jpg.

WHY THIS PIPELINE (see README / project notes for the full explanation):
The source image is a FLAT-COLOR VECTOR ILLUSTRATION (hard silhouette edges,
a handful of solid tonal regions, a uniform near-black background) rather
than a photograph. A generic "photo -> grayscale -> dither" ASCII filter is
the wrong tool here: it assumes continuous tone and noise, and it would
either mush the flat regions into mid-density noise or blow out the crisp
silhouette. Instead we:

  1. Estimate the background color from the image corners/edges and remove
     ONLY pixels close to that color (a color-distance mask), which keeps
     dark regions that belong to the subject (the shadow half of the
     illustration) intact instead of stripping them out as "background".
  2. Posterize the *subject* luminance into a small number of discrete bands
     (stretched to the subject's own min/max, not the whole image's), and
     hand-map each band to a character of deliberately increasing visual
     weight. This preserves the flat-region structure instead of adding
     fake photographic gradients.
  3. Downsample on a monospace character grid sized to match real
     monospace glyph proportions (~0.55 width:height) so the silhouette
     isn't stretched or squashed.

Run with --debug to dump intermediate PNGs (mask, isolated subject,
posterized preview) to generated/_debug/ for visual inspection.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, GENERATED, ASSETS, write_if_changed, FONT_FAMILY, embedded_font_style  # noqa: E402

INPUT_PATH = ASSETS / "input" / "portrait.jpg"
OUTPUT_PATH = GENERATED / "portrait.svg"
DEBUG_DIR = GENERATED / "_debug"

# Grid / typography
GRID_COLS = 100                 # character columns
CHAR_ASPECT = 0.52               # width:height ratio of a monospace glyph cell
CELL_W = 8                       # px per character cell (width)
CELL_H = CELL_W / CHAR_ASPECT    # px per character cell (height)

# Character ramp, ordered light -> heavy, chosen by hand for even visual
# weight steps (not a copy-pasted generic ASCII ramp).
RAMP = [" ", ".", ":", "o", "O", "#", "@"]

BG_DISTANCE_THRESHOLD = 34       # color-distance below this = background
EDGE_SAMPLE_PATCH = 6            # px patch size used to sample corner color


def sample_background_color(arr: np.ndarray) -> np.ndarray:
    """Average small patches from all four corners to estimate bg color."""
    h, w, _ = arr.shape
    p = EDGE_SAMPLE_PATCH
    patches = [
        arr[0:p, 0:p], arr[0:p, w - p:w],
        arr[h - p:h, 0:p], arr[h - p:h, w - p:w],
    ]
    samples = np.concatenate([patch.reshape(-1, 3) for patch in patches], axis=0)
    return samples.mean(axis=0)


def build_masks(arr: np.ndarray):
    """Remove background by FLOOD-FILL from the border, not a flat global
    color threshold. This is the key fix for illustrations that contain
    dark subject regions similar in color to the background: a pixel that
    matches the background color but is *enclosed* by subject pixels (not
    reachable from the border without crossing non-background color) is
    kept as part of the subject instead of being erased.
    """
    bg_color = sample_background_color(arr)
    dist = np.linalg.norm(arr.astype(np.float32) - bg_color, axis=2)
    bg_like = dist <= BG_DISTANCE_THRESHOLD

    labeled, num = ndimage.label(bg_like, structure=np.ones((3, 3)))
    border_labels = set(labeled[0, :]) | set(labeled[-1, :]) | set(labeled[:, 0]) | set(labeled[:, -1])
    border_labels.discard(0)

    true_bg = np.isin(labeled, list(border_labels)) if border_labels else np.zeros_like(bg_like)
    subject_mask = ~true_bg
    return subject_mask, bg_color, dist


def subject_bbox(mask: np.ndarray, pad_frac: float = 0.04):
    ys, xs = np.where(mask)
    if len(xs) == 0:
        h, w = mask.shape
        return 0, 0, w, h
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    h, w = mask.shape
    pad_x = int((x1 - x0) * pad_frac) + 2
    pad_y = int((y1 - y0) * pad_frac) + 2
    return (
        max(0, x0 - pad_x), max(0, y0 - pad_y),
        min(w, x1 + pad_x), min(h, y1 + pad_y),
    )


def luminance(arr: np.ndarray) -> np.ndarray:
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def downsample_grid(gray: np.ndarray, mask: np.ndarray, cols: int, rows: int):
    """Average-pool gray/mask into a cols x rows character grid."""
    h, w = gray.shape
    cell_w = w / cols
    cell_h = h / rows
    out_gray = np.zeros((rows, cols), dtype=np.float32)
    out_cov = np.zeros((rows, cols), dtype=np.float32)  # fraction of cell that is subject
    for r in range(rows):
        y0, y1 = int(r * cell_h), max(int((r + 1) * cell_h), int(r * cell_h) + 1)
        for c in range(cols):
            x0, x1 = int(c * cell_w), max(int((c + 1) * cell_w), int(c * cell_w) + 1)
            g_cell = gray[y0:y1, x0:x1]
            m_cell = mask[y0:y1, x0:x1]
            out_cov[r, c] = m_cell.mean() if m_cell.size else 0.0
            if m_cell.any():
                out_gray[r, c] = g_cell[m_cell].mean()
            else:
                out_gray[r, c] = g_cell.mean() if g_cell.size else 0.0
    return out_gray, out_cov


def posterize_to_chars(gray_grid: np.ndarray, cov_grid: np.ndarray, coverage_threshold: float = 0.16):
    subject_vals = gray_grid[cov_grid >= coverage_threshold]
    if subject_vals.size == 0:
        lo, hi = 0.0, 255.0
    else:
        lo, hi = float(subject_vals.min()), float(subject_vals.max())
        if hi - lo < 1e-3:
            hi = lo + 1.0
    n = len(RAMP)
    chars = np.full(gray_grid.shape, " ", dtype="<U1")
    rows, cols = gray_grid.shape
    for r in range(rows):
        for c in range(cols):
            if cov_grid[r, c] < coverage_threshold:
                continue
            v = (gray_grid[r, c] - lo) / (hi - lo)
            v = min(max(v, 0.0), 1.0)
            # Darker subject pixels -> heavier characters (index further in ramp)
            idx = int(round((1.0 - v) * (n - 1)))
            chars[r, c] = RAMP[idx]
    return chars, (lo, hi)


def save_debug_images(arr, mask, dist, gray_grid, cov_grid, chars):
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    Image.fromarray((mask * 255).astype(np.uint8)).save(DEBUG_DIR / "01_mask.png")
    isolated = arr.copy()
    isolated[~mask] = 0
    Image.fromarray(isolated).save(DEBUG_DIR / "02_isolated_subject.png")
    dist_norm = (255 * (dist / dist.max())).astype(np.uint8)
    Image.fromarray(dist_norm).save(DEBUG_DIR / "03_bg_distance.png")

    # Render the char grid as a quick raster preview so it's eyeball-able
    # without opening the SVG.
    rows, cols = chars.shape
    scale = 8
    prev = Image.new("L", (cols * scale, rows * scale), color=0)
    px = prev.load()
    ramp_to_val = {c: int(255 * i / (len(RAMP) - 1)) for i, c in enumerate(RAMP)}
    for r in range(rows):
        for c in range(cols):
            v = ramp_to_val[chars[r, c]]
            for yy in range(scale):
                for xx in range(scale):
                    px[c * scale + xx, r * scale + yy] = v
    prev.save(DEBUG_DIR / "04_char_preview.png")
    print(f"Debug images written to {DEBUG_DIR}")


def build_svg(chars: np.ndarray, gray_grid: np.ndarray, cov_grid: np.ndarray) -> str:
    rows, cols = chars.shape
    width = int(cols * CELL_W)
    height = int(rows * CELL_H)

    # Darkest possible glyph maps to a bright-ish gray, background stays
    # empty. Two-tone (light/dark half of illustration) is preserved by
    # varying fill lightness slightly with the char's own band, not a flat
    # single color -- keeps the split-face structure readable.
    min_l, max_l = 55, 235  # svg fill lightness range (0-255ish -> css gray)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT_FAMILY}" role="img" '
        f'aria-label="ASCII-style portrait">',
        f'<rect width="{width}" height="{height}" fill="none"/>',
        embedded_font_style(),
    ]

    # One <text> element per row, characters positioned with fixed
    # advance via xml:space + tspans is verbose; instead we rely on a
    # monospace font-family and letter-spacing tuned to CELL_W, which
    # keeps the file small (one <text> per row instead of per glyph).
    font_size = CELL_H * 0.92
    letter_spacing = 0.0  # monospace already advances at glyph width

    row_duration = 0.035  # seconds of stagger per row, typewriter feel
    for r in range(rows):
        row_chars = chars[r]
        if not (row_chars != " ").any():
            continue
        text = "".join(row_chars)
        # collapse leading/trailing spaces into an x-offset so short rows
        # don't pay for empty glyph cells at draw time
        stripped = text.rstrip()
        left_pad = len(stripped) - len(stripped.lstrip(" "))
        stripped_l = stripped.lstrip(" ")
        if not stripped_l:
            continue
        x = (left_pad) * CELL_W
        y = int((r + 0.82) * CELL_H)

        # Per-row grayscale fill approximated from the row's average band
        vals = gray_grid[r][cov_grid[r] >= 0.16]
        if vals.size:
            # normalize within full image, purely for a subtle tonal cue
            t = (vals.mean() - gray_grid.min()) / max(1.0, (gray_grid.max() - gray_grid.min()))
            lightness = int(min_l + t * (max_l - min_l))
        else:
            lightness = max_l
        fill = f"rgb({lightness},{lightness},{lightness})"

        begin = round(r * row_duration, 3)
        esc_text = (
            stripped_l.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        lines.append(
            f'<text x="{x}" y="{y}" font-size="{font_size:.2f}" '
            f'xml:space="preserve" fill="{fill}" opacity="0">'
            f'{esc_text}'
            f'<animate attributeName="opacity" from="0" to="1" '
            f'begin="{begin}s" dur="0.25s" fill="freeze" calcMode="linear"/>'
            f'</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="write intermediate images to generated/_debug/")
    parser.add_argument("--input", default=str(INPUT_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()

    img = Image.open(args.input).convert("RGB")
    arr = np.array(img)

    mask, bg_color, dist = build_masks(arr)
    x0, y0, x1, y1 = subject_bbox(mask)
    arr_c = arr[y0:y1, x0:x1]
    mask_c = mask[y0:y1, x0:x1]

    gray = luminance(arr_c)
    h_c, w_c = gray.shape
    rows = max(1, round(GRID_COLS * (h_c / w_c) * CHAR_ASPECT))

    gray_grid, cov_grid = downsample_grid(gray, mask_c, GRID_COLS, rows)
    chars, (lo, hi) = posterize_to_chars(gray_grid, cov_grid)

    if args.debug:
        save_debug_images(arr, mask, dist, gray_grid, cov_grid, chars)
        print(f"bg_color~={bg_color}, subject luminance range=({lo:.1f},{hi:.1f}), grid={GRID_COLS}x{rows}")

    svg = build_svg(chars, gray_grid, cov_grid)
    changed = write_if_changed(Path(args.output), svg)
    print(f"{'wrote' if changed else 'unchanged'}: {args.output}")


if __name__ == "__main__":
    main()
