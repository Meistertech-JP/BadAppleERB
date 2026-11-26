#!/usr/bin/env python3
"""Render a looping character preview from the frozen 79 x 24 grayscale cells.

Run from the repository root:
    python docs/make_highlights.py

NumPy and Pillow with animated WebP support are required. A monospaced font
named DejaVuSansMono.ttf must be available, or can be supplied with --font.
This is a representative font rendering of reference cells, not a recording
of a native terminal. Source motion keeps its original timing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version, features

SOURCE_FPS = 30
REFERENCE_SHAPE = (6573, 24, 79)
REFERENCE_SHA256 = "d9d69b416e4ed9d3b87465b0a003e038630ccf7a126054c045c9e76218052029"
CELL_WIDTH = 12
CELL_HEIGHT = 30
FONT_SIZE = 20
WEBP_METHOD = 4
WEBP_EFFORT = 80


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def round_milliseconds(source_frames: int) -> int:
    """Round a 30 fps source interval to the nearest integer millisecond."""
    return (source_frames * 1000 + SOURCE_FPS // 2) // SOURCE_FPS


def portable_name(path: Path, root: Path) -> str:
    """Keep generated metadata independent of a particular checkout path."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def render_cells(gray: np.ndarray, glyph: np.ndarray) -> Image.Image:
    """Paint '#' with each cell's grayscale foreground on a black background."""
    pixels = (
        (gray[:, :, None, None].astype(np.uint16) * glyph + 127) // 255
    ).transpose(0, 2, 1, 3).reshape(24 * CELL_HEIGHT, 79 * CELL_WIDTH)
    return Image.fromarray(pixels.astype(np.uint8)).convert("RGB")


def verify_animation(
    output: Path, frames: list[Image.Image], durations: list[int]
) -> dict:
    """Check decoded pixels and timeline, including coalesced identical frames."""
    expected_index = 0
    elapsed = 0
    decoded_durations = []
    with Image.open(output) as animation:
        if not animation.is_animated or animation.info.get("loop") != 0:
            raise RuntimeError("The WebP must be animated and loop indefinitely")
        for index in range(animation.n_frames):
            animation.seek(index)
            animation.load()
            duration = int(animation.info["duration"])
            encoded_end = elapsed + duration
            decoded = np.asarray(animation.convert("RGB"))
            while expected_index < len(frames) and elapsed < encoded_end:
                if not np.array_equal(decoded, np.asarray(frames[expected_index])):
                    raise RuntimeError(f"WebP pixels differ at sample {expected_index}")
                elapsed += durations[expected_index]
                expected_index += 1
            if elapsed != encoded_end:
                raise RuntimeError("WebP frame boundaries changed motion timing")
            decoded_durations.append(duration)
        if expected_index != len(frames) or elapsed != sum(durations):
            raise RuntimeError("WebP did not preserve the complete excerpt")
        return {
            "decoded_frame_count": animation.n_frames,
            "decoded_durations_ms": decoded_durations,
            "duration_ms": elapsed,
            "loop": animation.info.get("loop"),
            "lossless_pixels_match": True,
            "sample_timing_matches": True,
        }


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=repository / "reference_frames.npz")
    parser.add_argument("--output-dir", type=Path, default=repository / "docs")
    parser.add_argument("--font", default="DejaVuSansMono.ttf")
    parser.add_argument("--start-frame", type=int, default=240)
    parser.add_argument("--end-frame", type=int, default=600,
                        help="Exclusive source-frame boundary")
    parser.add_argument("--fps", type=int, choices=(15, 30), default=15)
    args = parser.parse_args()

    with np.load(args.reference) as source:
        gray = source["gray"]
    if gray.dtype != np.uint8 or gray.shape != REFERENCE_SHAPE:
        raise ValueError("Expected the frozen 6573 x 24 x 79 uint8 grayscale reference")
    reference_hash = sha256(gray.tobytes())
    if reference_hash != REFERENCE_SHA256:
        raise ValueError("Reference cells do not match this movie's frozen input")
    if not 0 <= args.start_frame < args.end_frame <= len(gray):
        raise ValueError("The source-frame range is outside the reference")

    step = SOURCE_FPS // args.fps
    indices = list(range(args.start_frame, args.end_frame, step))
    boundaries = [round_milliseconds(i - args.start_frame) for i in indices]
    boundaries.append(round_milliseconds(args.end_frame - args.start_frame))
    durations = [end - start for start, end in zip(boundaries, boundaries[1:])]

    font = ImageFont.truetype(args.font, FONT_SIZE)
    box = font.getbbox("#")
    if box[2] - box[0] > CELL_WIDTH or box[3] - box[1] > CELL_HEIGHT:
        raise ValueError("The selected font's '#' does not fit the fixed cell size")
    position = (
        (CELL_WIDTH - (box[2] - box[0])) // 2 - box[0],
        (CELL_HEIGHT - (box[3] - box[1])) // 2 - box[1],
    )
    mask = Image.new("L", (CELL_WIDTH, CELL_HEIGHT), 0)
    ImageDraw.Draw(mask).text(position, "#", font=font, fill=255)
    glyph = np.asarray(mask).astype(np.uint16)
    frames = [render_cells(gray[index], glyph) for index in indices]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    animation_path = args.output_dir / "highlights.webp"
    poster_path = args.output_dir / "highlights-poster.png"
    metadata_path = args.output_dir / "highlights.json"
    frames[0].save(poster_path, optimize=True)
    print(f"Encoding {len(frames)} samples, {sum(durations)} ms, {frames[0].size}", flush=True)
    frames[0].save(
        animation_path, format="WEBP", save_all=True, append_images=frames[1:],
        duration=durations, loop=0, lossless=True, quality=WEBP_EFFORT,
        method=WEBP_METHOD, minimize_size=False,
    )
    verification = verify_animation(animation_path, frames, durations)
    font_path = Path(font.path)
    metadata = {
        "format": "badapple-character-highlights-v1",
        "preview_scope": "Representative font rendering of frozen 79x24 grayscale cells; not a native terminal recording",
        "reference": {
            "file": portable_name(args.reference, repository),
            "key": "gray",
            "shape": list(gray.shape),
            "dtype": "uint8",
            "cells_sha256": reference_hash,
            "selected_cells_sha256": sha256(gray[indices].tobytes()),
        },
        "excerpt": {
            "source_fps": SOURCE_FPS,
            "start_frame_inclusive": args.start_frame,
            "end_frame_exclusive": args.end_frame,
            "source_time_start_ms": round_milliseconds(args.start_frame),
            "source_time_end_ms": round_milliseconds(args.end_frame),
            "source_span_frames": args.end_frame - args.start_frame,
            "sample_step_frames": step,
            "sample_fps": args.fps,
            "sample_count": len(indices),
            "sample_indices": indices,
            "sample_durations_ms": durations,
            "duration_ms": sum(durations),
            "motion_speed": 1,
            "edits": "One continuous excerpt; no speed changes, interpolation, fades, or overlays",
            "description": (
                "Profile with an apple, apple toss, polarity transition, and witch-and-broom zoom-out"
                if (args.start_frame, args.end_frame) == (240, 600)
                else "Selected continuous excerpt"
            ),
        },
        "rendering": {
            "logical_cells": [79, 24],
            "cell_size_px": [CELL_WIDTH, CELL_HEIGHT],
            "image_size_px": list(frames[0].size),
            "black_cells": "Space on black",
            "nonblack_cells": "# with RGB=(gray,gray,gray) on black",
            "font_family_style": list(font.getname()),
            "font_file": font_path.name,
            "font_sha256": sha256(font_path.read_bytes()),
            "font_size_px": FONT_SIZE,
            "glyph_draw_position_px": list(position),
            "glyph_mask_sha256": sha256(np.asarray(mask).tobytes()),
            "glyph_antialiasing": "Pillow grayscale font mask; integer foreground multiplication",
        },
        "encoding": {
            "format": "Animated WebP",
            "lossless": True,
            "method": WEBP_METHOD,
            "quality": WEBP_EFFORT,
            "quality_meaning": "Compression effort; lossless pixel encoding remains enabled",
            "minimize_size": False,
            "loop": 0,
            "pillow_version": pillow_version,
            "libwebp_version": features.version("webp"),
        },
        "verification": verification,
        "files": [
            {
                "path": portable_name(path, repository),
                "bytes": path.stat().st_size,
                "sha256": sha256(path.read_bytes()),
            }
            for path in (animation_path, poster_path)
        ],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "animation": portable_name(animation_path, repository),
        "bytes": animation_path.stat().st_size,
        "samples": len(indices),
        "encoded_frames": verification["decoded_frame_count"],
        "duration_ms": verification["duration_ms"],
        "lossless_pixels_match": verification["lossless_pixels_match"],
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
