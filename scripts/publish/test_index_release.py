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
ROOT = HERE.parent.parent
COMMON_COLS = ["record_id", "layer_id", "adm0", "adm0_basis", "adm0_other", "adm1", "adm2", "unit_basis", "unit_note", "adm1_point",
               "adm2_point", "approximate", "boundary_release"]
SETS = {
    "abf-dc": {"cols": COMMON_COLS + ["name", "status_raw", "type_group", "power_class", "power_mw"],
               "layers": {"dc_atlas_points": 3, "dc_epoch_points": 2}},
    "abf-energy": {"cols": COMMON_COLS + ["plant_name", "location_id", "type", "status_group", "capacity_mw"],
                   "layers": {"energy_plants_gem_units": 5}},
}
UNIT_NOTES = ["ambiguous_name", "connecticut", "no_county_field", "no_point", "no_state", "no_unit_near", "point_in_other_country",
              "region_not_matched", "region_only"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def make_set(root: Path, s: str, hashes: dict[str, str]) -> None:
    d = root / s
    d.mkdir(parents=True)
    files = {}
    zip_members = {}
    cols = SETS[s]["cols"]
    for iso, n in (("ABW", 2), ("FRA", 3)):
        csv = (",".join(cols) + "\n" + "".join(",".join([f"{iso}{i}"] + ["x"] * (len(cols) - 1)) + "\n" for i in range(n))).encode()
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
    meta = {"schema_version": "abf-index-meta-1.0", "set": s, "dataset": "abf-index", "boundary_release": BND, "files": files, "records": 5,
            "layers": SETS[s]["layers"], "unit_note_values": UNIT_NOTES,
            "aggregations": {"x": {"count": "records"}}}
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
        (self.src / "rules").mkdir()
        rules = (ROOT / "data" / "index" / "rules" / "atlas_adm1_countries.csv").read_bytes()
        (self.src / "rules" / "atlas_adm1_countries.csv").write_bytes(rules)
        self.inputs = {"atlas_adm1_countries.csv": {"bytes": len(rules), "sha256": sha(rules), "sha256_lf": sha(rules.replace(b"\r\n", b"\n"))}}
        (self.src / "build_hashes.json").write_text(json.dumps({"files": self.hashes, "inputs": self.inputs}), encoding="utf-8")
        rel = load_yaml(ROOT / "releases" / "abf-index-v0.1.0.yaml")
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
        self.assertIn("index/abf-dc/build_meta.json", files)
        self.assertIn("index/abf-dc/rules/atlas_adm1_countries.csv", files)
        self.assertNotIn("index/abf-energy/rules/atlas_adm1_countries.csv", files)
        self.assertEqual(manifest["indexes"][0]["rules"][0]["path"], "index/abf-dc/rules/atlas_adm1_countries.csv")
        self.assertNotIn("rules", manifest["indexes"][1])
        # zenodo list: archives, not the country files
        z = (out / "zenodo_files.txt").read_text(encoding="utf-8")
        self.assertIn("index/abf-dc/index_abf-dc.zip", z)
        self.assertNotIn("ABW.csv.gz", z)

    def test_public_meta_and_archive(self) -> None:
        out = self.run_release(self.rel)
        for s in ("abf-dc", "abf-energy"):
            build = json.loads((out / "index" / s / "build_meta.json").read_text(encoding="utf-8"))
            pub = json.loads((out / "index" / s / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual((out / "index" / s / "build_meta.json").read_bytes(), (self.src / s / "meta.json").read_bytes())
            for k, v in build.items():                       # the technical keys word for word
                self.assertEqual(pub[k], v, k)
            for k in ("title", "description", "known_gaps", "verification", "sources", "fields", "null_meaning", "unit_note_descriptions",
                      "license", "release", "aggregations_labels", "totals_note", "dataset_description", "attribution_text"):
                self.assertIn(k, pub, k)
            self.assertEqual([f["name"] for f in pub["fields"]], SETS[s]["cols"])
            self.assertEqual(pub["release"]["doi"], None)
            self.assertEqual(pub["license"]["family"], "attribution")
            self.assertNotIn("inputs", pub["sources"][0])
            self.assertEqual(set(pub["unit_note_descriptions"]), set(UNIT_NOTES))
        dc = json.loads((out / "index/abf-dc/meta.json").read_text(encoding="utf-8"))
        self.assertEqual([x["source_id"] for x in dc["sources"]][:1], ["atlas_of_data_center_politics"])
        self.assertEqual(len({x["source_id"] for x in dc["sources"]}), len(dc["sources"]))
        name = next(f for f in dc["fields"] if f["name"] == "name")
        self.assertEqual(name["copied_from"], ["dc_atlas_points", "dc_epoch_points"])
        # archive: deterministic, public meta.json inside, rules only in abf-dc
        zp = out / "index/abf-dc/index_abf-dc.zip"
        with zipfile.ZipFile(zp) as z:
            names = z.namelist()
            self.assertEqual(names, sorted(names))
            self.assertIn("rules/atlas_adm1_countries.csv", names)
            self.assertEqual(z.read("meta.json"), (out / "index/abf-dc/meta.json").read_bytes())
            self.assertNotIn("build_meta.json", names)
            self.assertTrue(all(i.date_time == (1980, 1, 1, 0, 0, 0) and i.compress_type == zipfile.ZIP_STORED for i in z.infolist()))
        with zipfile.ZipFile(out / "index/abf-energy/index_abf-energy.zip") as z:
            self.assertFalse(any(n.startswith("rules/") for n in z.namelist()))
        first = {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in out.rglob("*") if p.is_file() and p.suffix in (".zip", ".json")
                 and p.name != "build_log.json"}
        shutil.rmtree(self.tmp / "out")
        out2 = self.run_release(self.rel)
        second = {p.relative_to(out2).as_posix(): sha(p.read_bytes()) for p in out2.rglob("*") if p.is_file() and p.suffix in (".zip", ".json")
                  and p.name != "build_log.json"}
        self.assertEqual(first, second)
        # final: the DOI is in the public meta
        shutil.rmtree(self.tmp / "out")
        rel = copy.deepcopy(self.rel)
        rel["doi"] = "10.5281/zenodo.24030844"
        out3 = self.run_release(rel, "final")
        self.assertEqual(json.loads((out3 / "index/abf-dc/meta.json").read_text(encoding="utf-8"))["release"]["doi"], "10.5281/zenodo.24030844")

    def test_text_gates(self) -> None:
        def broken(mutate) -> None:
            shutil.rmtree(self.tmp / "out", ignore_errors=True)
            rel = copy.deepcopy(self.rel)
            mutate(rel)
            with self.assertRaises(GateError):
                self.run_release(rel)

        broken(lambda r: r["indexes"][0].pop("texts"))
        broken(lambda r: r["indexes"][0].pop("layer_metas"))
        broken(lambda r: r["indexes"][1].update(layer_metas={"energy_plants_gem_units": r["indexes"][1]["layer_metas"]["energy_plants_gem_units"],
                                                             "dc_epoch_points": r["indexes"][0]["layer_metas"]["dc_epoch_points"]}))
        broken(lambda r: r["indexes"][0].update(rules=["rules/missing.csv"]))
        # a column of the CSV without a text
        shutil.rmtree(self.tmp / "out", ignore_errors=True)
        rel = copy.deepcopy(self.rel)
        tp = self.tmp / "abf-dc-texts.yaml"
        d = load_yaml(ROOT / "releases" / "index_texts" / "abf-dc.yaml")
        d["copied_fields"]["dc_atlas_points"].remove("status_raw")
        tp.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
        rel["indexes"][0]["texts"] = [rel["indexes"][0]["texts"][0], str(tp)]
        with self.assertRaises(GateError):
            self.run_release(rel)

    def test_rules_file_changed_is_a_stop(self) -> None:
        p = self.src / "rules" / "atlas_adm1_countries.csv"
        p.write_bytes(p.read_bytes() + b"X,1\n")
        with self.assertRaises(GateError):
            self.run_release(self.rel)

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
        (self.src / "build_hashes.json").write_text(json.dumps({"files": self.hashes, "inputs": self.inputs}), encoding="utf-8")
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
        root = ROOT / "releases"
        a = load_yaml(root / "abf-index-v0.1.0.yaml")
        self.assertEqual((a["kind"], a["layers"], a["license"]["family"]), ("index", [], "attribution"))
        self.assertEqual([i["set"] for i in a["indexes"]], ["abf-dc", "abf-energy"])
        b = load_yaml(root / "abf-energync-v0.1.1.yaml")
        self.assertEqual(b["license"]["family"], "non_commercial")
        self.assertEqual(b["indexes"][0]["set"], "abf-energync")
        self.assertIn("version_note", b["release_texts"])
        self.assertEqual(b["identity"]["layers"], ["energy_plants_gem_tzsam_units", "energy_plants_gem_tzsam_locations"])
        self.assertEqual(b["layers"], load_yaml(root / "abf-energync-v0.1.0.yaml")["layers"])
        self.assertTrue(b["doi"] is None or b["doi"].startswith("10.5281/zenodo."))   # null until the DOI is reserved


if __name__ == "__main__":
    unittest.main()
