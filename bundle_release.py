"""Package the AA menu release while preserving verified playback code."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from archive_bundle import file_record, make_linux, make_zip

ROOT = Path(__file__).resolve().parent
PREFIX = "BadAppleERB_79x24_menu"


def read(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def function_blocks(path: Path) -> dict[str, str]:
    blocks = {}
    name = None
    lines = []
    for line in path.read_text(encoding="utf-8-sig").splitlines(keepends=True):
        if line.startswith("@"):
            if name is not None:
                blocks[name] = "".join(lines)
            name = line[1:].split("(", 1)[0].split()[0]
            lines = [line]
        elif name is not None:
            lines.append(line)
    if name is not None:
        blocks[name] = "".join(lines)
    return blocks


def executable_lines(block: str) -> list[str]:
    return [line.strip() for line in block.splitlines()
            if line.strip() and not line.lstrip().startswith(";")]


def make_utf8_patch(out: Path, files: dict[str, Path]) -> dict:
    """Build an overlay whose resulting inventory equals the complete release."""
    old = read("baseline/menu_win64_before_utf8_manifest.json")
    with zipfile.ZipFile(out / f"{PREFIX}_win64_PyPy.zip") as archive:
        manifest_bytes = archive.read(f"{PREFIX}/MANIFEST.json")
    current = json.loads(manifest_bytes)
    removed = set(old) - set(current)
    changed = {name for name, record in current.items() if old.get(name) != record}
    allowed = {"BadAppleERB.cmd", "console_utf8.py", "CREDITS.md", "README_ja.md", "README_en.md",
               "HOW_IT_WORKS_ja.txt", "HOW_IT_WORKS_en.txt", "VERIFICATION.json"}
    if removed or not {"BadAppleERB.cmd", "console_utf8.py"} <= changed or changed - allowed:
        raise ValueError("UTF-8 patch changed files outside its declared scope")
    overlay = {f"apply/{name}": files[name] for name in sorted(changed)}
    manifest_path = out / ".utf8_runtime_manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    overlay["apply/MANIFEST.json"] = manifest_path
    for language in ("ja", "en"):
        overlay[f"APPLY_{language}.txt"] = ROOT / "patch_notes" / f"APPLY_{language}.txt"
    patched = dict(old)
    for name in changed:
        patched[name] = file_record(files[name])
    if patched != current:
        raise ValueError("Patch overlay does not reproduce the complete package")
    result = make_zip(out / f"{PREFIX}_utf8_fix.zip", f"{PREFIX}_utf8_fix", overlay)
    result["changed_runtime_files"] = sorted(changed)
    result["overlay_matches_complete_windows_package"] = True
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-dir", type=Path, required=True)
    args = parser.parse_args()
    out = ROOT / "deliverables"
    out.mkdir(exist_ok=True)
    acceptance = read("validation/menu_acceptance.json")
    final_gate = read("validation/release_gate.json")
    previous_preservation = read("validation/previous_release_preservation.json")
    utf8_acceptance = read("validation/console_utf8_verification.json")
    if not all(report.get("pass") is True for report in (acceptance, final_gate, previous_preservation, utf8_acceptance)):
        raise ValueError("Menu acceptance or preservation has not passed")
    highlights = read("docs/highlights.json")
    preview_check = highlights["verification"]
    if not (preview_check["lossless_pixels_match"] and preview_check["sample_timing_matches"]
            and preview_check["duration_ms"] == highlights["excerpt"]["duration_ms"]):
        raise ValueError("Animated preview verification has not passed")
    expected_preview_paths = {"docs/highlights.webp", "docs/highlights-poster.png"}
    if {record["path"] for record in highlights["files"]} != expected_preview_paths:
        raise ValueError("Unexpected animated preview inventory")
    for record in highlights["files"]:
        current = file_record(ROOT / record["path"])
        if any(current[key] != record[key] for key in ("bytes", "sha256")):
            raise ValueError(f"Preview changed after validation: {record['path']}")
    documentation = ("README_ja.md", "README_en.md", "HOW_IT_WORKS_ja.txt", "HOW_IT_WORKS_en.txt")
    for name in documentation:
        path = ROOT / "runtime" / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            raise ValueError(f"Required documentation is missing: {name}")

    files = {}
    for path in sorted((ROOT / "runtime").rglob("*")):
        name = path.relative_to(ROOT / "runtime")
        if path.is_file() and name.parts[0] != "pypy" and str(name) not in {"MANIFEST.json", "VERIFICATION.json"}:
            if not any(part.startswith(".") or part in {"logs", "__pycache__"} for part in name.parts):
                files[str(name)] = path
    erb_names = [name for name in files if name.lower().endswith(".erb")]
    if erb_names != ["ERB/PLAYER.ERB"]:
        raise ValueError(f"This release must contain one ERB script: {erb_names}")
    current = function_blocks(ROOT / "runtime/ERB/PLAYER.ERB")
    baseline = function_blocks(ROOT / "baseline/PLAYER.ERB")
    unchanged = {name: executable_lines(block) == executable_lines(current[name])
                 for name, block in baseline.items() if name != "SYSTEM_TITLE"}
    if not all(unchanged.values()):
        raise ValueError("Existing playback or drawing instructions changed")
    if executable_lines(current["SYSTEM_TITLE"]) != ["@SYSTEM_TITLE", "CALL BA_MENU", "QUIT"]:
        raise ValueError("The production entry point does not open the menu")
    for implementation in ("cpython", "pypy"):
        frozen = read(f"baseline/{implementation}_timeline_runtime_before.json")
        for name, record in frozen.items():
            if name == "ERB/PLAYER.ERB":
                continue
            if name not in files or file_record(files[name])["sha256"] != record["sha256"]:
                raise ValueError(f"Verified engine/data/header changed: {name}")
    for name, sha256 in final_gate["runtime_file_sha256"].items():
        if name not in files or file_record(files[name])["sha256"] != sha256:
            raise ValueError(f"File changed after menu acceptance: {name}")
    for name, sha256 in utf8_acceptance["runtime_file_sha256"].items():
        if name not in files or file_record(files[name])["sha256"] != sha256:
            raise ValueError(f"File changed after UTF-8 startup acceptance: {name}")

    provenance = read("runtime/third_party/PyPy/bundle_provenance.json")
    archives = {}
    for record in provenance["archives"]:
        path = args.upstream_dir / record["name"]
        if file_record(path)["sha256"] != record["expected_sha256"]:
            raise ValueError(f"Upstream archive checksum mismatch: {path.name}")
        archives[path.suffix] = path
    report = {
        "title": "BadAppleERB 79x24 — AA menu, elapsed-time and all-frame playback",
        "date": "2026-11-26", "pass": True,
        "revision": "github-public-release-1",
        "runtime_revision": "windows-utf8-startup-1",
        "publication_notice": "CREDITS.md records original-work attribution and license scope. Recorded playback and UTF-8 startup checks retain their original evidence and hashes.",
        "publication_preview": highlights,
        "windows_console_utf8": utf8_acceptance,
        "single_erb_script": "ERB/PLAYER.ERB",
        "default_entry": "SYSTEM_TITLE -> BA_MENU",
        "choices": {"1": "BA_REALTIME", "2": "BA_PLAY", "0": "QUIT"},
        "return_to_menu_after_playback": True,
        "new_functions": sorted(set(current) - set(baseline)),
        "existing_function_instructions_unchanged": unchanged,
        "menu_acceptance": acceptance,
        "release_gate": final_gate,
        "previous_files_preserved": previous_preservation,
        "art": read("art/menu_art_metadata.json"),
        "prior_acceptance_scope": "Recorded full-film numerical and timing results cover identical playback functions, data and engine. Menu input is checked with the production playback limits; mode routing and return use isolated 120-frame sequences with the same menu functions.",
        "prior_full_logical_trace": read("baseline/actual_erb_full_report.json"),
        "prior_timeline_runs": {
            name: {key: value for key, value in read(f"baseline/{name}_timeline_full_audit.json").items()
                   if key not in {"selected_frame_indices", "presentation_records"}}
            for name in ("cpython", "pypy")
        },
        "pypy": provenance,
        "runtime_files": {name: file_record(file) for name, file in files.items()},
        "limits": [
            "Video only; no audio",
            "79x24 logical gray-cell accuracy, not original-resolution or physical-font pixel identity",
            "Terminal previews render logical cell values with a fixed font",
        ],
    }
    report_path = out / f"{PREFIX}_verification.json"
    write_json(report_path, report)
    files["VERIFICATION.json"] = report_path
    artifacts = [
        make_zip(out / f"{PREFIX}_win64_PyPy.zip", PREFIX, files, archives[".zip"]),
        make_linux(out / f"{PREFIX}_linux64_PyPy.tar.gz", PREFIX, files, archives[".gz"]),
    ]

    source = {f"runtime/{name}": path for name, path in files.items()}
    for name in (
        "README.md", "LICENSE", "CREDITS.md", ".gitattributes", ".gitignore",
        "bundle_release.py", "archive_bundle.py", "download_pypy.py",
        "menu_runtime_implementation.json", "previous_timeline_manifest.json",
        "extract_reference.py", "compiler_geometry.py", "pack_geometry.py",
        "reference_frames.npz", "reference_metadata.json", "requirements-build.txt",
    ):
        source[name] = ROOT / name
    for folder in ("validation", "baseline", "persistent_gray", "patch_notes"):
        for path in sorted((ROOT / folder).rglob("*")):
            relative = path.relative_to(ROOT)
            if path.is_file() and not any(part.startswith((".", "test_runtime")) or part == "__pycache__" for part in relative.parts):
                source[str(relative)] = path
    for path in sorted((ROOT / "docs").rglob("*")):
        if path.is_file():
            source[str(path.relative_to(ROOT))] = path
    for name in ("menu_art.txt", "menu_art_metadata.json", "menu_art_preview.png"):
        source[f"art/{name}"] = ROOT / "art" / name
    source["VERIFICATION.json"] = report_path
    artifacts.append(make_zip(out / f"{PREFIX}_source.zip", PREFIX + "_source", source))
    artifacts.append(make_utf8_patch(out, files))
    preview = out / f"{PREFIX}_preview.webp"
    shutil.copyfile(ROOT / "docs/highlights.webp", preview)
    for path in (report_path, preview):
        artifacts.append({"filename": path.name, **file_record(path)})
    write_json(out / "release_manifest.json", {"artifacts": artifacts})
    (out / "SHA256SUMS.txt").write_text("".join(
        f"{item['sha256']}  {item['filename']}\n" for item in artifacts
    ), encoding="utf-8")
    print(json.dumps({"artifacts": artifacts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
