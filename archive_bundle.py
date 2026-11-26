"""Create release archives, record member hashes, and verify archive readback."""
from __future__ import annotations
import copy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import zipfile


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_record(path: Path) -> dict:
    return {"type": "file", "bytes": path.stat().st_size, "sha256": digest(path.read_bytes())}


def safe_name(name: str) -> str:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise ValueError(f"Unsafe archive member: {name}")
    return str(p)


def verify_archive(path: Path, prefix: str, manifest: dict, is_tar: bool) -> dict:
    if is_tar:
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
            names = [m.name for m in members]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate archive names")
            actual = {m.name[len(prefix) + 1:] for m in members if m.isfile() or m.issym()}
            if actual != set(manifest) | {"MANIFEST.json"}:
                raise ValueError("Archive inventory differs from manifest")
            for name, record in manifest.items():
                member = archive.getmember(f"{prefix}/{name}")
                if record["type"] == "symlink":
                    if not member.issym() or member.linkname != record["target"]:
                        raise ValueError(f"Link changed: {name}")
                else:
                    data = archive.extractfile(member).read()
                    if len(data) != record["bytes"] or digest(data) != record["sha256"]:
                        raise ValueError(f"File changed: {name}")
    else:
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if not n.endswith("/")]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate archive names")
            if set(names) != {f"{prefix}/{name}" for name in manifest} | {f"{prefix}/MANIFEST.json"}:
                raise ValueError("Archive inventory differs from manifest")
            for name, record in manifest.items():
                data = archive.read(f"{prefix}/{name}")
                if len(data) != record["bytes"] or digest(data) != record["sha256"]:
                    raise ValueError(f"File changed: {name}")
    return {"filename": path.name, "bytes": path.stat().st_size,
            "sha256": digest(path.read_bytes()), "verified_members": len(manifest),
            "archive_readback_all_hashes_and_links_match": True}


def make_zip(path: Path, prefix: str, files: dict[str, Path], upstream: Path | None = None) -> dict:
    manifest = {name: file_record(file) for name, file in files.items()}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        for name, file in sorted(files.items()):
            out.write(file, f"{prefix}/{safe_name(name)}")
        if upstream:
            with zipfile.ZipFile(upstream) as source:
                for entry in source.infolist():
                    parts = PurePosixPath(entry.filename).parts
                    if len(parts) <= 1:
                        continue
                    relative = safe_name(str(PurePosixPath(*parts[1:])))
                    name = "pypy/" + relative
                    info = copy.copy(entry)
                    info.filename = f"{prefix}/{name}" + ("/" if entry.is_dir() else "")
                    data = source.read(entry)
                    out.writestr(info, data)
                    if not entry.is_dir():
                        manifest[name] = {"type": "file", "bytes": len(data), "sha256": digest(data)}
        out.writestr(f"{prefix}/MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    return verify_archive(path, prefix, manifest, False)


def make_linux(path: Path, prefix: str, files: dict[str, Path], upstream: Path) -> dict:
    manifest = {name: file_record(file) for name, file in files.items()}
    with tarfile.open(path, "w:gz", compresslevel=6, dereference=False) as out:
        for name, file in sorted(files.items()):
            out.add(file, arcname=f"{prefix}/{safe_name(name)}", recursive=False)
        with tarfile.open(upstream, "r:gz") as source:
            for entry in source:
                parts = PurePosixPath(entry.name).parts
                if len(parts) <= 1:
                    continue
                name = "pypy/" + safe_name(str(PurePosixPath(*parts[1:])))
                info = copy.copy(entry)
                info.name = f"{prefix}/{name}"
                if entry.isfile():
                    data = source.extractfile(entry).read()
                    manifest[name] = {"type": "file", "bytes": len(data), "sha256": digest(data)}
                    out.addfile(info, io.BytesIO(data))
                elif entry.issym():
                    manifest[name] = {"type": "symlink", "target": entry.linkname}
                    out.addfile(info)
                elif entry.isdir():
                    out.addfile(info)
                else:
                    raise ValueError(f"Unsupported upstream archive member: {entry.name}")
        data = (json.dumps(manifest, indent=2) + "\n").encode()
        info = tarfile.TarInfo(f"{prefix}/MANIFEST.json")
        info.size = len(data)
        info.mode = 0o644
        out.addfile(info, io.BytesIO(data))
    return verify_archive(path, prefix, manifest, True)
