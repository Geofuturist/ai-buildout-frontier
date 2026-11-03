r"""Tests of the GEM release code (abf-energy 0.1.0, abf-energync 0.1.0): class_minzoom, display.filters/popup/zoom_hint checks,
non_commercial licence gate, G3 only for the domain dc, input_columns_exact, csv_identical_to_input, git_copy, check_gem_phrases.

Run from the repository root (Windows):
    python scripts\publish\test_gem_release.py

What is real: the four layer yamls and the two release yamls of GEM, the meta schema. What is synthetic: the CSV files (a few
hundred rows with the real column names and order), the boundaries (squares), the source file and the GEM workbook.
"""
from __future__ import annotations

import copy
import gzip
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from shapely.geometry import box  # noqa: E402

import build_release as BR  # noqa: E402
import check_gem_phrases as CG  # noqa: E402
import finalize_release as FR  # noqa: E402
import layer_build as LB  # noqa: E402
from common import GateError, Report, load_yaml  # noqa: E402

COLS_UNITS = ['record_id', 'location_id', 'plant_name', 'unit_name', 'type', 'technology', 'fuel', 'capacity_mw', 'capacity_rating',
              'capacity_class', 'status', 'status_group', 'start_year', 'retired_year', 'owners', 'operators', 'country_area',
              'subnational_unit', 'iso3_gem', 'iso3_source', 'iso3_frame', 'iso3_frame_rule', 'control_iso3', 'location_accuracy',
              'coord_precision', 'coord_source', 'lon', 'lat', 'captive_industry_type', 'data_center_ppa', 'dc_link', 'river',
              'other_ids_location', 'other_ids_unit', 'wiki_url']
COLS_LOC = ['record_id', 'location_id', 'plant_name', 'wiki_url', 'type', 'status_group', 'statuses', 'technologies', 'capacity_mw',
            'capacity_class', 'n_units', 'capacity_ratings', 'start_year_min', 'start_year_max', 'iso3_gem', 'iso3_source', 'iso3_frame',
            'iso3_frame_rule', 'control_iso3', 'subnational_unit', 'location_accuracy', 'coord_precision', 'coord_source', 'lon', 'lat',
            'n_units_dc_link', 'dc_links', 'n_units_other_set']
INT_COLS = ["start_year", "retired_year", "n_units", "start_year_min", "start_year_max", "n_units_dc_link", "n_units_other_set"]
TYPES = ["coal", "oil/gas", "utility-scale solar", "wind", "hydropower", "nuclear", "bioenergy", "geothermal"]
CLASSES = [("lt10", 5.0), ("10_99", 50.0), ("100_999", 500.0), ("ge1000", 1500.0)]
ISOS = ["USA", "CHN", "FRA", "RUS", "UKR"]


def class_of(mw: float) -> str:
    return "lt10" if mw < 10 else "10_99" if mw < 100 else "100_999" if mw < 1000 else "ge1000"


def synth(kind: str, nc: bool) -> pd.DataFrame:
    """Rows with the real columns. kind: units or locations. nc: only solar, only the small classes (as in abf-energync)."""
    rows = []
    n = 0
    for t in (["utility-scale solar"] if nc else TYPES):
        for cls, mw in (CLASSES[:2] if nc else CLASSES):
            for sg in (["operating"] if nc else ["operating", "announced", "retired"]):
                n += 1
                iso = ISOS[n % len(ISOS)]
                acc = "approximate" if n % 3 == 0 else "exact"
                base = {
                    "record_id": f"G1{n:011d}" if kind == "units" else f"L1{n:011d}-{t[:4]}-{sg}",
                    "location_id": f"L1{n:011d}", "plant_name": "Станция" if (nc and n == 2) else f"Plant {n}", "type": t, "status_group": sg, "capacity_mw": mw,
                    "capacity_class": class_of(mw), "iso3_gem": iso, "iso3_source": iso,
                    "iso3_frame": "" if (n % 17 == 0 and not nc) else iso, "iso3_frame_rule": "" if (n % 17 == 0 and not nc) else "within", "control_iso3": "",
                    "subnational_unit": "Москва" if (n == 2 and not nc) else "", "location_accuracy": acc,
                    "coord_precision": "approximate" if acc == "approximate" else "site", "coord_source": "gem",
                    "lon": round(-100 + n * 0.37, 6), "lat": round(10 + n * 0.21, 6),
                    "wiki_url": f"https://www.gem.wiki/Plant_{n}",
                }
                if n == 7:   # a territory that GEM lists separately: not a country of the frame (gem_iso3_to_adm0.csv maps it to FRA)
                    base.update({"iso3_gem": "GLP", "iso3_source": "FRA", "iso3_frame": "FRA", "iso3_frame_rule": "within"})
                if kind == "units":
                    base.update({"unit_name": "" if (n % 5 == 0 and not nc) else f"Unit {n}", "technology": "Assumed PV" if nc else "", "fuel": "gas" if t == "oil/gas" else "",
                                 "capacity_rating": "MWac" if t == "utility-scale solar" else "",
                                 "status": sg if sg != "retired" else "retired", "start_year": 2000 + n % 20, "retired_year": "",
                                 "owners": "Владелец" if n == 3 else "", "operators": "", "country_area": iso,
                                 "captive_industry_type": "data center" if n == 4 and not nc else "", "data_center_ppa": "",
                                 "dc_link": "captive_dc" if n == 4 and not nc else "", "river": "", "other_ids_location": "",
                                 "other_ids_unit": "TZ: 1" if nc else ""})
                else:
                    base.update({"statuses": sg, "technologies": "Assumed PV" if nc else "", "n_units": 1, "capacity_ratings": "MWac" if t == "utility-scale solar" else "",
                                 "start_year_min": 2000 + n % 20, "start_year_max": 2000 + n % 20 + (n % 2), "dc_links": "captive_dc" if n == 4 and not nc else "",
                                 "n_units_dc_link": 1 if n == 4 and not nc else 0, "n_units_other_set": 0})
                rows.append(base)
    cols = COLS_UNITS if kind == "units" else COLS_LOC
    df = pd.DataFrame(rows)[cols]
    for c in INT_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].replace("", np.nan)).astype("Int64")
    df["capacity_mw"] = df["capacity_mw"].astype(float)
    return df


def make_boundaries(root: Path) -> LB.Boundaries:
    (root / "display").mkdir(parents=True)
    g = gpd.GeoDataFrame({"unit_id": ISOS, "iso3": ISOS}, geometry=[box(-179 + 5 * i, -80, -176 + 5 * i, -79) for i in range(len(ISOS))], crs="EPSG:4326")
    g.to_parquet(root / "display" / "adm0.parquet")
    return LB.Boundaries(root=root, registry=pd.DataFrame([{"iso3": "USA", "level": "ADM2", "verified": "true"}]))


class GemRelease(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.boundaries = make_boundaries(cls.tmp / "bnd")
        cls.dummy = cls.tmp / "GEM.xlsx"
        cls.dummy.write_bytes(b"dummy workbook")
        cls.rules = cls.tmp / "rules"
        cls.rules.mkdir()
        pd.DataFrame({"status": ["operating"], "status_group": ["operating"], "label": ["Operating"]}).to_csv(cls.rules / "gem_status_groups.csv", index=False, lineterminator="\n")
        pd.DataFrame({"gem_country_name": ["United States"], "iso3_gem": ["USA"]}).to_csv(cls.rules / "gem_country_table.csv", index=False, lineterminator="\n")
        pd.DataFrame({"iso3_gem": ["REU"], "iso3_source": ["FRA"], "reason": ["part of FRA in the abf-boundaries frame"]}).to_csv(cls.rules / "gem_iso3_to_adm0.csv", index=False, lineterminator="\n")
        cls.csv = {}
        for key, kind, nc in (("en_units", "units", False), ("en_loc", "locations", False), ("nc_units", "units", True), ("nc_loc", "locations", True)):
            p = cls.tmp / f"{key}.csv"
            LB.tilesio.write_csv(synth(kind, nc), p)
            cls.csv[key] = p

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def ctx(self, out: Path, channel: str = "dev") -> LB.BuildContext:
        out.mkdir(parents=True, exist_ok=True)
        rel = {"dataset": "abf-energy", "version": "0.1.0", "tag": "abf-energy-v0.1.0", "boundary_release": "abf-boundaries-v0.2.0"}
        return LB.BuildContext(release=rel, channel=channel, out_dir=out, built_at="2026-11-01T12:00:00Z", published_at="2026-11-01",
                               doi=None, boundaries=self.boundaries, report=Report("test"), tmp_dir=out.parent / "_tmp")

    def cfg(self, layer: str, key: str) -> dict:
        c = load_yaml(ROOT / "layers" / f"{layer}.yaml")
        c["input"]["table"] = str(self.csv[key])
        c["input"]["files"] = {k: str(self.dummy) for k in c["input"]["files"]}
        for e in c.get("extra_files") or []:
            e["path"] = str(self.rules / e["publish_as"])
        c.pop("expected_counts", None)   # the real numbers belong to the real files; the synthetic files have their own
        return c

    def build(self, layer: str, key: str, out_name: str, mutate=None, channel: str = "dev"):
        c = self.cfg(layer, key)
        if mutate:
            mutate(c)
        ctx = self.ctx(self.tmp / out_name, channel)
        return ctx, LB.build_point_layer(c, ctx)

    # ---- the four layers build in dev; meta matches the schema
    def test_all_four_layers_build_and_validate(self):
        for layer, key in (("energy_plants_gem_units", "en_units"), ("energy_plants_gem_locations", "en_loc"),
                           ("energy_plants_gem_tzsam_units", "nc_units"), ("energy_plants_gem_tzsam_locations", "nc_loc")):
            with self.subTest(layer=layer):
                ctx, lo = self.build(layer, key, f"o_{key}")
                BR.validate_meta(lo.meta)
                self.assertEqual(lo.meta["boundary_release"], "abf-boundaries-v0.2.0")
                self.assertEqual(ctx.report.warnings, [], ctx.report.warnings)   # includes csv_identical_to_input
                ids = {c["id"] for c in lo.meta["verification"]["automated_checks"]}
                self.assertIn("csv_identical_to_input", ids)

    def test_g3_does_not_stop_fuel_for_energy(self):
        _, lo = self.build("energy_plants_gem_units", "en_units", "o_g3")
        self.assertIn("fuel", [f["name"] for f in lo.meta["fields"]])
        with self.assertRaises(GateError):
            LB.gate_field_names("x", ["fuel"], "dc")
        LB.gate_field_names("x", ["fuel"], "energy")

    def test_nc_licence_family_and_attribution(self):
        _, lo = self.build("energy_plants_gem_tzsam_locations", "nc_loc", "o_nc")
        self.assertEqual(lo.meta["license"]["family"], "non_commercial")
        self.assertEqual(lo.meta["license"]["id"], "CC-BY-NC-4.0")
        text = lo.meta["license"]["attribution_text"]
        self.assertIn("Copyright © TransitionZero, Solar Asset Mapper, August 2025.", text)
        self.assertIn("Copernicus Sentinel-2", text)
        self.assertEqual([s["role"] for s in lo.meta["sources"]], ["primary", "attribute", "reference"])

    def test_energy_licence_is_cc_by(self):
        _, lo = self.build("energy_plants_gem_locations", "en_loc", "o_en")
        self.assertEqual((lo.meta["license"]["id"], lo.meta["license"]["family"]), ("CC-BY-4.0", "attribution"))

    def test_nc_source_must_be_primary(self):
        def swap(c):
            c["sources"][0]["license"] = copy.deepcopy(c["sources"][2]["license"])   # primary becomes CC BY, TZ stays NC
        with self.assertRaises(GateError) as cm:
            self.build("energy_plants_gem_tzsam_locations", "nc_loc", "o_nc_bad", swap)
        self.assertIn("G5", str(cm.exception))

    # ---- class_minzoom in the tile input; zoom_hint.below computed
    def tile_features(self, lo):
        with gzip.open(lo.tile_input, "rt", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]

    def test_class_minzoom_in_tiles(self):
        _, lo = self.build("energy_plants_gem_locations", "en_loc", "o_mz")
        feats = self.tile_features(lo)
        want = {"lt10": 5, "10_99": 4, "100_999": 3, "ge1000": 0}   # SPEC_GEM r10: one class, one zoom
        for f in feats:
            self.assertEqual(f["tippecanoe"]["minzoom"], want[f["properties"]["capacity_class"]])
        self.assertEqual(lo.tile_build["maxzoom"], 10)
        self.assertIn("start_year_min", lo.tile_fields)   # SPEC_GEM r7 W2

    def test_units_tiles_have_only_record_id(self):
        _, lo = self.build("energy_plants_gem_units", "en_units", "o_ut")
        self.assertEqual(lo.tile_fields, ["record_id"])
        self.assertEqual(lo.tile_build["maxzoom"], 5)
        self.assertFalse(lo.meta["display"]["map"])
        self.assertTrue(all(f["tippecanoe"]["minzoom"] <= 5 for f in self.tile_features(lo)))

    def test_zoom_hint_below_is_computed(self):
        _, lo = self.build("energy_plants_gem_tzsam_locations", "nc_loc", "o_zh")
        self.assertEqual(lo.meta["display"]["zoom_hint"]["below"], 4)       # only lt10 (5) and 10_99 (4) are in the layer
        self.assertEqual(lo.meta["display"]["zoom_hint"]["text"], "All plants of this layer are 20 MW or less. Zoom in to see them.")

        def wrong(c):
            c["display"]["zoom_hint"]["below"] = 3
        with self.assertRaises(GateError):
            self.build("energy_plants_gem_tzsam_locations", "nc_loc", "o_zh2", wrong)

    def test_nc_legend_has_one_class_and_no_symbol(self):
        # SPEC_GEM r10-r11: the NC legend shows one type; the shape of the symbol is not in the data
        _, nc = self.build("energy_plants_gem_tzsam_locations", "nc_loc", "o_ncl")
        d = nc.meta["display"]
        self.assertEqual(d["color_classes"], ["utility-scale solar"])
        self.assertEqual(list(d["legend_type_labels"]), ["utility-scale solar"])
        self.assertNotIn("symbol", d)
        self.assertIn("not in “Power plants”", d["legend_note"])

    def test_patch_gem_texts_r3(self):
        # RES r3: the known_gaps of the plant layer (sentence on the map fixed, item on shared points added), idempotent
        import patch_gem_texts_r3 as pg
        import yaml
        rows = [("L%d" % i, "120.0", "33.0", "CHN", "approximate", "Jiangsu") for i in range(25)]
        rows += [("L%d" % i, "10.5", "-3.0", "BRA", "approximate", "") for i in range(100, 122)]
        rows += [("L900", "1.0", "2.0", "FRA", "site", "X"), ("L901", "1.0", "2.0", "FRA", "site", "X")]
        df = pd.DataFrame(rows, columns=["location_id", "lon", "lat", "iso3_source", "coord_precision", "subnational_unit"])
        st = pg.shared_points(df)
        self.assertEqual((st["points"], st["plants"], st["china"], st["largest"], st["place"]), (2, 47, 25, 25, "Jiangsu"))
        self.assertTrue(st["all_approximate"])
        old = (ROOT / "layers" / "energy_plants_gem_locations.yaml").read_text(encoding="utf-8")
        if pg.APPROX_DONE in old:
            self.skipTest("texts already patched in this checkout")
        new, done = pg.patch_text(old, st)
        self.assertEqual(len(done), 2)
        gaps = yaml.safe_load(new)["coverage"]["known_gaps"]
        self.assertFalse(any("labeled as approximate" in g for g in gaps))
        self.assertTrue(any("Many approximate points are shared by several plants. 2 points carry 20 or more" in g for g in gaps))
        self.assertTrue(any("120°E, 33°N in Jiangsu, carries 25" in g for g in gaps))
        again, done2 = pg.patch_text(new, st)
        self.assertEqual((done2, again), ([], new))

    def test_class_minzoom_checks(self):
        def high(c):
            c["tiles"]["maxzoom"] = 4   # lt10 appears at zoom 5
        with self.assertRaises(GateError):
            self.build("energy_plants_gem_locations", "en_loc", "o_hi", high)

        def missing(c):
            c["display"]["class_minzoom"].pop("lt10")
        with self.assertRaises(GateError):
            self.build("energy_plants_gem_locations", "en_loc", "o_miss", missing)

    # ---- display.filters / popup / legend
    def test_display_filters_popup_legend(self):
        _, lo = self.build("energy_plants_gem_locations", "en_loc", "o_disp")
        d = lo.meta["display"]
        flt = {f["field"]: f for f in d["filters"]}
        self.assertEqual(flt["status_group"]["default"], "operating")
        self.assertEqual([v["label"] for v in flt["status_group"]["values"]],
                         ["Announced", "Pre-construction", "Construction", "Operating", "Shelved", "Cancelled", "Mothballed", "Retired"])
        self.assertEqual(flt["dc_links"]["mode"], "contains")
        self.assertIsNone(flt["dc_links"]["default"])
        self.assertNotIn("symbol", d)   # SPEC_GEM r10: the shape comes from content/site.json
        self.assertEqual(d["color_field"], "type")
        self.assertEqual(set(d["legend_size_labels"]), {"lt10", "10_99", "100_999", "ge1000"})
        self.assertIn("legend_approximate", d)
        self.assertNotIn("zoom_hint", d)

        def bad_filter(c):
            c["display"]["filters"][0]["field"] = "no_such_field"
        with self.assertRaises(GateError):
            self.build("energy_plants_gem_locations", "en_loc", "o_df", bad_filter)

        def bad_popup(c):
            c["display"]["popup"][2]["when"]["field"] = "no_such_field"
        with self.assertRaises(GateError):
            self.build("energy_plants_gem_locations", "en_loc", "o_dp", bad_popup)

        def bad_status(c):
            c["display"]["filters"][0]["values"].pop()
        with self.assertRaises(GateError):
            self.build("energy_plants_gem_locations", "en_loc", "o_ds", bad_status)

    # ---- input_columns_exact, csv_identical_to_input
    def test_input_columns_exact(self):
        def reorder(c):
            c["fields"][0], c["fields"][1] = c["fields"][1], c["fields"][0]
        with self.assertRaises(GateError) as cm:
            self.build("energy_plants_gem_locations", "en_loc", "o_ce", reorder)
        self.assertIn("G2", str(cm.exception))

    def test_csv_is_copied_byte_for_byte(self):
        # integers written as 800 (not 800.0) stay as they are: the released file is the input file
        df = pd.read_csv(self.csv["nc_loc"], dtype=str, keep_default_na=False)
        df["capacity_mw"] = df["capacity_mw"].str.replace(".0", "", regex=False)
        p = self.tmp / "ints.csv"
        df.to_csv(p, index=False, lineterminator="\n")
        old = self.csv["nc_loc"]
        self.csv["nc_loc"] = p
        try:
            ctx, lo = self.build("energy_plants_gem_tzsam_locations", "nc_loc", "o_ci_ok")
            self.assertEqual(ctx.report.warnings, [])
            self.assertEqual(lo.files["csv"].read_bytes(), p.read_bytes())
        finally:
            self.csv["nc_loc"] = old

    def test_csv_with_cr_inside_a_value_is_released(self):
        df = pd.read_csv(self.csv["nc_loc"], dtype=str, keep_default_na=False)
        df.loc[0, "plant_name"] = "Line one\r\nline two"   # GEM has one such value; it is the source's text
        p = self.tmp / "embedded.csv"
        p.write_bytes(df.to_csv(index=False, lineterminator="\n").encode("utf-8"))
        old = self.csv["nc_loc"]
        self.csv["nc_loc"] = p
        try:
            _, lo = self.build("energy_plants_gem_tzsam_locations", "nc_loc", "o_ci_cr")
            self.assertEqual(lo.files["csv"].read_bytes(), p.read_bytes())
        finally:
            self.csv["nc_loc"] = old

    def test_csv_not_releasable_stops(self):
        df = pd.read_csv(self.csv["nc_loc"], dtype=str, keep_default_na=False)
        old = self.csv["nc_loc"]
        try:
            for name, text in (("unsorted", df.iloc[::-1].to_csv(index=False, lineterminator="\n")),
                               ("crlf", df.to_csv(index=False, lineterminator="\r\n"))):
                p = self.tmp / f"{name}.csv"
                p.write_bytes(text.encode("utf-8"))
                self.csv["nc_loc"] = p
                for channel in ("dev", "final"):
                    with self.subTest(case=name, channel=channel):
                        with self.assertRaises(GateError) as cm:
                            self.build("energy_plants_gem_tzsam_locations", "nc_loc", f"o_ci_{name}_{channel}", channel=channel)
                        self.assertIn("G6", str(cm.exception))
        finally:
            self.csv["nc_loc"] = old

    def test_g7_cyrillic_outside_skip_list_stops(self):
        df = pd.read_csv(self.csv["en_loc"], dtype=str, keep_default_na=False)
        df.loc[0, "plant_name"] = "Станция"
        p = self.tmp / "cyr.csv"
        df.to_csv(p, index=False, lineterminator="\n")
        old = self.csv["en_loc"]
        self.csv["en_loc"] = p
        try:
            with self.assertRaises(GateError):
                self.build("energy_plants_gem_locations", "en_loc", "o_cyr")
        finally:
            self.csv["en_loc"] = old

    # ---- git_copy
    def test_files_for_git(self):
        _, lo_u = self.build("energy_plants_gem_units", "en_units", "o_g1")
        _, lo_l = self.build("energy_plants_gem_locations", "en_loc", "o_g2")
        plan = {"layers": [BR.plan_layer(lo_u, self.tmp, [], "x.pmtiles"), BR.plan_layer(lo_l, self.tmp, lo_l.extra_files, "y.pmtiles")]}
        for lp in plan["layers"]:
            lp["git_copy"] = {"csv": False, "extra_files": False}
        manifest = {"layers": [{"layer_id": lo.layer_id, "meta": {"path": lo.meta_path.name},
                                "files": {"csv": {"path": f"{lo.layer_id}.csv"}}} for lo in (lo_u, lo_l)],
                    "extra_files": [{"path": "gem_status_groups.csv"}]}
        self.assertEqual(FR.files_for_git(manifest, plan),
                         ["energy_plants_gem_units.meta.json", "energy_plants_gem_locations.meta.json", "manifest.json"])
        for lp in plan["layers"]:
            lp["git_copy"] = {"csv": True, "extra_files": True}
        got = FR.files_for_git(manifest, plan)
        self.assertIn("energy_plants_gem_units.csv", got)
        self.assertIn("gem_status_groups.csv", got)

    def test_git_copy_default_and_release_key(self):
        _, lo = self.build("energy_plants_gem_units", "en_units", "o_g3b")
        self.assertEqual(lo.git_copy, {"csv": True, "extra_files": True})
        _, lo2 = self.build("energy_plants_gem_units", "en_units", "o_g3c", lambda c: c.update({"git_copy": {"csv": False, "extra_files": False}}))
        self.assertEqual(lo2.git_copy, {"csv": False, "extra_files": False})
        with self.assertRaises(GateError):
            self.build("energy_plants_gem_units", "en_units", "o_g3d", lambda c: c.update({"git_copy": {"cvs": False}}))

    # ---- release yamls
    def test_release_yamls(self):
        for ds, u, l in (("abf-energy", "energy_plants_gem_units", "energy_plants_gem_locations"),
                         ("abf-energync", "energy_plants_gem_tzsam_units", "energy_plants_gem_tzsam_locations")):
            rel = load_yaml(ROOT / "releases" / f"{ds}-v0.1.0.yaml")
            self.assertEqual((rel["dataset"], rel["version"], rel["tag"]), (ds, "0.1.0", f"{ds}-v0.1.0"))
            self.assertEqual(rel["git_copy"], {"csv": False, "extra_files": False})
            self.assertEqual([Path(p.replace("\\", "/")).stem for p in rel["layers"]], [u, l])
            self.assertEqual(rel["phrase_check"]["kind"], "gem")

    # ---- check_gem_phrases
    def make_workbook(self, drop: str | None = None) -> Path:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "About"
        for i, (key, phrase, in_book) in enumerate(CG.PHRASES):
            if in_book and key != drop:
                ws.cell(row=i + 1, column=1, value="Note: " + phrase + " (end)")
        wb.create_sheet("Power facilities").cell(row=1, column=1, value="lack of observed progress")
        p = self.tmp / f"gem_{drop}.xlsx"
        wb.save(p)
        return p

    def test_phrase_check_finds_all_in_workbook_and_yaml(self):
        lines, not_found, problems = CG.run_check(self.make_workbook(), ROOT / "layers")
        self.assertEqual(problems, [])
        self.assertEqual(not_found, [], not_found)

    def test_phrase_check_reports_missing_and_ignores_data_sheet(self):
        # the data sheet holds the phrase, the About sheet does not: still MISSING
        lines, not_found, problems = CG.run_check(self.make_workbook(drop="inferred_progress"), ROOT / "layers")
        self.assertEqual(not_found, ["inferred_progress"])

    def test_phrase_check_in_build_release(self):
        report = Report("t")
        BR.run_phrase_check({"kind": "gem", "xlsx": str(self.make_workbook()), "layers": str(ROOT / "layers")}, "final", report)
        with self.assertRaises(GateError):
            BR.run_phrase_check({"kind": "gem", "xlsx": str(self.make_workbook(drop="gem_copyright")), "layers": str(ROOT / "layers")}, "final", report)
        BR.run_phrase_check({"kind": "gem", "xlsx": str(self.make_workbook(drop="gem_copyright")), "layers": str(ROOT / "layers")}, "dev", report)
        self.assertTrue(report.warnings)

    # ---- the whole release run (build_release.run) on the synthetic files, dev channel
    def test_release_run_dev_both_datasets(self):
        import argparse
        import yaml
        for ds, u, l, ku, kl in (("abf-energy", "energy_plants_gem_units", "energy_plants_gem_locations", "en_units", "en_loc"),
                                 ("abf-energync", "energy_plants_gem_tzsam_units", "energy_plants_gem_tzsam_locations", "nc_units", "nc_loc")):
            with self.subTest(dataset=ds):
                work = self.tmp / f"run_{ds}"
                work.mkdir()
                lay = []
                for lid, key in ((u, ku), (l, kl)):
                    c = self.cfg(lid, key)
                    (work / f"{lid}.yaml").write_text(yaml.safe_dump(c, sort_keys=False, allow_unicode=True), encoding="utf-8")
                    lay.append(str(work / f"{lid}.yaml"))
                reg = work / "registry.csv"
                reg.write_text("iso3,level,verified\nUSA,ADM2,true\n", encoding="utf-8")
                wb = self.make_workbook()
                rel = load_yaml(ROOT / "releases" / f"{ds}-v0.1.0.yaml")
                rel["layers"] = lay
                rel["boundaries"] = {"dir": str(self.tmp / "bnd"), "registry": str(reg)}
                rel["phrase_check"] = {"kind": "gem", "xlsx": str(wb), "layers": str(ROOT / "layers")}
                rp = work / "release.yaml"
                rp.write_text(yaml.safe_dump(rel, sort_keys=False, allow_unicode=True), encoding="utf-8")
                args = argparse.Namespace(release=str(rp), out=str(work / "out"), channel="dev", override=None,
                                          built_at="2026-11-01T12:00:00Z", verbose=False)
                self.assertEqual(BR.run(args), 0)
                out = work / "out" / f"{ds}-v0.1.0"
                plan = json.loads((out / "build_plan.json").read_text(encoding="utf-8"))
                self.assertEqual([x["layer_id"] for x in plan["layers"]], [u, l])
                self.assertTrue(all(x["git_copy"] == {"csv": False, "extra_files": False} for x in plan["layers"]))
                self.assertEqual({t["output"] for t in plan["tile_builds"]}, {f"{u}.pmtiles", f"{l}.pmtiles"})
                self.assertEqual([e["path"] for e in plan["layers"][1]["extra_files"]], ["gem_status_groups.csv", "gem_country_table.csv", "gem_iso3_to_adm0.csv"])
                self.assertEqual(plan["layers"][0]["extra_files"], [])
                for name in ("gem_status_groups.csv", f"{u}.csv", f"{l}.csv", f"{l}.meta.json"):
                    self.assertTrue((out / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
