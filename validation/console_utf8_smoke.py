#!/usr/bin/env python3
"""Capture the real menu and exit through the UTF-8 bootstrap in an 80x25 PTY."""
from __future__ import annotations

import argparse
import codecs
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import termios
import time

from menu_screen import MenuScreen

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True)
    parser.add_argument("--report", type=Path, default=Path(__file__).with_suffix(".json"))
    args = parser.parse_args()
    runtime = ROOT / "runtime"
    command = [args.python, "-B", str(runtime / "console_utf8.py"), str(runtime / "PyEmuera.pyz"), str(runtime)]
    expected_path = ROOT / "validation/production_pypy/menu_initial.json"
    expected = json.loads(expected_path.read_text())
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 25, 80, 0, 0))
    environment = dict(os.environ, TERM="xterm-256color", COLUMNS="80", LINES="25",
                       PYTHONIOENCODING="cp932", PYTHONUTF8="0")
    child = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=subprocess.PIPE,
                             env=environment, start_new_session=True)
    os.close(slave)
    raw = bytearray()
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    screen = MenuScreen()
    initial = None
    error = None
    eof = False
    start = last_output = time.monotonic()

    def pump(timeout=.05):
        nonlocal eof, last_output
        if eof or not select.select([master], [], [], timeout)[0]:
            return
        try:
            block = os.read(master, 65536)
        except OSError:
            eof = True
            return
        if not block:
            eof = True
            return
        raw.extend(block)
        screen.feed(decoder.decode(block))
        last_output = time.monotonic()

    try:
        deadline = start + 30
        while time.monotonic() < deadline:
            pump()
            lines = "\n".join(screen.lines())
            if all(text in lines for text in ("時間同期", "全フレーム", "終了", "番号を入力して Enter", "> ")):
                if time.monotonic() - last_output > .15:
                    initial = screen.state()
                    break
            if child.poll() is not None:
                raise RuntimeError("Entry point exited before the menu prompt")
        if initial is None:
            raise TimeoutError("Menu prompt was not reached")
        os.write(master, b"0\r")
        deadline = time.monotonic() + 10
        while child.poll() is None and time.monotonic() < deadline:
            pump()
        if child.poll() is None:
            raise TimeoutError("Menu choice 0 did not exit")
        for _ in range(4):
            pump(.01)
        decoder.decode(b"", final=True)
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()
        stderr = child.stderr.read()
        child.stderr.close()
        os.close(master)

    keys = ("terminal", "cursor", "characters", "foreground_rgb", "background_rgb",
            "max_nonblank_row", "max_nonblank_column", "last_row_blank", "last_column_blank")
    cells_match = initial is not None and all(initial[key] == expected[key] for key in keys)
    ansi_colors = b"\x1b[0;38;2;" in raw
    stderr_text = stderr.decode("utf-8", "backslashreplace")
    known_notice = "[PyEmuera warning] Text layout uses a logical cell grid; fonts and pixel positioning are not reproduced."
    unexpected_stderr = [line for line in stderr_text.splitlines() if line and line != known_notice]
    passed = (error is None and child.returncode == 0 and not unexpected_stderr and cells_match and ansi_colors
              and not screen.unsupported and not screen.overflows)
    report = {
        "pass": passed,
        "scope": "Actual bundled-interpreter menu startup and choice-0 exit with inherited cp932 standard-stream encoding; no movie playback",
        "command": [Path(args.python).name, "-B", "runtime/console_utf8.py", "runtime/PyEmuera.pyz", "runtime"],
        "initial_environment": {"PYTHONIOENCODING": "cp932", "PYTHONUTF8": "0"},
        "bootstrap_sha256": digest(runtime / "console_utf8.py"),
        "engine_sha256": digest(runtime / "PyEmuera.pyz"),
        "player_sha256": digest(runtime / "ERB/PLAYER.ERB"),
        "terminal": [80, 25], "exit_code": child.returncode, "error": error,
        "stdout_decodes_as_strict_utf8": error is None,
        "japanese_menu_and_colors_match_accepted_cells": cells_match,
        "rgb_escape_sequences_present": ansi_colors,
        "accepted_cell_reference": "validation/production_pypy/menu_initial.json",
        "accepted_cell_reference_sha256": digest(expected_path),
        "menu_lines": initial["lines"] if initial else [],
        "unsupported_ansi": screen.unsupported, "physical_overflow_events": screen.overflows,
        "stderr": stderr_text, "unexpected_stderr": unexpected_stderr,
        "stdout_sha256": hashlib.sha256(raw).hexdigest(), "stdout_bytes": len(raw),
        "stdout_utf8": raw.decode("utf-8", "backslashreplace"),
        "elapsed_seconds": time.monotonic() - start,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("pass", "exit_code", "error", "japanese_menu_and_colors_match_accepted_cells")}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
