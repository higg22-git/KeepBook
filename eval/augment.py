#!/usr/bin/env python3
"""Synthesize realistic phone-photo degradations of clean document images.

For every ``*_clean_*.png`` under --src, produces one or more "photo" variants
(perspective warp + rotation + desk framing, plus 2-3 randomly composed
degradations) and appends matching entries to labels.json using the same
doc_type/fields as the source image (augmentation never changes ground truth).

Deterministic (seeded per source file + variant index) and idempotent: if an
output file already exists it is not regenerated, and labels.json is only
backfilled (never duplicated) for it.

Usage:
    python augment.py --src testset/ --labels labels.json --out testset/
    python augment.py --src testset/ --labels labels.json --out testset/ --per-image 2 --seed 7
"""
import argparse
import copy
import hashlib
import io
import json
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

EFFECT_BUCKET = "photo"
DEGRADATIONS = ["shadow", "vignette", "blur", "noise", "jpeg"]


def derive_seed(base_seed: int, *parts) -> int:
    """Deterministic per-(file, variant) seed, independent of processing order."""
    h = hashlib.sha256(f"{base_seed}:{':'.join(str(p) for p in parts)}".encode()).hexdigest()
    return int(h[:16], 16)


def find_coeffs(pa, pb):
    """8 coeffs for PIL's PERSPECTIVE transform mapping output quad pa -> input quad pb."""
    matrix = []
    for (xo, yo), (xi, yi) in zip(pa, pb):
        matrix.append([xo, yo, 1, 0, 0, 0, -xi * xo, -xi * yo])
        matrix.append([0, 0, 0, xo, yo, 1, -yi * xo, -yi * yo])
    a = np.array(matrix, dtype=np.float64)
    b = np.array(pb, dtype=np.float64).reshape(8)
    return np.linalg.solve(a, b).tolist()


def make_desk_background(w: int, h: int, rng: random.Random) -> Image.Image:
    """A deterministic, vaguely woodgrain/desk-mat texture to frame the page with."""
    np_rng = np.random.default_rng(rng.randint(0, 2**32 - 1))
    themes = [
        (60, 40, 25),   # wood brown
        (45, 45, 48),   # charcoal desk
        (35, 40, 50),   # navy mat
        (70, 55, 35),   # lighter wood
    ]
    base = np.array(rng.choice(themes), dtype=np.float64)

    grain = np_rng.normal(0, 1, w).cumsum()
    grain = (grain - grain.min()) / (grain.max() - grain.min() + 1e-6)
    grain_2d = np.tile(grain, (h, 1))
    grain_2d = grain_2d + np_rng.normal(0, 0.04, (h, 1))

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    light_angle = rng.uniform(0, 2 * math.pi)
    grad = xx * math.cos(light_angle) + yy * math.sin(light_angle)
    grad = (grad - grad.min()) / (grad.max() - grad.min() + 1e-6)

    shade = 0.75 + 0.35 * grain_2d + 0.15 * grad
    shade = np.clip(shade, 0.5, 1.25)

    tex_noise = np_rng.normal(0, 6, (h, w))
    img = base[None, None, :] * shade[:, :, None] + tex_noise[:, :, None]
    img = np.clip(img, 0, 255).astype(np.uint8)
    return Image.fromarray(img, "RGB").convert("RGBA")


def photo_capture(img: Image.Image, rng: random.Random) -> Image.Image:
    """Rotate + perspective-warp the page like a handheld shot, then paste onto a desk."""
    src = img.convert("RGBA")
    w, h = src.size

    angle_deg = rng.uniform(1.0, 4.0) * rng.choice([-1, 1])
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    cx, cy = w / 2, h / 2

    corners0 = [(0, 0), (w, 0), (w, h), (0, h)]

    def rotate_pt(p):
        x, y = p[0] - cx, p[1] - cy
        return (cx + x * cos_t - y * sin_t, cy + x * sin_t + y * cos_t)

    jitter = rng.uniform(0.015, 0.03) * min(w, h)
    rotated = [rotate_pt(p) for p in corners0]
    jittered = [(x + rng.uniform(-jitter, jitter), y + rng.uniform(-jitter, jitter)) for x, y in rotated]

    xs = [p[0] for p in jittered]
    ys = [p[1] for p in jittered]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    bw, bh = maxx - minx, maxy - miny

    pad = rng.uniform(0.07, 0.13) * min(w, h)
    canvas_w = int(bw + 2 * pad)
    canvas_h = int(bh + 2 * pad)

    offx = pad - minx
    offy = pad - miny
    placed = [(x + offx, y + offy) for x, y in jittered]

    coeffs = find_coeffs(placed, corners0)
    warped = src.transform(
        (canvas_w, canvas_h), Image.PERSPECTIVE, coeffs,
        resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0),
    )

    desk = make_desk_background(canvas_w, canvas_h, rng)

    # soft drop shadow beneath the page, before pasting the page itself
    alpha = warped.split()[3]
    shadow_offset = max(2, int(0.006 * min(w, h)))
    shadow_mask = Image.new("L", (canvas_w, canvas_h), 0)
    shadow_mask.paste(alpha, (shadow_offset, shadow_offset))
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(radius=max(3, int(0.01 * min(w, h)))))
    shadow_dark = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 110))
    shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    shadow_layer = Image.composite(shadow_dark, shadow_layer, shadow_mask)
    desk = Image.alpha_composite(desk, shadow_layer)

    desk.paste(warped, (0, 0), warped)
    return desk.convert("RGB")


def apply_shadow(img: Image.Image, rng: random.Random) -> Image.Image:
    """Soft directional shadow gradient, like a hand or the phone itself over part of the page."""
    w, h = img.size
    arr = np.asarray(img).astype(np.float64)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    edge = rng.choice(["left", "right", "top", "bottom", "corner"])
    if edge == "left":
        d = xx / w
    elif edge == "right":
        d = 1 - xx / w
    elif edge == "top":
        d = yy / h
    elif edge == "bottom":
        d = 1 - yy / h
    else:
        cx, cy = rng.choice([(0, 0), (w, 0), (0, h), (w, h)])
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / math.hypot(w, h)
    d = np.clip(d, 0, 1)
    strength = rng.uniform(0.12, 0.22)
    falloff = rng.uniform(1.2, 2.0)
    mask = 1 - strength * (1 - d) ** falloff
    arr *= mask[:, :, None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def apply_vignette(img: Image.Image, rng: random.Random) -> Image.Image:
    """Uneven brightness falling off toward the corners."""
    w, h = img.size
    arr = np.asarray(img).astype(np.float64)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy = w / 2, h / 2
    dist = np.sqrt(((xx - cx) / (w / 2)) ** 2 + ((yy - cy) / (h / 2)) ** 2)
    strength = rng.uniform(0.08, 0.15)
    mask = 1 - strength * np.clip(dist, 0, 1.4) ** 2
    arr *= mask[:, :, None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def _shift(arr: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Shift an HxWxC array by (dx, dy) pixels, replicating edge pixels (no wraparound)."""
    if dx == 0 and dy == 0:
        return arr
    h, w = arr.shape[:2]
    pad_y, pad_x = abs(dy), abs(dx)
    padded = np.pad(arr, ((pad_y, pad_y), (pad_x, pad_x), (0, 0)), mode="edge")
    y0 = pad_y - dy
    x0 = pad_x - dx
    return padded[y0:y0 + h, x0:x0 + w]


def apply_blur(img: Image.Image, rng: random.Random) -> Image.Image:
    """Mild gaussian blur, or occasionally a slight directional motion blur."""
    if rng.random() < 0.7:
        radius = rng.uniform(0.4, 0.85)
        return img.filter(ImageFilter.GaussianBlur(radius=radius))

    # smooth shift-and-average motion blur (avoids ringing that a sparse
    # discrete kernel produces once JPEG recompression is layered on top)
    angle = rng.uniform(0, math.pi)
    dist = rng.uniform(2.5, 4.5)
    dx, dy = math.cos(angle) * dist, math.sin(angle) * dist
    n_samples = 7
    arr = np.asarray(img).astype(np.float64)
    acc = np.zeros_like(arr)
    for k in range(n_samples):
        t = k / (n_samples - 1) - 0.5
        acc += _shift(arr, int(round(t * dx)), int(round(t * dy)))
    acc /= n_samples
    return Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB")


def apply_noise(img: Image.Image, rng: random.Random, np_rng: np.random.Generator) -> Image.Image:
    """Sensor noise."""
    arr = np.asarray(img).astype(np.float64)
    sigma = rng.uniform(3, 7)
    noise = np_rng.normal(0, sigma, arr.shape)
    arr += noise
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def apply_jpeg(img: Image.Image, rng: random.Random) -> Image.Image:
    """Recompress through JPEG at a phone-camera-ish quality."""
    quality = rng.randint(60, 80)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def augment_one(img: Image.Image, seed: int) -> Image.Image:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    out = photo_capture(img, rng)

    n_effects = rng.randint(2, 3)
    chosen = set(rng.sample(DEGRADATIONS, n_effects))
    # fixed, physically-sensible order: scene lighting -> optics -> sensor -> codec
    for effect in DEGRADATIONS:
        if effect not in chosen:
            continue
        if effect == "shadow":
            out = apply_shadow(out, rng)
        elif effect == "vignette":
            out = apply_vignette(out, rng)
        elif effect == "blur":
            out = apply_blur(out, rng)
        elif effect == "noise":
            out = apply_noise(out, rng, np_rng)
        elif effect == "jpeg":
            out = apply_jpeg(out, rng)
    return out


def bucket_name(idx: int) -> str:
    return EFFECT_BUCKET if idx == 0 else f"{EFFECT_BUCKET}{idx + 1}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="directory to search for *_clean_*.png")
    ap.add_argument("--labels", required=True, help="labels.json to read ground truth from and append to")
    ap.add_argument("--out", required=True, help="directory to write variant PNGs to")
    ap.add_argument("--per-image", type=int, default=1, help="number of variants per source image")
    ap.add_argument("--seed", type=int, default=1337, help="base seed for determinism")
    args = ap.parse_args()

    src_dir = Path(args.src)
    out_dir = Path(args.out)
    labels_path = Path(args.labels)
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = {}
    if labels_path.exists():
        labels = json.loads(labels_path.read_text())

    sources = sorted(src_dir.glob("*_clean_*.png"))
    if not sources:
        print(f"no *_clean_*.png files found in {src_dir}")

    generated = 0
    skipped = 0
    backfilled = 0

    for src_path in sources:
        stem = src_path.stem
        src_label = labels.get(src_path.name)
        if src_label is None:
            print(f"WARNING: no labels.json entry for {src_path.name}, skipping")
            continue

        for i in range(args.per_image):
            bucket = bucket_name(i)
            out_name = f"{stem.replace('clean', bucket, 1)}{src_path.suffix}"
            out_path = out_dir / out_name

            if out_path.exists():
                skipped += 1
                if out_name not in labels:
                    labels[out_name] = copy.deepcopy(src_label)
                    backfilled += 1
                continue

            seed = derive_seed(args.seed, src_path.name, i)
            img = Image.open(src_path)
            variant = augment_one(img, seed)
            variant.save(out_path)
            labels[out_name] = copy.deepcopy(src_label)
            generated += 1

    labels_path.write_text(json.dumps(labels, indent=2, sort_keys=True) + "\n")
    print(f"generated={generated} skipped(existing)={skipped} backfilled_labels={backfilled}")
    print(f"labels written to {labels_path}")


if __name__ == "__main__":
    main()
