#!/usr/bin/env python3
"""Combine focused bootstrap checks and freeze the shipped Windows entry files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "validation"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    tests_path = OUT / "console_utf8_tests.json"
    smoke_path = OUT / "console_utf8_smoke.json"
    tests = json.loads(tests_path.read_text())
    smoke = json.loads(smoke_path.read_text())
    helper = ROOT / "runtime/console_utf8.py"
    launcher = ROOT / "runtime/BadAppleERB.cmd"
    helper_sha = digest(helper)
    launcher_text = launcher.read_text()
    dispatch = {
        "all_interpreter_branches_use_bootstrap": launcher_text.count("-B console_utf8.py PyEmuera.pyz . %*") == 3,
        "python_utf8_environment": 'set "PYTHONUTF8=1"' in launcher_text and 'set "PYTHONIOENCODING=utf-8"' in launcher_text,
        "arguments_forwarded": launcher_text.count(". %* 2>logs\\diagnostics.log") == 3,
        "engine_exit_code_saved": 'set "BA_EXIT_CODE=%ERRORLEVEL%"' in launcher_text,
        "engine_exit_code_returned": "endlocal & exit /b %BA_EXIT_CODE%" in launcher_text,
        "diagnostic_path_kept_out_of_picture": launcher_text.count("2>logs\\diagnostics.log") == 3,
    }
    movie_reference = json.loads((OUT / "menu_acceptance.json").read_text())["runtime_files"]
    movie_identity = {}
    for name, record in movie_reference.items():
        path = ROOT / "runtime" / name
        movie_identity[name] = {"sha256": digest(path), "matches_reference": digest(path) == record["sha256"]}
    evidence_matches = tests["bootstrap_sha256"] == smoke["bootstrap_sha256"] == helper_sha
    files = {
        name: {"bytes": (ROOT / "runtime" / name).stat().st_size, "sha256": digest(ROOT / "runtime" / name)}
        for name in ("console_utf8.py", "BadAppleERB.cmd")
    }
    report = {
        "pass": tests["pass"] and smoke["pass"] and evidence_matches
                and all(dispatch.values()) and all(value["matches_reference"] for value in movie_identity.values()),
        "scope": "UTF-8 standard streams and console-code-page lifecycle, Windows launcher dispatch, and actual interpreter menu rendering",
        "invocation": "python -B console_utf8.py PyEmuera.pyz . [engine arguments]",
        "runtime_files": files,
        "runtime_file_sha256": {name: record["sha256"] for name, record in files.items()},
        "evidence_matches_frozen_bootstrap": evidence_matches,
        "code_page_lifecycle": {
            "method": "Controlled API responses exercise input/output code-page setup and conditional restoration",
            "input_and_output_snapshotted_separately": True,
            "nonzero_code_pages_set_to": 65001,
            "zero_code_page_requires_no_console_mutation": True,
            "stream_flush_precedes_restoration": True,
            "original_exception_and_system_exit_preserved": True,
            "test_count": tests["tests_run"], "cases": tests["cases"],
            "report": "validation/console_utf8_tests.json", "report_sha256": digest(tests_path),
        },
        "launcher": {"method": "Static dispatch and exit-code checks", "checks": dispatch},
        "menu_smoke": {
            "method": "Actual bundled interpreter, 80x25 PTY, inherited cp932 stream encoding, menu then choice0",
            "report": "validation/console_utf8_smoke.json", "report_sha256": digest(smoke_path),
            "command": smoke["command"], "initial_environment": smoke["initial_environment"],
            "stdout_decodes_as_strict_utf8": smoke["stdout_decodes_as_strict_utf8"],
            "rgb_escape_sequences_present": smoke["rgb_escape_sequences_present"],
            "japanese_menu_and_colors_match_accepted_cells": smoke["japanese_menu_and_colors_match_accepted_cells"],
            "exit_code": smoke["exit_code"], "movie_playback_performed": False,
            "unexpected_stderr": smoke["unexpected_stderr"],
        },
        "movie_payload_identity": {"reference": "validation/menu_acceptance.json", "files": movie_identity},
    }
    target = OUT / "console_utf8_verification.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"pass": report["pass"], "runtime_file_sha256": report["runtime_file_sha256"],
                      "output": "validation/console_utf8_verification.json"}))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
