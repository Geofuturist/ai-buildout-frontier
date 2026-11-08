r"""Tests of the abf-layers 0.2.0 release code (state layers of the United States), no network, no real geometry.

Run from the repository root (Windows):
    python scripts\publish\test_layers_release.py

What is real: the layer yamls and the release yaml, the four CSV files of the state layers, state_reconciliation.csv, the input
tables of the county layers and the published CSV of the county layers of 0.1.0, units.csv of abf-boundaries 0.2.0.
What is synthetic: the boundaries release (squares instead of outlines) and the saved pages of the phrase check.
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
RECON = ROOT / "data" / "conus" / "state_reconciliation_20261107.csv"
HAVE = UNITS.exists() and OLD.exists() and RECON.exists()

AK_HI = "Not processed: this release covers only the contiguous United States and the District of Columbia."
AK_HI_NREL = AK_HI[:-1] + ", and so does the source."
CT_NOTE = ("Not covered: the source codes Connecticut projects by the pre-2022 counties, which do not map onto the 2022 planning regions. "
           "The seven active Connecticut requests are counted in the Connecticut state value.")
FAMILIES = {
    "generation_eia860": ("net_summer_capacity_mw", "Generation · EIA-860"),
    "queue_lbnl": ("queue_mw_active", "Interconnection queue · LBNL Queued Up"),
    "demand_nrel8562": ("peak_demand_mw", "Demand · NREL OEDI 8562"),
    "transmission_hifld": ("km_total", "Transmission lines · HIFLD"),
}


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
        rel = {"dataset": "abf-layers", "version": "0.2.0", "tag": "abf-layers-v0.2.0", "boundary_release": "abf-boundaries-v0.2.0"}
        cls.ctx = LB.BuildContext(release=rel, channel="dev", out_dir=cls.out, built_at="2026-11-07T12:00:00Z", published_at="2026-11-07",
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
                self.assertEqual(int((df["coverage_status"] == "covered").sum()), 49)
                self.assertEqual(sorted(df.loc[df["coverage_status"] == "not_covered", "unit_id"]), ["USA-1-02", "USA-1-15"])
                self.assertEqual(df.columns[:4].tolist(), ["unit_id", "name", "coverage_status", "coverage_note"])
                self.assertEqual(df.loc[df["unit_id"] == "USA-1-51", "name"].iloc[0], "Virginia")   # name from units.csv
                self.assertEqual(lo.meta["coverage"]["n_units_frame"], 51)
                self.assertEqual(lo.meta["coverage"]["n_units_covered"], 49)
                self.assertEqual(lo.meta["coverage"]["iso3"], ["USA"])
                self.assertEqual(lo.meta["display"]["series"], series)
                self.assertEqual(lo.meta["display"]["value_field"], value)
                self.assertEqual(lo.meta["level"], "ADM1")

    def test_coverage_notes_state_layers(self):
        for fam in FAMILIES:
            df = self.csv(f"energy_{fam}_adm1")
            want = AK_HI_NREL if fam == "demand_nrel8562" else AK_HI
            self.assertEqual(set(df.loc[df["coverage_status"] == "not_covered", "coverage_note"]), {want}, fam)
            self.assertEqual(set(df.loc[df["coverage_status"] == "covered", "coverage_note"]), {""}, fam)

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
        known = ("totals_vs_source not run", "USA-2-19079 (Hamilton)", "USA-2-26035 (Clare)")   # the source files are not here; two known HIFLD counties
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
        self.assertEqual(self.csv("state_reconciliation").shape[0], 735)

    # ---- county layers: values of 0.1.0, new column coverage_note
    def test_county_layers_equal_0_1_0_except_coverage_note(self):
        for fam in FAMILIES:
            lid = f"energy_{fam}_adm2"
            with self.subTest(fam):
                new = self.out / f"{lid}.csv"
                self.assertEqual(CV.compare_csv(OLD / f"{lid}.csv", new, ("coverage_note",)), [])
                self.assertTrue(CV.compare_csv(OLD / f"{lid}.csv", new), "without the allowance the added column must be reported")
                df = self.csv(lid)
                self.assertEqual(df.columns.tolist().index("coverage_note"), df.columns.tolist().index("coverage_status") + 1)
                want = AK_HI_NREL if fam == "demand_nrel8562" else AK_HI
                ak = df[df["unit_id"].str[len("USA-2-"):].str[:2].isin(["02", "15"])]
                self.assertEqual(set(ak["coverage_note"]), {want})

    def test_eia_county_layer_has_the_69_generators_line(self):
        gaps = self.layers["generation_eia860_adm2"].meta["coverage"]["known_gaps"]
        self.assertTrue(any(g.startswith("69 operating generators") for g in gaps))
        gaps1 = self.layers["generation_eia860_adm1"].meta["coverage"]["known_gaps"]
        self.assertTrue(any(g.startswith("69 operating generators") for g in gaps1))

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
        rel = load_yaml(ROOT / "releases" / "abf-layers-v0.2.0.yaml")
        self.assertEqual(rel["cross_checks"], [self.CHK])

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
        self.assertEqual(CB.check("abf-layers", "0.2.0", "dev"), [])

    def test_final_needs_the_doi(self):
        probs = CB.check("abf-layers", "0.2.0", "final")
        self.assertTrue(any("doi" in p for p in probs) or load_yaml(ROOT / "releases" / "abf-layers-v0.2.0.yaml").get("doi"))

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
            self.assertTrue(any("rollup_sums" in p for p in CB.check("abf-layers", "0.2.0", "dev", tmp)))
            (tmp / "releases/abf-layers-v0.2.0.yaml").unlink()
            self.assertEqual(CB.check("abf-layers", "0.2.0", "dev", tmp), ["releases/abf-layers-v0.2.0.yaml is not on this branch"])
            sch = tmp / "schemas/meta.schema.json"
            (tmp / "releases/abf-layers-v0.2.0.yaml").write_text((ROOT / "releases/abf-layers-v0.2.0.yaml").read_text(encoding="utf-8"), encoding="utf-8")
            sch.write_text(sch.read_text(encoding="utf-8").replace('"series"', '"seriez"'), encoding="utf-8")
            self.assertTrue(any("series" in p for p in CB.check("abf-layers", "0.2.0", "dev", tmp)))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Phrases(unittest.TestCase):
    OEDI = ("<html><body><p>Retail sales of electricity reported by utilities are totaled to the state level and then allocated "
            "to counties by each county's share of state population.</p></body></html>")
    EIA = "<html><body><p>EIA-860 collects data on generators of 1 megawatt or greater. Released September 10, 2026.</p></body></html>"

    def run_check(self, oedi: str, eia: str):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "o.html").write_text(oedi, encoding="utf-8")
            (d / "e.html").write_text(eia, encoding="utf-8")
            return CP.run_check({"oedi_8562": d / "o.html", "eia860": d / "e.html"}, ROOT / "layers")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_all_found(self):
        lines, not_found, problems = self.run_check(self.OEDI, self.EIA)
        self.assertEqual((not_found, problems), ([], []))

    def test_missing_phrase_is_reported_with_the_text_to_remove(self):
        lines, not_found, problems = self.run_check(self.OEDI.replace("share of state population", "weights"), self.EIA)
        self.assertEqual(not_found, ["oedi_population_share"])
        self.assertTrue(any("REMOVE from the yaml" in l and "closer than the county" in l for l in lines))

    def test_threshold_and_date(self):
        _, nf, _ = self.run_check(self.OEDI, self.EIA.replace("1 megawatt or greater", "5 megawatts"))
        self.assertEqual(nf, ["eia_threshold"])
        _, nf, _ = self.run_check(self.OEDI, self.EIA.replace("September 10, 2026", "later"))
        self.assertEqual(nf, [], "the release date is not quoted in the texts and does not block")

    def test_no_page_is_a_problem(self):
        _, _, problems = CP.run_check({}, ROOT / "layers")
        self.assertTrue(problems)

    def test_the_texts_that_depend_on_the_pages_are_in_the_yamls(self):
        _, nf, _ = self.run_check(self.OEDI, self.EIA)
        self.assertFalse([n for n in nf if "(yaml)" in n])

    def test_release_yaml_names_both_pages(self):
        pc = load_yaml(ROOT / "releases" / "abf-layers-v0.2.0.yaml")["phrase_check"]
        self.assertEqual((pc["kind"], sorted(pc["pages"])), ("layers", ["eia860", "oedi_8562"]))


class Yamls(unittest.TestCase):
    def test_release_yaml_lists_nine_layers_and_files_exist(self):
        rel = load_yaml(ROOT / "releases" / "abf-layers-v0.2.0.yaml")
        self.assertEqual(len(rel["layers"]), 9)
        self.assertEqual(rel["boundary_release"], "abf-boundaries-v0.2.0")
        for l in rel["layers"]:
            self.assertTrue((ROOT / l.replace("\\", "/")).exists(), l)
        self.assertEqual(rel["identity"]["layers"], ["energy_transmission_lines_hifld"])

    def test_series_on_all_nine_layers(self):
        rel = load_yaml(ROOT / "releases" / "abf-layers-v0.2.0.yaml")
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


if __name__ == "__main__":
    unittest.main()
