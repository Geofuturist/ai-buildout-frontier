r"""Tests of the publication helpers added after abf-index 0.2.0 (A-062): the folder for Zenodo (make_zenodo_folder.py) and the Cyrillic check
of scan_meta_texts.py. No network; nothing is written to the repository.

Run from the repository root (Windows):
    python scripts\publish\test_publish_tools.py

What is real: the code, the meta.json and manifest.json files of every release in data\ (the Cyrillic check must pass them all).
What is synthetic: the release folder of the folder test (made by build_release.py from the synthetic index of test_index_release.py)
and the small folders of the Cyrillic test.
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import finalize_release as FR  # noqa: E402
import make_zenodo_folder as MZ  # noqa: E402
import scan_meta_texts as SC  # noqa: E402
import test_index_release as TI  # noqa: E402

ROOT = HERE.parent.parent
DOI = "10.5281/zenodo.24437451"


class ZenodoFolder(unittest.TestCase):
    def setUp(self) -> None:
        TI.IndexRelease.setUp(self)                      # synthetic index folder and release yaml (same helpers as the index tests)
        self.rel["doi"], self.rel["published_at"] = DOI, "2026-11-22"
        self.out = TI.IndexRelease.run_release(self, self.rel, channel="final")
        plan = json.loads((self.out / "build_plan.json").read_text(encoding="utf-8"))
        manifest = FR.compose_manifest(plan, self.out)
        (self.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")   # what verify_release --save-manifest does
        self.dest = self.tmp / "zenodo"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, True)

    def run_tool(self, *extra: str) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(MZ.main(["--release-dir", str(self.out), "--out", str(self.dest), "--date", "2026-11-22", *extra]), 0)
        return buf.getvalue()

    def test_listed_names_drop_the_remark(self) -> None:
        self.assertEqual(MZ.listed_names("a.csv\nindex/x/y.zip\nmanifest.json  (after verify_release.py --save-manifest)\n"),
                         ["a.csv", "index/x/y.zip", "manifest.json"])

    def test_flat_folder_with_exactly_the_listed_files(self) -> None:
        text = self.run_tool()
        folder = self.dest / "zenodo_upload_20261122" / "abf-index"
        names = sorted(p.name for p in folder.iterdir())
        self.assertEqual(names, ["index_abf-dc.zip", "index_abf-energy.zip", "manifest.json"])
        self.assertTrue(all(p.is_file() for p in folder.iterdir()))                      # no sub-folders
        for name in names:                                                               # same bytes as the release folder
            src = self.out / ("manifest.json" if name == "manifest.json" else f"index/{name[6:-4]}/{name}")
            self.assertEqual((folder / name).read_bytes(), src.read_bytes())
            self.assertIn(f"{MZ.md5_file(folder / name)}  {name}", text)
        self.assertIn(DOI, text)

    def test_stops_without_manifest(self) -> None:
        (self.out / "manifest.json").unlink()
        with self.assertRaises(SystemExit) as cm:
            MZ.plan_copies(self.out)
        self.assertIn("--save-manifest", str(cm.exception))
        self.assertFalse(self.dest.exists())

    def test_stops_on_a_file_that_is_not_the_published_one(self) -> None:
        z = self.out / "index" / "abf-dc" / "index_abf-dc.zip"
        z.write_bytes(z.read_bytes() + b"x")             # a manual archive instead of the built one
        with self.assertRaises(SystemExit) as cm:
            MZ.plan_copies(self.out)
        self.assertIn("differs from manifest.json", str(cm.exception))

    def test_stops_on_another_doi(self) -> None:
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        m["doi"] = "10.5281/zenodo.1"
        (self.out / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
        with self.assertRaises(SystemExit) as cm:
            MZ.plan_copies(self.out)
        self.assertIn("not of this release", str(cm.exception))

    def test_stops_on_a_missing_listed_file(self) -> None:
        (self.out / "index" / "abf-energy" / "index_abf-energy.zip").unlink()
        with self.assertRaises(SystemExit) as cm:
            MZ.plan_copies(self.out)
        self.assertIn("not in the release folder", str(cm.exception))

    def test_stops_when_two_files_get_one_name(self) -> None:
        zf = self.out / "zenodo_files.txt"
        zf.write_text(zf.read_text(encoding="utf-8") + "index_abf-dc.zip\n", encoding="utf-8")
        shutil.copy2(self.out / "index" / "abf-dc" / "index_abf-dc.zip", self.out / "index_abf-dc.zip")
        with self.assertRaises(SystemExit) as cm:
            MZ.plan_copies(self.out)
        self.assertIn("would both be uploaded as", str(cm.exception))

    def test_stops_when_the_folder_is_not_empty_and_changes_nothing(self) -> None:
        self.run_tool()
        folder = self.dest / "zenodo_upload_20261122" / "abf-index"
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        with self.assertRaises(SystemExit) as cm:
            self.run_tool()
        self.assertIn("already holds files", str(cm.exception))
        self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()}, before)

    def test_release_folder_is_not_changed(self) -> None:
        before = {p.relative_to(self.out).as_posix(): p.read_bytes() for p in self.out.rglob("*") if p.is_file()}
        self.run_tool()
        after = {p.relative_to(self.out).as_posix(): p.read_bytes() for p in self.out.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


class CyrillicCheck(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "rel"
        (self.root / "index" / "abf-dc" / "rules").mkdir(parents=True)

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def check(self) -> tuple[int, int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            n, bad = SC.cyrillic_problems(self.root)
        return n, bad, buf.getvalue()

    def test_title_ru_is_the_one_allowed_place(self) -> None:
        self.write("a.meta.json", json.dumps({"title_ru": "Электростанции", "title": "Power plants", "description": "Plain English."}))
        n, bad, _ = self.check()
        self.assertEqual((n, bad), (1, 0))

    def test_cyrillic_in_a_public_text_is_found_with_its_path(self) -> None:
        self.write("a.meta.json", json.dumps({"title_ru": "Да", "fields": [{"description": "Страна"}]}))
        n, bad, text = self.check()
        self.assertEqual(bad, 1)
        self.assertIn("a.meta.json fields[0].description", text)

    def test_other_title_with_cyrillic_is_found(self) -> None:
        self.write("a.meta.json", json.dumps({"title": "Страны"}))
        self.assertEqual(self.check()[1], 1)

    def test_manifest_listing_build_meta_and_reference_tables(self) -> None:
        self.write("manifest.json", json.dumps({"note": "Ошибка"}))
        self.write("index/abf-dc/build_meta.json", json.dumps({"x": "Ж"}))
        self.write("index/abf-dc/listing.json", json.dumps({"files": ["ok.csv.gz"]}))
        self.write("index/abf-dc/rules/aliases.csv", "iso3,name\nRUS,Москва\n")
        self.write("name_overrides.csv", "iso3,name\nRUS,Moscow\n")
        n, bad, text = self.check()
        self.assertEqual(bad, 3)
        self.assertIn("rules/aliases.csv line 2", text)
        self.assertNotIn("name_overrides.csv", text)

    def test_data_files_of_layers_and_unpublished_files_are_not_read(self) -> None:
        self.write("dc_atlas_points.meta.json", json.dumps({"title": "Data centers"}))
        self.write("dc_atlas_points.csv", "name\nЦОД\n")                       # source records may keep the original script
        self.write("build_plan.json", json.dumps({"x": "Ж"}))
        self.write("release_report.md", "Отчёт\n")
        self.write("zenodo_files.txt", "Ж\n")
        self.write("index/abf-dc/ABW.csv.gz", "binary-not-text")
        self.write("index/abf-dc/other/hidden.csv", "x\nЖ\n")
        n, bad, _ = self.check()
        self.assertEqual(bad, 0)
        self.assertEqual(n, 1)                                                 # only dc_atlas_points.meta.json

    def test_main_returns_one_on_a_problem(self) -> None:
        self.write("a.meta.json", json.dumps({"title": "Страны"}))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(SC.main(["scan_meta_texts.py", str(self.root)]), 1)
        self.assertIn("Problems found: 1", buf.getvalue())

    def test_past_releases_have_no_cyrillic_outside_title_ru(self) -> None:
        folders = sorted((ROOT / "data").glob("abf-*/v*"))
        self.assertGreaterEqual(len(folders), 10)
        for folder in folders:
            self.root = folder
            n, bad, text = self.check()
            self.assertGreater(n, 0, folder.name)
            self.assertEqual(bad, 0, f"{folder}\n{text}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
