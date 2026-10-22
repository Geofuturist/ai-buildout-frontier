r"""abf-dc v0.1.0: build of the world data-center layers (SPEC_DC_world_v0_1_0 r2, section 2).

Run (Windows cmd, from the repo root)::

    python -m pip install pandas pyarrow shapely geopandas pyproj requests openpyxl
    python scripts\dc\dc_fetch.py --sources-dir "D:\GISData\DC\sources"
    python scripts\dc\dc_build.py --inputs-dir "D:\GISData\DC\inputs" --sources-dir "D:\GISData\DC\sources" --out-dir "D:\GISData\DC\out\abf-dc-v0.1.0"

Optional: --v-table "D:\GISData\DC\review_atlas_dcp.xlsx" (the filled table of V, section 2.8). Without it the cells with candidates
stay `not_checked`, and the table for V is written to <out-dir>\review_atlas_dcp.xlsx.

Inputs (--inputs-dir; the layout of abf-scratch research/dc_world/inputs/):
    atlas_copies/  atlas_coverage/  geonames/{cities500.zip,admin1CodesASCII.txt,countryInfo.txt,Readme.txt}  pilot_case1/{objects,checks}.csv
    manual_checks.csv  epoch/data_centers.csv  rules/country_name_aliases_20261022.csv  groups/GROUPS_members_v1.csv
Sources (--sources-dir; made by dc_fetch.py): frame/{units.csv,adm0.parquet,analysis_usa_adm2.parquet,contested_areas.parquet}, census/2023_Gaz_place_national.txt

Outputs (--out-dir): dc_atlas_points.csv, dc_epoch_points.csv, dc_atlas_count_adm0.csv, checks.csv, groups.csv, record_hashes.csv,
place_trace.csv, p9_withheld.csv, sources_manifest.json, build_log.json, build_report.md, inputs_archive/, review_atlas_dcp.xlsx.
Any failed check of section 2.9 stops the run (nothing is written as a result).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import platform
import shutil
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dc_atlas as A  # noqa: E402
import dc_checks as K  # noqa: E402
import dc_count as C  # noqa: E402
import dc_lib as L  # noqa: E402
import dc_place as P  # noqa: E402
import dc_power as W  # noqa: E402

VERSION = "0.1.0"
BOUNDARY_RELEASE = "abf-boundaries-v0.2.0"
EPOCH_FILE_DATE = "2026-10-12"

CONTRACT = ["record_id", "unit_id", "lon", "lat", "coord_source", "coord_precision", "source_grade", "ref", "checked_at", "checked_by"]
ATLAS_COLS = CONTRACT + ["name", "operator", "operator_type", "status_raw", "start_year", "power_class", "power_basis", "power_status",
                         "power_status_reason", "atlas_confidence", "country_source", "adm1_raw", "adm2_raw", "address_raw", "source_urls",
                         "same_key_group", "identical_group", "iso3_source", "iso3_frame", "control_iso3", "resolved_by_population", "location_state"]
EPOCH_COLS = CONTRACT + ["name", "owner", "users", "project", "country_source", "address_raw", "power_mw", "power_basis", "power_status",
                         "power_status_reason", "power_ref", "power_source_date", "power_checked_by", "h100e_current", "capital_cost_usd_bn",
                         "chip_types_current", "selected_sources", "iso3_source", "iso3_frame", "control_iso3", "resolved_by_population", "location_state"]


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def main() -> int:
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs-dir", required=True, type=Path)
    ap.add_argument("--sources-dir", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--v-table", type=Path, default=None)
    ap.add_argument("--aliases", default="rules/country_name_aliases_20261022.csv")
    ap.add_argument("--epoch-file-date", default=EPOCH_FILE_DATE)
    ap.add_argument("--expected-records", type=int, default=A.EXPECTED_RECORDS, help="9865 until the Portugal copy without filter is swapped in")
    a = ap.parse_args()
    I, S, O = a.inputs_dir, a.sources_dir, a.out_dir
    checked_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    A.EXPECTED_RECORDS = a.expected_records
    report: list[str] = ["# abf-dc v0.1.0 build report", "", f"Built {checked_at}; boundary_release {BOUNDARY_RELEASE}.", ""]
    notes: dict[str, object] = {}

    # ------------------------------------------------------------------ inputs
    gn = L.GeoNames(I / "geonames")
    frame = P.Frame(S / "frame")
    adm0_units = frame.units[frame.units["level"] == "ADM0"]
    if len(adm0_units) != 242:
        raise L.BuildStop(f"frame has {len(adm0_units)} ADM0 units, expected 242")
    aliases = L.load_aliases(I / a.aliases)
    countries = L.Countries(gn, aliases, adm0_units)
    L.extend_country_tokens(gn.country_names, {r["name_in_source"]: gn.iso3_to_2[r["iso3"]] for r in aliases.values() if r["iso3"] in gn.iso3_to_2})
    census = P.Census(S / "census" / "2023_Gaz_place_national.txt")
    resolver = P.PlaceResolver(gn, countries, frame, census)

    # ------------------------------------------------------------------ Atlas records, ids, groups, countries
    report.append("## Atlas blocks")
    atl, rec_h, blocks_df, dropped = A.read_atlas(I / "atlas_copies", report)
    atl = A.add_ids_and_groups(atl, rec_h)
    iso_by_block, iso_by_field, problems = {}, {}, []
    for name in atl["_selection_name"].unique():
        iso, how = countries.iso3(name)
        if iso is None or iso not in countries.adm0:
            raise L.BuildStop(f"Atlas block name {name!r} does not map to exactly one ADM0 unit (via {how})")
        iso_by_block[name] = iso
    for name in atl["country"].unique():
        iso, how = countries.iso3(name)
        if iso is None:
            raise L.BuildStop(f"Atlas country field {name!r} is not in the alias table")
        iso_by_field[name] = iso
    atl["iso3_source"] = atl["_selection_name"].map(iso_by_block)
    bad = atl[atl["country"].map(iso_by_field) != atl["iso3_source"]]
    if len(bad):
        raise L.BuildStop(f"iso3 by `country` differs from iso3 by block name for {len(bad)} records: {bad[['_selection_name', 'country']].drop_duplicates().values.tolist()[:5]}")
    notes["atlas_scope_kind_not_country"] = blocks_df[blocks_df["scope_kind"] != "country"][["selection_name", "scope_kind"]].values.tolist()
    report.append("")
    report.append("Blocks whose scope_kind is not `country`: " + (", ".join(f"{n} ({k})" for n, k in notes["atlas_scope_kind_not_country"]) or "none"))
    mc = {r["check_id"]: r for r in csv.DictReader(open(I / "manual_checks.csv", encoding="utf-8-sig", newline=""))}
    report.append(f"mc-0002 lists 126 National countries; this build has {atl['_selection_name'].nunique()} distinct block names (Gibraltar included): "
                  + ("consistent." if atl["_selection_name"].nunique() == 126 else "NOT consistent, question to [RES]."))
    filtered = blocks_df[blocks_df["active_filters"].str.contains("Status=", na=False)]
    retired_not_copied = {iso_by_block[n] for n in filtered["selection_name"] if "Retired" not in filtered.loc[filtered["selection_name"] == n, "active_filters"].iloc[0]}
    report.append("Blocks copied with a status filter (retired records not copied): " + (", ".join(sorted(retired_not_copied)) or "none"))
    listed_iso3 = set(atl["iso3_source"])

    # ------------------------------------------------------------------ Epoch records
    ep = pd.read_csv(I / "epoch" / "data_centers.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if len(ep) != 94:
        raise L.BuildStop(f"Epoch has {len(ep)} rows, expected 94")
    ep["record_id"] = ["EPO-" + L.slug(n) for n in ep["Name"]]
    if ep["record_id"].duplicated().any():
        raise L.BuildStop("Epoch slug is not unique")
    iso_e = []
    for n in ep["Country"]:
        iso, how = countries.iso3(n)
        if iso is None or iso not in countries.adm0:
            raise L.BuildStop(f"Epoch country {n!r} does not map to exactly one ADM0 unit")
        iso_e.append(iso)
    ep["iso3_source"] = iso_e

    # ------------------------------------------------------------------ place chain
    def run_chain(df: pd.DataFrame, name_col: str, op_col: str | None, adm1: str | None, adm2: str | None, addr_col: str, country_col: str) -> pd.DataFrame:
        rows = []
        for i, r in df.iterrows():
            rec = dict(iso3=r["iso3_source"], cc=countries.iso2(r["iso3_source"]), country_field=r[country_col], adm1=r[adm1] if adm1 else "",
                       adm2=r[adm2] if adm2 else "", address=r[addr_col], name=r[name_col], operator=r[op_col] if op_col else "")
            rows.append(resolver.resolve(rec))
        return pd.DataFrame(rows, index=df.index)

    pa = run_chain(atl, "name_or_title", "primary_actor", "adm1", "adm2", "address", "country")
    pe = run_chain(ep, "Name", "Owner", None, None, "Address", "Country")
    fa, fe = (frame.assign_frame(p.loc[p["coord_precision"] == "city", ["lon", "lat"]].astype(float), d["iso3_source"])
              for p, d in ((pa, atl), (pe, ep)))

    def attach(d: pd.DataFrame, p: pd.DataFrame, f: pd.DataFrame) -> pd.DataFrame:
        d = d.copy()
        for c in ["unit_id", "lon", "lat", "coord_source", "coord_precision", "resolved_by_population", "location_state"]:
            d[c] = p[c]
        d["iso3_frame"] = f["iso3_frame"].reindex(d.index).fillna("")
        d["control_iso3"] = f["control_iso3"].reindex(d.index).fillna("")
        d["frame_how"] = f["frame_how"].reindex(d.index).fillna("")
        d["resolved_by_population"] = d["resolved_by_population"].map(lambda v: "true" if v else "false")
        return d

    atl = attach(atl, pa, fa)
    ep = attach(ep, pe, fe)
    atl["place_step"], ep["place_step"] = pa["step"], pe["step"]
    atl["gid_"], ep["gid_"] = pa["geonameid"], pe["geonameid"]
    atl["place_"], ep["place_"] = pa["place"], pe["place"]

    def county_of_point(r):
        if r["coord_precision"] == "city" and r["iso3_frame"] == "USA":
            return frame.county_of(float(r["lon"]), float(r["lat"])) or ""
        return ""

    ep["county_"] = ep.apply(county_of_point, axis=1)
    atl["county_"] = atl.apply(county_of_point, axis=1)

    # ------------------------------------------------------------------ Atlas layer
    pw = pd.DataFrame([W.atlas_power(c) for c in atl["capacity_type"]], index=atl.index)
    atl = pd.concat([atl, pw], axis=1)
    atl["ref"] = [f"Atlas of Data Center Politics, National table {sn}, copy {ex[:10]}; file {fn}, row {ln}"
                  for sn, ex, fn, ln in zip(atl["_selection_name"], atl["_exported_at"], atl["_file"], atl["_line"])]
    atl["checked_at"], atl["checked_by"], atl["source_grade"] = checked_at, "script:dc_build", "secondary"
    atlas_out = pd.DataFrame({
        "record_id": atl["record_id"], "unit_id": atl["unit_id"], "lon": atl["lon"], "lat": atl["lat"], "coord_source": atl["coord_source"],
        "coord_precision": atl["coord_precision"], "source_grade": atl["source_grade"], "ref": atl["ref"], "checked_at": atl["checked_at"],
        "checked_by": atl["checked_by"], "name": atl["name_or_title"], "operator": atl["primary_actor"], "operator_type": atl["primary_actor_type"],
        "status_raw": atl["status"], "start_year": atl["start_year"], "power_class": atl["power_class"], "power_basis": atl["power_basis"],
        "power_status": atl["power_status"], "power_status_reason": atl["power_status_reason"], "atlas_confidence": atl["confidence"],
        "country_source": atl["country"], "adm1_raw": atl["adm1"], "adm2_raw": atl["adm2"], "address_raw": atl["address"], "source_urls": atl["source_urls"],
        "same_key_group": atl["same_key_group"], "identical_group": atl["identical_group"], "iso3_source": atl["iso3_source"],
        "iso3_frame": atl["iso3_frame"], "control_iso3": atl["control_iso3"], "resolved_by_population": atl["resolved_by_population"],
        "location_state": atl["location_state"]})[ATLAS_COLS].sort_values("record_id").reset_index(drop=True)

    # ------------------------------------------------------------------ Epoch layer
    withheld, withheld_rows = W.p9_withheld(I / "pilot_case1")
    withheld = {n: v for n, v in withheld.items() if n in set(ep["Name"])}
    epw = pd.DataFrame([W.epoch_power(r["Current power (MW)"], r["Name"], withheld, a.epoch_file_date) for _, r in ep.iterrows()], index=ep.index)
    ep = pd.concat([ep, epw], axis=1)
    ep["ref"] = [f"Epoch AI, AI data centers, {n}, data_centers.csv of {a.epoch_file_date}" for n in ep["Name"]]
    ep["checked_at"], ep["checked_by"], ep["source_grade"] = checked_at, "script:dc_build", "secondary"
    ol = L.one_line
    epoch_out = pd.DataFrame({
        "record_id": ep["record_id"], "unit_id": ep["unit_id"], "lon": ep["lon"], "lat": ep["lat"], "coord_source": ep["coord_source"],
        "coord_precision": ep["coord_precision"], "source_grade": ep["source_grade"], "ref": ep["ref"], "checked_at": ep["checked_at"],
        "checked_by": ep["checked_by"], "name": ep["Name"], "owner": ep["Owner"].map(ol), "users": ep["Users"].map(ol), "project": ep["Project"].map(ol),
        "country_source": ep["Country"], "address_raw": ep["Address"].map(ol), "power_mw": ep["power_mw"], "power_basis": ep["power_basis"],
        "power_status": ep["power_status"], "power_status_reason": ep["power_status_reason"], "power_ref": ep["power_ref"],
        "power_source_date": ep["power_source_date"], "power_checked_by": ep["power_checked_by"], "h100e_current": ep["Current H100 equivalents"],
        "capital_cost_usd_bn": ep["Current total capital cost (2025 USD billions)"], "chip_types_current": ep["Current chip types"].map(ol),
        "selected_sources": ep["Selected Sources"].map(ol), "iso3_source": ep["iso3_source"], "iso3_frame": ep["iso3_frame"],
        "control_iso3": ep["control_iso3"], "resolved_by_population": ep["resolved_by_population"], "location_state": ep["location_state"]})[EPOCH_COLS]
    epoch_out = epoch_out.sort_values("record_id").reset_index(drop=True)

    # ------------------------------------------------------------------ country count, groups
    special = {"SOM": "Includes the 1 record of the Atlas block 'Somaliland' (counted under SOM, decision V 18.10)."}
    counts = C.count_table(atlas_out, adm0_units, listed_iso3, retired_not_copied, special, a.expected_records)
    groups = C.group_table(I / "groups" / "GROUPS_members_v1.csv", counts)

    # ------------------------------------------------------------------ checks.csv (section 2.8)
    checks, review, check_notes = K.build_checks(epoch_out, atlas_out, ep, atl, counts, checked_at, a.v_table, report)

    # ------------------------------------------------------------------ stops (section 2.9)
    K.stop_checks(atlas_out, epoch_out, counts, frame, a.expected_records, ATLAS_COLS, EPOCH_COLS)

    # ------------------------------------------------------------------ write
    if O.exists() and any(O.iterdir()):
        shutil.rmtree(O)
    O.mkdir(parents=True, exist_ok=True)
    atlas_out.to_csv(O / "dc_atlas_points.csv", index=False, lineterminator="\n", encoding="utf-8")
    epoch_out.to_csv(O / "dc_epoch_points.csv", index=False, lineterminator="\n", encoding="utf-8")
    counts.to_csv(O / "dc_atlas_count_adm0.csv", index=False, lineterminator="\n", encoding="utf-8")
    groups.to_csv(O / "groups.csv", index=False, lineterminator="\n", encoding="utf-8")
    checks.to_csv(O / "checks.csv", index=False, lineterminator="\n", encoding="utf-8")
    pd.DataFrame(withheld_rows, columns=["epoch_name", "pilot_record_id", "pilot_power_basis"]).to_csv(O / "p9_withheld.csv", index=False, lineterminator="\n")
    hashes = []
    for layer, df in (("dc_atlas_points", atlas_out), ("dc_epoch_points", epoch_out)):
        cols = [c for c in df.columns if c != "checked_at"]
        for r in df[cols].itertuples(index=False):
            hashes.append(dict(layer=layer, record_id=r[0], row_sha256=hashlib.sha256("\x1f".join(str(v) for v in r).encode("utf-8")).hexdigest()))
    pd.DataFrame(hashes).to_csv(O / "record_hashes.csv", index=False, lineterminator="\n")
    trace_a = pd.DataFrame({"record_id": atl["record_id"], "layer": "dc_atlas_points", "step": pa["step"], "place": pa["place"], "geonameid": pa["geonameid"],
                            "via": pa["via"], "basis_text": pa["basis_text"], "iso3_frame_how": atl["frame_how"]})
    trace_e = pd.DataFrame({"record_id": ep["record_id"], "layer": "dc_epoch_points", "step": pe["step"], "place": pe["place"], "geonameid": pe["geonameid"],
                            "via": pe["via"], "basis_text": pe["basis_text"], "iso3_frame_how": ep["frame_how"]})
    pd.concat([trace_a, trace_e]).sort_values(["layer", "record_id"]).to_csv(O / "place_trace.csv", index=False, lineterminator="\n")
    if review is not None:
        K.write_review_xlsx(review, O / "review_atlas_dcp.xlsx")

    # archive of inputs for the release (SPEC section 4 p.4)
    arch = O / "inputs_archive"
    shutil.copytree(I / "atlas_copies", arch / "atlas_copies")
    shutil.copy2(I / "epoch" / "data_centers.csv", arch / "data_centers.csv")
    shutil.copy2(I / "manual_checks.csv", arch / "manual_checks.csv")
    shutil.copy2(I / a.aliases, arch / "country_name_aliases.csv")
    shutil.copy2(I / "groups" / "GROUPS_members_v1.csv", arch / "GROUPS_members_v1.csv")

    # sources manifest
    man = {}
    for p in sorted(I.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(I)).replace("\\", "/")
            man[f"inputs/{rel}"] = dict(url="manual", size=p.stat().st_size, sha256=sha_file(p), origin=_origin(rel))
    fm = S / "sources_manifest_fetch.json"
    if fm.exists():
        man.update(json.loads(fm.read_text(encoding="utf-8")))
    (O / "sources_manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")

    # report
    _report(report, atlas_out, epoch_out, atl, ep, pa, pe, counts, groups, checks, check_notes, withheld_rows, retired_not_copied, frame, dropped)
    (O / "build_report.md").write_text("\n".join(report), encoding="utf-8")
    log = dict(version=VERSION, boundary_release=BOUNDARY_RELEASE, built_at=checked_at, seconds=round(time.time() - t0, 1), python=platform.python_version(),
               platform=platform.platform(), libs={m: sys.modules[m].__version__ for m in ("pandas", "geopandas", "shapely", "pyarrow") if m in sys.modules},
               rows=dict(dc_atlas_points=len(atlas_out), dc_epoch_points=len(epoch_out), dc_atlas_count_adm0=len(counts), checks=len(checks)),
               args={k: str(v) for k, v in vars(a).items()})
    (O / "build_log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK: {len(atlas_out)} Atlas, {len(epoch_out)} Epoch, {len(counts)} ADM0, {len(checks)} cells -> {O}")
    return 0


def _origin(rel: str) -> str:
    if rel.startswith("atlas_copies/"):
        return "manual copy by V from the Atlas site (Copy as: Table), 2026-10-14..18; atlas_data_updated 2026-10-08"
    if rel.startswith("geonames/"):
        return "download by V from download.geonames.org (CC BY 4.0, Readme.txt)"
    if rel.startswith("epoch/"):
        return "https://epoch.ai/data/data_centers/data_centers.csv, retrieved 2026-10-14T12:01:57Z (page: Updated Oct. 12, 2026)"
    if rel.startswith("pilot_case1/"):
        return "pilot case 1 (Virginia), abf-scratch research/dc_world/inputs/pilot_case1"
    return "abf-scratch main"


def _report(rep, atlas_out, epoch_out, atl, ep, pa, pe, counts, groups, checks, check_notes, withheld_rows, retired_not_copied, frame, dropped):
    rep += ["", "## Numbers", "", f"- dc_atlas_points {len(atlas_out)}; dc_epoch_points {len(epoch_out)}; dc_atlas_count_adm0 {len(counts)}; checks {len(checks)}",
            f"- sum of n_records over ADM0: {int(counts['n_records'].sum())}"]
    for nm, d in (("Atlas", atlas_out), ("Epoch", epoch_out)):
        rep += ["", f"## {nm}: coord_source / coord_precision", "", "| coord_source | coord_precision | records |", "|---|---|---:|"]
        g = d.groupby([d["coord_source"].replace("", "(none)"), "coord_precision"]).size()
        rep += [f"| {a} | {b} | {n} |" for (a, b), n in g.items()]
        rep += ["", f"location_state (records without a city point): " + str(d[d["coord_precision"] != "city"]["location_state"].value_counts().to_dict()),
                f"resolved_by_population = true: {int((d['resolved_by_population'] == 'true').sum())}"]
    ne = int((atlas_out["iso3_frame"] != atlas_out["iso3_source"]).sum() - (atlas_out["iso3_frame"] == "").sum())
    rep += ["", "## iso3_frame != iso3_source (records with a point)", ""]
    for nm, d in (("Atlas", atlas_out), ("Epoch", epoch_out)):
        x = d[(d["iso3_frame"] != "") & (d["iso3_frame"] != d["iso3_source"])]
        rep.append(f"- {nm}: {len(x)}" + ("" if x.empty else "; " + "; ".join(f"{r.record_id} {r.iso3_source}->{r.iso3_frame}" + (f" (control {r.control_iso3})" if r.control_iso3 else "") for r in x.head(60).itertuples())))
    rep += ["", "## contested zones", ""]
    for nm, d in (("Atlas", atlas_out), ("Epoch", epoch_out)):
        x = d[d["control_iso3"] != ""]
        rep.append(f"- {nm}: {len(x)} record(s) with control_iso3: " + "; ".join(f"{r.record_id} iso3_source={r.iso3_source} iso3_frame={r.iso3_frame} control={r.control_iso3}" for r in x.itertuples()))
    z = atlas_out[(atlas_out["adm1_raw"].str.casefold().isin(["crimea", "sevastopol"])) & (atlas_out["control_iso3"] == "")]
    rep.append(f"- Atlas records with adm1 Crimea/Sevastopol but no point in the zone: {len(z)}" + ("; " + "; ".join(z["record_id"]) if len(z) else ""))
    rep += ["", "## P9 / withheld", "", f"- withheld: {len(withheld_rows)}" + ("" if not withheld_rows else " -> p9_withheld.csv")]
    rep += ["", "## Dropped repeated Atlas blocks", ""] + [f"- {d['selection_name']}: dropped {d['dropped']}, kept {d['kept']}, identical content {d['identical_content']}" for d in dropped]
    rep += ["", "## Retired records not copied", "", ", ".join(sorted(retired_not_copied)) or "none"]
    rep += ["", "## checks.csv", ""] + check_notes
    rep += ["", "## Comparison with the scouting run (differences over 5 points are listed)", ""]
    n_city_e = int((epoch_out["coord_precision"] == "city").sum())
    rep.append(f"- Epoch records with a city point: {n_city_e} of 94 (scouting: 63 resolved); difference {n_city_e - 63:+d} ({(n_city_e - 63) / 94 * 100:+.1f} points)")
    tgt = atl[(atl["address"].str.strip() == "") & ~((atl["iso3_source"] == "USA") & (atl["adm2"].str.strip() != ""))]
    s3 = int((tgt["place_step"] == 3).sum())
    rep.append(f"- Atlas records without address and without US county: {len(tgt)}; place from the name (step 3): {s3} = {s3 / len(tgt) * 100:.1f}% (scouting: 865 of 2044 = 42.3%); difference {s3 / len(tgt) * 100 - 42.3:+.1f} points")


if __name__ == "__main__":
    sys.exit(main())
