r"""Tests of the abf-boundaries 0.3.0 release code (no network, no real geometry, nothing written to the repository).

Run from the repository root (Windows):
    python scripts\publish\test_release_bnd_v030.py

What is real: the release yaml and the layer yaml of 0.3.0, boundaries\boundary_registry.csv, boundaries\national_sources_v030.csv,
the registry published with v0.2.0 and the units.csv of v0.2.0, schemas\meta.schema.json, content\methodology.md.
What is synthetic: the meta.json of CODE-BND (made from national_sources_v030.csv), the unit rows of the 15 new countries and the
saved pages of the phrase check.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import jsonschema  # noqa: E402
import pandas as pd  # noqa: E402

import boundaries_build as BB  # noqa: E402
import check_bnd_phrases as CP  # noqa: E402
import patch_bnd_v030 as PB  # noqa: E402
import patch_methodology_bnd_v030 as PM  # noqa: E402
import scan_meta_texts as SC  # noqa: E402
from common import GateError, load_yaml  # noqa: E402

REL = ROOT / "releases" / "abf-boundaries-v0.3.0.yaml"
LAYER = ROOT / "layers" / "abf_boundaries.yaml"
REGISTRY = ROOT / "boundaries" / "boundary_registry.csv"
SOURCES_CSV = ROOT / "boundaries" / "national_sources_v030.csv"
UNITS_020 = ROOT / "data" / "abf-boundaries" / "v0.2.0" / "units.csv"
SCHEMA = ROOT / "schemas" / "meta.schema.json"
CYR = re.compile("[Ѐ-ӿ]")
NEW15 = ["COL", "EST", "HKG", "IDN", "IRL", "LVA", "LUX", "MEX", "NZL", "PER", "PHL", "KOR", "TWN", "THA", "VNM"]
OLD_EXCLUDE = ["USA", "FRA", "GBR", "NOR"]


class Ctx:
    """The little that compute_verification and the unit-type check need from the build context."""
    def __init__(self, channel: str = "dev", root: Path | None = None) -> None:
        self.channel = channel
        self.warnings: list[str] = []
        self.report = SimpleNamespace(warn=self.warnings.append)
        self.boundaries = SimpleNamespace(root=root)


@contextlib.contextmanager
def in_root():
    old = Path.cwd()
    os.chdir(ROOT)
    try:
        yield
    finally:
        os.chdir(old)


class ReleaseFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rel = load_yaml(REL)
        cls.cfg = load_yaml(LAYER)
        cls.registry = pd.read_csv(REGISTRY, dtype=str, keep_default_na=False)

    def test_release_yaml_basics(self) -> None:
        r = self.rel
        self.assertEqual((r["dataset"], r["version"], r["tag"]), ("abf-boundaries", "0.3.0", "abf-boundaries-v0.3.0"))
        self.assertIn(r["doi"], (None, "10.5281/zenodo.24403851"))        # null before the final build, the DOI of the record after it
        self.assertIn(r["published_at"], (None, "2026-11-20"))
        self.assertEqual(r["expected_counts"], {"adm0": 242, "adm1": 2092, "adm2": 3602})
        fm = r["file_map"]
        self.assertEqual(len(fm), 24)                               # 5 display + 19 analysis
        self.assertEqual(sum(1 for k in fm if k.startswith("analysis/")), 19)
        self.assertEqual(len(set(fm.values())), len(fm))
        for iso in NEW15:
            self.assertIn(f"analysis_{iso.lower()}_adm1", fm.values())
        ver = r["verification_from_registry"]
        self.assertEqual(set(ver["exclude_iso3"]), set(OLD_EXCLUDE + NEW15))
        self.assertEqual((ver["expected_countries"], ver["expected_units"]), (104, 431))
        self.assertEqual(r["registry_unit_types"], {"exclude_iso3": OLD_EXCLUDE, "multi_type": 32, "empty": 21})
        self.assertEqual(r["registry_frozen_rows"]["changed_rows"], [])

    def test_reference_files(self) -> None:
        ref = self.rel["reference_files"]
        for key in ref:
            self.assertIn(key, BB.REFERENCE_DESCRIPTIONS, key)
        for key in ("overlap_whitelist", "national_adm1_units", "national_adm1_report", "diag_outside_adm0"):
            self.assertIn(key, ref)
        # no .txt diagnostics and no validation_report.md (ARCH7, D2)
        self.assertFalse([k for k in ref if "txt" in k or k.endswith("_md")])
        for key, value in ref.items():
            if isinstance(value, dict) and "sha256" in value:
                self.assertRegex(value["sha256"], r"^[0-9a-f]{64}$", key)
        self.assertEqual(ref["national_adm1_units"]["sha256"], "a2a5729e011b872a29ddccd47e0d8df876b6982d69748140a3323f185d2dd824")
        for key, value in ref.items():                                 # files of the repository: they must exist and have no Cyrillic (G7)
            if isinstance(value, str) and value.startswith("boundaries"):
                p = ROOT / value.replace("\\", "/")
                self.assertTrue(p.exists(), p)
                BB.check_reference_text(p)

    def test_registry_numbers(self) -> None:
        reg = self.registry
        adm1 = reg[reg["level"].str.upper() == "ADM1"]
        self.assertEqual(adm1[adm1["verified"].str.lower() == "true"]["iso3"].nunique(), 123)
        ctx = Ctx("final")
        lines: list[str] = []
        BB.check_registry_unit_types(self.rel, reg, ctx, lines)    # raises in final when 32 / 21 are wrong
        self.assertEqual(ctx.warnings, [])
        bad = dict(self.rel, registry_unit_types={"exclude_iso3": OLD_EXCLUDE, "multi_type": 29, "empty": 21})
        with self.assertRaises(GateError):
            BB.check_registry_unit_types(bad, reg, Ctx("final"), [])

    def test_verification_share(self) -> None:
        units = pd.read_csv(UNITS_020, dtype=str, keep_default_na=False)
        rows = {lvl: units[units["level"] == lvl][["unit_id", "iso3"]] for lvl in ("ADM0", "ADM1", "ADM2")}
        new = pd.DataFrame({"unit_id": [f"{iso}-1-{i}" for iso in NEW15 for i in range(1000)][:0], "iso3": []})
        counts = {"COL": 33, "EST": 15, "HKG": 18, "IDN": 38, "IRL": 26, "LVA": 42, "LUX": 12, "MEX": 32, "NZL": 17, "PER": 25,
                  "PHL": 18, "KOR": 16, "TWN": 22, "THA": 77, "VNM": 34}
        new = pd.DataFrame([{"unit_id": f"{iso}-1-{i}", "iso3": iso} for iso, n in counts.items() for i in range(n)])
        # the 15 countries were in the display file of 0.2.0 as ADM0 only; units of 0.2.0 + the 425 new ones
        levels = {"adm0": rows["ADM0"], "adm1": pd.concat([rows["ADM1"], new]), "adm2": rows["ADM2"]}
        self.assertEqual({k: len(v) for k, v in levels.items()}, {"adm0": 242, "adm1": 2092, "adm2": 3602})
        ctx = Ctx("final")
        out = BB.compute_verification(self.cfg, self.rel, self.registry, levels, ctx, [])
        self.assertEqual(ctx.warnings, [])                               # 27 countries, 431 units, verdicts 22 / 3 / 2
        self.assertAlmostEqual(out["verification"]["sample_share"]["adm1_countries_official_list"], 0.260, places=3)
        self.assertAlmostEqual(out["verification"]["levels"]["agent_sample"], 0.073, places=3)

    def test_frozen_rows_against_v020(self) -> None:
        with in_root():
            BB.check_registry_frozen_rows(self.rel, [])

    def test_frozen_rows_catch_a_change(self) -> None:
        with tempfile.TemporaryDirectory() as td, in_root():
            changed = self.registry.copy()
            i = changed.index[(changed["iso3"] == "POL") & (changed["level"].str.upper() == "ADM1")][0]
            changed.loc[i, "notes"] = changed.loc[i, "notes"] + " x"
            p = Path(td) / "reg.csv"
            changed.to_csv(p, index=False, encoding="utf-8")
            rel = dict(self.rel, boundaries={**self.rel["boundaries"], "registry": str(p)})
            with self.assertRaises(GateError):
                BB.check_registry_frozen_rows(rel, [])

    def test_no_cyrillic_and_no_placeholders_in_public_text(self) -> None:
        texts: list[tuple[str, str]] = []

        def walk(o, path=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{path}[{i}]")
            elif isinstance(o, str):
                texts.append((path, o))
        walk({k: v for k, v in self.cfg.items() if k not in ("title_ru", "citation")})
        self.assertGreater(len(texts), 100)
        for path, t in texts:
            self.assertFalse(CYR.search(t), path)
            self.assertFalse(re.search(r"\{[^}]*\}", t), f"placeholder in {path}: {t[:80]}")
            self.assertNotIn("[RES]", t, path)

    def test_scan_meta_texts_patterns(self) -> None:
        """The words that scan_meta_texts.py looks for (British spelling, [RES], '0 more', wrong license names)."""
        cfg = {k: v for k, v in self.cfg.items() if k not in ("title_ru", "citation")}
        for path, text in SC.walk(cfg):
            clean = SC.ALLOWED.sub(" ", text)
            for name, rx, _ in SC.CHECKS:
                self.assertFalse(rx.search(clean), f"{name} in {path}")

    def test_sources_against_synthetic_meta(self) -> None:
        table = pd.read_csv(SOURCES_CSV, dtype=str, keep_default_na=False)
        recs = [{"publisher": r.publisher, "product": r.product, "sha256": f"{i:064x}", "retrieved_at": "2026-11-10T10:00:00Z"}
                for i, r in enumerate(table.itertuples())]
        for s in self.cfg["sources"]:                                    # the four sources of 0.2.0
            if s["source_id"] in ("natural_earth", "census_cb_2023", "kartverket_inndelingsbase", "unicode_cldr"):
                recs.append({"publisher": s["publisher"], "product": ("Unicode CLDR release-48-2: common/subdivisions/en.xml"
                                                                       if s["source_id"] == "unicode_cldr" else s["bnd_match"][0] + " file"),
                             "sha256": f"{len(recs) + 100:064x}", "retrieved_at": "2026-10-14T10:00:00Z"})
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "meta.json").write_text(json.dumps({"sources": recs}), encoding="utf-8")
            sources = BB._boundaries_sources(self.cfg, Ctx("dev", Path(td)))
        self.assertEqual(len(sources), 19)
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        sub = {"$ref": "#/$defs/source", "$defs": schema["$defs"]}
        ids = set()
        for s in sources:
            jsonschema.validate(s, sub)                                  # file names without a slash, dates valid, license family known
            self.assertNotIn(s["source_id"], ids)
            ids.add(s["source_id"])
            self.assertTrue(s["inputs"], s["source_id"])
        by = {s["source_id"]: s for s in sources}
        self.assertEqual(len(by["lva_vzd_address_register"]["inputs"]), 2)
        self.assertEqual(len(by["nzl_statsnz_2025"]["inputs"]), 2)
        self.assertEqual(by["idn_big_provinces"]["license"]["family"], "attribution")
        self.assertEqual(by["idn_big_provinces"]["rights_basis"]["type"], "statute")
        self.assertEqual(by["idn_big_provinces"]["rights_basis"]["checked_at"], "2026-11-17")
        self.assertEqual(by["idn_big_provinces"]["rights_basis"]["evidence_url"],
                         "https://peraturan.bpk.go.id/Details/38690/uu-no-28-tahun-2014")
        self.assertEqual({s["rights_basis"]["checked_by"] for s in sources if s["source_id"] in
                          {x["id"] for x in PB.SOURCES}}, {"agent:RES7"})

    def test_publisher_strings_equal_the_table(self) -> None:
        table = pd.read_csv(SOURCES_CSV, dtype=str, keep_default_na=False)
        have = {(r["publisher"]) for r in self.cfg["sources"]}
        for pub in set(table["publisher"]):
            self.assertIn(pub, have)
        for r in table.itertuples():                                       # every table product is hit by the match of its source
            src = next(s for s in self.cfg["sources"] if s["publisher"] == r.publisher)
            self.assertTrue(any(m in r.product for m in src["bnd_match"]), (r.iso3, r.product))

    def test_patches_are_idempotent(self) -> None:
        with in_root(), contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(PB.main(["x"]), 0)
            self.assertIn("Nothing to change", buf.getvalue())
        with in_root(), contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(PM.main(["x"]), 0)
            self.assertIn("Nothing to change", buf.getvalue())

    def test_methodology_numbers(self) -> None:
        text = (ROOT / "content" / "methodology.md").read_text(encoding="utf-8")
        for needle in ("| Colombia | 33:", "| Vietnam | 34 provinces and cities", "119 countries and", "Act No. 21446", "the other 115 countries"):
            self.assertIn(needle, text)
        self.assertNotIn("The build was reproduced on a second machine.", text)
        self.assertNotIn("134 countries", text)
        sec = re.search(r"## Administrative boundaries.*?(?=^## )", text, flags=re.S | re.M).group(0)
        self.assertFalse(CYR.search(sec))
        self.assertEqual(len(re.findall(r"^  \| (?:Colombia|Estonia|Hong Kong|Indonesia|Ireland|Latvia|Luxembourg|Mexico|New Zealand|Peru|"
                                        r"Philippines|South Korea|Taiwan|Thailand|Vietnam) \|", sec, flags=re.M)), 15)

    def test_known_gaps_numbers(self) -> None:
        gaps = self.cfg["coverage"]["known_gaps"]
        self.assertEqual(len(gaps), 20)
        self.assertIn("In 32 countries with more than one type", gaps[10])
        self.assertIn("In 21 countries the types are not filled", gaps[10])
        self.assertIn("The other 119 countries and territories have ADM0 only", gaps[4])
        self.assertTrue(gaps[3].startswith("First-level units built from Natural Earth are cut"))
        self.assertIn("(123 in this release)", gaps[4])


class PhraseCheck(unittest.TestCase):
    def test_variants_decode_escaped_json(self) -> None:
        raw = '{"license":"\\u003cp\\u003eCreative Commons Attribution 4.0 International\\u003c/p\\u003e"}'
        self.assertTrue(any(re.search(CP.CC4_RX, v) for v in CP.variants(raw)))
        self.assertTrue(any(re.search(CP.CC4_RX, v) for v in CP.variants("Creative%20Commons%20Attribution%204.0%20International")))

    def test_run_on_synthetic_pages(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            (t / "pages" / "KOR").mkdir(parents=True)
            (t / "pages" / "KOR" / "a.html").write_text("<p>제한 없음</p><p>부칙 제21446호</p>", encoding="utf-8")
            (t / "pages" / "IDN").mkdir()
            (t / "pages" / "IDN" / "BATAS_KABKOTA_AR.xml").write_text("<x/>", encoding="utf-8")
            (t / "pages" / "IDN" / "BATAS_KABKOTA_AR_dummy.htm").write_text("Hak Cipta", encoding="utf-8")   # not an xml: out of scope
            notes: list[str] = []
            kor = CP.collect("KOR", t / "pages", t / "work", [], notes)
            self.assertIn("page:a.html", [r["key"] for r in kor])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                bad = CP.check_phrases(t / "pages", t / "work", [])
            out = buf.getvalue()
            self.assertIn("[OK] no restriction", out)
            self.assertIn("[OK] Act No. 21446", out)
            self.assertIn("[OK] no 'Hak Cipta' in the BIG metadata", out)
            self.assertIn("[MISSING] open data: no file to look in", out)      # EST has no pages here
            self.assertIn("a.html | ", out)                                    # the list of files looked at, with sizes
            self.assertIn("== pages to save by hand", out)
            self.assertIn("EST: missing", out)
            self.assertNotIn("KOR: missing", out)                              # nothing to save for what was found
            self.assertGreater(bad, 0)

    def test_deep_folders_zip_case_and_preflight(self) -> None:
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            deep = t / "pages" / "mex" / "Pages" / "files"                    # folder name in lower case, results in subfolders
            deep.mkdir(parents=True)
            (deep / "package_show_cod-ab-mex.JSON").write_text('{"license_id": "cc-by-igo"}', encoding="utf-8")
            (t / "pages" / "PHL" / "pages").mkdir(parents=True)
            with zipfile.ZipFile(t / "pages" / "PHL" / "pages" / "hdx.zip", "w") as z:
                z.writestr("inner/meta.txt", "License: Creative Commons Attribution for Intergovernmental Organisations")
            (t / "pages" / "PHL" / "pages" / "R.A. No. 12000.pdf").write_bytes(b"%PDF-1.4 broken")   # unreadable pdf: listed, no crash
            (t / "pages" / "THA").mkdir()
            (t / "pages" / "THA" / "map.shp").write_bytes(b"\x00\x01")        # not text: listed as skipped
            pf = t / "pages" / "deeper" / "_preflight_v030"                    # found by name, anywhere below the pages folder
            pf.mkdir(parents=True)
            (pf / "results.json").write_text(json.dumps([{"iso3": "VNM", "license_title": "CC BY-IGO"}]), encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                CP.check_phrases(t / "pages", t / "work", [])
            out = buf.getvalue().replace("\\\\", "/").replace("\\", "/")     # Windows prints backslashes (doubled inside a list)
            self.assertIn("MEX: 1 file(s) looked at", out)
            self.assertIn("[OK] HDX license CC BY-IGO: FOUND in ['page:Pages/files/package_show_cod-ab-mex.JSON']", out)
            self.assertIn("hdx.zip!inner/meta.txt", out)
            self.assertIn("map.shp | 2 bytes | not text (type skipped)", out)
            self.assertRegex(out, r"VNM: \d+ file\(s\) looked at")
            self.assertIn("FOUND in ['preflight:_preflight_v030/results.json[VNM]']", out)
            self.assertNotIn("MEX: missing", out)
            self.assertIn("THA: missing", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
