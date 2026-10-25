r"""Tests of the abf-dc 0.2.0 data step on the pinned published files (no network). Run from the repo root::

    python scripts\dc\test_dc_count_v020.py
"""

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import pandas as pd  # noqa: E402

import dc_count_v020 as C  # noqa: E402
from dc_lib import BuildStop  # noqa: E402

PTS = ROOT / "data" / "abf-dc" / "v0.1.0" / "dc_atlas_points.csv"
UNITS = ROOT / "data" / "abf-boundaries" / "v0.2.0" / "units.csv"


@unittest.skipUnless(PTS.exists() and UNITS.exists(), "published input files not in the working tree")
class DataStep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pts, _ = C.read_pinned(str(PTS), "points")
        cls.units, _ = C.read_pinned(str(UNITS), "units")

    def run_cli(self, out: Path, *extra):
        r = subprocess.run([sys.executable, str(HERE / "dc_count_v020.py"), "--points", str(PTS), "--units", str(UNITS), "--out-dir", str(out),
                            "--checked-at", "2026-10-24T12:00:00Z", *extra], capture_output=True, text=True)
        return r

    def test_numbers_and_rerun_bytes(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t) / "a", Path(t) / "b"
            self.assertEqual(self.run_cli(a).returncode, 0)
            self.assertEqual(self.run_cli(b).returncode, 0)
            for f in ("dc_atlas_count_places.csv", "dc_atlas_count_usa_adm2.csv", "county_records.csv", "sources_manifest.json", "build_report.md"):
                self.assertEqual((a / f).read_bytes(), (b / f).read_bytes(), f)
            self.assertNotIn(b"\r", (a / "county_records.csv").read_bytes())

    def test_pinned_hash(self):
        with tempfile.TemporaryDirectory() as t:
            lf = PTS.read_bytes().replace(b"\r\n", b"\n")              # the working tree may already be CRLF (git on Windows)
            crlf = Path(t) / "crlf.csv"
            crlf.write_bytes(lf.replace(b"\n", b"\r\n"))
            df, info = C.read_pinned(str(crlf), "points")
            self.assertEqual(len(df), 9865)
            self.assertIn("CRLF", info["read"])
            plain = Path(t) / "lf.csv"
            plain.write_bytes(lf)
            self.assertEqual(C.read_pinned(str(plain), "points")[1]["read"], "as is")
            bad = Path(t) / "bad.csv"
            bad.write_bytes(lf.replace(b"ATL-", b"ATX-", 1))
            with self.assertRaises(BuildStop):
                C.read_pinned(str(bad), "points")

    def test_places_stops(self):
        p = self.pts.copy()
        i = p.index[p["coord_precision"] == "city"][0]
        q = p.copy(); q.loc[i, "place_ref"] = ""
        with self.assertRaises(BuildStop):
            C.build_places(q, "2026-10-24T12:00:00Z")
        ref = p.loc[i, "place_ref"]
        j = p.index[(p["place_ref"] == ref) & (p.index != i)]
        if len(j):
            q = p.copy(); q.loc[j[0], "lon"] = "0.0"
            with self.assertRaises(BuildStop):
                C.build_places(q, "2026-10-24T12:00:00Z")
        k = p.index[p["coord_precision"] == "none"][0]
        q = p.copy(); q.loc[k, "place_ref"] = "geonames:1"
        with self.assertRaises(BuildStop):
            C.build_places(q, "2026-10-24T12:00:00Z")

    def test_sum_by_status_stops(self):
        p = self.pts[self.pts["coord_precision"] == "city"].copy()
        p.loc[p.index[0], "status_raw"] = "Something else"
        with self.assertRaises(BuildStop):
            C.tally(p, "place_ref")

    def run_mutated(self, mutate):
        """Run the whole step on a mutated copy of the points file (the pin is moved to the copy, so the stops of the step itself fire)."""
        import argparse
        with tempfile.TemporaryDirectory() as t:
            p = self.pts.copy()
            mutate(p)
            f = Path(t) / "pts.csv"
            p.to_csv(f, index=False, lineterminator="\n", encoding="utf-8")
            old = dict(C.PINNED)
            C.PINNED["points"] = (old["points"][0], hashlib.sha256(f.read_bytes()).hexdigest())
            try:
                C.run(argparse.Namespace(points=str(f), units=str(UNITS), out_dir=str(Path(t) / "o"), checked_at="2026-10-24T12:00:00Z",
                                         analysis_adm2=None, sources_manifest=[], groups=str(C.DEFAULT_GROUPS)))
            finally:
                C.PINNED.update(old)

    def test_county_link_stops(self):
        def m(p):
            i = p.index[p["coord_precision"] == "county"][0]
            p.loc[i, "unit_id"] = "USA-2-01001"                       # another county than the record names
        with self.assertRaisesRegex(BuildStop, "link.county_precision"):
            self.run_mutated(m)

    def test_expected_numbers_are_stops(self):
        def m(p):
            i = p.index[p["iso3_source"] == "USA"][0]
            p.loc[i, "adm2_raw"] = ""                                 # one more record without a county field
        with self.assertRaisesRegex(BuildStop, "us.no_county_field"):
            self.run_mutated(m)

    def test_place_numbers_are_stops(self):
        def m(p):
            i = p.index[p["coord_precision"] == "city"][0]
            p.loc[i, "status_raw"] = "Planned" if p.loc[i, "status_raw"] != "Planned" else "Retired"   # status moves, totals stay
            c = p[p["coord_precision"] == "city"]
            j = c.index[c["place_ref"].map(c["place_ref"].value_counts()) > 1][0]
            p.loc[j, "place_ref"] = "geonames:999999999"              # a new place of one record, taken from a larger one: 2 304 places
        with self.assertRaises(BuildStop):
            self.run_mutated(m)

    def run_groups(self, mutate_table):
        """Run the step with a mutated operator_type_groups.csv."""
        import argparse
        with tempfile.TemporaryDirectory() as t:
            g = pd.read_csv(C.DEFAULT_GROUPS, dtype=str, keep_default_na=False)
            g = mutate_table(g)
            f = Path(t) / "groups.csv"
            g.to_csv(f, index=False, lineterminator="\n")
            C.run(argparse.Namespace(points=str(PTS), units=str(UNITS), out_dir=str(Path(t) / "o"), checked_at="2026-10-24T12:00:00Z",
                                     analysis_adm2=None, sources_manifest=[], groups=str(f)))

    def test_groups_table_stops(self):
        def drop(g):                                   # an operator type of the points is not in the table
            return g[g["operator_type"] != "Crypto"]
        def number(g):                                 # n_records of a row differs from the points
            g.loc[g["operator_type"] == "Cloud", "n_records"] = "896"
            return g
        def group(g):                                  # a group outside the seven
            g.loc[g["operator_type"] == "Cloud", "type_group"] = "clouds"
            return g
        def dup(g):
            return pd.concat([g, g.head(1)])
        for m in (drop, number, group, dup):
            with self.assertRaises(BuildStop, msg=m.__name__):
                self.run_groups(m)

    def test_moved_type_changes_split_stop(self):
        def m(g):                                      # Telecom into 'other': the numbers of SPEC section 8 item 4 no longer hold
            g.loc[g["operator_type"] == "Telecom", "type_group"] = "other"
            return g
        with self.assertRaises(BuildStop):
            self.run_groups(m)

    def test_type_columns(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(self.run_cli(Path(t)).returncode, 0)
            pl = pd.read_csv(Path(t) / "dc_atlas_count_places.csv", dtype=str, keep_default_na=False)
            cols = list(pl.columns)
            i = cols.index("power_class")
            self.assertEqual(cols[i + 1:], ["type_group", *C.TYPE_COLS])
            n = pl["n_records"].astype(int)
            self.assertTrue((pl[C.TYPE_COLS].astype(int).sum(axis=1) == n).all())
            self.assertTrue((pl.loc[n == 1, "type_group"] != "").all())
            self.assertTrue((pl.loc[n >= 2, "type_group"] == "").all())
            for g in C.GROUPS:                         # the group of a single-record place is its only non-zero column
                one = pl[(n == 1) & (pl["type_group"] == g)]
                self.assertTrue((one["n_type_" + g].astype(int) == 1).all())
            self.assertEqual(sum(pl[c].astype(int).sum() for c in C.TYPE_COLS), 6087)
            self.assertNotIn(b"\r", (Path(t) / "operator_type_groups.csv").read_bytes())
            self.assertEqual((Path(t) / "operator_type_groups.csv").read_bytes(), C.DEFAULT_GROUPS.read_bytes().replace(b"\r\n", b"\n"))

    def test_report_against_named_county(self):
        import geopandas as gpd
        from shapely.geometry import box
        with tempfile.TemporaryDirectory() as t:
            m = self.pts[(self.pts["iso3_source"] == "USA") & (self.pts["coord_precision"] == "city")].head(3)
            cr, _, _ = C.build_counties(self.pts, self.units)
            named = cr.set_index("record_id").loc[m["record_id"]]
            geoms = []
            for r, u in zip(m.itertuples(), named["unit_id"]):
                lon, lat = float(r.lon), float(r.lat)
                geoms.append((u or "USA-2-00000", box(lon - .1, lat - .1, lon + .1, lat + .1)))
            g = gpd.GeoDataFrame({"unit_id": [x[0] for x in geoms]}, geometry=[x[1] for x in geoms], crs="EPSG:4326")
            pq = Path(t) / "analysis_usa_adm2.parquet"
            g.to_parquet(pq)
            lines: list[str] = []
            info = C.point_vs_named_county(self.pts, cr, pq, [], lines)
            self.assertEqual(info["same_county"] + info["other_county"] + info["outside_all_counties"], info["records_with_point_and_named_county"])
            self.assertGreaterEqual(info["same_county"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
