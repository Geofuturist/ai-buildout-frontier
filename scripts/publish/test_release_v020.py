r"""Tests of the abf-dc 0.2.0 release code on the published 0.1.0 points and the 0.2.0 data step (no network, no real geometry).

Run from the repository root (Windows):
    python scripts\publish\test_release_v020.py

What is real: dc_atlas_points.csv and units.csv of the published releases (the same files the data step pins), the data step
output made here, the layer yamls and the release yaml. What is synthetic: the boundaries release (squares instead of outlines),
the dummy source files, and the manifest of the identity tests.
"""
from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
from shapely.geometry import box  # noqa: E402

import build_release as BR  # noqa: E402
import layer_build as LB  # noqa: E402
import patch_dc_atlas_points_v020 as PP  # noqa: E402
import patch_dc_texts_v020 as PT  # noqa: E402
from common import GateError, Report, load_yaml, sha256_file  # noqa: E402

PTS = ROOT / "data" / "abf-dc" / "v0.1.0" / "dc_atlas_points.csv"
UNITS = ROOT / "data" / "abf-boundaries" / "v0.2.0" / "units.csv"
STEP = ROOT / "scripts" / "dc" / "dc_count_v020.py"
HAVE_INPUTS = PTS.exists() and UNITS.exists()
GROUPS = ["colocation", "telecom", "developer_investor", "cloud", "enterprise_it", "ai_compute", "other"]
C_TYPE_COLS = [f"n_type_{g}" for g in GROUPS]


def make_boundaries(root: Path) -> LB.Boundaries:
    """Squares instead of outlines: contiguous counties in a grid, Alaska and Hawaii far west."""
    units = pd.read_csv(UNITS, dtype=str, keep_default_na=False)
    (root / "display").mkdir(parents=True)
    adm0 = units[units["level"] == "ADM0"].copy().reset_index(drop=True)
    g0 = gpd.GeoDataFrame(adm0[["unit_id", "name", "iso3"]],
                          geometry=[box(-179 + (i % 100), -80 + (i // 100) * 2, -178.5 + (i % 100), -79 + (i // 100) * 2) for i in range(len(adm0))],
                          crs="EPSG:4326")
    g0.to_parquet(root / "display" / "adm0.parquet")
    adm2 = units[(units["iso3"] == "USA") & (units["level"] == "ADM2")].sort_values("unit_id").reset_index(drop=True)
    geoms = []
    for i, uid in enumerate(adm2["unit_id"]):
        code = uid.split("-")[2]
        if code[:2] in ("02", "15"):
            x, y = -170 + (i % 10) * 0.1, 55 + (i % 7) * 0.1
        else:
            x, y = -120 + (i % 60), 25 + (i // 60) % 24
        geoms.append(box(x, y, x + 0.5, y + 0.5))
    g2 = gpd.GeoDataFrame(adm2[["unit_id", "name"]], geometry=geoms, crs="EPSG:4326")
    g2.to_parquet(root / "display" / "adm2.parquet")
    reg = pd.DataFrame([{"iso3": "USA", "level": "ADM2", "verified": "true"}])
    return LB.Boundaries(root=root, registry=reg)


@unittest.skipUnless(HAVE_INPUTS, "published input files are not in the working tree")
class NewLayers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.step_out = cls.tmp / "step"
        r = subprocess.run([sys.executable, str(STEP), "--points", str(PTS), "--units", str(UNITS), "--out-dir", str(cls.step_out),
                            "--checked-at", "2026-10-24T12:00:00Z"], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        cls.boundaries = make_boundaries(cls.tmp / "bnd")
        cls.dummy = cls.tmp / "dummy.bin"
        cls.dummy.write_bytes(b"dummy input")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---- helpers
    def ctx(self, out: Path, channel: str = "final") -> LB.BuildContext:
        out.mkdir(parents=True, exist_ok=True)
        rel = {"dataset": "abf-dc", "version": "0.2.0", "tag": "abf-dc-v0.2.0", "boundary_release": "abf-boundaries-v0.2.0"}
        return LB.BuildContext(release=rel, channel=channel, out_dir=out, built_at="2026-10-24T12:00:00Z", published_at="2026-10-24",
                               doi=None, boundaries=self.boundaries, report=Report("test"), tmp_dir=out.parent / "_tmp")

    def cfg(self, name: str) -> dict:
        c = load_yaml(ROOT / "layers" / f"{name}.yaml")
        c["input"]["table"] = str(self.step_out / f"{name}.csv")
        for k in list(c["input"].get("files") or {}):
            c["input"]["files"][k] = str(self.dummy)
        if "points_v010" in (c["input"].get("files") or {}):
            c["input"]["files"]["points_v010"] = str(PTS)
        for e in c.get("extra_files") or []:
            e["path"] = str(self.step_out / e["publish_as"])
        return c

    def build_both(self, out: Path, channel: str = "final"):
        ctx = self.ctx(out, channel)
        lp = LB.build_point_layer(self.cfg("dc_atlas_count_places"), ctx)
        lc = LB.build_adm_layer(self.cfg("dc_atlas_count_usa_adm2"), ctx)
        shutil.copyfile(PTS, out / "dc_atlas_points.csv")
        return ctx, lp, lc

    # ---- the two layers build with the numbers of SPEC 2.4 (expected_counts stop in final)
    def test_layers_build_final_channel(self):
        out = self.tmp / "o1"
        ctx, lp, lc = self.build_both(out, "final")
        self.assertEqual(lp.meta["coverage"]["n_records"], 2303)
        self.assertEqual(lc.meta["coverage"]["n_units_frame"], 3144)
        self.assertEqual(lc.meta["coverage"]["n_units_covered"], 3127)
        self.assertEqual(ctx.report.warnings, [])
        ids = {c["id"] for c in lp.meta["verification"]["automated_checks"]}
        self.assertIn("counts_match_texts", ids)
        self.assertIn("power_class_adr", ids)
        self.assertFalse(lp.carries_power)
        self.assertFalse(lc.carries_power)

    def test_display_and_tiles(self):
        out = self.tmp / "o2"
        _, lp, lc = self.build_both(out)
        d = lp.meta["display"]
        self.assertEqual((d["count_field"], d["count_breaks"], d["size_field"], d["size_breaks"]), ("n_records", [2], "power_class", [10, 100, 1000]))
        self.assertEqual((d["color_field"], d["color_classes"], d["symbol" if "symbol" in d else "color_field"]), ("type_group", GROUPS, "type_group"))
        self.assertEqual(d["filter_fields"], {g: f"n_type_{g}" for g in GROUPS})
        self.assertEqual(d["legend_count_classes"], ["Two or more records at the town: the number is the count"])
        self.assertTrue(d["fan_note"].startswith("Schematic: all these records share the town point."))
        self.assertEqual(d["list_title"], "{n} Atlas records at {place_name}")
        self.assertEqual(set(d["legend_type_labels"]), set(GROUPS))
        self.assertEqual(lp.tile_build["args"][0], "-r1")
        self.assertEqual(lp.tile_build["geometry_type"], "point")
        self.assertEqual(lp.tile_fields, ["record_id", "place_ref", "place_name", "n_records", "power_class", "n_operating_or_construction", "n_planned",
                                          "n_retired", "n_class_lt10", "n_class_10_99", "n_class_100_999", "n_class_ge1000", "n_class_unknown",
                                          "type_group", *C_TYPE_COLS, "iso3_source", "control_iso3"])
        dc = lc.meta["display"]
        self.assertEqual((dc["value_field"], dc["breaks"], dc["breaks_fixed"], dc["zero_class"]), ("n_records", [1, 3, 10, 30, 100], True, True))
        west, _, east, _ = dc["home_bbox"]
        self.assertGreater(west, -125)      # no Alaska, no Hawaii
        self.assertEqual([e["file"] for e in lc.meta["extra_files"]], ["county_records.csv"])
        self.assertEqual([e["file"] for e in lp.meta["extra_files"]], ["operator_type_groups.csv"])
        self.assertTrue((out / "county_records.csv").exists())
        self.assertTrue((out / "operator_type_groups.csv").exists())
        for meta in (lp.meta, lc.meta):
            BR.validate_meta(meta)

    def test_places_layer_columns_and_single_class(self):
        out = self.tmp / "o3"
        _, lp, _ = self.build_both(out)
        df = pd.read_csv(out / "dc_atlas_count_places.csv", dtype=str, keep_default_na=False)
        self.assertEqual(len(df), 2303)
        self.assertEqual((df["n_records"].astype(int) == 1).sum(), 1424)
        self.assertTrue((df.loc[df["n_records"].astype(int) > 1, "power_class"] == "").all())
        self.assertNotIn("unit_id", df.columns)
        n = df["n_records"].astype(int)
        self.assertTrue((df[C_TYPE_COLS].astype(int).sum(axis=1) == n).all())
        self.assertEqual([int(df[c].astype(int).sum()) for c in C_TYPE_COLS], [2774, 1089, 671, 562, 386, 138, 467])
        self.assertTrue((df.loc[n > 1, "type_group"] == "").all())
        self.assertTrue((df.loc[n == 1, "type_group"] != "").all())

    def test_county_layer_not_covered(self):
        out = self.tmp / "o4"
        _, _, lc = self.build_both(out)
        df = pd.read_csv(out / "dc_atlas_count_usa_adm2.csv", dtype=str, keep_default_na=False)
        nc = df[df["coverage_status"] == "not_covered"]
        self.assertEqual(len(nc), 17)
        self.assertTrue((nc["n_records"] == "").all())
        self.assertTrue((nc["coverage_note"] != "").all())
        loudoun = df[df["unit_id"] == "USA-2-51107"].iloc[0]
        self.assertEqual(loudoun["n_records"], "179")

    # ---- cross checks (the yaml of the release, the three new kinds)
    def checks(self):
        rel = load_yaml(ROOT / "releases" / "abf-dc-v0.2.0.yaml")
        return [c for c in rel["cross_checks"] if c.get("count_layer") in ("dc_atlas_count_places", "dc_atlas_count_usa_adm2")
                or c.get("file") == "county_records.csv"]

    def test_cross_checks_green(self):
        out = self.tmp / "o5"
        ctx, _, _ = self.build_both(out)
        self.assertEqual(len(self.checks()), 3)
        BR.run_cross_checks(self.checks(), out, self.boundaries, ctx.report)
        self.assertTrue(any("cross-check" in n for n in ctx.report.notes))

    def mutate(self, name: str, fn):
        out = self.tmp / f"m_{name}"
        ctx, _, _ = self.build_both(out)
        p = out / (name if name.endswith(".csv") else f"{name}.csv")
        df = pd.read_csv(p, dtype=str, keep_default_na=False)
        df = fn(df)
        df.to_csv(p, index=False, lineterminator="\n")
        with self.assertRaises(GateError) as cm:
            BR.run_cross_checks(self.checks(), out, self.boundaries, ctx.report)
        return str(cm.exception)

    def test_cross_check_stops_places_count(self):
        def f(df):
            df.loc[0, "n_records"] = str(int(df.loc[0, "n_records"]) + 1)
            return df
        self.assertIn("dc_atlas_count_places", self.mutate("dc_atlas_count_places", f))

    def test_cross_check_stops_places_single_class(self):
        def f(df):
            i = df.index[df["n_records"] == "1"][0]
            df.loc[i, "power_class"] = "ge1000" if df.loc[i, "power_class"] != "ge1000" else "lt10"
            return df
        self.assertIn("power_class", self.mutate("dc_atlas_count_places", f))

    def test_cross_check_stops_places_type_column(self):
        def f(df):
            i = df.index[df["n_records"] == "1"][0]
            c = next(c for c in C_TYPE_COLS if df.loc[i, c] == "1")
            o = next(c2 for c2 in C_TYPE_COLS if c2 != c)
            df.loc[i, c], df.loc[i, o] = "0", "1"                     # the one record moved to another group
            return df
        self.assertIn("n_type_", self.mutate("dc_atlas_count_places", f))

    def test_cross_check_stops_places_type_group(self):
        def f(df):
            i = df.index[df["n_records"] == "1"][0]
            df.loc[i, "type_group"] = "other" if df.loc[i, "type_group"] != "other" else "cloud"
            return df
        self.assertIn("type_group", self.mutate("dc_atlas_count_places", f))

    def test_cross_check_stops_groups_table_changed(self):
        def f(df):                                                    # Telecom moved to 'other' in the published table only
            df.loc[df["operator_type"] == "Telecom", "type_group"] = "other"
            return df
        self.assertIn("n_type_", self.mutate("operator_type_groups.csv", f))

    def test_cross_check_stops_type_not_in_groups_table(self):
        def f(df):
            return df[df["operator_type"] != "Crypto"]
        self.assertIn("not in operator_type_groups.csv", self.mutate("operator_type_groups.csv", f))

    def test_cross_check_stops_place_ref_missing(self):
        def f(df):
            return df.iloc[1:]
        self.assertIn("keys that are not in", self.mutate("dc_atlas_count_places", f))

    def test_cross_check_stops_county_value(self):
        def f(df):
            i = df.index[df["unit_id"] == "USA-2-51107"][0]
            df.loc[i, "n_planned"] = str(int(df.loc[i, "n_planned"]) + 1)
            return df
        self.assertIn("n_planned", self.mutate("dc_atlas_count_usa_adm2", f))

    def test_cross_check_stops_county_value_in_not_covered(self):
        def f(df):
            i = df.index[df["coverage_status"] == "not_covered"][0]
            df.loc[i, "n_records"] = "1"
            return df
        self.assertIn("not covered", self.mutate("dc_atlas_count_usa_adm2", f))

    def test_cross_check_stops_record_not_in_points(self):
        def f(df):
            df.loc[0, "record_id"] = "ATL-doesnotexist"
            return df
        msg = self.mutate("county_records.csv", f)
        self.assertTrue("not in dc_atlas_points" in msg or "mapping" in msg or "one_to_one" in msg or "differs" in msg, msg)

    # ---- the release run: Atlas points + the two new layers, release-level code (cross checks, G13 marks, files list)
    def release_run(self, channel: str):
        import argparse
        import yaml
        base = self.tmp / f"rel_{channel}_{len(list(self.tmp.glob('rel_*')))}"
        base.mkdir()
        (base / "reg.csv").write_text("iso3,level,verified\nUSA,ADM2,true\n", encoding="utf-8")
        layer_files = []
        for n in ("dc_atlas_points", "dc_atlas_count_places", "dc_atlas_count_usa_adm2"):
            c = self.cfg(n)
            if n == "dc_atlas_points":
                c["input"]["table"] = str(PTS)
                for e in c.get("source_archives") or []:
                    e["path"] = str(self.dummy)
            f = base / f"{n}.yaml"
            f.write_text(yaml.safe_dump(c, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
            layer_files.append(str(f))
        rel = load_yaml(ROOT / "releases" / "abf-dc-v0.2.0.yaml")
        rel["layers"] = layer_files
        rel["boundaries"] = {"dir": str(self.tmp / "bnd"), "registry": str(base / "reg.csv")}
        rel["cross_checks"] = [c for c in rel["cross_checks"] if c.get("count_layer") in ("dc_atlas_count_places", "dc_atlas_count_usa_adm2")
                               or c.get("file") == "county_records.csv"]
        rel.pop("identity")
        rel.pop("phrase_check")
        rel["doi"] = "10.5281/zenodo.1" if channel == "final" else None
        rel["built_at"] = "2026-10-24T12:00:00Z"
        rel["published_at"] = "2026-10-24"
        rf = base / "rel.yaml"
        rf.write_text(yaml.safe_dump(rel, allow_unicode=True, sort_keys=False), encoding="utf-8")
        args = argparse.Namespace(release=str(rf), out=str(base / "out"), channel=channel, built_at=None, override=None)
        return args, base / "out" / "abf-dc-v0.2.0"

    def test_release_run_dev_has_no_g13_and_no_stop(self):
        args, out = self.release_run("dev")
        self.assertEqual(BR.run(args), 0)
        report = (out / "release_report.md").read_text(encoding="utf-8")
        self.assertNotIn("unfilled places in public text (G13)", report)
        self.assertIn("cross-check: 16 count columns of dc_atlas_count_places", report)
        self.assertIn("cross-check: 9 count columns of dc_atlas_count_usa_adm2", report)
        zf = (out / "zenodo_files.txt").read_text(encoding="utf-8")
        self.assertIn("county_records.csv", zf)
        self.assertIn("operator_type_groups.csv", zf)
        self.assertIn("dc_atlas_count_places.csv", zf)
        plan = json.loads((out / "build_plan.json").read_text(encoding="utf-8"))
        ids = [x["layer_id"] for x in plan["layers"]]
        self.assertEqual(ids, ["dc_atlas_points", "dc_atlas_count_places", "dc_atlas_count_usa_adm2"])
        self.assertEqual(plan["tile_builds"][0]["args"][0], "-r1")
        self.assertEqual(plan["tile_builds"][1]["args"][0], "-r1")
        self.assertGreater(plan["layers"][2]["home_bbox"][0], -125)
        points_meta = json.loads((out / "dc_atlas_points.meta.json").read_text(encoding="utf-8"))
        self.assertIs(points_meta["display"]["map"], False)
        self.assertEqual(points_meta["release"]["version"], "0.2.0")

    def test_release_run_final_is_clean(self):
        args, out = self.release_run("final")
        self.assertEqual(BR.run(args), 0)
        meta = json.loads((out / "dc_atlas_count_places.meta.json").read_text(encoding="utf-8"))
        self.assertIn("by place and by U.S. county", json.dumps(meta))

    def test_release_run_final_stops_on_unfilled_texts(self):
        import yaml
        args, _ = self.release_run("final")
        f = Path(args.release).parent / "dc_atlas_count_places.yaml"
        c = yaml.safe_load(f.read_text(encoding="utf-8"))
        c["description"] = "[RES] " + c["description"]
        f.write_text(yaml.safe_dump(c, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
        with self.assertRaises(GateError) as cm:
            BR.run(args)
        self.assertIn("G13", str(cm.exception))


class DisplayKeys(unittest.TestCase):
    def call(self, display):
        names = ["a", "b"]
        table = pd.DataFrame({"a": [1], "b": [2]})
        LB.check_display_keys({"layer_id": "x"}, display, names, table)

    def test_ok(self):
        self.call({"count_field": "a", "count_breaks": [2, 10], "map": False})

    def test_count_field_unknown(self):
        with self.assertRaises(GateError):
            self.call({"count_field": "zz", "count_breaks": [2]})

    def test_count_breaks_order(self):
        with self.assertRaises(GateError):
            self.call({"count_field": "a", "count_breaks": [10, 2]})

    def test_count_field_needs_breaks_and_back(self):
        with self.assertRaises(GateError):
            self.call({"count_field": "a"})
        with self.assertRaises(GateError):
            self.call({"count_breaks": [2]})

    def test_map_boolean(self):
        with self.assertRaises(GateError):
            self.call({"map": "no"})

    def color(self, **kw):
        names = ["a", "b", "g", "n_x", "n_y"]
        table = pd.DataFrame({"a": [1, 2], "b": [2, 3], "g": ["x", ""], "n_x": [1, 0], "n_y": [0, 1]})
        d = {"color_field": "g", "color_classes": ["x", "y"], "filter_fields": {"x": "n_x", "y": "n_y"}, "legend_type_labels": {"x": "X", "y": "Y"}}
        d.update(kw)
        d = {k: v for k, v in d.items() if v is not None}
        LB.check_display_keys({"layer_id": "x"}, d, names, table)

    def test_color_ok(self):
        self.color()
        self.color(symbol="diamond")

    def test_color_errors(self):
        for kw in ({"color_field": "zz"}, {"color_classes": ["x"]}, {"color_classes": ["x", "x", "y"]}, {"color_classes": []},
                   {"filter_fields": {"x": "n_x"}}, {"filter_fields": {"x": "n_x", "y": "nope"}},
                   {"legend_type_labels": {"x": "X"}}, {"symbol": "star"}):
            with self.assertRaises(GateError, msg=str(kw)):
                self.color(**kw)

    def test_color_keys_need_color_field(self):
        for kw in ({"color_classes": ["x"]}, {"filter_fields": {"x": "a"}}, {"legend_type_title": "t"}):
            with self.assertRaises(GateError, msg=str(kw)):
                LB.check_display_keys({"layer_id": "x"}, kw, ["a"], pd.DataFrame({"a": [1]}))

    def test_legend_count_classes(self):
        self.call({"count_field": "a", "count_breaks": [2, 10], "legend_count_classes": ["2-9", "10+"]})
        with self.assertRaises(GateError):
            self.call({"count_field": "a", "count_breaks": [2, 10], "legend_count_classes": ["2-9"]})
        with self.assertRaises(GateError):
            self.call({"legend_count_classes": ["2-9"]})


class Identity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.old, self.out = self.tmp / "old", self.tmp / "new"
        self.old.mkdir()
        self.out.mkdir()
        (self.out / "sources").mkdir()
        gdf = gpd.GeoDataFrame({"record_id": ["a", "b"], "v": [1, 2]}, geometry=[box(0, 0, 1, 1), box(2, 2, 3, 3)], crs="EPSG:4326")
        gdf.to_parquet(self.old / "l.parquet")
        (self.old / "l.csv").write_text("record_id,v\na,1\nb,2\n", encoding="utf-8", newline="\n")
        (self.old / "l.geojson.gz").write_bytes(gzip.compress(json.dumps({"type": "FeatureCollection", "features": [1, 2]}).encode(), mtime=0))
        (self.old / "x.csv").write_text("k\n1\n", encoding="utf-8", newline="\n")
        (self.old / "arch.zip").write_bytes(b"zip bytes")
        for f in ("l.parquet", "l.csv", "l.geojson.gz", "x.csv"):
            shutil.copyfile(self.old / f, self.out / f)
        shutil.copyfile(self.old / "arch.zip", self.out / "sources" / "arch.zip")
        (self.out / "l.pmtiles").write_bytes(b"new tiles differ")
        fi = lambda n, p=None: {"path": p or n, "bytes": 1, "sha256": sha256_file(self.old / n)}  # noqa: E731
        self.manifest = {"tag": "abf-dc-v0.1.0", "layers": [{
            "layer_id": "l", "files": {"parquet": fi("l.parquet"), "csv": fi("l.csv"), "geojson.gz": fi("l.geojson.gz"),
                                       "pmtiles": {"path": "l.pmtiles", "bytes": 1, "sha256": "0" * 64}},
            "extra_files": [fi("x.csv")]}],
            "source_archives": [fi("arch.zip", "sources/arch.zip")]}
        (self.tmp / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        self.spec = {"manifest": str(self.tmp / "manifest.json"), "layers": ["l"], "old_release_dir": str(self.old)}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_id(self, spec=None):
        r = Report("t")
        BR.run_identity(spec or self.spec, self.out, r)
        return r

    def test_identical(self):
        r = self.run_id()
        self.assertIn("5 files by SHA-256, 0 by values", " ".join(r.notes))   # parquet csv geojson extra archive
        self.assertIn("Identity with abf-dc-v0.1.0", r.sections)

    def test_csv_changed_stops(self):
        (self.out / "l.csv").write_text("record_id,v\na,1\nb,3\n", encoding="utf-8", newline="\n")
        with self.assertRaises(GateError) as cm:
            self.run_id()
        self.assertIn("l.csv", str(cm.exception))

    def test_archive_changed_stops(self):
        (self.out / "sources" / "arch.zip").write_bytes(b"other")
        with self.assertRaises(GateError):
            self.run_id()

    def test_extra_file_changed_stops(self):
        (self.out / "x.csv").write_text("k\n2\n", encoding="utf-8", newline="\n")
        with self.assertRaises(GateError):
            self.run_id()

    def test_missing_file_stops(self):
        (self.out / "x.csv").unlink()
        with self.assertRaises(GateError):
            self.run_id()

    def test_parquet_other_bytes_equal_values(self):
        gdf = gpd.read_parquet(self.old / "l.parquet")
        gdf.to_parquet(self.out / "l.parquet", compression="gzip")          # other bytes, same values
        self.assertNotEqual(sha256_file(self.out / "l.parquet"), self.manifest["layers"][0]["files"]["parquet"]["sha256"])
        r = self.run_id()
        self.assertIn("1 by values", " ".join(r.notes))

    def test_parquet_other_bytes_without_old_folder_stops(self):
        gpd.read_parquet(self.old / "l.parquet").to_parquet(self.out / "l.parquet", compression="gzip")
        spec = dict(self.spec)
        spec.pop("old_release_dir")
        with self.assertRaises(GateError) as cm:
            self.run_id(spec)
        self.assertIn("old_release_dir", str(cm.exception))

    def test_parquet_values_differ_stops(self):
        gdf = gpd.read_parquet(self.old / "l.parquet")
        gdf.loc[0, "v"] = 9
        gdf.to_parquet(self.out / "l.parquet")
        with self.assertRaises(GateError) as cm:
            self.run_id()
        self.assertIn("values", str(cm.exception))

    def test_parquet_geometry_differs_stops(self):
        gdf = gpd.read_parquet(self.old / "l.parquet")
        gdf.loc[0, "geometry"] = box(5, 5, 6, 6)
        gdf.to_parquet(self.out / "l.parquet")
        with self.assertRaises(GateError):
            self.run_id()

    def test_old_folder_not_the_published_file_stops(self):
        gpd.read_parquet(self.old / "l.parquet").to_parquet(self.out / "l.parquet", compression="gzip")
        gpd.read_parquet(self.old / "l.parquet").to_parquet(self.old / "l.parquet", compression="gzip")   # old folder is not the published file
        with self.assertRaises(GateError) as cm:
            self.run_id()
        self.assertIn("not the published file", str(cm.exception))

    def test_geojson_other_bytes_equal_features(self):
        (self.out / "l.geojson.gz").write_bytes(gzip.compress(json.dumps({"type": "FeatureCollection", "features": [1, 2]}, indent=1).encode(), mtime=5))
        r = self.run_id()
        self.assertIn("1 by values", " ".join(r.notes))

    def test_geojson_features_differ_stops(self):
        (self.out / "l.geojson.gz").write_bytes(gzip.compress(json.dumps({"type": "FeatureCollection", "features": [1, 3]}).encode()))
        with self.assertRaises(GateError):
            self.run_id()

    def test_layer_not_in_manifest_stops(self):
        with self.assertRaises(GateError):
            self.run_id({**self.spec, "layers": ["nope"]})


class StaticFiles(unittest.TestCase):
    def test_release_yaml(self):
        rel = load_yaml(ROOT / "releases" / "abf-dc-v0.2.0.yaml")
        self.assertEqual((rel["dataset"], rel["version"], rel["tag"]), ("abf-dc", "0.2.0", "abf-dc-v0.2.0"))
        self.assertIsNone(rel["doi"])
        ids = []
        for y in rel["layers"]:
            p = ROOT / y.replace("\\", "/")
            self.assertTrue(p.exists(), y)
            ids.append(load_yaml(p)["layer_id"])
        self.assertEqual(ids, ["dc_atlas_points", "dc_epoch_points", "dc_atlas_count_adm0", "dc_atlas_count_places", "dc_atlas_count_usa_adm2"])
        self.assertTrue(set(rel["identity"]["layers"]) <= set(ids))
        self.assertEqual(set(rel["identity"]["layers"]), set(ids[:3]))
        known = {"refs_in_layer", "counts_match", "counts_by_key"}
        self.assertTrue({c["kind"] for c in rel["cross_checks"]} <= known)
        self.assertEqual(sum(c["kind"] == "counts_by_key" for c in rel["cross_checks"]), 2)

    def test_new_yamls_have_unit_word_last_in_title(self):
        self.assertTrue(load_yaml(ROOT / "layers" / "dc_atlas_count_places.yaml")["title"].endswith("· places"))
        self.assertTrue(load_yaml(ROOT / "layers" / "dc_atlas_count_usa_adm2.yaml")["title"].endswith("· county"))

    def test_new_yamls_have_the_texts_of_res_and_no_marks(self):
        for n in ("dc_atlas_count_places", "dc_atlas_count_usa_adm2"):
            text = (ROOT / "layers" / f"{n}.yaml").read_text(encoding="utf-8")
            self.assertNotIn("[RES]", text)
            self.assertIn("by place and by U.S. county. These figures are not the Atlas as published.", " ".join(text.split()))
        pl = load_yaml(ROOT / "layers" / "dc_atlas_count_places.yaml")
        self.assertTrue(pl["description"].startswith("Data-center records of the Atlas of Data Center Politics that have a town point"))
        self.assertEqual([f["name"] for f in pl["fields"]][-9:-7], ["power_class", "type_group"])
        self.assertEqual([f["name"] for f in pl["fields"]][-7:], C_TYPE_COLS)
        self.assertEqual(len(pl["coverage"]["known_gaps"]), 7)
        self.assertEqual(pl["extra_files"][0]["publish_as"], "operator_type_groups.csv")
        co = load_yaml(ROOT / "layers" / "dc_atlas_count_usa_adm2.yaml")
        self.assertEqual(len(co["coverage"]["known_gaps"]), 5)

    def test_points_yaml_has_the_patch(self):
        c = load_yaml(ROOT / "layers" / "dc_atlas_points.yaml")
        self.assertEqual(c["tiles"]["extra_args"][0], "-r1")
        self.assertIs(c["display"]["map"], False)

    def test_schema_knows_the_new_display_keys(self):
        schema = json.loads((ROOT / "schemas" / "meta.schema.json").read_text(encoding="utf-8"))
        props = schema["$defs"]["display"]["properties"]
        for k in ("map", "count_field", "count_breaks", "color_field", "color_classes", "filter_fields", "symbol", "legend_type_title",
                  "legend_type_note", "legend_type_labels", "legend_type_filter_all", "legend_count_classes", "list_title", "list_note",
                  "legend_layer_note", "fan_note"):
            self.assertIn(k, props)


class TextPatchScript(unittest.TestCase):
    """patch_dc_texts_v020.py on the 0.1.0 texts (as in git) in LF and in CRLF."""
    def git_text(self, name: str) -> str:
        """The layer yaml as it was before this patch: the working file with the patch undone (the committed file is already patched)."""
        text = (ROOT / "layers" / name).read_bytes().decode("utf-8").replace("\r\n", "\n")
        for new_s, old_s in ((PT.ATTR_NEW, PT.ATTR_OLD), (PT.DESC_NEW, PT.DESC_OLD), (PT.GAP_NEW, PT.GAP_OLD)):
            text = text.replace(new_s, old_s)
        keep = [l for l in text.split("\n") if l not in ("  symbol: diamond", PT.LAYER_NOTE_LINE)]
        return "\n".join(keep)

    def test_points(self):
        old = self.git_text("dc_atlas_points.yaml")
        new, done = PT.patch_points(old)
        self.assertEqual(len(done), 3)
        self.assertIn("counted by country, by place and by U.S. county.", new)
        self.assertIn("estimated. On the project map the records are shown by place (dc_atlas_count_places).", new)
        self.assertIn("The 1,583 county records are counted by county in dc_atlas_count_usa_adm2", new)
        self.assertNotIn("but are not drawn on the map", new)
        self.assertEqual(PT.patch_points(new), (new, []))
        c = __import__("yaml").safe_load(new)
        self.assertIn("Neither group is drawn on the map.", " ".join(c["coverage"]["known_gaps"][2].split()))

    def test_adm0_and_epoch(self):
        a, done = PT.patch_adm0(self.git_text("dc_atlas_count_adm0.yaml"))
        self.assertEqual(done, ["attribution_text"])
        self.assertEqual(PT.patch_adm0(a), (a, []))
        e, done = PT.patch_epoch(self.git_text("dc_epoch_points.yaml"))
        self.assertEqual(done, ["display.legend_layer_note"])
        c = __import__("yaml").safe_load(e)
        self.assertNotIn("symbol", c["display"])
        self.assertEqual(c["display"]["legend_layer_note"], "AI data centers that Epoch AI selects by their AI computing capacity.")
        self.assertEqual(PT.patch_epoch(e), (e, []))
        # a file made by the first version of the script (symbol: diamond + note): the symbol line is removed, the rest stays
        old = e.replace("  geometry_type: point\n", "  geometry_type: point\n  symbol: diamond\n", 1)
        again, done = PT.patch_epoch(old)
        self.assertEqual((again, done), (e, ["display.symbol removed"]))

    def test_main_keeps_crlf(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "layers").mkdir()
            for n in ("dc_atlas_points.yaml", "dc_atlas_count_adm0.yaml", "dc_epoch_points.yaml"):
                (root / "layers" / n).write_bytes(self.git_text(n).replace("\n", "\r\n").encode("utf-8"))
            old_root = PT.REPO_ROOT
            PT.REPO_ROOT = root
            try:
                self.assertEqual(PT.main(), 0)
                for n in ("dc_atlas_points.yaml", "dc_atlas_count_adm0.yaml", "dc_epoch_points.yaml"):
                    b = (root / "layers" / n).read_bytes()
                    self.assertEqual(b.count(b"\n"), b.count(b"\r\n"), n)
                    self.assertNotIn(b"counted by country.", b)
            finally:
                PT.REPO_ROOT = old_root


class PatchScript(unittest.TestCase):
    SAMPLE = ("display:\n  geometry_type: point\n  size_field: power_class\ntiles:\n  minzoom: 0\n"
              "  extra_args: [\"--drop-densest-as-needed\", \"--extend-zooms-if-still-dropping\"]\ncitation:\n  text: x\n")

    def test_patch_and_idempotent(self):
        new, done = PP.patch_text(self.SAMPLE)
        self.assertEqual(len(done), 2)
        self.assertIn('extra_args: ["-r1", "--drop-densest', new)
        self.assertIn("display:\n  geometry_type: point\n  map: false", new)
        again, done2 = PP.patch_text(new)
        self.assertEqual((again, done2), (new, []))

    def test_unknown_form_stops(self):
        with self.assertRaises(SystemExit):
            PP.patch_text("display:\n  geometry_type: point\ntiles:\n  extra_args: [\"-x\"]\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
