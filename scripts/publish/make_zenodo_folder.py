r"""Put the files for Zenodo of one release into one flat folder: zenodo_upload_<date>\<dataset>\ (A-062).

Run command (from the repository root, Windows), after verify_release.py --save-manifest:
    python scripts\publish\make_zenodo_folder.py --release-dir "D:\GISData\release\abf-index-v0.2.0"

Options: --out "D:\GISData\release" (default: the folder that holds the release folder), --date 2026-11-22 (default: today).

What it does: reads zenodo_files.txt of the release folder, copies exactly those files, without any sub-folders, into
<out>\zenodo_upload_<date>\<dataset>\ and checks every copy against manifest.json (size and SHA-256), so that a file of another
build cannot reach Zenodo. Then it prints the MD5 of every file; Zenodo shows the same MD5 for each file of a draft.
The upload to Zenodo takes only the files of this folder. Nothing in the release folder is changed or deleted.
It stops, and copies nothing, if: manifest.json is missing (verify_release.py --save-manifest was not run), the manifest is not
of this release or has another DOI than build_plan.json, a listed file is missing or differs from the manifest, two files
would get one name, or the target folder already holds files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import sha256_file  # noqa: E402

ANNOTATION = re.compile(r"^(\S+)\s+\(.*\)\s*$")     # "manifest.json  (after verify_release.py --save-manifest)"


def listed_names(text: str) -> list[str]:
    """Names of zenodo_files.txt, one per line, without the remark in brackets."""
    names: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = ANNOTATION.match(line)
        names.append(m.group(1) if m else line)
    return names


def manifest_refs(manifest: dict) -> dict[str, dict]:
    """path -> {bytes, sha256} for every file the manifest names one by one."""
    refs: dict[str, dict] = {}

    def add(ref: dict) -> None:
        refs[ref["path"]] = {"bytes": ref["bytes"], "sha256": ref["sha256"]}

    for layer in manifest.get("layers", []):
        add(layer["meta"])
        for ref in layer["files"].values():
            add(ref)
        for ref in layer.get("extra_files", []):
            add(ref)
    for ref in manifest.get("extra_files", []):
        add(ref)
    for ref in manifest.get("source_archives", []):
        add(ref)
    for ix in manifest.get("indexes", []):
        for key in ("meta", "build_meta", "adm0_other", "summary", "archive"):
            add(ix[key])
        add(ix["country_files"]["listing"])
        for ref in ix.get("rules", []):
            add(ref)
    return refs


def md5_file(path: Path) -> str:
    h = hashlib.md5()  # noqa: S324 (the same sum Zenodo shows; not used for security)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def plan_copies(release_dir: Path) -> tuple[dict, list[tuple[Path, str]]]:
    """Check the release folder and return (plan, [(source, target name)]). Raises SystemExit with a clear text."""
    zf = release_dir / "zenodo_files.txt"
    if not zf.exists():
        raise SystemExit(f"STOP: {zf} not found; is this a release folder made by build_release.py?")
    plan_path = release_dir / "build_plan.json"
    if not plan_path.exists():
        raise SystemExit(f"STOP: {plan_path} not found")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    mpath = release_dir / "manifest.json"
    if not mpath.exists():
        raise SystemExit("STOP: manifest.json is not in the release folder. Run verify_release.py with --save-manifest on the "
                         "final manifest of this release first.")
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    for key in ("dataset", "version", "doi"):
        if manifest.get(key) != plan.get(key):
            raise SystemExit(f"STOP: manifest.json has {key} {manifest.get(key)!r}, build_plan.json has {plan.get(key)!r}; "
                             "the manifest is not of this release")
    if not manifest.get("doi"):
        raise SystemExit("STOP: the manifest has no DOI; Zenodo gets only the files of a final release")
    refs = manifest_refs(manifest)
    copies: list[tuple[Path, str]] = []
    seen: dict[str, str] = {}
    for name in listed_names(zf.read_text(encoding="utf-8")):
        src = release_dir / name
        if not src.is_file():
            raise SystemExit(f"STOP: {name} is listed in zenodo_files.txt but is not in the release folder")
        target = src.name
        if target in seen:
            raise SystemExit(f"STOP: {name} and {seen[target]} would both be uploaded as {target}")
        seen[target] = name
        if name != "manifest.json":
            ref = refs.get(name)
            if ref is None:
                raise SystemExit(f"STOP: {name} is not in manifest.json")
            if src.stat().st_size != ref["bytes"] or sha256_file(src) != ref["sha256"]:
                raise SystemExit(f"STOP: {name} differs from manifest.json (size or SHA-256); it is not the file that was published")
        copies.append((src, target))
    return manifest, copies


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--release-dir", required=True, help=r'release folder, for example "D:\GISData\release\abf-index-v0.2.0"')
    ap.add_argument("--out", help="folder for zenodo_upload_<date> (default: the folder that holds the release folder)")
    ap.add_argument("--date", default=date.today().isoformat(), help="date in the folder name, YYYY-MM-DD (default: today)")
    args = ap.parse_args(argv)
    release_dir = Path(args.release_dir)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        raise SystemExit("STOP: --date must look like 2026-11-22")
    manifest, copies = plan_copies(release_dir)
    out_root = Path(args.out) if args.out else release_dir.parent
    target_dir = out_root / f"zenodo_upload_{args.date.replace('-', '')}" / manifest["dataset"]
    if target_dir.exists() and any(target_dir.iterdir()):
        raise SystemExit(f"STOP: {target_dir} already holds files; remove it or choose another --date")
    target_dir.mkdir(parents=True, exist_ok=True)
    for src, name in copies:
        shutil.copy2(src, target_dir / name)
    print(f"{manifest['dataset']} {manifest['version']}  DOI {manifest['doi']}")
    print(f"Folder for Zenodo: {target_dir}")
    print(f"{len(copies)} files, checked against manifest.json. MD5 as Zenodo shows it:")
    for _, name in copies:
        print(f"  {md5_file(target_dir / name)}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
