#!/usr/bin/env python3
"""Exercise the real unified menu in an 80x25 POSIX PTY.

Production tests use unchanged release bytes. Branch-return tests use an
explicit isolated copy with movie limits reduced to 120 frames, never a fake
renderer or stubbed result. The menu and all mathematical routines are exact.
"""
from __future__ import annotations
import argparse
import codecs
import difflib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import re
import select
import shutil
import struct
import subprocess
import termios
import time
import numpy as np
from menu_screen import MenuScreen, render_state


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def active_manifest(root):
    paths = [p for directory in ("ERB", "CSV") for p in (root/directory).rglob("*") if p.is_file()]
    paths += [root/f"txt{i:02d}.txt" for i in range(5)] + [root/"PyEmuera.pyz"]
    return {str(p.relative_to(root)): {"bytes": p.stat().st_size, "sha256": sha(p)} for p in sorted(paths)}


def load_reference(path):
    """Read a uint8 grayscale array from .npy or the shipped .npz gray member."""
    loaded = np.load(path, allow_pickle=False)
    if isinstance(loaded, np.lib.npyio.NpzFile):
        with loaded:
            if "gray" not in loaded.files:
                raise ValueError("Reference NPZ must contain the gray array")
            reference = loaded["gray"]
    else:
        reference = loaded
    if reference.dtype != np.uint8 or reference.ndim != 3 or reference.shape[1:] != (24, 79) or len(reference) < 120:
        raise ValueError("Reference must be uint8 with shape (at least 120 frames, 24, 79)")
    return reference


def functions(text):
    matches = list(re.finditer(r"^@([A-Z0-9_]+)(?:\([^\n]*\))?\s*$", text, re.M))
    return {m.group(1): text[m.start():matches[i+1].start() if i+1<len(matches) else len(text)] for i,m in enumerate(matches)}


def short_copy(source, target):
    if target.exists():
        raise ValueError("Short-test copy already exists; choose a fresh output directory")
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".pyemuera", "logs", "__pycache__"))
    file = target/"ERB/PLAYER.ERB"
    old = file.read_text(encoding="utf-8-sig")
    blocks = functions(old)
    realtime = blocks["BA_REALTIME"]
    assert realtime.count("BA_RT_AUDIT = 0") == 1
    assert realtime.count("CALL BA_RUN_REALTIME, BA_FRAMES") == 1
    realtime = realtime.replace("BA_RT_AUDIT = 0", "BA_RT_AUDIT = 1").replace("CALL BA_RUN_REALTIME, BA_FRAMES", "CALL BA_RUN_REALTIME, 120")
    sequential = blocks["BA_RUN"]
    for expression in ("FOR LF, 0, BA_FRAMES", "BA_STARTMS + BA_FRAMES * 1000 / BA_FPS", "Completed {BA_FRAMES} / {BA_FRAMES}"):
        assert sequential.count(expression) == 1, expression
    sequential = sequential.replace("FOR LF, 0, BA_FRAMES", "FOR LF, 0, 120")
    sequential = sequential.replace("BA_STARTMS + BA_FRAMES * 1000 / BA_FPS", "BA_STARTMS + 120 * 1000 / BA_FPS")
    sequential = sequential.replace("Completed {BA_FRAMES} / {BA_FRAMES}", "Completed {120} / {120}")
    new = old.replace(blocks["BA_REALTIME"], realtime).replace(blocks["BA_RUN"], sequential)
    file.write_text(new, encoding="utf-8-sig")
    modified = functions(new)
    menu_names = [n for n in blocks if n == "SYSTEM_TITLE" or n.startswith("BA_MENU")]
    unchanged = {n: blocks[n] == modified[n] for n in blocks if n not in ("BA_REALTIME", "BA_RUN")}
    if not all(unchanged.values()):
        raise ValueError("Short test unexpectedly changed an unrelated function")
    return {"scope": "Isolated 120-frame real-loop test; not a full 6573-frame movie run",
            "source_runtime": str(source), "test_runtime": str(target),
            "menu_functions_byte_identical": all(blocks[n] == modified[n] for n in menu_names),
            "unchanged_functions": unchanged,
            "changes": ["BA_REALTIME passes 120 to the unchanged BA_RUN_REALTIME and emits audit after playback",
                        "BA_RUN iterates 0..119, waits for 120/30 seconds, reports 120; its actual sequential render/present body is unchanged"],
            "full_data_frame_constant_unchanged": True,
            "diff": "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile="production PLAYER.ERB", tofile="isolated short-test PLAYER.ERB"))}


def movie_audit(frames, expected_indices, reference):
    expected = []
    for index in expected_indices:
        image = reference[index]
        key = hashlib.sha256(image.tobytes()).hexdigest()
        if not expected or expected[-1][0] != key:
            expected.append((key, index))
    start = next((i for i,(key,_) in enumerate(frames) if key == expected[0][0]), None)
    matched = 0
    errors = []
    if start is not None:
        for key, image in frames[start:]:
            if matched < len(expected):
                if key != expected[matched][0]:
                    errors.append({"at": matched, "expected_source_frame": expected[matched][1]})
                    break
                matched += 1
            elif np.any(image):
                errors.append({"extra_nonempty_image": key})
                break
    return {"pass": matched == len(expected) and not errors,
            "expected_render_calls": len(expected_indices), "first_frame": expected_indices[0], "last_frame": expected_indices[-1],
            "expected_distinct_images": len(expected), "matched_distinct_images": matched,
            "mismatching_images": len(errors), "errors": errors}


class Session:
    def __init__(self, command, out):
        self.out = out
        self.raw = bytearray()
        self.screen = MenuScreen()
        self.decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 25, 80, 0, 0))
        self.err = (out/"stderr.log").open("wb")
        self.start = time.monotonic()
        self.last_output = self.start
        self.child = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=self.err,
            env=dict(os.environ, TERM="xterm-256color", COLUMNS="80", LINES="25"), start_new_session=True)
        os.close(slave)
        self.eof = False

    def pump(self, timeout=.05):
        if self.eof:
            return
        if select.select([self.master], [], [], timeout)[0]:
            try:
                chunk = os.read(self.master, 262144)
            except OSError:
                self.eof = True
                return
            if not chunk:
                self.eof = True
                return
            self.raw.extend(chunk)
            self.screen.feed(self.decoder.decode(chunk))
            self.last_output = time.monotonic()

    def menu(self, since=0, required_text="", footer="", timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump()
            visible = "\n".join(self.screen.lines())
            raw_tail = self.raw[since:].decode("utf-8", "replace")
            if (len(self.raw) > since and "B A D" in visible and "時間同期" in visible
                    and "全フレーム" in visible and "番号を入力して Enter" in visible
                    and "> " in visible and required_text in visible and footer in raw_tail
                    and time.monotonic() - self.last_output > .15):
                return self.screen.state()
            if self.child.poll() is not None:
                raise ValueError("Player exited before returning to the menu")
        raise TimeoutError("Menu/input prompt was not reached")

    def send(self, text):
        os.write(self.master, text.encode("utf-8") + b"\r")

    def close(self):
        if self.child.poll() is None:
            self.child.kill()
        self.child.wait()
        self.err.close()
        os.close(self.master)
        (self.out/"stdout.ansi").write_bytes(self.raw)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runtime", required=True, type=Path)
    p.add_argument("--python", required=True)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--scenario", choices=("production", "branches"), required=True)
    p.add_argument("--reference", type=Path, help="Grayscale .npy or .npz with a gray array; reference_frames.npz is supported")
    p.add_argument("--short-copy", type=Path)
    p.add_argument("--ascii-font", type=Path, help="Monospaced ASCII TTF/OTF font for the actual-cell preview")
    p.add_argument("--cjk-font", type=Path, help="Japanese CJK TTF/OTF/TTC font for the actual-cell preview")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    production = a.runtime.resolve()
    before = active_manifest(production)
    short = None
    runtime = production
    if a.scenario == "branches":
        if a.short_copy is None or a.reference is None:
            raise ValueError("Branch scenario requires --short-copy and --reference")
        runtime = a.short_copy.resolve()
        short = short_copy(production, runtime)
        (a.out/"short_test_changes.json").write_text(json.dumps(short, ensure_ascii=False, indent=2) + "\n")
    command = [a.python, "-B", str(runtime/"PyEmuera.pyz"), str(runtime)]
    session = Session(command, a.out)
    states = []
    movies = []
    error = None
    try:
        first = session.menu()
        states.append({"stage": "initial", "state": first})
        (a.out/"menu_initial.json").write_text(json.dumps(first, ensure_ascii=False, indent=2) + "\n")
        render_state(first, a.out/"menu_initial.png", ascii_font_path=a.ascii_font, cjk_font_path=a.cjk_font)
        if a.scenario == "production":
            for value in ("9", "abc", ""):
                offset = len(session.raw)
                session.send(value)
                state = session.menu(offset, required_text="0・1・2")
                states.append({"stage": "invalid_input", "input": value, "state": state})
        else:
            reference = load_reference(a.reference)
            for sequence, value in enumerate(("1", "2", "1")):
                offset = len(session.raw)
                image_start = len(session.screen.frames)
                session.send(value)
                footer = "Realtime complete." if value == "1" else "Completed 120 / 120"
                state = session.menu(offset, required_text="再生が終了しました", footer=footer)
                text = session.raw[offset:].decode("utf-8", "strict")
                timeline = None
                records = []
                record_conflicts = []
                if value == "1":
                    # Retained-screen scrolling repaints existing audit lines.
                    # Deduplicate identical records by index; reject any conflict.
                    by_index = {}
                    for match in re.findall(r"@PRESENT (\d+) (\d+) (\d+)", text):
                        record = tuple(map(int, match))
                        index = record[0]
                        if index in by_index:
                            if by_index[index] != record:
                                record_conflicts.append(index)
                        else:
                            by_index[index] = record
                            records.append(record)
                    indices = [r[0] for r in records]
                    timelines = set(tuple(map(int, m)) for m in re.findall(r"@TIMELINE (\d+) (\d+) (\d+) (\d+) (\d+)", text))
                    if len(timelines) == 1:
                        timeline = timelines.pop()
                    clock_ok = (bool(records) and not record_conflicts and records[0][0:2] == (0, 0)
                                and records[-1][0] == 119
                                and all(frame == min(119, elapsed*30//1000) and finished >= elapsed for frame,elapsed,finished in records)
                                and all(b[0] > a[0] and b[1] >= a[2] for a,b in zip(records, records[1:]))
                                and timeline is not None and timeline[0] == 120 and timeline[1] == len(records)
                                and timeline[1] + timeline[2] == 120 and timeline[3] >= 4000 and timeline[4] == 119)
                else:
                    indices = list(range(120))
                    clock_ok = True
                result = movie_audit(session.screen.frames[image_start:], indices, reference)
                result.update({"selection": value, "sequence": sequence, "footer_present": footer in text,
                               "clock_choice_pass": clock_ok, "return_menu": True,
                               "timeline_summary": timeline, "presentation_records": records,
                               "conflicting_frame_records": record_conflicts})
                result["pass"] = result["pass"] and clock_ok and footer in text
                movies.append(result)
                states.append({"stage": "returned_after_movie", "selection": value, "state": state})
        session.send("0")
        deadline = time.monotonic() + 10
        while session.child.poll() is None and time.monotonic() < deadline:
            session.pump()
        for _ in range(4):
            session.pump(.01)
        if session.child.poll() is None:
            raise TimeoutError("0 did not exit")
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        session.close()
    after = active_manifest(production)
    layout = []
    for record in states:
        state = record["state"]
        ok = (state["active_alternate_screen"] and state["max_nonblank_row"] <= 24
              and state["max_nonblank_column"] <= 79 and state["last_row_blank"] and state["last_column_blank"]
              and not state["unsupported_ansi"] and not state["physical_overflow_events"])
        layout.append({"stage": record["stage"], "pass": ok, "max_row": state["max_nonblank_row"],
                       "max_column": state["max_nonblank_column"], "cursor": state["cursor"]})
    result = {"pass": error is None and session.child.returncode == 0 and before == after and all(r["pass"] for r in layout) and all(m["pass"] for m in movies),
              "scenario": a.scenario, "command": command, "terminal": [80, 25],
              "production_runtime": str(production), "production_files_unchanged": before == after,
              "runtime_files": before, "exit_code": session.child.returncode, "error": error,
              "menu_states": layout, "movies": movies, "short_test_scope": short,
              "unsupported_ansi": session.screen.unsupported, "overflow_events": session.screen.overflows,
              "exit_choice_0_completed": error is None and session.child.returncode == 0,
              "elapsed_seconds": time.monotonic() - session.start,
              "capture_sha256": hashlib.sha256(session.raw).hexdigest(),
              "capture_bytes": len(session.raw),
              "initial_menu_state": str(a.out/"menu_initial.json"), "initial_menu_preview": str(a.out/"menu_initial.png")}
    (a.out/"states.json").write_text(json.dumps(states, ensure_ascii=False, indent=2) + "\n")
    (a.out/"report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k:result[k] for k in ("pass", "scenario", "exit_code", "error", "menu_states", "movies")}, ensure_ascii=False))
    raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
