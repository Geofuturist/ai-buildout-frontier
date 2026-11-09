r"""Tests of the abf-layers 0.3.0 release code (state and county layers of the United States, Alaska and Hawaii), no network,
no real geometry.

Run from the repository root (Windows):
    python scripts\publish\test_layers_release.py

What is real: the layer yamls and the release yaml, the four CSV files of the state layers, state_reconciliation.csv, the input
tables of the county layers and the published CSV of the county layers of 0.1.0, units.csv of abf-boundaries 0.2.0.
What is synthetic: the boundaries release (squares instead of outlines), the saved pages and the PDF of the phrase check, the
segment layers of the rows_superset test.
"""
from __future__ import annotations

import copy
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
import pandas as pd  # noqa: E402
from shapely.geometry import box  # noqa: E402

import build_release as BR  # noqa: E402
import check_branch as CB  # noqa: E402
import check_layers_phrases as CP  # noqa: E402
import compare_release_values as CV  # noqa: E402
import layer_build as LB  # noqa: E402
import rollup_check as RC  # noqa: E402
from common import GateError, Report, load_yaml  # noqa: E402

UNITS = ROOT / "data" / "abf-boundaries" / "v0.2.0" / "units.csv"
OLD = ROOT / "data" / "abf-layers" / "v0.1.0"
RECON = ROOT / "data" / "conus" / "state_reconciliation_20261108.csv"
HAVE = UNITS.exists() and OLD.exists() and RECON.exists()

AK_HI_LBNL = "Not covered: the source collects no interconnection queue data for Alaska or Hawaii."
AK_HI_NREL = "Not covered: the source covers only the contiguous United States."
AK_HI_NOTES = {"queue_lbnl": AK_HI_LBNL, "demand_nrel8562": AK_HI_NREL}     # the two layers whose sources have no data there
HOME_BBOX = [-124.7631, 24.5213, -66.9499, 49.3844]
CT_NOTE = ("Not covered: the source codes Connecticut projects by the pre-2022 counties, which do not map onto the 2022 planning regions. "
           "The seven active Connecticut requests are counted in the Connecticut state value.")
FAMILIES = {
    "generation_eia860": ("net_summer_capacity_mw", "Generation · EIA-860"),
    "queue_lbnl": ("queue_mw_active", "Interconnection queue · LBNL Queued Up"),
    "demand_nrel8562": ("peak_demand_mw", "Demand · NREL OEDI 8562"),
    "transmission_hifld": ("km_total", "Transmission lines · HIFLD"),
}


def pdf_lib() -> bool:
    for name in ("pypdf", "pdfminer"):
        try:
            __import__(name)
            return True
        except ImportError:
            continue
    return False


def make_pdf(path: Path, text: str) -> None:
    """A one-page PDF with the text (hand-written, so that no PDF library is needed to write it)."""
    stream = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources << /Font << /F1 4 0 R >> >> >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)


def make_boundaries(root: Path) -> LB.Boundaries:
    """Squares instead of outlines: states and counties of the United States; Alaska and Hawaii far from the rest."""
    units = pd.read_csv(UNITS, dtype=str, keep_default_na=False)
    (root / "display").mkdir(parents=True)
    for level, n in (("ADM1", 1), ("ADM2", 2)):
        sub = units[(units["iso3"] == "USA") & (units["level"] == level)].sort_values("unit_id").reset_index(drop=True)
        geoms = []
        for i, uid in enumerate(sub["unit_id"]):
            code = uid.split("-")[2]
            if code[:2] in ("02", "15"):
                x, y = -170 + (i % 10) * 0.1, 55 + (i % 7) * 0.1
            else:
                x, y = -120 + (i % 60), 25 + (i // 60) % 24
            geoms.append(box(x, y, x + 0.5, y + 0.5))
        gpd.GeoDataFrame(sub[["unit_id", "name"]], geometry=geoms, crs="EPSG:4326").to_parquet(root / "display" / f"adm{n}.parquet")
    reg = pd.DataFrame([{"iso3": "USA", "level": "ADM1", "verified": "true"}, {"iso3": "USA", "level": "ADM2", "verified": "true"}])
    return LB.Boundaries(root=root, registry=reg)


@unittest.skipUnless(HAVE, "published input files are not in the working tree")
class StateLayers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.boundaries = make_boundaries(cls.tmp / "bnd")
        cls.out = cls.tmp / "out"
        cls.out.mkdir()
        rel = {"dataset": "abf-layers", "version": "0.3.0", "tag": "abf-layers-v0.3.0", "boundary_release": "abf-boundaries-v0.2.0"}
        cls.ctx = LB.BuildContext(release=rel, channel="dev", out_dir=cls.out, built_at="2026-11-08T12:00:00Z", published_at="2026-11-08",
                                  doi=None, boundaries=cls.boundaries, report=Report("test"), tmp_dir=cls.tmp / "_tmp")
        cls.layers: dict[str, LB.LayerOutput] = {}
        for fam in FAMILIES:
            for level in ("adm2", "adm1"):
                cfg = load_yaml(ROOT / "layers" / f"energy_{fam}_{level}.yaml")
                cfg.pop("rights_check", None)      # needs the HIFLD archive of the real machine
                cfg.pop("source_archive", None)
                for src in cfg["sources"]:
                    src["input_refs"] = [r for r in src.get("input_refs", []) if r != "archive"]
                if level == "adm1" and cfg.get("extra_files"):
                    pass                            # the real state_reconciliation file of the repository
                cls.layers[f"{fam}_{level}"] = LB.build_adm_layer(cfg, cls.ctx)
        shutil.copyfile(RECON, cls.out / "state_reconciliation.csv")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def csv(self, name: str) -> pd.DataFrame:
        return pd.read_csv(self.out / f"{name}.csv", dtype=str, keep_default_na=False)

    # ---- state layers
    def test_state_layers_rows_and_coverage(self):
        for fam, (value, series) in FAMILIES.items():
            with self.subTest(fam):
                lo = self.layers[f"{fam}_adm1"]
                df = self.csv(f"energy_{fam}_adm1")
                self.assertEqual(len(df), 51)
                n_cov = 49 if fam in AK_HI_NOTES else 51          # sources without Alaska and Hawaii stay not_covered
                self.assertEqual(int((df["coverage_status"] == "covered").sum()), n_cov)
                self.assertEqual(sorted(df.loc[df["coverage_status"] == "not_covered", "unit_id"]),
                                 ["USA-1-02", "USA-1-15"] if fam in AK_HI_NOTES else [])
                self.assertEqual(df.columns[:4].tolist(), ["unit_id", "name", "coverage_status", "coverage_note"])
                self.assertEqual(df.loc[df["unit_id"] == "USA-1-51", "name"].iloc[0], "Virginia")   # name from units.csv
                self.assertEqual(lo.meta["coverage"]["n_units_frame"], 51)
                self.assertEqual(lo.meta["coverage"]["n_units_covered"], n_cov)
                self.assertEqual(lo.meta["display"]["home_bbox"], HOME_BBOX)
                self.assertEqual(lo.meta["coverage"]["geography"] == "United States: the 50 states and the District of Columbia",
                                 fam not in AK_HI_NOTES)
                self.assertEqual(lo.meta["coverage"]["iso3"], ["USA"])
                self.assertEqual(lo.meta["display"]["series"], series)
                self.assertEqual(lo.meta["display"]["value_field"], value)
                self.assertEqual(lo.meta["level"], "ADM1")

    def test_coverage_notes_state_layers(self):
        for fam in FAMILIES:
            df = self.csv(f"energy_{fam}_adm1")
            self.assertEqual(set(df.loc[df["coverage_status"] == "not_covered", "coverage_note"]),
                             {AK_HI_NOTES[fam]} if fam in AK_HI_NOTES else set(), fam)
            self.assertEqual(set(df.loc[df["coverage_status"] == "covered", "coverage_note"]), {""}, fam)

    def test_alaska_and_hawaii_values_of_the_covered_layers(self):
        eia = self.csv("energy_generation_eia860_adm1").set_index("unit_id")
        self.assertEqual([eia.loc["USA-1-02", c] for c in ("net_summer_capacity_mw", "n_op_generators", "n_op_plants")], ["2220.47", "486", "141"])
        self.assertEqual([eia.loc["USA-1-15", c] for c in ("net_summer_capacity_mw", "n_op_generators", "n_op_plants")], ["3435.42", "212", "73"])
        hf = self.csv("energy_transmission_hifld_adm1").set_index("unit_id")
        self.assertEqual((hf.loc["USA-1-02", "km_total"], hf.loc["USA-1-15", "km_total"]), ("2812", "1250"))
        self.assertEqual((hf.loc["USA-1-02", "max_voltage_kv"], hf.loc["USA-1-15", "max_voltage_kv"]), ("230.0", "138.0"))

    def test_county_layers_cover_3144_or_3109_counties(self):
        for fam in FAMILIES:
            df = self.csv(f"energy_{fam}_adm2")
            self.assertEqual(len(df), 3144)
            ak_hi = df[df["unit_id"].str[len("USA-2-"):].str[:2].isin(["02", "15"])]
            self.assertEqual(len(ak_hi), 35)                  # 30 Alaska + 5 Hawaii
            if fam in AK_HI_NOTES:
                self.assertEqual(set(ak_hi["coverage_status"]), {"not_covered"})
                self.assertEqual(set(ak_hi["coverage_note"]), {AK_HI_NOTES[fam]})
                self.assertEqual(int((df["coverage_status"] == "covered").sum()), 3109 - (9 if fam == "queue_lbnl" else 0))
            else:
                self.assertEqual(set(ak_hi["coverage_status"]), {"covered"})
                self.assertEqual(set(df["coverage_status"]), {"covered"})
                self.assertEqual(set(df["coverage_note"]), {""})

    def test_connecticut_covered_in_state_queue_not_in_county_queue(self):
        st = self.csv("energy_queue_lbnl_adm1").set_index("unit_id")
        self.assertEqual(st.loc["USA-1-09", "coverage_status"], "covered")
        self.assertEqual(float(st.loc["USA-1-09", "queue_mw_active"]) > 0, True)
        co = self.csv("energy_queue_lbnl_adm2")
        ct = co[co["unit_id"].str.startswith("USA-2-09")]
        self.assertEqual(len(ct), 9)
        self.assertEqual(set(ct["coverage_status"]), {"not_covered"})
        self.assertEqual(set(ct["coverage_note"]), {CT_NOTE})

    def test_no_unexpected_warnings_in_the_build(self):
        # the source files are not here; two known HIFLD counties; with Alaska and Hawaii (low values) the first quintile of the
        # state values moved below the approved first breaks of EIA and HIFLD (SPEC r2 4a: breaks stay, the values fall in classes)
        known = ("totals_vs_source not run", "USA-2-19079 (Hamilton)", "USA-2-26035 (Clare)",
                 "energy_generation_eia860_adm1: quantiles moved", "energy_transmission_hifld_adm1: quantiles moved")
        bad = [w for w in self.ctx.report.warnings if not any(k in w for k in known)]
        self.assertEqual(bad, [])

    def test_empty_exceptions_list_is_a_check_not_a_warning(self):
        """EIA-860 by state has no exception (offshore plants are inside the states): `exceptions: []` writes the check."""
        d = Path(tempfile.mkdtemp())
        try:
            src = d / "gen.xlsx"
            pd.DataFrame({"Status": ["OP", "OP", "SB"], "State": ["VA", "NY", "VA"], "Summer Capacity (MW)": [10.0, 5.5, 99.0]}).to_excel(
                src, sheet_name="Operable", index=False)
            tvs = {"source_file": str(src), "sheet": "Operable", "header_row": 0, "status_column": "Status", "status_value": "OP",
                   "state_column": "State", "mw_column": "Summer Capacity (MW)", "layer_column": "v", "states": ["VA", "NY"], "exceptions": []}
            table = pd.DataFrame({"v": [10.0, 5.5]})
            checks: list = []
            rep = Report("t")
            LB.run_totals_vs_source("x", tvs, pd.DataFrame(), table, checks, rep)
            self.assertEqual([c["id"] for c in checks], ["totals_vs_source"])
            self.assertIn("with no exceptions", checks[0]["description"])
            self.assertEqual(rep.warnings, [])
            with self.assertRaises(GateError):
                LB.run_totals_vs_source("x", tvs, pd.DataFrame(), pd.DataFrame({"v": [10.0, 9.0]}), [], Report("t"))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_state_reconciliation_is_an_extra_file_of_the_eia_state_layer(self):
        lo = self.layers["generation_eia860_adm1"]
        self.assertEqual([e["file"] if "file" in e else e["path"] for e in lo.extra_files], ["state_reconciliation.csv"])
        self.assertEqual(self.csv("state_reconciliation").shape[0], 759)

    # ---- county layers: values of 0.1.0 outside Alaska and Hawaii, new column coverage_note
    def test_county_layers_equal_0_1_0_except_coverage_note_and_alaska_hawaii(self):
        prefixes = ("USA-2-02", "USA-2-15")
        for fam in FAMILIES:
            lid = f"energy_{fam}_adm2"
            with self.subTest(fam):
                new = self.out / f"{lid}.csv"
                self.assertEqual(CV.compare_csv(OLD / f"{lid}.csv", new, ("coverage_note",), prefixes), [])
                self.assertTrue(CV.compare_csv(OLD / f"{lid}.csv", new, ("coverage_note",)) or fam in AK_HI_NOTES,
                                "without the allowance the changed rows of Alaska and Hawaii must be reported")
                self.assertTrue(CV.compare_csv(OLD / f"{lid}.csv", new, (), prefixes), "without the allowance the added column must be reported")
                df = self.csv(lid)
                self.assertEqual(df.columns.tolist().index("coverage_note"), df.columns.tolist().index("coverage_status") + 1)

    def test_eia_county_layer_has_the_69_generators_line_and_the_alaska_plants(self):
        gaps = self.layers["generation_eia860_adm2"].meta["coverage"]["known_gaps"]
        self.assertIn("69 operating generators have no numeric summer capacity in the source and add nothing to net_summer_capacity_mw.", gaps)
        self.assertTrue(any("Chevak and Hooper Bay" in g and "Kusilvak" in g for g in gaps))
        gaps1 = self.layers["generation_eia860_adm1"].meta["coverage"]["known_gaps"]
        self.assertIn("69 operating generators have no numeric summer capacity in the source and add nothing to net_summer_capacity_mw.", gaps1)
        self.assertFalse(any("Alaska and Hawaii are not covered" in g for g in gaps + gaps1))

    def test_no_text_of_0_2_0_is_left_where_alaska_and_hawaii_are_now_covered_or_explained(self):
        for key, lo in self.layers.items():
            with self.subTest(key):
                blob = json.dumps(lo.meta, ensure_ascii=False)
                self.assertNotIn("Not processed", blob)
                self.assertNotIn("which this release does not cover", blob)
                self.assertNotIn("49 covered units", blob)

    def test_eia_source_total_is_checked_over_all_51_states(self):
        """On the real machine totals_vs_source reads the EIA-860 workbook; its state list must include Alaska and Hawaii,
        otherwise the layer total (which has them) differs from the source total by their 5,655.9 MW."""
        for lvl in ("adm1", "adm2"):
            states = load_yaml(ROOT / "layers" / f"energy_generation_eia860_{lvl}.yaml")["checks"]["totals_vs_source"]["states"]
            self.assertEqual((len(states), len(set(states)), "AK" in states, "HI" in states, "DC" in states), (51, 51, True, True, True), lvl)
        queue = load_yaml(ROOT / "layers" / "energy_queue_lbnl_adm1.yaml")["checks"]["totals_vs_source"]["states"]
        self.assertFalse({"AK", "HI"} & set(queue), "the queue source has no records of Alaska and Hawaii")

    def test_hifld_gap_lines_of_0_3_0(self):
        for lvl, unit in (("adm1", "state"), ("adm2", "county")):
            gaps = self.layers[f"transmission_hifld_{lvl}"].meta["coverage"]["known_gaps"]
            self.assertTrue(any("EPSG:5070" in g and "0.5% in Alaska and 0.1% in Hawaii" in g for g in gaps), lvl)
            self.assertTrue(any("30.3%" in g and "138 kV" in g for g in gaps), lvl)
        g1 = self.layers["transmission_hifld_adm1"].meta["coverage"]["known_gaps"]
        self.assertTrue(any("by up to 12 km in one state and by 33 km over all 51 states" in g for g in g1))
        self.assertTrue(any(g.startswith("1,479.5 km of line lie in no county polygon") for g in g1))
        g2 = self.layers["transmission_hifld_adm2"].meta["coverage"]["known_gaps"]
        self.assertTrue(any(g.startswith("29 county-equivalents have no line inside them") for g in g2))

    def test_reconciliation_hifld_numbers_quoted_in_the_text(self):
        d = pd.read_csv(RECON, dtype=str, keep_default_na=False)
        h = d[(d["layer_id"] == "energy_transmission_hifld_adm1") & (d["field"] == "km_total")]
        diff = pd.to_numeric(h["difference"])
        self.assertEqual((len(h), float(diff.abs().max()), float(diff.sum())), (51, 12.0, 33.0))

    # ---- rollup_sums on the published files
    CHK = {"kind": "rollup_sums", "file": "state_reconciliation.csv", "pairs": [
        {"state_layer": "energy_generation_eia860_adm1", "county_layer": "energy_generation_eia860_adm2",
         "fields": ["net_summer_capacity_mw", "n_op_generators", "n_op_plants"]},
        {"state_layer": "energy_queue_lbnl_adm1", "county_layer": "energy_queue_lbnl_adm2", "fields": ["queue_mw_active", "n_active_projects"]},
        {"state_layer": "energy_demand_nrel8562_adm1", "county_layer": "energy_demand_nrel8562_adm2", "fields": ["peak_demand_mw"],
         "peak_fields": ["peak_demand_mw"]},
        {"state_layer": "energy_transmission_hifld_adm1", "county_layer": "energy_transmission_hifld_adm2",
         "fields": ["km_ge765", "km_v500", "km_v345", "km_v230", "km_v138", "km_v115", "km_v69", "km_lt69_unknown", "km_total"],
         "max_fields": ["max_voltage_kv"], "any_fields": ["has_any_line"]}]}

    def test_rollup_sums_passes_on_the_release_files(self):
        rep = Report("t")
        BR.run_cross_checks([self.CHK], self.out, self.boundaries, rep)
        self.assertTrue(any("rollup_sums" in n for n in rep.notes))

    def test_release_yaml_cross_check_equals_the_one_tested_here(self):
        rel = load_yaml(ROOT / "releases" / "abf-layers-v0.3.0.yaml")
        self.assertEqual(rel["cross_checks"][0], self.CHK)
        self.assertEqual(rel["cross_checks"][1], {"kind": "rows_superset", "layer": "energy_transmission_lines_hifld", "key": "record_id",
                                                  "old_release_dir": "D:\\GISData\\release\\abf-layers-v0.2.0", "expected_old": 93880,
                                                  "expected_added": 349})
        self.assertEqual(len(rel["cross_checks"]), 2)

    def _tampered(self, edit):
        d = self.tmp / "tamper"
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(self.out, d, ignore=shutil.ignore_patterns("*.parquet", "*.geojson.gz"))
        edit(d)
        return d

    def test_rollup_sums_catches_a_county_value(self):
        def edit(d):
            f = d / "energy_queue_lbnl_adm2.csv"
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
            i = df.index[(df["unit_id"].str.startswith("USA-2-48")) & (df["coverage_status"] == "covered")][0]
            df.loc[i, "queue_mw_active"] = str(float(df.loc[i, "queue_mw_active"]) + 5)
            df.to_csv(f, index=False)
        with self.assertRaises(GateError) as cm:
            RC.check_rollup_sums(self.CHK, self._tampered(edit), Report("t"))
        self.assertIn("rollup_sums", str(cm.exception))

    def test_rollup_sums_catches_a_state_value_and_a_residual(self):
        def edit(d):
            f = d / "energy_generation_eia860_adm1.csv"
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
            df.loc[df["unit_id"] == "USA-1-41", "net_summer_capacity_mw"] = "1.0"
            df.to_csv(f, index=False)
        with self.assertRaises(GateError):
            RC.check_rollup_sums(self.CHK, self._tampered(edit), Report("t"))

        def edit2(d):
            f = d / "state_reconciliation.csv"
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
            m = (df["layer_id"] == "energy_queue_lbnl_adm1") & (df["unit_id"] == "USA-1-48") & (df["field"] == "queue_mw_active")
            df.loc[m, "residual"] = "12.5"
            df.to_csv(f, index=False)
        with self.assertRaises(GateError):
            RC.check_rollup_sums(self.CHK, self._tampered(edit2), Report("t"))

    def test_rollup_sums_catches_a_peak_above_the_sum_and_a_missing_state(self):
        def edit(d):
            f = d / "energy_demand_nrel8562_adm1.csv"
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
            df.loc[df["unit_id"] == "USA-1-09", "peak_demand_mw"] = "999999"
            df.to_csv(f, index=False)
        with self.assertRaises(GateError):
            RC.check_rollup_sums(self.CHK, self._tampered(edit), Report("t"))

        def edit2(d):
            f = d / "state_reconciliation.csv"
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
            df = df[~((df["layer_id"] == "energy_transmission_hifld_adm1") & (df["unit_id"] == "USA-1-06") & (df["field"] == "km_v345"))]
            df.to_csv(f, index=False)
        with self.assertRaises(GateError):
            RC.check_rollup_sums(self.CHK, self._tampered(edit2), Report("t"))

    def test_rollup_sums_catches_max_voltage_and_has_any_line(self):
        def edit(d):
            f = d / "energy_transmission_hifld_adm1.csv"
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
            df.loc[df["unit_id"] == "USA-1-06", "max_voltage_kv"] = "1.0"
            df.to_csv(f, index=False)
        with self.assertRaises(GateError):
            RC.check_rollup_sums(self.CHK, self._tampered(edit), Report("t"))


class CompareAddedColumns(unittest.TestCase):
    def write(self, d: Path, name: str, rows: list[dict]) -> Path:
        p = d / name
        pd.DataFrame(rows).to_csv(p, index=False)
        return p

    def test_allowance_is_narrow(self):
        d = Path(tempfile.mkdtemp())
        try:
            old = self.write(d, "old.csv", [{"unit_id": "A", "coverage_status": "covered", "v": 1}, {"unit_id": "B", "coverage_status": "not_covered", "v": ""}])
            new_ok = self.write(d, "ok.csv", [{"unit_id": "A", "coverage_status": "covered", "coverage_note": "", "v": 1},
                                              {"unit_id": "B", "coverage_status": "not_covered", "coverage_note": "why", "v": ""}])
            self.assertEqual(CV.compare_csv(old, new_ok, ("coverage_note",)), [])
            new_val = self.write(d, "val.csv", [{"unit_id": "A", "coverage_status": "covered", "coverage_note": "", "v": 2},
                                                {"unit_id": "B", "coverage_status": "not_covered", "coverage_note": "why", "v": ""}])
            self.assertTrue(any("values differ" in p for p in CV.compare_csv(old, new_val, ("coverage_note",))))
            new_cov = self.write(d, "cov.csv", [{"unit_id": "A", "coverage_status": "covered", "coverage_note": "oops", "v": 1},
                                                {"unit_id": "B", "coverage_status": "not_covered", "coverage_note": "why", "v": ""}])
            self.assertTrue(any("covered rows" in p for p in CV.compare_csv(old, new_cov, ("coverage_note",))))
            new_nc = self.write(d, "nc.csv", [{"unit_id": "A", "coverage_status": "covered", "coverage_note": "", "v": 1},
                                              {"unit_id": "B", "coverage_status": "not_covered", "coverage_note": "", "v": ""}])
            self.assertTrue(any("not_covered rows" in p for p in CV.compare_csv(old, new_nc, ("coverage_note",))))
            other = self.write(d, "other.csv", [{"unit_id": "A", "coverage_status": "covered", "extra": "", "v": 1},
                                                {"unit_id": "B", "coverage_status": "not_covered", "extra": "", "v": ""}])
            self.assertTrue(any("columns differ" in p for p in CV.compare_csv(old, other, ("coverage_note",))))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class Guard(unittest.TestCase):
    def test_release_yaml_is_complete_on_this_branch(self):
        self.assertEqual(CB.check("abf-layers", "0.3.0", "dev"), [])

    def test_final_needs_the_doi(self):
        probs = CB.check("abf-layers", "0.3.0", "final")
        self.assertTrue(any("doi" in p for p in probs) or load_yaml(ROOT / "releases" / "abf-layers-v0.3.0.yaml").get("doi"))

    def test_existing_releases_pass(self):
        for f in sorted((ROOT / "releases").glob("abf-*-v*.yaml")):
            d, v = f.stem.rsplit("-v", 1)
            self.assertEqual(CB.check(d, v, "dev"), [], f.name)

    def test_branch_with_old_code_stops(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            for sub in ("releases", "layers", "scripts/publish", "schemas"):
                shutil.copytree(ROOT / sub, tmp / sub, ignore=shutil.ignore_patterns("__pycache__", "test_*"))
            (tmp / "scripts/publish/index_build.py").unlink()
            self.assertTrue(any("index_build.py" in p for p in CB.check("abf-index", "0.1.0", "dev", tmp)))
            bld = tmp / "scripts/publish/build_release.py"
            bld.write_text(bld.read_text(encoding="utf-8").replace('kind == "rollup_sums"', 'kind == "other"'), encoding="utf-8")
            self.assertTrue(any("rollup_sums" in p for p in CB.check("abf-layers", "0.3.0", "dev", tmp)))
            bld.write_text(bld.read_text(encoding="utf-8").replace('kind == "rows_superset"', 'kind == "other2"'), encoding="utf-8")
            self.assertTrue(any("rows_superset" in p for p in CB.check("abf-layers", "0.3.0", "dev", tmp)))
            (tmp / "releases/abf-layers-v0.3.0.yaml").unlink()
            self.assertEqual(CB.check("abf-layers", "0.3.0", "dev", tmp), ["releases/abf-layers-v0.3.0.yaml is not on this branch"])
            sch = tmp / "schemas/meta.schema.json"
            (tmp / "releases/abf-layers-v0.3.0.yaml").write_text((ROOT / "releases/abf-layers-v0.3.0.yaml").read_text(encoding="utf-8"), encoding="utf-8")
            sch.write_text(sch.read_text(encoding="utf-8").replace('"series"', '"seriez"'), encoding="utf-8")
            self.assertTrue(any("series" in p for p in CB.check("abf-layers", "0.3.0", "dev", tmp)))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Phrases(unittest.TestCase):
    OEDI = ("<html><body><p>Retail sales of electricity reported by utilities are totaled to the state level and then allocated "
            "to counties by each county's share of state population.</p></body></html>")
    EIA = "<html><body><p>EIA-860 collects data on generators of 1 megawatt or greater. Released September 10, 2026.</p></body></html>"
    QUP = "Queued Up 2026. Figure 4. Note: No data collected for Hawaii or Alaska."

    def run_check(self, oedi: str, eia: str, qup: str | None = None):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "o.html").write_text(oedi, encoding="utf-8")
            (d / "e.html").write_text(eia, encoding="utf-8")
            pages = {"oedi_8562": d / "o.html", "eia860": d / "e.html"}
            if pdf_lib():
                make_pdf(d / "q.pdf", self.QUP if qup is None else qup)
                pages["queued_up"] = d / "q.pdf"
            else:
                (d / "q.pdf").write_text("x", encoding="utf-8")
            return CP.run_check(pages, ROOT / "layers")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    @unittest.skipUnless(pdf_lib(), "neither pypdf nor pdfminer.six is installed")
    def test_all_found(self):
        lines, not_found, problems = self.run_check(self.OEDI, self.EIA)
        self.assertEqual((not_found, problems), ([], []))

    @unittest.skipUnless(pdf_lib(), "neither pypdf nor pdfminer.six is installed")
    def test_queued_up_phrase_in_the_pdf(self):
        lines, nf, problems = self.run_check(self.OEDI, self.EIA, "Queued Up 2026. Data are shown for all states.")
        self.assertEqual((nf, problems), (["queued_up_ak_hi"], []))
        self.assertTrue(any("REMOVE from the yaml" in l and "no data was collected for them" in l for l in lines))

    def test_pdf_without_a_library_is_a_problem_not_a_crash(self):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "q.pdf").write_bytes(b"%PDF-1.4")
            real = CP.pdf_text
            def boom(path):
                raise RuntimeError("to read a PDF install pypdf: python -m pip install pypdf")
            CP.pdf_text = boom
            try:
                _, nf, problems = CP.run_check({"queued_up": d / "q.pdf"}, ROOT / "layers")
            finally:
                CP.pdf_text = real
            self.assertTrue(any("install pypdf" in p for p in problems))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_missing_phrase_is_reported_with_the_text_to_remove(self):
        lines, not_found, problems = self.run_check(self.OEDI.replace("share of state population", "weights"), self.EIA)
        self.assertIn("oedi_population_share", not_found)
        self.assertTrue(any("REMOVE from the yaml" in l and "closer than the county" in l for l in lines))

    def test_threshold_and_date(self):
        _, nf, _ = self.run_check(self.OEDI, self.EIA.replace("1 megawatt or greater", "5 megawatts"))
        self.assertIn("eia_threshold", nf)
        _, nf, _ = self.run_check(self.OEDI, self.EIA.replace("September 10, 2026", "later"))
        self.assertNotIn("eia_release_date", nf, "the release date is not quoted in the texts and does not block")

    def test_no_page_is_a_problem(self):
        _, _, problems = CP.run_check({}, ROOT / "layers")
        self.assertTrue(problems)

    def test_the_texts_that_depend_on_the_pages_are_in_the_yamls(self):
        _, nf, _ = self.run_check(self.OEDI, self.EIA)
        self.assertFalse([n for n in nf if "(yaml)" in n])
        self.assertTrue(any(k == "queued_up_ak_hi" for k, *_ in CP.PHRASES))

    def test_release_yaml_names_the_pages(self):
        pc = load_yaml(ROOT / "releases" / "abf-layers-v0.3.0.yaml")["phrase_check"]
        self.assertEqual((pc["kind"], sorted(pc["pages"])), ("layers", ["eia860", "oedi_8562", "queued_up"]))
        self.assertTrue(pc["pages"]["queued_up"].endswith(".pdf"))


class Yamls(unittest.TestCase):
    def test_release_yaml_lists_nine_layers_and_files_exist(self):
        rel = load_yaml(ROOT / "releases" / "abf-layers-v0.3.0.yaml")
        self.assertEqual(len(rel["layers"]), 9)
        self.assertEqual(rel["boundary_release"], "abf-boundaries-v0.2.0")
        for l in rel["layers"]:
            self.assertTrue((ROOT / l.replace("\\", "/")).exists(), l)
        self.assertEqual(rel["identity"]["layers"], [])        # the segments are no longer the same file; rows_superset proves them
        self.assertEqual((rel["version"], rel["tag"]), ("0.3.0", "abf-layers-v0.3.0"))

    def test_series_on_all_nine_layers(self):
        rel = load_yaml(ROOT / "releases" / "abf-layers-v0.3.0.yaml")
        series = [load_yaml(ROOT / l.replace("\\", "/"))["display"]["series"] for l in rel["layers"]]
        self.assertEqual(len(series), 9)
        self.assertEqual(sorted(set(series)), sorted(v[1] for v in FAMILIES.values()))

    def test_titles_match_spec(self):
        want = {"energy_generation_eia860_adm1": "Generation · EIA-860 · state", "energy_demand_nrel8562_adm1": "Demand · NREL OEDI 8562 · state",
                "energy_transmission_hifld_adm1": "Transmission lines · HIFLD · state",
                "energy_queue_lbnl_adm1": "Interconnection queue · LBNL Queued Up · state"}
        for lid, title in want.items():
            self.assertEqual(load_yaml(ROOT / "layers" / f"{lid}.yaml")["title"], title)

    def test_breaks_and_zero_class(self):
        d = {k: load_yaml(ROOT / "layers" / f"energy_{k}_adm1.yaml")["display"] for k in FAMILIES}
        self.assertEqual(d["generation_eia860"]["breaks"], [10000, 15000, 20000, 30000])
        self.assertEqual(d["queue_lbnl"]["breaks"], [10000, 15000, 25000, 40000])
        self.assertEqual(d["transmission_hifld"]["breaks"], [8000, 15000, 20000, 25000])
        self.assertEqual(d["demand_nrel8562"]["breaks"], [5000, 10000, 16000, 23000])
        self.assertEqual([k for k, v in d.items() if v["zero_class"]], ["queue_lbnl"])


class RowsSuperset(unittest.TestCase):
    """Cross-check rows_superset (the segment layer of 0.3.0) and the options of compare_release_values for 0.3.0."""

    def write(self, d: Path, rows: list[tuple], name: str, extra_col: bool = False) -> Path:
        gdf = gpd.GeoDataFrame({"record_id": [r[0] for r in rows], "voltage_kv": [r[1] for r in rows]},
                               geometry=[r[2] for r in rows], crs="EPSG:4326")
        p = d / name
        gdf.to_parquet(p)
        return p

    def setUp(self):
        from shapely.geometry import LineString
        self.d = Path(tempfile.mkdtemp())
        self.old_dir, self.new_dir = self.d / "old", self.d / "new"
        self.old_dir.mkdir()
        self.new_dir.mkdir()
        self.L = LineString
        self.old_rows = [("1", 230.0, LineString([(0, 0), (1, 1)])), ("2", None, LineString([(2, 2), (3, 3)])), ("3", 345.0, LineString([(4, 4), (5, 5)]))]
        self.new_rows = self.old_rows + [("9001", 138.0, LineString([(-150, 61), (-149, 62)])), ("9002", 69.0, LineString([(-157, 21), (-156, 20)]))]
        self.write(self.old_dir, self.old_rows, "lay.parquet")
        self.chk = {"kind": "rows_superset", "layer": "lay", "key": "record_id", "old_release_dir": str(self.old_dir),
                    "expected_old": 3, "expected_added": 2}

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_chk(self, new_rows, **over):
        self.write(self.new_dir, new_rows, "lay.parquet")
        rep = Report("t")
        BR.run_cross_checks([{**self.chk, **over}], self.new_dir, None, rep)
        return rep

    def test_passes_with_counted_new_rows(self):
        rep = self.run_chk(self.new_rows)
        self.assertTrue(any("rows_superset" in n and "2 new" in n for n in rep.notes))

    def test_a_changed_value_a_moved_geometry_and_a_lost_row_stop(self):
        bad_value = [("1", 231.0, self.old_rows[0][2])] + self.new_rows[1:]
        with self.assertRaises(GateError) as cm:
            self.run_chk(bad_value)
        self.assertIn("voltage_kv", str(cm.exception))
        moved = [("1", 230.0, self.L([(0, 0), (1, 1.000001)]))] + self.new_rows[1:]
        with self.assertRaises(GateError) as cm:
            self.run_chk(moved)
        self.assertIn("geometry", str(cm.exception))
        with self.assertRaises(GateError) as cm:
            self.run_chk(self.new_rows[1:])
        self.assertIn("not in the new file", str(cm.exception))

    def test_a_count_that_is_not_the_expected_one_stops(self):
        with self.assertRaises(GateError) as cm:
            self.run_chk(self.new_rows[:-1])
        self.assertIn("expected 2", str(cm.exception))
        with self.assertRaises(GateError):
            self.run_chk(self.new_rows, expected_old=4)

    def test_a_repeated_key_stops(self):
        with self.assertRaises(GateError) as cm:
            self.run_chk(self.new_rows + [self.new_rows[-1]])
        self.assertIn("repeated", str(cm.exception))

    def test_the_earlier_folder_must_be_the_published_one(self):
        import hashlib
        old = self.old_dir / "lay.parquet"
        manifest = {"tag": "abf-layers-v0.2.0", "layers": [{"layer_id": "lay", "files": {"parquet": {"sha256": hashlib.sha256(old.read_bytes()).hexdigest()}}}]}
        (self.old_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.run_chk(self.new_rows)
        manifest["layers"][0]["files"]["parquet"]["sha256"] = "0" * 64
        (self.old_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(GateError) as cm:
            self.run_chk(self.new_rows)
        self.assertIn("not the published file", str(cm.exception))

    def test_compare_geometry_and_csv_in_subset_mode(self):
        self.write(self.new_dir, self.new_rows, "lay.parquet")
        self.assertEqual(CV.compare_geometry(self.old_dir / "lay.parquet", self.new_dir / "lay.parquet", subset=True), [])
        self.assertTrue(CV.compare_geometry(self.old_dir / "lay.parquet", self.new_dir / "lay.parquet", subset=False))
        old = self.d / "o.csv"; new = self.d / "n.csv"
        pd.DataFrame({"record_id": ["1", "2"], "v": ["a", "b"]}).to_csv(old, index=False)
        pd.DataFrame({"record_id": ["1", "2", "3"], "v": ["a", "b", "c"]}).to_csv(new, index=False)
        self.assertEqual(CV.compare_csv(old, new, subset=True), [])
        self.assertTrue(CV.compare_csv(old, new))
        pd.DataFrame({"record_id": ["1", "2", "3"], "v": ["a", "X", "c"]}).to_csv(new, index=False)
        self.assertTrue(CV.compare_csv(old, new, subset=True))

    def test_changed_prefixes_leave_out_only_those_states(self):
        old = self.d / "o.csv"; new = self.d / "n.csv"
        pd.DataFrame({"unit_id": ["USA-1-01", "USA-1-02", "USA-1-15"], "coverage_status": ["covered", "not_covered", "not_covered"],
                      "v": ["1", "", ""]}).to_csv(old, index=False)
        pd.DataFrame({"unit_id": ["USA-1-01", "USA-1-02", "USA-1-15"], "coverage_status": ["covered", "covered", "covered"],
                      "v": ["1", "5", "6"]}).to_csv(new, index=False)
        self.assertEqual(CV.compare_csv(old, new, (), ("USA-1-02", "USA-1-15")), [])
        self.assertTrue(CV.compare_csv(old, new))
        pd.DataFrame({"unit_id": ["USA-1-01", "USA-1-02", "USA-1-15"], "coverage_status": ["covered", "covered", "covered"],
                      "v": ["2", "5", "6"]}).to_csv(new, index=False)
        self.assertTrue(any("values differ" in p for p in CV.compare_csv(old, new, (), ("USA-1-02", "USA-1-15"))))

    def test_identity_with_no_layers_checks_the_archive_only(self):
        rep = Report("t")
        out = self.d / "rel"; out.mkdir()
        arc = out / "a.zip"; arc.write_bytes(b"zip")
        import hashlib
        mf = {"tag": "abf-layers-v0.1.0", "layers": [], "source_archives": [{"path": "a.zip", "sha256": hashlib.sha256(b"zip").hexdigest()}]}
        (self.d / "mf.json").write_text(json.dumps(mf), encoding="utf-8")
        BR.run_identity({"manifest": str(self.d / "mf.json"), "layers": []}, out, rep)
        self.assertTrue(any("none (only the source archives" in l for l in rep.sections["Identity with abf-layers-v0.1.0"]))
        arc.write_bytes(b"changed")
        with self.assertRaises(GateError):
            BR.run_identity({"manifest": str(self.d / "mf.json"), "layers": []}, out, Report("t"))


if __name__ == "__main__":
    unittest.main()
