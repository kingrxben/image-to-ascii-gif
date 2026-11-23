#!/usr/bin/env python3
"""
Reusable tool to convert images, GIFs, and videos into animated ASCII art.

Supports PNG, JPG, JPEG, WEBP, BMP, TIFF, GIF, and common video formats
(MP4, MOV, WEBM, MKV, AVI) via Pillow + imageio/ffmpeg.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import imageio.v3 as iio
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageSequence

# ---------------------------------------------------------------------------
# Presets & Constants
# ---------------------------------------------------------------------------

PALETTES: dict[str, str] = {
    "detailed": " .'`^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$",
    "classic": " .:-=+*#%@",
    "blocks": " ░▒▓█",
    "minimal": " .·:+*#",
    "matrix": " .,:;irsXA253hMHGS#9B&@",
}

DETAIL_PRESETS: dict[str, dict[str, int | float]] = {
    "low": {"width": 75, "font_size": 15, "edge_boost": 0.12},
    "medium": {"width": 100, "font_size": 13, "edge_boost": 0.16},
    "high": {"width": 125, "font_size": 12, "edge_boost": 0.20},
    "ultra": {"width": 160, "font_size": 10, "edge_boost": 0.24},
}

COLOR_MODES: dict[str, dict[str, object]] = {
    "color": {"bg": (10, 12, 18), "invert": False, "tint": None},
    "amber": {"bg": (14, 10, 6), "invert": False, "tint": (255, 182, 66)},
    "green": {"bg": (6, 14, 9), "invert": False, "tint": (72, 255, 130)},
    "cyan": {"bg": (7, 13, 20), "invert": False, "tint": (96, 232, 255)},
    "mono": {"bg": (12, 12, 14), "invert": False, "tint": (242, 242, 245)},
    "paper": {"bg": (244, 240, 232), "invert": True, "tint": (28, 28, 32)},
}

EFFECTS = ("luminous", "shimmer", "sweep", "breathe", "scanline", "drift", "none")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".gif"}

FONT_CANDIDATES = [
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Monaco.ttf",
    "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
    "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
    "/System/Library/Fonts/Courier.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
]


@dataclass
class RenderConfig:
    width: int = 125
    detail: str = "high"
    palette: str = "detailed"
    color_mode: str = "color"
    bg_color: tuple[int, int, int] | None = None
    effect: str = "luminous"
    intensity: float = 0.55
    speed: float = 1.0
    fps: int = 12
    frames: int = 24
    max_video_frames: int = 120
    font_size: int = 12
    font_path: str | None = None
    contrast: float = 1.12
    saturation: float = 1.18
    gamma: float = 0.94
    glow: float = 0.22
    export_png: bool = True
    export_gif: bool = True
    export_mp4: bool = True
    export_txt: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_hex_color(value: str) -> tuple[int, int, int]:
    cleaned = value.strip().lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join(c * 2 for c in cleaned)
    if len(cleaned) != 6:
        raise ValueError(f"Color hexadecimal inválido: {value!r}")
    return (int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16))


def resolve_palette(palette_arg: str) -> str:
    if palette_arg in PALETTES:
        return PALETTES[palette_arg]
    if len(palette_arg) < 2:
        raise ValueError("La paleta personalizada debe tener al menos 2 caracteres.")
    return palette_arg


def load_monospace_font(font_size: int, font_path: str | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [font_path] if font_path else []
    candidates.extend(FONT_CANDIDATES)
    for path in candidates:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=font_size)
            except OSError:
                continue
    return ImageFont.load_default()


def build_glyph_atlas(
    chars: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> tuple[np.ndarray, int, int]:
    """Pre-render every character in `chars` to a float32 alpha mask [0..1]."""
    # Determine uniform monospace cell dimensions
    sample_chars = "M@#W8B0Qg_|/\\"
    max_w = 0
    min_top = 10_000
    max_bottom = -10_000
    for ch in set(chars + sample_chars):
        bbox = font.getbbox(ch)
        if bbox:
            w = bbox[2] - bbox[0]
            max_w = max(max_w, w)
            min_top = min(min_top, bbox[1])
            max_bottom = max(max_bottom, bbox[3])

    adv = int(math.ceil(font.getlength("M"))) if hasattr(font, "getlength") else max_w
    cell_w = max(adv, max_w, 6)
    cell_h = max(max_bottom - min_top + 2, int(cell_w * 1.45), 10)

    atlas = np.zeros((len(chars), cell_h, cell_w), dtype=np.float32)
    from PIL import ImageDraw

    y_offset = -min_top + 1
    for idx, ch in enumerate(chars):
        tile = Image.new("L", (cell_w, cell_h), 0)
        draw = ImageDraw.Draw(tile)
        bbox = font.getbbox(ch)
        if bbox:
            ch_w = bbox[2] - bbox[0]
            x_pos = (cell_w - ch_w) // 2 - bbox[0]
        else:
            x_pos = 0
        draw.text((x_pos, y_offset), ch, fill=255, font=font)
        atlas[idx] = np.asarray(tile, dtype=np.float32) / 255.0

    return atlas, cell_w, cell_h


def load_input_frames(
    input_path: Path,
    max_frames: int = 120,
    target_fps: int = 12,
) -> tuple[list[Image.Image], float, bool]:
    """
    Load static image, animated GIF, or video into RGB PIL frames.
    Returns (frames, source_fps, is_animated_source).
    """
    ext = input_path.suffix.lower()

    if ext in VIDEO_EXTENSIONS:
        frames: list[Image.Image] = []
        meta = {}
        try:
            meta = iio.immeta(input_path, plugin="pyav")
        except Exception:
            try:
                meta = iio.immeta(input_path)
            except Exception:
                meta = {}

        src_fps = float(meta.get("fps", target_fps) or target_fps)
        step = max(1, int(round(src_fps / max(1, target_fps))))

        for idx, arr in enumerate(iio.imiter(input_path)):
            if idx % step != 0:
                continue
            frames.append(Image.fromarray(arr).convert("RGB"))
            if len(frames) >= max_frames:
                break

        if not frames:
            raise RuntimeError(f"No se pudieron leer fotogramas del video: {input_path}")

        effective_fps = max(1.0, min(src_fps / step, float(target_fps)))
        return frames, effective_fps, len(frames) > 1

    with Image.open(input_path) as img:
        is_animated = bool(getattr(img, "is_animated", False)) and getattr(img, "n_frames", 1) > 1
        if is_animated:
            raw_frames: list[Image.Image] = []
            durations: list[int] = []
            for frame in ImageSequence.Iterator(img):
                durations.append(int(frame.info.get("duration", int(1000 / target_fps)) or int(1000 / target_fps)))
                raw_frames.append(frame.convert("RGB"))
            step = max(1, math.ceil(len(raw_frames) / max_frames))
            sampled = raw_frames[::step]
            avg_ms = sum(durations) / max(1, len(durations))
            src_fps = max(1.0, min(30.0, 1000.0 / max(10.0, avg_ms * step)))
            return sampled, src_fps, True

        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            bg = Image.new("RGB", img.size, (10, 12, 18))
            rgba = img.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            return [bg], float(target_fps), False

        return [img.convert("RGB")], float(target_fps), False


def prepare_grid(
    img: Image.Image,
    cols: int,
    cell_w: int,
    cell_h: int,
    contrast: float,
    saturation: float,
    gamma: float,
    edge_boost: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Resize image to the ASCII character grid preserving exact visual aspect ratio.
    Returns (rgb_float [H,W,3], luminance [H,W], edge_map [H,W]) all in [0, 1].
    """
    src_w, src_h = img.size
    aspect = src_h / max(1, src_w)
    rows = max(12, int(round(cols * aspect * (cell_w / max(1, cell_h)))))

    # Subtle enhancement before downsampling to keep contours crisp
    enhanced = ImageEnhance.Contrast(img).enhance(contrast)
    enhanced = ImageEnhance.Color(enhanced).enhance(saturation)
    enhanced = enhanced.filter(ImageFilter.UnsharpMask(radius=1.2, percent=95, threshold=3))

    resized = enhanced.resize((cols, rows), Image.Resampling.LANCZOS)
    rgb = np.asarray(resized, dtype=np.float32) / 255.0

    # Perceptual luminance (Rec. 709)
    lum = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]

    # Gentle percentile stretch so shadows and highlights use the full character range
    lo, hi = np.percentile(lum, [1.5, 99.0])
    if hi - lo > 0.08:
        lum = np.clip((lum - lo) / (hi - lo), 0.0, 1.0)

    # Gamma correction
    lum = np.power(np.clip(lum, 0.0, 1.0), gamma)

    # Edge magnitude for preserving fine structural detail (crown, face, outlines)
    gy, gx = np.gradient(lum)
    edge = np.sqrt(gx * gx + gy * gy)
    edge_max = float(np.percentile(edge, 98.5))
    if edge_max > 1e-5:
        edge = np.clip(edge / edge_max, 0.0, 1.0)
    else:
        edge = np.zeros_like(lum)

    # Subtle micro-contrast along edges
    if edge_boost > 0:
        lum = np.clip(lum + (edge - 0.25) * edge_boost * 0.45, 0.0, 1.0)

    return rgb, lum, edge


def apply_animation_effect(
    rgb: np.ndarray,
    lum: np.ndarray,
    edge: np.ndarray,
    phase: float,
    effect: str,
    intensity: float,
    noise_phase: np.ndarray,
    xx: np.ndarray,
    yy: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Apply a seamless periodic visual modulation (phase in [0, 2*pi)).
    Designed to preserve subject recognizability while bringing light and texture alive.
    """
    if effect == "none" or intensity <= 0:
        return rgb, lum

    strength = float(np.clip(intensity, 0.0, 1.5))
    rgb_out = rgb.copy()
    lum_out = lum.copy()

    if effect == "luminous":
        # 1) Soft diagonal light sweep
        diag = xx * 0.72 + yy * 0.48
        wave = 0.5 + 0.5 * np.cos(2.0 * math.pi * diag - phase)
        sweep = np.power(wave, 5.0)

        # 2) Specular shimmer on bright regions & intricate metallic/detail highlights
        highlight_mask = np.clip((lum - 0.52) / 0.48, 0.0, 1.0) ** 1.4
        detail_mask = np.clip(edge * 0.55 + highlight_mask * 0.85, 0.0, 1.0)
        twinkle = np.sin(phase + noise_phase) * 0.6 + np.sin(2.0 * phase - noise_phase * 1.7) * 0.4
        shimmer = twinkle * detail_mask

        # 3) Very gentle ambient breathing
        breath = 0.5 + 0.5 * math.sin(phase)

        lum_delta = (
            sweep * (0.11 * strength) * (0.35 + 0.65 * lum)
            + shimmer * (0.09 * strength)
            + (breath - 0.5) * (0.035 * strength)
        )
        lum_out = np.clip(lum + lum_delta, 0.0, 1.0)

        color_boost = (
            1.0
            + sweep * (0.20 * strength)
            + np.maximum(0.0, shimmer) * (0.24 * strength)
            + (breath - 0.5) * (0.05 * strength)
        )
        rgb_out = np.clip(rgb * color_boost[:, :, None], 0.0, 1.0)

        # Warm specular lift on the brightest flares during shimmer peaks
        spark = np.clip(highlight_mask * np.maximum(0.0, twinkle), 0.0, 1.0) * (0.14 * strength)
        rgb_out = np.clip(rgb_out + spark[:, :, None], 0.0, 1.0)

    elif effect == "shimmer":
        highlight_mask = np.clip((lum - 0.35) / 0.65, 0.0, 1.0)
        twinkle = np.sin(phase + noise_phase) * 0.65 + np.cos(2.0 * phase + noise_phase * 1.3) * 0.35
        mod = twinkle * (0.3 + 0.7 * highlight_mask + 0.35 * edge)
        lum_out = np.clip(lum + mod * (0.12 * strength), 0.0, 1.0)
        rgb_out = np.clip(rgb * (1.0 + mod[:, :, None] * (0.18 * strength)), 0.0, 1.0)

    elif effect == "sweep":
        diag = xx * 0.75 + yy * 0.45
        band = np.power(0.5 + 0.5 * np.cos(2.0 * math.pi * diag - phase), 6.0)
        lum_out = np.clip(lum + band * (0.18 * strength) * (0.25 + 0.75 * lum), 0.0, 1.0)
        rgb_out = np.clip(rgb * (1.0 + band[:, :, None] * (0.28 * strength)) + band[:, :, None] * (0.06 * strength), 0.0, 1.0)

    elif effect == "breathe":
        pulse = math.sin(phase)
        lum_out = np.clip(lum * (1.0 + pulse * 0.10 * strength) + pulse * 0.03 * strength, 0.0, 1.0)
        rgb_out = np.clip(rgb * (1.0 + pulse * 0.14 * strength), 0.0, 1.0)

    elif effect == "scanline":
        pos = (phase / (2.0 * math.pi)) % 1.0
        dist = np.abs(((yy - pos + 0.5) % 1.0) - 0.5)
        beam = np.exp(-(dist * dist) / (2.0 * (0.055 ** 2)))
        fine_lines = 0.94 + 0.06 * np.sin(yy * lum.shape[0] * math.pi)
        lum_out = np.clip(lum * fine_lines + beam * (0.18 * strength), 0.0, 1.0)
        rgb_out = np.clip(rgb * fine_lines[:, :, None] * (1.0 + beam[:, :, None] * (0.26 * strength)), 0.0, 1.0)

    elif effect == "drift":
        ripple = np.sin(2.0 * math.pi * (yy * 2.0 + xx * 0.5) - phase)
        lum_out = np.clip(lum + ripple * (0.07 * strength) * (0.3 + 0.7 * edge + 0.4 * lum), 0.0, 1.0)
        rgb_out = np.clip(rgb * (1.0 + ripple[:, :, None] * (0.11 * strength)), 0.0, 1.0)

    return rgb_out, lum_out


def render_ascii_frame(
    rgb: np.ndarray,
    lum: np.ndarray,
    atlas: np.ndarray,
    chars: str,
    color_mode: str,
    bg_rgb: tuple[int, int, int],
    glow: float,
) -> tuple[Image.Image, str]:
    """Render a single ASCII frame using the precomputed glyph atlas."""
    mode_cfg = COLOR_MODES[color_mode]
    invert = bool(mode_cfg["invert"])
    tint = mode_cfg["tint"]

    mapped_lum = (1.0 - lum) if invert else lum
    n_chars = len(chars)
    indices = np.clip((mapped_lum * (n_chars - 1) + 0.5).astype(np.int32), 0, n_chars - 1)

    # Text lines
    lines = ["".join(chars[i] for i in row) for row in indices]
    ascii_text = "\n".join(lines)

    # Per-cell foreground color in [0, 255]
    if tint is None:
        # Slight lift so dark subject details (shadows, faces) stay readable on dark bg
        fg = np.clip(rgb * 1.12 + 0.025, 0.0, 1.0) * 255.0
    else:
        tint_arr = np.array(tint, dtype=np.float32)[None, None, :]
        if invert:
            # Dark ink on light paper: darker pixels get full ink, lighter pixels fade toward paper
            ink_strength = np.clip(mapped_lum * 1.15, 0.0, 1.0)[:, :, None]
            bg_arr = np.array(bg_rgb, dtype=np.float32)[None, None, :]
            fg = bg_arr * (1.0 - ink_strength) + tint_arr * ink_strength
        else:
            intensity = np.clip(0.18 + 0.92 * mapped_lum, 0.0, 1.0)[:, :, None]
            fg = tint_arr * intensity

    # Vectorized glyph compositing: (rows, cols, cell_h, cell_w)
    alpha = atlas[indices]  # float32 [0..1]
    rows, cols, cell_h, cell_w = alpha.shape
    bg_arr = np.array(bg_rgb, dtype=np.float32)

    alpha_exp = alpha[:, :, :, :, None]
    fg_exp = fg[:, :, None, None, :]
    comp = bg_arr[None, None, None, None, :] * (1.0 - alpha_exp) + fg_exp * alpha_exp

    img_arr = comp.transpose(0, 2, 1, 3, 4).reshape(rows * cell_h, cols * cell_w, 3)
    frame_img = Image.fromarray(np.clip(img_arr, 0, 255).astype(np.uint8), mode="RGB")

    # Optional subtle bloom/glow on dark backgrounds
    if glow > 0 and not invert:
        blur = frame_img.filter(ImageFilter.GaussianBlur(radius=2.2))
        base_f = np.asarray(frame_img, dtype=np.float32)
        blur_f = np.asarray(blur, dtype=np.float32)
        # Screen-like soft glow focused on brighter areas
        bloom = np.clip(base_f + blur_f * (glow * 0.55), 0.0, 255.0).astype(np.uint8)
        frame_img = Image.fromarray(bloom, mode="RGB")

    return frame_img, ascii_text


def ensure_even_dimensions(img: Image.Image, bg_rgb: tuple[int, int, int]) -> Image.Image:
    """MP4 (H.264 yuv420p) requires even width and height."""
    w, h = img.size
    new_w = w + (w % 2)
    new_h = h + (h % 2)
    if new_w == w and new_h == h:
        return img
    canvas = Image.new("RGB", (new_w, new_h), bg_rgb)
    canvas.paste(img, (0, 0))
    return canvas


def save_animated_gif(frames: Sequence[Image.Image], out_path: Path, fps: float) -> None:
    duration_ms = max(20, int(round(1000.0 / max(1.0, fps))))
    # Build a shared 256-color palette from representative frames for cleaner GIFs without flicker
    sample_indices = np.linspace(0, len(frames) - 1, min(6, len(frames)), dtype=int)
    w, h = frames[0].size
    strip = Image.new("RGB", (w, h * len(sample_indices)))
    for i, idx in enumerate(sample_indices):
        strip.paste(frames[idx], (0, i * h))
    palette_img = strip.quantize(colors=256, method=Image.Quantize.MEDIANCUT)

    quantized = [f.quantize(palette=palette_img, dither=Image.Dither.NONE) for f in frames]
    quantized[0].save(
        out_path,
        save_all=True,
        append_images=quantized[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )


def save_mp4(frames: Sequence[Image.Image], out_path: Path, fps: float, bg_rgb: tuple[int, int, int]) -> bool:
    try:
        even_frames = [np.asarray(ensure_even_dimensions(f, bg_rgb)) for f in frames]
        iio.imwrite(
            out_path,
            even_frames,
            fps=fps,
            codec="libx264",
            pixelformat="yuv420p",
            macro_block_size=1,
            quality=8,
        )
        return True
    except Exception as exc:
        print(f"[aviso] No se pudo exportar MP4: {exc}", file=sys.stderr)
        return False


def _ease_in_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - ((-2.0 * t + 2.0) ** 3) / 2.0


def _draw_studio_card(
    inner_img: Image.Image,
    cmd_label: str,
    badge_text: str,
    badge_accent: tuple[int, int, int],
    progress: float,
    ui_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    badge_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> Image.Image:
    """Wrap a rendered frame inside a sleek dark GitHub-friendly terminal studio card."""
    iw, ih = inner_img.size
    pad = 10
    header_h = 38
    footer_h = 10
    card_w = iw + pad * 2
    card_h = header_h + ih + footer_h

    # Outer canvas matches GitHub dark mode canvas seamlessly
    card = Image.new("RGB", (card_w, card_h), (13, 17, 23))
    draw = ImageDraw.Draw(card)

    # Header bar background + subtle bottom divider
    draw.rectangle([0, 0, card_w, header_h - 1], fill=(22, 27, 34))
    draw.line([(0, header_h - 1), (card_w, header_h - 1)], fill=(38, 46, 58), width=1)

    # Outer subtle border
    draw.rectangle([0, 0, card_w - 1, card_h - 1], outline=(48, 54, 61), width=1)

    # Traffic-light dots on left
    dot_y = header_h // 2
    dot_r = 5
    for i, color in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        cx = 18 + i * 18
        draw.ellipse([cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r], fill=color)

    # Command text
    prompt_x = 76
    prompt_bbox = draw.textbbox((0, 0), "$ ", font=ui_font)
    text_h = prompt_bbox[3] - prompt_bbox[1]
    text_y = (header_h - text_h) // 2 - prompt_bbox[1]
    draw.text((prompt_x, text_y), "$ ", fill=(88, 166, 255), font=ui_font)
    prompt_w = prompt_bbox[2] - prompt_bbox[0]
    draw.text((prompt_x + prompt_w, text_y), cmd_label, fill=(201, 209, 217), font=ui_font)

    # Status pill badge on right
    b_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    b_tw = b_bbox[2] - b_bbox[0]
    b_th = b_bbox[3] - b_bbox[1]
    pill_h = 22
    pill_w = b_tw + 24
    pill_x1 = card_w - 12
    pill_x0 = pill_x1 - pill_w
    pill_y0 = (header_h - pill_h) // 2
    pill_y1 = pill_y0 + pill_h

    # Tinted dark pill fill + accent border
    pill_bg = (
        int(18 + badge_accent[0] * 0.14),
        int(22 + badge_accent[1] * 0.14),
        int(30 + badge_accent[2] * 0.14),
    )
    pill_border = (
        int(35 + badge_accent[0] * 0.45),
        int(40 + badge_accent[1] * 0.45),
        int(48 + badge_accent[2] * 0.45),
    )
    draw.rounded_rectangle([pill_x0, pill_y0, pill_x1, pill_y1], radius=11, fill=pill_bg, outline=pill_border, width=1)

    # Tiny live indicator dot inside pill
    ind_x = pill_x0 + 9
    ind_y = (pill_y0 + pill_y1) // 2
    draw.ellipse([ind_x - 3, ind_y - 3, ind_x + 3, ind_y + 3], fill=badge_accent)

    b_tx = pill_x0 + 16
    b_ty = pill_y0 + (pill_h - b_th) // 2 - b_bbox[1]
    draw.text((b_tx, b_ty), badge_text, fill=(238, 244, 250), font=badge_font)

    # Paste inner visual frame
    card.paste(inner_img, (pad, header_h))
    draw.rectangle([pad - 1, header_h, pad + iw, header_h + ih], outline=(33, 38, 45), width=1)

    # Bottom sleek micro-progress bar
    bar_y0 = header_h + ih + 4
    bar_y1 = bar_y0 + 2
    draw.rectangle([pad, bar_y0, pad + iw, bar_y1], fill=(28, 34, 42))
    fill_w = int(round(iw * max(0.0, min(1.0, progress))))
    if fill_w > 0:
        draw.rectangle([pad, bar_y0, pad + fill_w, bar_y1], fill=badge_accent)

    return card


def create_showcase_gif(
    input_path: Path,
    out_path: Path,
    config: RenderConfig,
    cmd_label: str | None = None,
    showcase_cols: int = 92,
    showcase_font_size: int = 10,
    fps: int = 14,
) -> Path:
    """
    Generate a polished Before -> After transition GIF showing the original photo
    transforming via a glowing diagonal scanner beam into living animated ASCII art,
    then looping smoothly back to the original.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de entrada: {input_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    source_frames, _, _ = load_input_frames(input_path, max_frames=1, target_fps=fps)
    orig_img = source_frames[0]

    chars = resolve_palette(config.palette)
    glyph_font = load_monospace_font(showcase_font_size, config.font_path)
    ui_font = load_monospace_font(12, config.font_path)
    badge_font = load_monospace_font(10, config.font_path)

    atlas, cell_w, cell_h = build_glyph_atlas(chars, glyph_font)
    bg_rgb = config.bg_color if config.bg_color is not None else COLOR_MODES[config.color_mode]["bg"]  # type: ignore[assignment]
    edge_boost = float(DETAIL_PRESETS[config.detail]["edge_boost"])

    rgb, lum, edge = prepare_grid(
        orig_img,
        cols=showcase_cols,
        cell_w=cell_w,
        cell_h=cell_h,
        contrast=config.contrast,
        saturation=config.saturation,
        gamma=config.gamma,
        edge_boost=edge_boost,
    )
    rows, cols = lum.shape
    rng = np.random.default_rng(42)
    noise_phase = rng.uniform(0.0, 2.0 * math.pi, size=(rows, cols)).astype(np.float32)
    yy_grid, xx_grid = np.mgrid[0:rows, 0:cols].astype(np.float32)
    xx_grid /= max(1, cols - 1)
    yy_grid /= max(1, rows - 1)

    # Timeline structure (56 frames @ 14fps = 4.0s seamless loop)
    hold_orig = 10
    wipe_in = 14
    hold_ascii = 22
    wipe_out = 10
    total_frames = hold_orig + wipe_in + hold_ascii + wipe_out

    # Pre-render the native-resolution animated ASCII frames for the active phases
    ascii_cycle_len = wipe_in + hold_ascii + wipe_out
    ascii_arrays: list[np.ndarray] = []
    for i in range(ascii_cycle_len):
        phase = 2.0 * math.pi * (i / max(1, hold_ascii))
        mod_rgb, mod_lum = apply_animation_effect(
            rgb,
            lum,
            edge,
            phase=phase,
            effect=config.effect if config.effect != "none" else "luminous",
            intensity=max(0.55, config.intensity),
            noise_phase=noise_phase,
            xx=xx_grid,
            yy=yy_grid,
        )
        ascii_pil, _ = render_ascii_frame(
            mod_rgb, mod_lum, atlas, chars, config.color_mode, bg_rgb, max(0.24, config.glow)
        )
        ascii_arrays.append(np.asarray(ascii_pil, dtype=np.float32))

    h, w, _ = ascii_arrays[0].shape
    orig_aligned = orig_img.resize((w, h), Image.Resampling.LANCZOS)
    orig_arr = np.asarray(orig_aligned, dtype=np.float32)

    # Diagonal wipe coordinate across pixel space
    py, px = np.mgrid[0:h, 0:w].astype(np.float32)
    u_diag = 0.78 * (px / max(1, w - 1)) + 0.22 * (py / max(1, h - 1))

    label = cmd_label or f"ascii-gif {input_path.name} --effect {config.effect}"
    effect_badge = f"ASCII · {config.effect.upper()}"

    slate_accent = (148, 163, 184)
    gold_accent = (255, 196, 86)
    cyan_accent = (88, 214, 255)

    beam_core_color = np.array([255.0, 248.0, 224.0], dtype=np.float32)[None, None, :]
    beam_halo_color = np.array([255.0, 186.0, 74.0], dtype=np.float32)[None, None, :]
    beam_cool_color = np.array([92.0, 218.0, 255.0], dtype=np.float32)[None, None, :]

    card_frames: list[Image.Image] = []

    for f_idx in range(total_frames):
        if f_idx < hold_orig:
            # Phase 1: Crisp original image
            inner = orig_aligned
            card = _draw_studio_card(
                inner,
                cmd_label=label,
                badge_text="ORIGINAL",
                badge_accent=slate_accent,
                progress=0.0,
                ui_font=ui_font,
                badge_font=badge_font,
            )
        elif f_idx < hold_orig + wipe_in:
            # Phase 2: Luminous diagonal scan from Original -> Animated ASCII
            step = f_idx - hold_orig
            raw_t = (step + 0.5) / wipe_in
            t = _ease_in_out_cubic(raw_t)
            sweep_pos = -0.10 + 1.20 * t
            ascii_arr = ascii_arrays[step]

            # Smooth step mask: 1 behind sweep (ASCII), 0 ahead of sweep (Original)
            dist = sweep_pos - u_diag
            mask = (1.0 / (1.0 + np.exp(-dist / 0.014)))[:, :, None]

            # Glowing dual-tone scanner beam along u_diag == sweep_pos
            core = np.exp(-((dist / 0.0075) ** 2))[:, :, None]
            halo = np.exp(-((dist / 0.032) ** 2))[:, :, None]
            trail = np.exp(-(((dist - 0.018) / 0.028) ** 2))[:, :, None] * (dist > 0)[:, :, None]

            blended = (
                orig_arr * (1.0 - mask)
                + ascii_arr * mask
                + beam_core_color * (core * 0.92)
                + beam_halo_color * (halo * 0.36)
                + beam_cool_color * (trail * 0.24)
            )
            inner = Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8), mode="RGB")
            card = _draw_studio_card(
                inner,
                cmd_label=label,
                badge_text="SCANNING -> ASCII",
                badge_accent=gold_accent,
                progress=t,
                ui_font=ui_font,
                badge_font=badge_font,
            )
        elif f_idx < hold_orig + wipe_in + hold_ascii:
            # Phase 3: Full living animated ASCII art showcase
            ascii_idx = f_idx - hold_orig
            inner = Image.fromarray(np.clip(ascii_arrays[ascii_idx], 0, 255).astype(np.uint8), mode="RGB")
            card = _draw_studio_card(
                inner,
                cmd_label=label,
                badge_text=effect_badge,
                badge_accent=cyan_accent,
                progress=1.0,
                ui_font=ui_font,
                badge_font=badge_font,
            )
        else:
            # Phase 4: Clean reverse luminous wipe back to Original for seamless loop
            step = f_idx - (hold_orig + wipe_in + hold_ascii)
            raw_t = (step + 0.5) / wipe_out
            t = _ease_in_out_cubic(raw_t)
            sweep_pos = 1.10 - 1.20 * t
            ascii_arr = ascii_arrays[f_idx - hold_orig]

            dist = sweep_pos - u_diag
            mask = (1.0 / (1.0 + np.exp(-dist / 0.016)))[:, :, None]
            core = np.exp(-((dist / 0.007) ** 2))[:, :, None]
            halo = np.exp(-((dist / 0.028) ** 2))[:, :, None]

            blended = (
                orig_arr * (1.0 - mask)
                + ascii_arr * mask
                + beam_core_color * (core * 0.65)
                + beam_cool_color * (halo * 0.30)
            )
            inner = Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8), mode="RGB")
            card = _draw_studio_card(
                inner,
                cmd_label=label,
                badge_text="ORIGINAL",
                badge_accent=slate_accent,
                progress=1.0 - t,
                ui_font=ui_font,
                badge_font=badge_font,
            )

        card_frames.append(card)

    # Build a rich shared 256-color palette balanced across Original, Wipe, and ASCII phases
    palette_sample_ids = [
        0,
        hold_orig + wipe_in // 2,
        hold_orig + wipe_in + 2,
        hold_orig + wipe_in + hold_ascii // 2,
        hold_orig + wipe_in + hold_ascii - 2,
    ]
    cw, ch = card_frames[0].size
    strip = Image.new("RGB", (cw, ch * len(palette_sample_ids)))
    for i, idx in enumerate(palette_sample_ids):
        strip.paste(card_frames[idx], (0, i * ch))
    palette_img = strip.quantize(colors=256, method=Image.Quantize.MEDIANCUT)

    quantized = [f.quantize(palette=palette_img, dither=Image.Dither.NONE) for f in card_frames]
    duration_ms = max(20, int(round(1000.0 / max(1, fps))))
    quantized[0].save(
        out_path,
        save_all=True,
        append_images=quantized[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )
    return out_path


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------


def convert_to_animated_ascii(
    input_path: Path,
    output_dir: Path,
    config: RenderConfig,
    output_name: str | None = None,
) -> dict[str, Path]:
    if not input_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de entrada: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_name or input_path.stem
    safe_stem = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in stem).strip("_") or "ascii_art"

    chars = resolve_palette(config.palette)
    font = load_monospace_font(config.font_size, config.font_path)
    atlas, cell_w, cell_h = build_glyph_atlas(chars, font)

    bg_rgb = config.bg_color if config.bg_color is not None else COLOR_MODES[config.color_mode]["bg"]  # type: ignore[assignment]
    edge_boost = float(DETAIL_PRESETS[config.detail]["edge_boost"])

    source_frames, source_fps, is_animated_source = load_input_frames(
        input_path,
        max_frames=config.max_video_frames,
        target_fps=config.fps,
    )

    effective_fps = max(1.0, (source_fps if is_animated_source else float(config.fps)) * config.speed)
    rendered_frames: list[Image.Image] = []
    key_ascii_text = ""

    rng = np.random.default_rng(42)

    if is_animated_source:
        total = len(source_frames)
        noise_phase: np.ndarray | None = None
        xx: np.ndarray | None = None
        yy: np.ndarray | None = None

        for idx, src_img in enumerate(source_frames):
            rgb, lum, edge = prepare_grid(
                src_img,
                cols=config.width,
                cell_w=cell_w,
                cell_h=cell_h,
                contrast=config.contrast,
                saturation=config.saturation,
                gamma=config.gamma,
                edge_boost=edge_boost,
            )
            if noise_phase is None:
                rows, cols = lum.shape
                noise_phase = rng.uniform(0.0, 2.0 * math.pi, size=(rows, cols)).astype(np.float32)
                yy, xx = np.mgrid[0:rows, 0:cols].astype(np.float32)
                xx /= max(1, cols - 1)
                yy /= max(1, rows - 1)

            phase = 2.0 * math.pi * (idx / max(1, total))
            # For animated inputs, keep extra effect subtle so original motion leads
            mod_rgb, mod_lum = apply_animation_effect(
                rgb,
                lum,
                edge,
                phase=phase,
                effect=config.effect,
                intensity=config.intensity * 0.45,
                noise_phase=noise_phase,
                xx=xx,  # type: ignore[arg-type]
                yy=yy,  # type: ignore[arg-type]
            )
            frame_img, ascii_txt = render_ascii_frame(
                mod_rgb, mod_lum, atlas, chars, config.color_mode, bg_rgb, config.glow
            )
            rendered_frames.append(frame_img)
            if idx == 0:
                key_ascii_text = ascii_txt
    else:
        rgb, lum, edge = prepare_grid(
            source_frames[0],
            cols=config.width,
            cell_w=cell_w,
            cell_h=cell_h,
            contrast=config.contrast,
            saturation=config.saturation,
            gamma=config.gamma,
            edge_boost=edge_boost,
        )
        rows, cols = lum.shape
        noise_phase = rng.uniform(0.0, 2.0 * math.pi, size=(rows, cols)).astype(np.float32)
        yy, xx = np.mgrid[0:rows, 0:cols].astype(np.float32)
        xx /= max(1, cols - 1)
        yy /= max(1, rows - 1)

        total_frames = 1 if config.effect == "none" else max(2, config.frames)
        for idx in range(total_frames):
            phase = 2.0 * math.pi * (idx / total_frames)
            mod_rgb, mod_lum = apply_animation_effect(
                rgb,
                lum,
                edge,
                phase=phase,
                effect=config.effect,
                intensity=config.intensity,
                noise_phase=noise_phase,
                xx=xx,
                yy=yy,
            )
            frame_img, ascii_txt = render_ascii_frame(
                mod_rgb, mod_lum, atlas, chars, config.color_mode, bg_rgb, config.glow
            )
            rendered_frames.append(frame_img)
            if idx == 0:
                key_ascii_text = ascii_txt

    outputs: dict[str, Path] = {}

    if config.export_png:
        png_path = output_dir / f"{safe_stem}_ascii.png"
        # Pick a flattering representative frame (peak of first third of light sweep)
        key_idx = min(len(rendered_frames) - 1, len(rendered_frames) // 4)
        rendered_frames[key_idx].save(png_path, optimize=True)
        outputs["png"] = png_path

    if config.export_txt and key_ascii_text:
        txt_path = output_dir / f"{safe_stem}_ascii.txt"
        txt_path.write_text(key_ascii_text + "\n", encoding="utf-8")
        outputs["txt"] = txt_path

    if config.export_gif and len(rendered_frames) > 1:
        gif_path = output_dir / f"{safe_stem}_ascii.gif"
        save_animated_gif(rendered_frames, gif_path, fps=effective_fps)
        outputs["gif"] = gif_path

    if config.export_mp4 and len(rendered_frames) > 1:
        mp4_path = output_dir / f"{safe_stem}_ascii.mp4"
        if save_mp4(rendered_frames, mp4_path, fps=effective_fps, bg_rgb=bg_rgb):
            outputs["mp4"] = mp4_path

    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convierte imágenes, GIFs o videos en arte ASCII animado (PNG, GIF, MP4 y TXT).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="Ruta a la imagen, GIF o video original.")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Carpeta donde se guardarán los resultados.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Nombre base para los archivos de salida (por defecto usa el nombre del archivo original).",
    )
    parser.add_argument(
        "--detail",
        choices=list(DETAIL_PRESETS.keys()),
        default="high",
        help="Nivel de detalle general (ajusta ancho y tamaño de fuente si no se especifican).",
    )
    parser.add_argument(
        "-w",
        "--width",
        type=int,
        default=None,
        help="Ancho en caracteres ASCII (sobrescribe el valor del nivel de detalle).",
    )
    parser.add_argument(
        "--palette",
        type=str,
        default="detailed",
        help=f"Paleta de caracteres ({', '.join(PALETTES.keys())}) o cadena personalizada de oscuro a claro.",
    )
    parser.add_argument(
        "--color-mode",
        choices=list(COLOR_MODES.keys()),
        default="color",
        help="Modo de color del arte ASCII.",
    )
    parser.add_argument(
        "--bg-color",
        type=str,
        default=None,
        help="Color de fondo en hexadecimal (ej. #0a0c12).",
    )
    parser.add_argument(
        "--effect",
        choices=list(EFFECTS),
        default="luminous",
        help="Tipo de animación sutil.",
    )
    parser.add_argument(
        "--intensity",
        type=float,
        default=0.55,
        help="Intensidad del movimiento/efecto (0.0 a 1.5).",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Multiplicador de velocidad de la animación (ej. 0.5 lento, 1.5 rápido).",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=12,
        help="Fotogramas por segundo base.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=24,
        help="Número de fotogramas para el bucle en imágenes estáticas.",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=None,
        help="Tamaño de fuente en píxeles para el renderizado.",
    )
    parser.add_argument(
        "--font",
        type=str,
        default=None,
        help="Ruta opcional a una fuente monoespaciada (.ttf/.ttc/.otf).",
    )
    parser.add_argument(
        "--glow",
        type=float,
        default=0.22,
        help="Nivel de resplandor sutil en fondos oscuros (0.0 a 1.0).",
    )
    parser.add_argument(
        "--contrast",
        type=float,
        default=1.12,
        help="Factor de contraste previo al mapeo ASCII.",
    )
    parser.add_argument(
        "--saturation",
        type=float,
        default=1.18,
        help="Factor de saturación de color.",
    )
    parser.add_argument("--no-png", action="store_true", help="Omitir exportación de PNG.")
    parser.add_argument("--no-gif", action="store_true", help="Omitir exportación de GIF.")
    parser.add_argument("--no-mp4", action="store_true", help="Omitir exportación de MP4.")
    parser.add_argument("--no-txt", action="store_true", help="Omitir exportación de TXT.")
    parser.add_argument(
        "--showcase",
        action="store_true",
        help="Generar además un GIF showcase (Original -> barrido luminoso -> ASCII animado).",
    )
    parser.add_argument(
        "--showcase-only",
        action="store_true",
        help="Generar únicamente el GIF showcase sin exportar PNG/GIF/MP4/TXT normales.",
    )
    parser.add_argument(
        "--showcase-out",
        type=Path,
        default=None,
        help="Ruta personalizada para el GIF showcase (por defecto outputs/<nombre>_showcase.gif).",
    )
    parser.add_argument(
        "--showcase-cmd",
        type=str,
        default=None,
        help="Texto de comando mostrado en la barra superior del GIF showcase.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    preset = DETAIL_PRESETS[args.detail]
    width = args.width if args.width is not None else int(preset["width"])
    font_size = args.font_size if args.font_size is not None else int(preset["font_size"])
    bg_color = parse_hex_color(args.bg_color) if args.bg_color else None

    config = RenderConfig(
        width=max(20, width),
        detail=args.detail,
        palette=args.palette,
        color_mode=args.color_mode,
        bg_color=bg_color,
        effect=args.effect,
        intensity=args.intensity,
        speed=max(0.1, args.speed),
        fps=max(1, args.fps),
        frames=max(1, args.frames),
        font_size=max(6, font_size),
        font_path=args.font,
        contrast=args.contrast,
        saturation=args.saturation,
        glow=max(0.0, args.glow),
        export_png=not args.no_png,
        export_gif=not args.no_gif,
        export_mp4=not args.no_mp4,
        export_txt=not args.no_txt,
    )

    outputs: dict[str, Path] = {}
    if not args.showcase_only:
        outputs = convert_to_animated_ascii(
            input_path=args.input,
            output_dir=args.output_dir,
            config=config,
            output_name=args.name,
        )

    if args.showcase or args.showcase_only or args.showcase_out is not None:
        stem = args.name or args.input.stem
        safe_stem = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in stem).strip("_") or "ascii_art"
        showcase_path = args.showcase_out or (args.output_dir / f"{safe_stem}_showcase.gif")
        create_showcase_gif(
            input_path=args.input,
            out_path=showcase_path,
            config=config,
            cmd_label=args.showcase_cmd,
        )
        outputs["showcase"] = showcase_path

    print("Archivos generados:")
    for kind, path in outputs.items():
        size_kb = path.stat().st_size / 1024.0
        print(f"  - {kind.upper():8s}: {path} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
