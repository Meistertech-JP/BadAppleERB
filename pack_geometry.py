"""Pack persistent ERB trajectories without a table of finished raster frames.

The five UTF-8 text files hold track topology and piecewise rational curves.
Every encoded number uses non-surrogate BMP code units, offset by U+0100.
Coefficient and track identifiers use two little-endian base-32768 digits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def digit(value: int) -> str:
    if not 0 <= value < 32768:
        raise ValueError(f"Packed digit outside range: {value}")
    return chr(256 + value)


def ident(value: int) -> str:
    if not 0 <= value < 32768**2:
        raise ValueError(f"Packed identifier outside range: {value}")
    return digit(value % 32768) + digit(value // 32768)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model", type=Path)
    ap.add_argument("runtime", type=Path)
    args = ap.parse_args()
    with np.load(args.model) as archive:
        z = {name: archive[name] for name in archive.files}
    target = args.runtime
    (target / "ERB").mkdir(parents=True, exist_ok=True)
    tracks = int(z["BA_TRACKS"])
    curves = int(z["BA_CURVES"])
    order = np.asarray(z["BA_BIRTH_ID"], dtype=np.int64)
    inverse = np.empty(tracks, dtype=np.int64)
    inverse[order] = np.arange(tracks)
    if len(np.unique(order)) != tracks:
        raise ValueError("Birth order is not a track permutation")
    coeff, coeff_ids = np.unique(
        np.column_stack([z["BA_C_BASE"], z["BA_C_NUM"], z["BA_C_DEN"]]),
        axis=0,
        return_inverse=True,
    )
    if len(coeff) > 1_000_000:
        raise ValueError("Coefficient dictionary exceeds the ERB array limit")
    if np.any(coeff[:, 2] < 1):
        raise ValueError("Curve denominator must be positive")
    durations = z["BA_C_LAST"] - z["BA_C_START"] + 1
    if np.any(durations < 1) or np.any(durations >= 32768):
        raise ValueError("Invalid packed curve duration")
    channel_starts = np.sort(np.concatenate([z["BA_TR_LEFT"], z["BA_TR_RIGHT"], z["BA_TR_GRAY"]]))
    if len(np.unique(channel_starts)) != tracks * 3 or int(channel_starts[0]) != 0:
        raise ValueError("Channel pools do not have unique contiguous starts")
    channel_ends = np.empty(curves, dtype=np.int64)
    channel_ends[channel_starts] = np.r_[channel_starts[1:], curves]
    counts = {}
    for channel, file_index in [("LEFT", 0), ("RIGHT", 1), ("GRAY", 2)]:
        lines = []
        total = 0
        for old in order:
            old = int(old)
            start = int(z["BA_TR_" + channel][old])
            end = int(channel_ends[start])
            if int(durations[start:end].sum()) != int(z["BA_TR_LAST"][old] - z["BA_TR_FIRST"][old] + 1):
                raise ValueError(f"Curve coverage mismatch: track {old}, {channel}")
            lines.append("".join(digit(int(durations[i])) + ident(int(coeff_ids[i])) for i in range(start, end)))
            total += end - start
        path = target / f"txt{file_index:02d}.txt"
        path.write_bytes("\n".join(lines).encode("utf-8"))
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError(f"LOADTEXT size limit exceeded: {path}")
        counts[channel] = total
    metadata = []
    deaths = [[] for _ in range(int(z["BA_FRAMES"]) + 1)]
    previous_first = -1
    for new, old_value in enumerate(order):
        old = int(old_value)
        first = int(z["BA_TR_FIRST"][old])
        last = int(z["BA_TR_LAST"][old])
        row = int(z["BA_TR_ROW"][old])
        previous = int(z["BA_TR_BIRTH_PREV"][old])
        mapped_previous = int(inverse[previous]) if previous >= 0 else -1
        if first < previous_first:
            raise ValueError("Birth frames are not sorted")
        previous_first = first
        metadata.append(digit(first) + digit(row) + ident(mapped_previous + 1))
        deaths[last + 1].append(new)
    (target / "txt03.txt").write_bytes("\n".join(metadata).encode("utf-8"))
    (target / "txt04.txt").write_bytes("\n".join("".join(ident(i) for i in events) for events in deaths).encode("utf-8"))
    def decl(name: str, values) -> str:
        vals = np.asarray(values).reshape(-1)
        return f"#DIM CONST {name}, {len(vals)} = " + ",".join(str(int(x)) for x in vals) + "\n"
    header = "; Shared rational-curve coefficients. Track topology/curves are in txt00..04.\n"
    for name in ["BA_WIDTH", "BA_HEIGHT", "BA_FRAMES", "BA_FPS", "BA_TRACKS", "BA_CURVES"]:
        header += decl(name, [int(z[name])])
    header += decl("BA_COEFFS", [len(coeff)])
    for index, name in enumerate(["BA_D_BASE", "BA_D_NUM", "BA_D_DEN"]):
        header += decl(name, coeff[:, index])
    (target / "ERB/GEOMETRY.ERH").write_text(header, encoding="utf-8")
    paths = [target / f"txt{i:02d}.txt" for i in range(5)] + [target / "ERB/GEOMETRY.ERH"]
    report = {
        "format": "persistent-tracks-bmp15-v1",
        "tracks": tracks,
        "curve_pieces": curves,
        "shared_coefficients": len(coeff),
        "channel_pieces": counts,
        "digit_encoding": "Unicode code point = 256 + digit; digit range 0..32767; all code points U+0100..U+80FF, no surrogates",
        "identifier_encoding": "Two little-endian base-32768 digits",
        "txt00_txt02": "One line per birth-ordered track. Each curve piece is [duration, coefficient_id_low, coefficient_id_high]. Track first frame starts the first piece; subsequent pieces follow consecutively.",
        "txt03": "One line per birth-ordered track: [first_frame, row, previous_track_plus_one_low, previous_track_plus_one_high]. Zero previous-plus-one means row head.",
        "txt04": "One line per source frame, including the end sentinel frame N. Each death identifier is two digits. Process all deaths before that frame's births.",
        "files": [{"path": str(p.relative_to(target)), "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
    }
    (target / "packed_format.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("tracks", "curve_pieces", "shared_coefficients", "channel_pieces", "files")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
