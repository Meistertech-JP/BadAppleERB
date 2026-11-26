#!/usr/bin/env python3
"""Compile decoded reference rows into exact, interpolated span geometry.

The compiler stores adaptive integer-valued trajectories, not rendered frame
strings.  A segment has a constant number of horizontal color spans; both the
interior span boundaries and span luminances are calculated from rational
velocities.  Topology changes begin a new segment.  This is a data-derived
animation model, not a reconstruction of the source animator's scene graph.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np


def choose_slope(ln: int, ld: int, un: int, ud: int) -> tuple[int, int]:
    """Choose a small rational in the exact half-open interval [lo, hi)."""
    if ln <= 0 < un:
        return 0, 1
    integer = -((-ln) // ld)
    if integer * ud < un:
        return integer, 1
    midpoint = Fraction(ln * ud + un * ld, 2 * ld * ud)
    for limit in (64, 1024):
        candidate = midpoint.limit_denominator(limit)
        p, q = candidate.numerator, candidate.denominator
        if p * ld >= ln * q and p * ud < un * q:
            return p, q
    return midpoint.numerator, midpoint.denominator


def fit_integer_vectors(vectors: np.ndarray, first: int = 0):
    """Yield maximal-prefix exact rational segments for fixed-size vectors.

    For a fixed integer base b, round-half-up(b + v*dt) == sample imposes
    (2*(sample-b)-1)/(2*dt) <= v < (2*(sample-b)+1)/(2*dt).
    Intersect these rational intervals using integer cross products only.
    Endpoints belong to consecutive disjoint segments, rather than being
    duplicated between segments.
    """
    values = np.asarray(vectors, dtype=np.int64)
    count, dimensions = values.shape
    start = 0
    while start < count:
        base = values[start].copy()
        if start + 1 == count or dimensions == 0:
            last = count - 1
            yield first + start, first + last, base, np.zeros(dimensions, np.int64), np.ones(dimensions, np.int64)
            break
        delta = values[start + 1] - base
        ln, un = 2 * delta - 1, 2 * delta + 1
        ld = np.full(dimensions, 2, np.int64)
        ud = np.full(dimensions, 2, np.int64)
        last = start + 1
        for index in range(start + 2, count):
            denominator = 2 * (index - start)
            delta = values[index] - base
            lower, upper = 2 * delta - 1, 2 * delta + 1
            take_lower = lower * ld > ln * denominator
            take_upper = upper * ud < un * denominator
            new_ln = np.where(take_lower, lower, ln)
            new_ld = np.where(take_lower, denominator, ld)
            new_un = np.where(take_upper, upper, un)
            new_ud = np.where(take_upper, denominator, ud)
            if np.any(new_ln * new_ud >= new_un * new_ld):
                break
            ln, ld, un, ud = new_ln, new_ld, new_un, new_ud
            last = index
        slopes = [choose_slope(int(a), int(b), int(c), int(d)) for a, b, c, d in zip(ln, ld, un, ud)]
        numerators = np.asarray([v[0] for v in slopes], dtype=np.int64)
        denominators = np.asarray([v[1] for v in slopes], dtype=np.int64)
        yield first + start, first + last, base, numerators, denominators
        start = last + 1


def evaluate(base, num, den, elapsed):
    """Exactly match ERB integer division, including negative velocities."""
    numerator = (2 * base + 1) * den + 2 * num * elapsed
    if np.any(numerator < 0):
        raise ValueError("Trajectory numerator became negative")
    return numerator // (2 * den)


def row_vectors(frames: np.ndarray, row: int):
    """Return constant-topology runs of (interior boundaries, colors)."""
    data = frames[:, row, :]
    changes = data[:, 1:] != data[:, :-1]
    counts = changes.sum(axis=1) + 1
    total = len(data)
    first = 0
    while first < total:
        runs = int(counts[first])
        last = first + 1
        while last < total and counts[last] == runs:
            last += 1
        vector = np.empty((last - first, 2 * runs - 1), dtype=np.int64)
        for local, index in enumerate(range(first, last)):
            edges = np.flatnonzero(changes[index]) + 1
            vector[local, :runs - 1] = edges
            vector[local, runs - 1:] = data[index, np.r_[0, edges]]
        yield first, last, runs, vector
        first = last


def compile_geometry(frames: np.ndarray):
    frames = np.asarray(frames, dtype=np.uint8)
    if frames.ndim != 3:
        raise ValueError("Expected (frames,height,width) reference")
    nframes, height, width = frames.shape
    arrays = {name: [] for name in (
        "BA_ROW_FIRST", "BA_ROW_END", "BA_SEG_START", "BA_SEG_LAST",
        "BA_SEG_COUNT", "BA_SEG_BOUND_OFF", "BA_SEG_COLOR_OFF",
        "BA_BOUND_BASE", "BA_BOUND_NUM", "BA_BOUND_DEN",
        "BA_COLOR_BASE", "BA_COLOR_NUM", "BA_COLOR_DEN",
    )}
    for row in range(height):
        arrays["BA_ROW_FIRST"].append(len(arrays["BA_SEG_START"]))
        for first, _, runs, vectors in row_vectors(frames, row):
            for start, last, base, num, den in fit_integer_vectors(vectors, first):
                arrays["BA_SEG_START"].append(start)
                arrays["BA_SEG_LAST"].append(last)
                arrays["BA_SEG_COUNT"].append(runs)
                arrays["BA_SEG_BOUND_OFF"].append(len(arrays["BA_BOUND_BASE"]))
                arrays["BA_SEG_COLOR_OFF"].append(len(arrays["BA_COLOR_BASE"]))
                boundary = runs - 1
                for suffix, values in (("BASE", base), ("NUM", num), ("DEN", den)):
                    arrays["BA_BOUND_" + suffix].extend(values[:boundary].tolist())
                    arrays["BA_COLOR_" + suffix].extend(values[boundary:].tolist())
        arrays["BA_ROW_END"].append(len(arrays["BA_SEG_START"]))
        print(f"compiled row {row + 1}/{height}: segments={len(arrays['BA_SEG_START'])}, color_trajectories={len(arrays['BA_COLOR_BASE'])}", flush=True)
    result = {key: np.asarray(value, dtype=np.int64) for key, value in arrays.items()}
    result["BA_WIDTH"] = np.asarray(width)
    result["BA_HEIGHT"] = np.asarray(height)
    result["BA_FRAMES"] = np.asarray(nframes)
    result["BA_FPS"] = np.asarray(30)
    result["BA_SEGMENTS"] = np.asarray(len(arrays["BA_SEG_START"]))
    result["BA_BOUNDARIES"] = np.asarray(len(arrays["BA_BOUND_BASE"]))
    result["BA_COLORS"] = np.asarray(len(arrays["BA_COLOR_BASE"]))
    return result


def validate(model, frames):
    """Reconstruct every cell from geometry, independent of the fitter state."""
    frames = np.asarray(frames, dtype=np.uint8)
    reconstructed = np.empty_like(frames)
    nframes, height, width = frames.shape
    invalid_boundaries = 0
    for row in range(height):
        covered = 0
        for index in range(int(model["BA_ROW_FIRST"][row]), int(model["BA_ROW_END"][row])):
            start, last = int(model["BA_SEG_START"][index]), int(model["BA_SEG_LAST"][index])
            if start != covered:
                raise ValueError("Segment gap or overlap")
            runs = int(model["BA_SEG_COUNT"][index])
            bo = int(model["BA_SEG_BOUND_OFF"][index])
            co = int(model["BA_SEG_COLOR_OFF"][index])
            bs, cs = slice(bo, bo + runs - 1), slice(co, co + runs)
            for frame in range(start, last + 1):
                t = frame - start
                boundaries = evaluate(model["BA_BOUND_BASE"][bs], model["BA_BOUND_NUM"][bs], model["BA_BOUND_DEN"][bs], t)
                colors = evaluate(model["BA_COLOR_BASE"][cs], model["BA_COLOR_NUM"][cs], model["BA_COLOR_DEN"][cs], t)
                ends = np.r_[0, boundaries, width]
                if np.any(ends[1:] <= ends[:-1]) or np.any(colors < 0) or np.any(colors > 255):
                    invalid_boundaries += 1
                    raise ValueError("Invalid reconstructed spans")
                for left, right, color in zip(ends[:-1], ends[1:], colors):
                    reconstructed[frame, row, left:right] = color
            covered = last + 1
        if covered != nframes:
            raise ValueError("Row does not cover all frames")
    mismatch = reconstructed != frames
    lengths = model["BA_SEG_LAST"] - model["BA_SEG_START"] + 1
    histogram = Counter(int(x) for x in lengths)
    source_runs = int((frames[:, :, 1:] != frames[:, :, :-1]).sum() + nframes * height)
    source_boundary_values = source_runs - nframes * height
    model_boundaries = len(model["BA_BOUND_BASE"])
    model_colors = len(model["BA_COLOR_BASE"])
    trajectory_scalars = 3 * (model_boundaries + model_colors)
    source_scalars = source_runs + source_boundary_values
    return {
        "method": "Exact rational scanline span-boundary and luminance trajectories; topology-dependent adaptive segments",
        "frames": nframes, "height": height, "width": width,
        "pixels_compared": int(frames.size),
        "mismatching_pixels": int(mismatch.sum()),
        "mismatching_frames": int(np.count_nonzero(np.any(mismatch, axis=(1, 2)))),
        "reference_gray_sha256": hashlib.sha256(frames.tobytes()).hexdigest(),
        "reconstructed_gray_sha256": hashlib.sha256(reconstructed.tobytes()).hexdigest(),
        "segments": int(len(lengths)),
        "segment_length_histogram": dict(sorted(histogram.items())),
        "segments_length_1": histogram[1],
        "segments_length_2": histogram[2],
        "segments_length_ge_3": int(np.count_nonzero(lengths >= 3)),
        "row_frames_in_length_1_segments": histogram[1],
        "row_frames_in_length_2_segments": 2 * histogram[2],
        "row_frames_in_length_ge_3_segments": int(lengths[lengths >= 3].sum()),
        "total_row_frames": int(nframes * height),
        "longest_segment_frames": int(lengths.max()),
        "source_per_frame_span_count": source_runs,
        "source_per_frame_boundary_values": source_boundary_values,
        "boundary_trajectories": model_boundaries,
        "color_trajectories": model_colors,
        "constant_boundary_trajectories": int(np.count_nonzero(model["BA_BOUND_NUM"] == 0)),
        "constant_color_trajectories": int(np.count_nonzero(model["BA_COLOR_NUM"] == 0)),
        "trajectory_scalar_count": trajectory_scalars,
        "uncompressed_per_frame_span_scalar_count": source_scalars,
        "trajectory_scalar_ratio_to_per_frame_spans": trajectory_scalars / source_scalars,
        "largest_array_elements": max(int(v.size) for v in model.values()),
        "max_denominator": int(max(model["BA_BOUND_DEN"].max(initial=1), model["BA_COLOR_DEN"].max(initial=1))),
        "pass": not mismatch.any() and invalid_boundaries == 0,
        "limitations": [
            "Input-derived 1D contour-crossing/luminance model; not the original animation scene graph or skeletal motion.",
            "Every source frame participates in exact fitting and validation; some topology changes necessarily require one-frame segments.",
            "Exactness applies to the frozen resized uint8 reference, not the original-resolution video or physical font rasterization.",
        ],
    }


def write_header(model, path):
    oversized = [key for key, array in model.items() if array.size > 1_000_000]
    if oversized:
        raise ValueError("ERB numeric array capacity exceeded; use --no-header and the packed exporter: " + ", ".join(oversized))
    lines = [
        "; Generated exact rational scanline geometry. No complete frame strings.",
        "; Coordinates and luminance are evaluated at runtime from adaptive segments.",
    ]
    for key, array in model.items():
        if array.ndim == 0:
            lines.append(f"#DIM CONST {key} = {int(array)}")
        else:
            if len(array) == 0:
                lines.append(f"#DIM CONST {key}, 1 = 0")
            else:
                lines.append(f"#DIM CONST {key}, {len(array)} = " + ",".join(str(int(x)) for x in array))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def fit_scalar(samples, first):
    """Scalar version of the exact interval fitter, avoiding tiny NumPy calls."""
    start, count = 0, len(samples)
    while start < count:
        base = int(samples[start])
        if start + 1 == count:
            yield first + start, first + start, base, 0, 1
            break
        delta = int(samples[start + 1]) - base
        ln, un, ld, ud = 2 * delta - 1, 2 * delta + 1, 2, 2
        last = start + 1
        for index in range(start + 2, count):
            denominator = 2 * (index - start)
            delta = int(samples[index]) - base
            a, b, c, d = ln, ld, un, ud
            low, up = 2 * delta - 1, 2 * delta + 1
            if low * b > a * denominator:
                a, b = low, denominator
            if up * d < c * denominator:
                c, d = up, denominator
            if a * d >= c * b:
                break
            ln, ld, un, ud = a, b, c, d
            last = index
        num, den = choose_slope(ln, ld, un, ud)
        yield first + start, first + last, base, num, den
        start = last + 1


def match_spans(previous, current):
    """Maximum-weight monotone matching; identities do not affect exactness.

    Positive overlap, nearby endpoints and nearby luminance favor continuity.
    Unmatched spans are born or die.  Matching remains monotone so live tracks
    never exchange order, and can be maintained by an ordered linked list.
    """
    n, m = len(previous), len(current)
    if n == 0 or m == 0:
        return []
    back = [bytearray(m + 1) for _ in range(n + 1)]
    prior = [0] * (m + 1)
    for i, (left, right, gray) in enumerate(previous, 1):
        scores = [0] * (m + 1)
        for j, (nl, nr, ng) in enumerate(current, 1):
            best = prior[j]
            direction = 1
            if scores[j - 1] > best:
                best, direction = scores[j - 1], 2
            overlap = max(0, min(right, nr) - max(left, nl))
            distance = abs(left - nl) + abs(right - nr)
            weight = 64 * (8 + 2 * overlap - distance) - abs(gray - ng)
            if weight > 0 and prior[j - 1] + weight >= best:
                best, direction = prior[j - 1] + weight, 3
            scores[j] = best
            back[i][j] = direction
        prior = scores
    matched = []
    i, j = n, m
    while i and j:
        direction = back[i][j]
        if direction == 3:
            matched.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif direction == 1:
            i -= 1
        else:
            j -= 1
    matched.reverse()
    return matched


def compile_persistent(frames):
    """Track nonblack spans across row topology changes and fit each channel."""
    frames = np.asarray(frames, dtype=np.uint8)
    nframes, height, width = frames.shape
    names = ("BA_TR_ROW", "BA_TR_FIRST", "BA_TR_LAST", "BA_TR_BIRTH_PREV",
             "BA_TR_LEFT", "BA_TR_RIGHT", "BA_TR_GRAY",
             "BA_C_START", "BA_C_LAST", "BA_C_BASE", "BA_C_NUM", "BA_C_DEN")
    a = {name: [] for name in names}
    birth_order = []
    joint_curve_count = 0
    samples_by_id = {}

    def finish(tid, last):
        nonlocal joint_curve_count
        samples = samples_by_id.pop(tid)
        a["BA_TR_LAST"][tid] = last
        first = a["BA_TR_FIRST"][tid]
        for channel, name in enumerate(("BA_TR_LEFT", "BA_TR_RIGHT", "BA_TR_GRAY")):
            a[name][tid] = len(a["BA_C_START"])
            for values in fit_scalar([s[channel] for s in samples], first):
                for key, value in zip(("BA_C_START", "BA_C_LAST", "BA_C_BASE", "BA_C_NUM", "BA_C_DEN"), values):
                    a[key].append(int(value))
        # Each joint vector segment would carry three trajectories.  Comparing
        # these counts quantifies why independent channels preserve good motion.
        joint_curve_count += 3 * sum(1 for _ in fit_integer_vectors(np.asarray(samples, dtype=np.int64), first))

    for row in range(height):
        previous, previous_ids = [], []
        for frame in range(nframes):
            data = frames[frame, row]
            edges = np.r_[0, np.flatnonzero(data[1:] != data[:-1]) + 1, width]
            current = [(int(left), int(right), int(data[left])) for left, right in zip(edges[:-1], edges[1:]) if data[left] != 0]
            matching = match_spans(previous, current)
            matched_old = {old for old, _ in matching}
            for old, tid in enumerate(previous_ids):
                if old not in matched_old:
                    finish(tid, frame - 1)
            inherited = {new: previous_ids[old] for old, new in matching}
            current_ids = []
            for new, sample in enumerate(current):
                if new in inherited:
                    tid = inherited[new]
                else:
                    tid = len(a["BA_TR_ROW"])
                    prev_id = current_ids[-1] if current_ids else -1
                    for key, value in (("BA_TR_ROW", row), ("BA_TR_FIRST", frame),
                                       ("BA_TR_LAST", -1), ("BA_TR_BIRTH_PREV", prev_id),
                                       ("BA_TR_LEFT", -1), ("BA_TR_RIGHT", -1), ("BA_TR_GRAY", -1)):
                        a[key].append(value)
                    samples_by_id[tid] = []
                    birth_order.append((frame, row, sample[0], tid))
                samples_by_id[tid].append(sample)
                current_ids.append(tid)
            previous, previous_ids = current, current_ids
        for tid in previous_ids:
            finish(tid, nframes - 1)
        print(f"tracked row {row + 1}/{height}: tracks={len(a['BA_TR_ROW'])}, curves={len(a['BA_C_START'])}", flush=True)
    result = {key: np.asarray(values, dtype=np.int64) for key, values in a.items()}
    result["BA_BIRTH_ID"] = np.asarray([t[3] for t in sorted(birth_order)], dtype=np.int64)
    result["BA_DEATH_ID"] = np.asarray(sorted(range(len(a["BA_TR_ROW"])), key=lambda t: (a["BA_TR_LAST"][t], a["BA_TR_ROW"][t], t)), dtype=np.int64)
    for key, value in (("BA_WIDTH", width), ("BA_HEIGHT", height), ("BA_FRAMES", nframes),
                       ("BA_FPS", 30), ("BA_TRACKS", len(a["BA_TR_ROW"])),
                       ("BA_CURVES", len(a["BA_C_START"]))):
        result[key] = np.asarray(value)
    return result, {"joint_fit_channel_trajectories": joint_curve_count,
                    "independent_fit_channel_trajectories": len(a["BA_C_START"])}


def validate_persistent(model, frames):
    """Evaluate persistent tracks independently of their matching history."""
    nframes, height, width = frames.shape
    reconstructed = np.zeros_like(frames)
    occupancy = np.zeros_like(frames, dtype=bool)
    count = int(model["BA_TRACKS"])
    interpolated_samples = {name: 0 for name in ("left", "right", "gray")}
    moving_interpolated_samples = {name: 0 for name in interpolated_samples}
    nonzero_spans = 0
    for tid in range(count):
        row = int(model["BA_TR_ROW"][tid])
        first = int(model["BA_TR_FIRST"][tid])
        last = int(model["BA_TR_LAST"][tid])
        channels = []
        for label, key in (("left", "BA_TR_LEFT"), ("right", "BA_TR_RIGHT"), ("gray", "BA_TR_GRAY")):
            values = np.empty(last - first + 1, dtype=np.int64)
            pointer = int(model[key][tid])
            covered = first
            while covered <= last:
                start, end = int(model["BA_C_START"][pointer]), int(model["BA_C_LAST"][pointer])
                if start != covered or end > last:
                    raise ValueError("Curve gap, overlap or channel overrun")
                elapsed = np.arange(end - start + 1)
                values[start - first:end - first + 1] = evaluate(model["BA_C_BASE"][pointer], model["BA_C_NUM"][pointer], model["BA_C_DEN"][pointer], elapsed)
                interior = max(0, end - start - 1)
                interpolated_samples[label] += interior
                if model["BA_C_NUM"][pointer] != 0:
                    moving_interpolated_samples[label] += interior
                covered = end + 1
                pointer += 1
            channels.append(values)
        for local, (left, right, gray) in enumerate(zip(*channels)):
            frame = first + local
            if not (0 <= left < right <= width and 0 < gray <= 255):
                raise ValueError("Invalid active span")
            if occupancy[frame, row, left:right].any():
                raise ValueError("Active spans overlap")
            occupancy[frame, row, left:right] = True
            reconstructed[frame, row, left:right] = gray
            nonzero_spans += 1
    # Validate exactly the event ordering the ERB linked-list runtime will use.
    heads = [-1] * height
    nxt, prev, alive = [-1] * count, [-1] * count, [False] * count
    bp, dp = 0, 0
    births, deaths = model["BA_BIRTH_ID"], model["BA_DEATH_ID"]
    for frame in range(nframes):
        while dp < count and model["BA_TR_LAST"][deaths[dp]] < frame:
            tid = int(deaths[dp]); row = int(model["BA_TR_ROW"][tid])
            if not alive[tid]:
                raise ValueError("Delete inactive track")
            if prev[tid] < 0:
                heads[row] = nxt[tid]
            else:
                nxt[prev[tid]] = nxt[tid]
            if nxt[tid] >= 0:
                prev[nxt[tid]] = prev[tid]
            alive[tid] = False
            dp += 1
        while bp < count and model["BA_TR_FIRST"][births[bp]] == frame:
            tid = int(births[bp]); row = int(model["BA_TR_ROW"][tid])
            left = int(model["BA_TR_BIRTH_PREV"][tid])
            if left >= 0 and (not alive[left] or model["BA_TR_ROW"][left] != row):
                raise ValueError("Birth predecessor is not active on this row")
            right = heads[row] if left < 0 else nxt[left]
            prev[tid], nxt[tid] = left, right
            if left < 0:
                heads[row] = tid
            else:
                nxt[left] = tid
            if right >= 0:
                prev[right] = tid
            alive[tid] = True
            bp += 1
        for row in range(height):
            cursor, seen = heads[row], 0
            while cursor >= 0:
                if not alive[cursor] or seen > count:
                    raise ValueError("Corrupt active track list")
                cursor = nxt[cursor]
                seen += 1
    mismatch = reconstructed != frames
    lengths = model["BA_C_LAST"] - model["BA_C_START"] + 1
    track_lengths = model["BA_TR_LAST"] - model["BA_TR_FIRST"] + 1
    return {
        "method": "Persistent nonblack scanline-span tracks; independent exact rational left/right/luminance trajectories",
        "frames": nframes, "height": height, "width": width,
        "pixels_compared": int(frames.size),
        "mismatching_pixels": int(mismatch.sum()),
        "mismatching_frames": int(np.count_nonzero(np.any(mismatch, axis=(1, 2)))),
        "reference_gray_sha256": hashlib.sha256(frames.tobytes()).hexdigest(),
        "reconstructed_gray_sha256": hashlib.sha256(reconstructed.tobytes()).hexdigest(),
        "tracks": count, "curves": int(len(lengths)),
        "track_length_histogram": dict(sorted(Counter(int(x) for x in track_lengths).items())),
        "curve_length_histogram": dict(sorted(Counter(int(x) for x in lengths).items())),
        "tracks_length_1": int(np.count_nonzero(track_lengths == 1)),
        "tracks_length_2": int(np.count_nonzero(track_lengths == 2)),
        "tracks_length_ge_3": int(np.count_nonzero(track_lengths >= 3)),
        "curves_length_1": int(np.count_nonzero(lengths == 1)),
        "curves_length_2": int(np.count_nonzero(lengths == 2)),
        "curves_length_ge_3": int(np.count_nonzero(lengths >= 3)),
        "longest_track_frames": int(track_lengths.max()),
        "longest_curve_frames": int(lengths.max()),
        "source_nonzero_span_samples": nonzero_spans,
        "source_nonzero_span_scalars": nonzero_spans * 3,
        "channel_samples_evaluated": nonzero_spans * 3,
        "channel_samples_from_curve_interiors": interpolated_samples,
        "channel_samples_from_nonconstant_curve_interiors": moving_interpolated_samples,
        "constant_curves": int(np.count_nonzero(model["BA_C_NUM"] == 0)),
        "curve_scalar_count": 5 * int(len(lengths)),
        "largest_array_elements": max(int(v.size) for v in model.values()),
        "max_denominator": int(model["BA_C_DEN"].max(initial=1)),
        "event_linked_list_checks": "pass",
        "pass": not mismatch.any(),
        "limitations": [
            "Data-derived horizontal span trajectories, not the original scene graph, bones or authored motion curves.",
            "Exactness applies to the frozen resized uint8 reference, not original-resolution video or physical font rasterization.",
            "Single- and two-frame curves remain where topology or exact luminance changes require dense keys.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("--key", default="gray")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-header", action="store_true")
    parser.add_argument("--persistent", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with np.load(args.reference) as loaded:
        frames = loaded[args.key]
    if args.key == "frames":
        frames = frames * np.uint8(255)
    fit_metrics = {}
    if args.persistent:
        model, fit_metrics = compile_persistent(frames)
    else:
        model = compile_geometry(frames)
    np.savez_compressed(args.output / "geometry_model.npz", **model)
    report = validate_persistent(model, frames) if args.persistent else validate(model, frames)
    report.update(fit_metrics)
    report["compiler_seconds"] = round(time.monotonic() - start, 3)
    if not args.no_header:
        write_header(model, args.output / "GEOMETRY.ERH")
    (args.output / "geometry_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    concise = {key: value for key, value in report.items() if not key.endswith("_histogram")}
    print(json.dumps(concise, ensure_ascii=False, indent=2))
    if not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
