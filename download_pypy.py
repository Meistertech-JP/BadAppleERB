"""Download the exact official PyPy archives recorded by this release.

Uses normal HTTPS and checks the published SHA-256 before committing each file.
This is a source-package rebuild helper, not part of the movie launch process.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("pypy_downloads"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    data = json.loads((root / "runtime/third_party/PyPy/bundle_provenance.json").read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    for item in data["archives"]:
        final = args.out / item["name"]
        expected = item["expected_sha256"]
        if final.exists() and hashlib.sha256(final.read_bytes()).hexdigest() == expected:
            print(f"Verified existing {final.name}")
            continue
        temporary = final.with_name(final.name + ".partial")
        checksum = hashlib.sha256()
        with urllib.request.urlopen(item["source_url"], timeout=120) as response, temporary.open("wb") as out:
            for block in iter(lambda: response.read(1024 * 1024), b""):
                out.write(block)
                checksum.update(block)
        if checksum.hexdigest() != expected:
            temporary.unlink()
            raise ValueError(f"Official checksum did not match: {item['name']}")
        temporary.replace(final)
        print(f"Downloaded and verified {final.name}")


if __name__ == "__main__":
    main()
