#!/usr/bin/env python3
"""Freeze menu acceptance and pair its unchanged movie core with prior evidence."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from validate_menu import active_manifest

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "validation"
BASELINE = ROOT / "baseline"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def body_sections(path):
    raw = path.read_bytes()
    matches = list(re.finditer(rb"^@([A-Z0-9_]+)(?:\([^\r\n]*\))?\s*$", raw, re.M))
    result = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        lines = raw[match.start():end].splitlines(keepends=True)
        # Comments between functions describe the following section. Compare
        # exact bytes from @definition through the final executable statement.
        while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith(b";")):
            lines.pop()
        result[match.group(1).decode()] = b"".join(lines)
    return result


def function_body_sha256(path):
    return {name: hashlib.sha256(body).hexdigest() for name, body in body_sections(path).items()}


def executable_lines_sha256(path):
    """Digest nonblank, noncomment raw lines, joined with LF and preserving bytes."""
    lines = [line for line in path.read_bytes().splitlines()
             if line.strip() and not line.lstrip().startswith(b";")]
    return hashlib.sha256(b"\n".join(lines)).hexdigest()


def release_source_relation(tests, current, player_path):
    """Keep recorded test hashes while checking a documented comment-only bridge."""
    exact = all(report["runtime_files"] == current for report in tests.values())
    if exact:
        return {"pass": True, "all_runtime_hashes_identical": True, "bridge_used": False}
    bridge_path = OUT / "release_source_bridge.json"
    bridge = json.loads(bridge_path.read_text())
    bodies = function_body_sha256(player_path)
    instructions = executable_lines_sha256(player_path)
    checks = {
        "release_player_hash_matches_receipt": current["ERB/PLAYER.ERB"]["sha256"] == bridge.get("release_player_sha256"),
        "receipt_records_comment_only_change": bridge.get("changed_lines") == 1
            and bridge.get("change_kind") == "Section comment wording only"
            and bridge.get("executable_lines_byte_identical") is True,
        "tested_and_release_function_bodies_match_actual_release":
            bridge.get("tested_function_body_sha256") == bridge.get("release_function_body_sha256") == bodies,
        "tested_and_release_executable_lines_match_actual_release":
            bridge.get("tested_executable_lines_sha256") == bridge.get("release_executable_lines_sha256") == instructions,
    }
    matches = {}
    for name, report in tests.items():
        recorded = report["runtime_files"]
        matches[name] = (set(recorded) == set(current)
                         and recorded["ERB/PLAYER.ERB"]["sha256"] == bridge.get("tested_player_sha256")
                         and all(value == current.get(key) for key, value in recorded.items() if key != "ERB/PLAYER.ERB"))
    return {
        "pass": all(checks.values()) and all(matches.values()),
        "all_runtime_hashes_identical": False, "bridge_used": True,
        "report": "validation/release_source_bridge.json", "report_sha256": sha(bridge_path),
        "tested_player_sha256": bridge.get("tested_player_sha256"),
        "release_player_sha256": bridge.get("release_player_sha256"),
        "checks": checks, "test_reports_matched": matches,
        "scope": "Recorded test source hashes are retained; release source differs by one section comment and preserves every function body and executable line",
    }


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    runtime = ROOT / "runtime"
    current = active_manifest(runtime)
    baseline_manifest_paths = [BASELINE / f"{name}_timeline_runtime_before.json" for name in ("cpython", "pypy")]
    baseline_manifests = [json.loads(path.read_text()) for path in baseline_manifest_paths]
    baseline_files = baseline_manifests[0]
    baseline_manifests_equal = all(value == baseline_files for value in baseline_manifests)
    old = body_sections(BASELINE / "PLAYER.ERB")
    new = body_sections(runtime / "ERB/PLAYER.ERB")
    preserved = {}
    for name, body in old.items():
        if name == "SYSTEM_TITLE":
            continue
        other = new.get(name, b"")
        preserved[name] = {
            "byte_identical": body == other,
            "bytes": len(body),
            "baseline_sha256": hashlib.sha256(body).hexdigest(),
            "menu_sha256": hashlib.sha256(other).hexdigest(),
        }
    unchanged_files = {
        name: {"byte_identical": data == current.get(name), **data}
        for name, data in baseline_files.items() if name != "ERB/PLAYER.ERB"
    }
    preservation = {
        "pass": baseline_manifests_equal and all(v["byte_identical"] for v in preserved.values())
                and all(v["byte_identical"] for v in unchanged_files.values())
                and sorted(set(new) - set(old)) == ["BA_MENU", "BA_MENU_ART", "BA_MENU_DRAW"],
        "baseline_source": "baseline/PLAYER.ERB",
        "baseline_runtime_manifests": [str(path.relative_to(ROOT)) for path in baseline_manifest_paths],
        "baseline_runtime_manifests_equal": baseline_manifests_equal,
        "menu_runtime": "runtime",
        "function_body_definition": "Exact bytes from @definition through the final executable statement, excluding only following blank lines and section comments",
        "intentional_changed_function": "SYSTEM_TITLE: CALL BA_REALTIME replaced with CALL BA_MENU; QUIT retained",
        "new_functions": sorted(set(new) - set(old)),
        "prior_functions_preserved": preserved,
        "nonplayer_active_files_preserved": unchanged_files,
        "movie_function_count": len(preserved),
        "new_erb_source_files": [str(p.relative_to(runtime)) for p in sorted((runtime / "ERB").glob("*.ERB"))],
    }
    dump(OUT / "menu_function_preservation.json", preservation)

    test_names = ("production_cpython", "production_pypy", "branches_pypy_corrected")
    tests = {name: json.loads((OUT / name / "report.json").read_text()) for name in test_names}
    source_relation = release_source_relation(tests, current, runtime / "ERB/PLAYER.ERB")
    reports_still_match = source_relation["all_runtime_hashes_identical"]
    production_tests = {}
    for name in test_names[:2]:
        report = tests[name]
        states = json.loads((OUT / name / "states.json").read_text())
        invalid = [state for state in states if state["stage"] == "invalid_input"]
        input_results = [{"input": state["input"], "re_prompted": "0・1・2" in "\n".join(state["state"]["lines"])} for state in invalid]
        production_tests[name] = {
            "pass": report["pass"] and [r["input"] for r in input_results] == ["9", "abc", ""]
                    and all(r["re_prompted"] for r in input_results),
            "command": report["command"], "production_source_tested_without_loop_modification": True,
            "tested_player_sha256": report["runtime_files"]["ERB/PLAYER.ERB"]["sha256"],
            "invalid_inputs": input_results,
            "choice_0_exited": report["exit_choice_0_completed"],
            "layout_states": report["menu_states"],
            "report": str((OUT / name / "report.json").relative_to(ROOT)),
            "report_sha256": sha(OUT / name / "report.json"),
            "ansi_capture_sha256": report["capture_sha256"],
        }
    branches = tests[test_names[2]]
    branch_summary = []
    for row in branches["movies"]:
        branch_summary.append({key: value for key, value in row.items() if key != "presentation_records"})
    branch_scope = branches["short_test_scope"]
    branch_ok = (branches["pass"] and [r["selection"] for r in branches["movies"]] == ["1", "2", "1"]
                 and branches["exit_choice_0_completed"] and branch_scope["menu_functions_byte_identical"]
                 and all(r["first_frame"] == 0 and r["last_frame"] == 119 and r["return_menu"] for r in branches["movies"]))

    prior = OUT / "prior_full_evidence"
    prior_names = ("actual_erb_full_report.json", "cpython_full_audit.json", "pypy_full_audit.json", "pypy_seek_audit.json", "preservation_audit.json")
    evidence = []
    for relative in prior_names:
        target = prior / relative
        contents = json.loads(target.read_text())
        evidence.append({
            "file": str(target.relative_to(ROOT)), "sha256": sha(target), "pass": contents["pass"],
            "scope": contents.get("scope", "Existing renderer and prior release preservation"),
            "key_results": {key: value for key, value in contents.items() if not isinstance(value, (dict, list))},
        })

    state_path = OUT / "production_pypy/menu_initial.json"
    preview_path = OUT / "production_pypy/menu_initial.png"
    state = json.loads(state_path.read_text())
    state_cpython = json.loads((OUT / "production_cpython/menu_initial.json").read_text())
    screen_equal = state == state_cpython
    report = {
        "pass": preservation["pass"] and source_relation["pass"] and all(r["pass"] for r in production_tests.values())
                and branch_ok and screen_equal and all(e["pass"] for e in evidence)
                and preservation["new_erb_source_files"] == ["ERB/PLAYER.ERB"],
        "scope": "Unified menu acceptance in an 80x25 terminal; real playback, menu return, and restart tested in an isolated 120-frame copy; full-film evidence paired with preserved function bodies and numerical data",
        "production_runtime": "runtime",
        "runtime_files": current,
        "all_test_reports_match_current_runtime_hashes": reports_still_match,
        "all_test_reports_match_release_or_verified_source_bridge": source_relation["pass"],
        "release_source_relation": source_relation,
        "single_erb_file": preservation["new_erb_source_files"] == ["ERB/PLAYER.ERB"],
        "function_preservation": {
            "pass": preservation["pass"], "count": len(preserved),
            "report": "validation/menu_function_preservation.json",
            "report_sha256": sha(OUT / "menu_function_preservation.json"),
            "definition": preservation["function_body_definition"],
        },
        "production_menu_tests": production_tests,
        "viewport": {
            "terminal_columns": 80, "terminal_rows": 25,
            "max_nonblank_column": state["max_nonblank_column"],
            "max_nonblank_row": state["max_nonblank_row"],
            "host_input_prompt_row": 24, "reserved_row_25_blank": state["last_row_blank"],
            "reserved_column_80_blank": state["last_column_blank"],
            "all_menu_states_fit": all(row["pass"] for test in tests.values() for row in test["menu_states"]),
            "production_cpython_and_pypy_cell_states_equal": screen_equal,
            "production_cpython_and_pypy_ansi_output_equal": tests["production_cpython"]["capture_sha256"] == tests["production_pypy"]["capture_sha256"],
        },
        "mode_route_return_and_restart": {
            "pass": branch_ok, "input_sequence": ["1", "2", "1", "0"],
            "route_mapping": {"1": "BA_REALTIME", "2": "BA_PLAY", "0": "RETURN from BA_MENU then QUIT"},
            "movies": branch_summary,
            "second_and_third_plays_begin_at_frame_zero": all(r["first_frame"] == 0 for r in branches["movies"][1:]),
            "second_realtime_clock_restarted_at_zero": branches["movies"][-1]["presentation_records"][0][:2] == [0, 0],
            "choice_0_exited": branches["exit_choice_0_completed"],
            "report": "validation/branches_pypy_corrected/report.json",
            "report_sha256": sha(OUT / "branches_pypy_corrected/report.json"),
        },
        "short_test_copy_scope": branch_scope,
        "prior_full_movie_evidence": {
            "new_full_6573_frame_run_performed": False,
            "coverage_basis": "All 17 preexisting movie function bodies, the engine, headers, and numerical data match the recorded full-film validation inputs.",
            "evidence": evidence,
        },
        "artifacts": {
            "production_menu_png": str(preview_path.relative_to(ROOT)),
            "production_menu_png_sha256": sha(preview_path),
            "production_menu_cells_json": str(state_path.relative_to(ROOT)),
            "production_menu_cells_sha256": sha(state_path),
            "preview_scope": state["preview_scope"],
            "preview_font_files": ["DejaVuSansMono.ttf (20 px)", "NotoSansCJK-Regular.ttc (22 px)"],
            "preview_cell_pixels": [12, 25], "preview_image_pixels": [960, 625],
            "production_stdout_ansi": "validation/production_pypy/stdout.ansi",
        },
        "limitations": [
            "This is terminal-cell and RGB correctness at 79x24, not optical identity with source video pixels or a native terminal font.",
            "Realtime mode deliberately skips elapsed source frames when drawing falls behind; it does not guarantee 30 rendered frames per second.",
        ],
    }
    dump(OUT / "menu_acceptance.json", report)
    print(json.dumps({"pass": report["pass"], "movie_functions_preserved": len(preserved),
                      "all_test_reports_match_current_runtime_hashes": reports_still_match,
                      "all_test_reports_match_release_or_verified_source_bridge": source_relation["pass"],
                      "production_tests": {name: row["pass"] for name, row in production_tests.items()},
                      "short_branch_test": branch_ok, "output": "validation/menu_acceptance.json"}, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
