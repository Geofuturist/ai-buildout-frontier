r"""Tests of the release code of the territory index (abf-index 0.1.0, index of abf-energync in 0.1.1): index_build, kind index,
manifest with indexes, schema, files of the manifest, git copy, content headers of .csv.gz.

Run from the repository root (Windows):
    python scripts\publish\test_index_release.py

What is real: the manifest schema, the code. What is synthetic: the index folder (two countries, a few rows), made here with the
same file names and meta.json keys as scripts/index/build_index.py of CODE-GEM.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_release as BR  # noqa: E402
import finalize_release as FR  # noqa: E402
import index_build as IB  # noqa: E402
import verify_release as VR  # noqa: E402
from common import GateError, content_headers, load_yaml  # noqa: E402

BND = "abf-boundaries-v0.2.0"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def make_set(root: Path, s: str, hashes: dict[str, str]) -> None:
    d = root / s
    d.mkdir(parents=True)
    files = {}
    zip_members = {}
    for iso, n in (("ABW", 2), ("FRA", 3)):
        csv = ("unit_id,count\n" + "".join(f"{iso}{i},{i}\n" for i in range(n))).encode()
        gz = gzip.compress(csv, mtime=0)
        (d / f"{iso}.csv").write_bytes(csv)
        (d / f"{iso}.csv.gz").write_bytes(gz)
        hashes[f"{s}/{iso}.csv"], hashes[f"{s}/{iso}.csv.gz"] = sha(csv), sha(gz)
        files[iso] = {"rows": n, "csv_bytes": len(csv), "csv_gz_bytes": len(gz), "sha256": sha(csv)}
        zip_members[f"{iso}.csv.gz"] = gz
    other = b"unit_id,count\nZZZ,1\n"
    (d / "adm0_other.csv").write_bytes(other)
    (d / "adm0_other.csv.gz").write_bytes(gzip.compress(other, mtime=0))
    (d / "summary.csv").write_bytes(b"iso3,rows\nABW,2\nFRA,3\n")
    meta = {"schema_version": "abf-index-meta-1.0", "set": s, "boundary_release": BND, "files": files, "records": 5,
            "layers": {"layer_a": 3, "layer_b": 2}}
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with zipfile.ZipFile(d / f"index_{s}.zip", "w", zipfile.ZIP_STORED) as z:
        for k, v in zip_members.items():
            z.writestr(k, v)
        z.writestr("summary.csv", (d / "summary.csv").read_bytes())
        z.writestr("meta.json", (d / "meta.json").read_bytes())
    for name in ("adm0_other.csv.gz", "summary.csv", "meta.json", f"index_{s}.zip"):
        hashes[f"{s}/{name}"] = sha((d / name).read_bytes())


class IndexRelease(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = self.tmp / "index"
        self.hashes: dict[str, str] = {}
        for s in ("abf-dc", "abf-energy"):
            make_set(self.src, s, self.hashes)
        (self.src / "build_hashes.json").write_text(json.dumps({"files": self.hashes, "inputs": {}}), encoding="utf-8")
        rel = load_yaml(HERE.parent.parent / "releases" / "abf-index-v0.1.0.yaml")
        rel["indexes_dir"] = str(self.src)
        self.rel = rel

    def run_release(self, rel: dict, channel: str = "dev") -> Path:
        rp = self.tmp / "release.yaml"
        rp.write_text(yaml.safe_dump(rel, sort_keys=False, allow_unicode=True), encoding="utf-8")
        args = argparse.Namespace(release=str(rp), out=str(self.tmp / "out"), channel=channel, override=None,
                                  built_at="2026-11-06T12:00:00Z", verbose=False)
        self.assertEqual(BR.run(args), 0)
        return self.tmp / "out" / rel["tag"]

    def test_full_chain(self) -> None:
        out = self.run_release(self.rel)
        plan = json.loads((out / "build_plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["kind"], "index")
        self.assertEqual(plan["layers"], [])
        self.assertEqual([e["index_id"] for e in plan["indexes"]], ["index_abf-dc", "index_abf-energy"])
        for name in ("index/abf-dc/ABW.csv.gz", "index/abf-dc/adm0_other.csv.gz", "index/abf-dc/summary.csv", "index/abf-dc/meta.json",
                     "index/abf-dc/index_abf-dc.zip", "index/abf-energy/listing.json"):
            self.assertTrue((out / name).exists(), name)
        manifest = FR.compose_manifest(plan, out)
        FR.validate_manifest(manifest)
        self.assertEqual(manifest["kind"], "index")
        self.assertEqual(manifest["indexes"][0]["country_files"]["count"], 2)
        files = FR.manifest_files(manifest, out)
        self.assertIn("index/abf-dc/FRA.csv.gz", files)
        self.assertIn("index/abf-energy/index_abf-energy.zip", files)
        for rel, ref in files.items():
            self.assertEqual(sha((out / rel).read_bytes()), ref["sha256"], rel)
        # the same through the verify code (listings come from the listing.json files)
        listings = {ix["index_id"]: json.loads((out / ix["country_files"]["listing"]["path"]).read_text())["files"] for ix in manifest["indexes"]}
        self.assertEqual(set(VR.files_of(manifest, listings)), set(files))
        git = FR.files_for_git(manifest, plan)
        self.assertEqual(sorted(git), ["index/abf-dc/meta.json", "index/abf-energy/meta.json", "manifest.json"])
        # zenodo list: archives, not the country files
        z = (out / "zenodo_files.txt").read_text(encoding="utf-8")
        self.assertIn("index/abf-dc/index_abf-dc.zip", z)
        self.assertNotIn("ABW.csv.gz", z)

    def test_manifest_schema_rules(self) -> None:
        out = self.run_release(self.rel)
        plan = json.loads((out / "build_plan.json").read_text(encoding="utf-8"))
        good = FR.compose_manifest(plan, out)
        bad = copy.deepcopy(good)
        del bad["indexes"]
        with self.assertRaises(GateError):
            FR.validate_manifest(bad)
        bad = copy.deepcopy(good)
        del bad["license"]
        with self.assertRaises(GateError):
            FR.validate_manifest(bad)
        bad = copy.deepcopy(good)
        del bad["kind"]          # without kind a manifest needs layers
        with self.assertRaises(GateError):
            FR.validate_manifest(bad)

    def test_gate_g14(self) -> None:
        def broken(mutate) -> None:
            shutil.rmtree(self.tmp / "out", ignore_errors=True)
            rel = copy.deepcopy(self.rel)
            mutate(rel)
            with self.assertRaises(GateError):
                self.run_release(rel)

        broken(lambda r: r.update(layers=["layers\\x.yaml"]))                 # kind index with layers
        broken(lambda r: r.pop("license"))
        broken(lambda r: r.update(boundary_release="abf-boundaries-v0.1.0"))   # index built on another boundary release
        broken(lambda r: r["indexes"].append(dict(r["indexes"][0])))           # a set twice

    def test_changed_file_is_a_stop(self) -> None:
        p = self.src / "abf-dc" / "FRA.csv.gz"
        p.write_bytes(p.read_bytes() + b"x")
        with self.assertRaises(GateError):
            self.run_release(self.rel)

    def test_csv_not_matching_gz_is_a_stop(self) -> None:
        p = self.src / "abf-energy" / "ABW.csv"
        data = p.read_bytes() + b"ABW9,9\n"
        p.write_bytes(data)
        self.hashes["abf-energy/ABW.csv"] = sha(data)
        (self.src / "build_hashes.json").write_text(json.dumps({"files": self.hashes, "inputs": {}}), encoding="utf-8")
        with self.assertRaises(GateError):
            self.run_release(self.rel)

    def test_content_headers(self) -> None:
        h = content_headers("index/abf-dc/ABW.csv.gz")
        self.assertEqual(h["Content-Type"], "application/gzip")
        self.assertNotIn("Content-Encoding", h)
        self.assertIn("immutable", h["Cache-Control"])
        self.assertEqual(content_headers("dev/abf-index/v0.1.0/index/abf-dc/ABW.csv.gz")["Cache-Control"], "public, max-age=60")
        self.assertEqual(content_headers("index/abf-dc/summary.csv")["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(content_headers("index/abf-dc/index_abf-dc.zip")["Content-Type"], "application/zip")

    def test_yamls_of_the_release(self) -> None:
        root = HERE.parent.parent / "releases"
        a = load_yaml(root / "abf-index-v0.1.0.yaml")
        self.assertEqual((a["kind"], a["layers"], a["license"]["family"]), ("index", [], "attribution"))
        self.assertEqual([i["set"] for i in a["indexes"]], ["abf-dc", "abf-energy"])
        b = load_yaml(root / "abf-energync-v0.1.1.yaml")
        self.assertEqual(b["license"]["family"], "non_commercial")
        self.assertEqual(b["indexes"][0]["set"], "abf-energync")
        self.assertEqual(b["identity"]["layers"], ["energy_plants_gem_tzsam_units", "energy_plants_gem_tzsam_locations"])
        self.assertEqual(b["layers"], load_yaml(root / "abf-energync-v0.1.0.yaml")["layers"])
        self.assertIsNone(b["doi"])


if __name__ == "__main__":
    unittest.main()
