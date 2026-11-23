<div align="center">

# `image-to-ascii-gif`

**Turn images, GIFs, and videos into subtly animated ASCII art — preserving the subject, framing, and fine detail.**

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/uv-compatible-DE5FE9?style=flat-square&logo=uv&logoColor=white" alt="uv compatible">
  <img src="https://img.shields.io/badge/Outputs-PNG%20%7C%20GIF%20%7C%20MP4%20%7C%20TXT-0ea5e9?style=flat-square" alt="Outputs">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=flat-square" alt="MIT License"></a>
</p>

<br>

<img src="assets/demo.gif" alt="Demo: original photo transitioning into animated ASCII art" width="480" />

<p align="center">
  <sub>Generated directly with <code>ascii-gif photo.jpg --showcase</code></sub>
</p>

</div>

---

## Features

- **Faithful to the subject:** automatically compensates for character aspect ratio using real monospace font metrics and applies subtle edge micro-contrast so faces, silhouettes, and textures stay sharp and recognizable.
- **Seamless subtle motion:** brings static images to life with gentle light sweeps, highlight shimmer, breathing glow, or CRT scanlines (`luminous`, `shimmer`, `sweep`, `breathe`, `scanline`, `drift`) without distorting the image.
- **Full media support:** accepts `PNG`, `JPG`, `WEBP`, `BMP`, `TIFF`, animated `GIF`, and video files (`MP4`, `MOV`, `WEBM`, `MKV`, `AVI`).
- **Share-ready exports:** outputs `PNG`, `GIF`, `MP4` (H.264), and plain-text `TXT` into `outputs/` while keeping your original file untouched.
- **Built-in Showcase mode:** generate before-and-after transition GIFs (*Original → luminous scan → animated ASCII*) with `--showcase`, ready for READMEs and social posts.
- **Fast glyph-atlas renderer:** vectorized with NumPy + Pillow with optional soft bloom (`--glow`).

---

## Installation

Requires **Python 3.10+**.

### Option 1: Install from GitHub with [`uv`](https://docs.astral.sh/uv/) *(recommended)*

```bash
uv tool install git+https://github.com/kingrxben/image-to-ascii-gif.git
```

This installs the `ascii-gif` and `image-to-ascii-gif` CLI commands globally.

> Or run it on the fly without installing permanently:
> ```bash
> uvx --from git+https://github.com/kingrxben/image-to-ascii-gif.git ascii-gif path/to/image.jpg
> ```

### Option 2: Install with `pip`

```bash
pip install git+https://github.com/kingrxben/image-to-ascii-gif.git
```

### Option 3: Clone and run locally

```bash
git clone https://github.com/kingrxben/image-to-ascii-gif.git
cd image-to-ascii-gif
uv sync
```

Then run it inside the project:

```bash
uv run ascii-gif path/to/image.jpg
```

---

## Quick Start

Convert any image using sensible defaults (`--detail high`, `--palette detailed`, `--color-mode color`, `--effect luminous`):

```bash
ascii-gif path/to/image.jpg
```

Your original file is never modified, and results are saved cleanly inside `outputs/`:

```text
outputs/
├── image_ascii.png   # Crisp keyframe PNG
├── image_ascii.gif   # Seamless looping animated GIF
├── image_ascii.mp4   # H.264 MP4 video
└── image_ascii.txt   # Plain-text ASCII art
```

### Generate a Before → After Showcase GIF

Create a transition GIF just like the hero demo above (original photo → luminous diagonal scan → living animated ASCII):

```bash
ascii-gif path/to/image.jpg --showcase-only --showcase-out assets/demo.gif
```

Or generate all standard outputs **plus** the showcase GIF:

```bash
ascii-gif path/to/image.jpg --showcase
```

---

## Examples

```bash
# Custom base filename for outputs
ascii-gif portrait.png --name knight

# Retro green terminal aesthetic with CRT scanline
ascii-gif photo.jpg --color-mode green --effect scanline --palette matrix

# Vintage amber with slow, subtle highlight shimmer
ascii-gif photo.webp --color-mode amber --effect shimmer --speed 0.7 --intensity 0.5

# High-detail dark ink on warm paper
ascii-gif portrait.jpg --color-mode paper --detail ultra --effect breathe --intensity 0.4

# Convert an animated GIF or video clip to ASCII
ascii-gif clip.mp4 --width 110 --fps 12

# Use a custom character ramp (dark to bright)
ascii-gif photo.jpg --palette " .:-=+*#%@" --glow 0.3
```

---

## CLI Options

| Option | Default | Description |
| --- | --- | --- |
| `--name` | input stem | Base filename for generated outputs. |
| `-o`, `--output-dir` | `outputs` | Directory where output files are saved. |
| `--detail` | `high` | Detail preset: `low`, `medium`, `high`, `ultra`. |
| `-w`, `--width` | from `--detail` | Exact width in ASCII characters (e.g. `90`, `140`). |
| `--palette` | `detailed` | Preset (`detailed`, `classic`, `blocks`, `minimal`, `matrix`) or custom character string. |
| `--color-mode` | `color` | Color mode: `color`, `amber`, `green`, `cyan`, `mono`, `paper`. |
| `--bg-color` | from mode | Background color in hex (e.g. `#0a0c12`). |
| `--effect` | `luminous` | Animation effect: `luminous`, `shimmer`, `sweep`, `breathe`, `scanline`, `drift`, `none`. |
| `--intensity` | `0.55` | Effect intensity (`0.0` to `1.5`). |
| `--speed` | `1.0` | Playback speed multiplier (`0.5` slower, `1.5` faster). |
| `--fps` / `--frames` | `12` / `24` | Base frame rate and frame count for static-image loops. |
| `--font-size` / `--font` | from `--detail` | Font size in pixels or path to a monospace font (`.ttf`/`.ttc`/`.otf`). |
| `--glow` | `0.22` | Subtle bloom/glow strength on dark backgrounds (`0.0` to disable). |
| `--contrast` / `--saturation` | `1.12` / `1.18` | Pre-mapping contrast and color saturation multipliers. |
| `--showcase` / `--showcase-only` | off | Export the *Original → animated ASCII* transition GIF. |
| `--showcase-out` / `--showcase-cmd` | auto | Custom output path and header command label for the showcase GIF. |
| `--no-png` / `--no-gif` / `--no-mp4` / `--no-txt` | all enabled | Skip specific output formats. |

### Effects Reference

- **`luminous`** *(default)*: gentle diagonal light sweep + specular highlight shimmer + subtle ambient breathing.
- **`shimmer`**: organic twinkle focused on highlights, reflections, and intricate edges.
- **`sweep`**: clean diagonal beam of light gliding across the frame.
- **`breathe`**: calm pulsing of brightness and tonal depth.
- **`scanline`**: horizontal glowing CRT scanline band.
- **`drift`**: subtle luminance ripple over textures without warping geometry.
- **`none`**: static export with no animation.

---

## License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more information.
