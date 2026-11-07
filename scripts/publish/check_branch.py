r"""Guard at the start of the Action "Build tiles and finalize": the branch must carry the release yaml and the code it needs.

Run command (the Action runs it before anything is uploaded; it needs only the Python standard library and PyYAML):
    python scripts/publish/check_branch.py --dataset abf-layers --version 0.2.0 --channel final

Why: a final run from a branch with older code once failed half way, after files of the release were already copied
to the public bucket (abf-energync 0.1.1, 07.11.2026). This check stops such a run before any upload.

It prints the branch and the commit (the person who starts the Action compares them with the branch named in the
instruction) and checks, by reading the files of the checkout:
  1. releases/<dataset>-v<version>.yaml exists and names the same dataset, version and tag;
  2. every layer yaml that the release lists exists;
  3. the code knows every feature the release uses: kind index (index_build.py), identity, phrase_check, each
     cross_checks kind (a branch of run_cross_checks in build_release.py), display.series (the key is in the layer
     schema), `requires_code` (files listed in the release yaml);
  4. channel final: the release has a DOI (10.5281/zenodo.<number>) and published_at.
Exit code 0 all good, 1 something is missing (the Action stops).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DOI_RE = re.compile(r"^10\.5281/zenodo\.\d+$")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def check(dataset: str, version: str, channel: str, root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    rel_path = root / "releases" / f"{dataset}-v{version}.yaml"
    if not rel_path.exists():
        return [f"releases/{dataset}-v{version}.yaml is not on this branch"]
    rel = yaml.safe_load(rel_path.read_text(encoding="utf-8")) or {}
    if rel.get("dataset") != dataset or str(rel.get("version")) != version or rel.get("tag") != f"{dataset}-v{version}":
        problems.append(f"the release yaml says dataset={rel.get('dataset')} version={rel.get('version')} tag={rel.get('tag')}, "
                        f"the Action was started for {dataset} {version}")
    build_release = read(root / "scripts/publish/build_release.py")
    schema = read(root / "schemas/meta.schema.json")
    layer_files = [str(x) for x in (rel.get("layers") or [])]
    for name in layer_files:
        if not (root / name.replace("\\", "/")).exists():
            problems.append(f"layer yaml {name} is not on this branch")
    if rel.get("kind") == "index" and not (root / "scripts/publish/index_build.py").exists():
        problems.append("the release has kind: index, but scripts/publish/index_build.py is not on this branch")
    if rel.get("identity") and "def run_identity" not in build_release:
        problems.append("the release has an identity block, the code of this branch has no run_identity")
    if rel.get("phrase_check") and "def run_phrase_check" not in build_release:
        problems.append("the release has phrase_check, the code of this branch has no run_phrase_check")
    for chk in rel.get("cross_checks") or []:
        kind = chk.get("kind")
        if f'kind == "{kind}"' not in build_release:
            problems.append(f"cross_checks kind {kind!r} is not known to the code of this branch")
    uses_series = False
    for name in layer_files:
        text = read(root / name.replace("\\", "/"))
        if re.search(r"^\s+series\s*:", text, flags=re.M):
            uses_series = True
    if uses_series and '"series"' not in schema:
        problems.append("a layer yaml has display.series, the schema of this branch has no such key")
    for req in rel.get("requires_code") or []:
        if not (root / str(req).replace("\\", "/")).exists():
            problems.append(f"requires_code: {req} is not on this branch")
    if channel == "final":
        if not rel.get("doi") or not DOI_RE.match(str(rel["doi"])):
            problems.append(f"channel final: doi in the release yaml is {rel.get('doi')!r}, expected 10.5281/zenodo.<number>")
        if not rel.get("published_at"):
            problems.append("channel final: published_at is empty in the release yaml")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Check that the branch carries the release yaml and the code the release needs.")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--channel", default="dev", choices=["dev", "final"])
    a = ap.parse_args()
    print(f"Branch: {os.environ.get('GITHUB_REF_NAME', '(not in Actions)')}  commit: {os.environ.get('GITHUB_SHA', '(unknown)')}")
    problems = check(a.dataset, a.version, a.channel)
    if problems:
        print(f"STOP before any upload: this branch is not ready for {a.dataset} {a.version} ({a.channel}):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK: the branch has the release yaml and the code for {a.dataset} {a.version} ({a.channel})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
