r"""abf-dc: accuracy of step 3 (place from the record name) on the scouting reference, by the FINAL rule (SPEC_DC_world_v0_1_0 r3, section 10).

Reference: the 4 160 Atlas records of the scouting run whose place is known from the address (`geonames_status = resolved`,
pass 2b, with GeoNames `cities500`). For each of them step 3 is applied alone (no network):
  name/asciiname only (no alternatenames); an n-gram equal to the region name only for PPLA/PPLC; in the US only inside the
  record's county (adm2); population rule; overlapping matches -> the longest; two different places -> ambiguous.
Result per record: same place / other place closer than 25 km / other place 25 km or farther / step 3 gives no place
(none, ambiguous, or blocked by the US county rule). The share is computed over the records for which step 3 gives a place.

Run (Windows cmd, from the repo root)::

    python scripts\dc\dc_eval_step3.py --inputs-dir "D:\GISData\DC\inputs" --sources-dir "D:\GISData\DC\sources" ^
        --reference "D:\GISData\DC\inputs\reference\atlas_locations_geonames_pass2b.csv" --out-dir "D:\GISData\DC\out\step3_accuracy"

The reference table is the scouting file `pass2/trial/atlas_locations_geonames.csv` (branch claude/cool-lovelace-45hy7b), copied unchanged.
Records are joined to the current Atlas copies by (country, name, address, adm1) and the order inside equal keys.
"""

from __future__ import annotations

import argparse
import collections
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dc_atlas as A  # noqa: E402
import dc_lib as L  # noqa: E402
import dc_place as P  # noqa: E402


def hav(lat1, lon1, lat2, lon2) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(d))


def key(country, name, address, adm1) -> str:
    return "\x1f".join((L.norm(country), L.norm(name), L.norm(address), L.norm(adm1)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs-dir", required=True, type=Path)
    ap.add_argument("--sources-dir", required=True, type=Path)
    ap.add_argument("--reference", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--aliases", default="rules/country_name_aliases_20261022.csv")
    ap.add_argument("--without-r3c", action="store_true", help="drop item 3c (place must occur in the address): the situation of records WITHOUT an address, which are the real targets of step 3")
    a = ap.parse_args()
    I, S = a.inputs_dir, a.sources_dir

    gn = L.GeoNames(I / "geonames")
    frame = P.Frame(S / "frame")
    aliases = L.load_aliases(I / a.aliases)
    countries = L.Countries(gn, aliases, frame.units[frame.units["level"] == "ADM0"])
    L.extend_country_tokens(gn.country_names, {r["name_in_source"]: gn.iso3_to_2[r["iso3"]] for r in aliases.values() if r["iso3"] in gn.iso3_to_2})
    resolver = P.PlaceResolver(gn, countries, frame, census=None, rules=(P.ALL_RULES - {"r3c"}) if a.without_r3c else P.ALL_RULES)

    report: list[str] = []
    atl, rec_h, _, _ = A.read_atlas(I / "atlas_copies", report)
    atl["iso3_source"] = [countries.iso3(n)[0] for n in atl["_selection_name"]]
    # item 3b of SPEC r5 section 12: the ADM1 of a record is learned from step 1 on all Atlas records, as in the build
    resolver.learn_adm1([dict(iso3=r.iso3_source, cc=countries.iso2(r.iso3_source), adm1=r.adm1, adm2=r.adm2, address=r.address, name=r.name_or_title,
                              operator=r.primary_actor) for r in atl.itertuples()])

    ref = pd.read_csv(a.reference, dtype=str, keep_default_na=False)
    ref = ref[ref["geonames_status"] == "resolved"].copy()
    if len(ref) != 4160:
        raise L.BuildStop(f"reference has {len(ref)} resolved records, expected 4160")

    # join: (country, name, address, adm1) + order inside equal keys (reference order = file#block:row)
    def order_key(rid: str):
        f, rest = rid.rsplit("#", 1)
        b, r = rest.split(":")
        return (f, int(b), int(r))

    ref["kk"] = [key(c, n, ad, r1) for c, n, ad, r1 in zip(ref["country_field"], ref["name"], ref["address"], ref["region_rule"])]
    ref["oo"] = ref["record_id"].map(order_key)
    ref = ref.sort_values("oo")
    ref["ii"] = ref.groupby("kk").cumcount()
    atl["_k"] = [key(c, n, ad, r1) for c, n, ad, r1 in zip(atl["country"], atl["name_or_title"], atl["address"], atl["adm1"])]
    atl = atl.sort_values(["_file", "_line"])
    atl["_i"] = atl.groupby("_k").cumcount()
    cur = atl.set_index(["_k", "_i"])

    rows = []
    unmatched = 0
    for r in ref.itertuples():
        idx = (r.kk, r.ii)
        if idx not in cur.index:
            unmatched += 1
            continue
        c = cur.loc[idx]
        if isinstance(c, pd.DataFrame):
            c = c.iloc[0]
        iso3 = c["iso3_source"]
        rec = dict(iso3=iso3, cc=countries.iso2(iso3), adm1=c["adm1"], adm2=c["adm2"], address=c["address"], name=c["name_or_title"], operator=c["primary_actor"])
        res = resolver.step3_only(rec)
        known = gn.by_id.get(r.geonameid)
        row = dict(reference_record_id=r.record_id, country=c["country"], iso3=iso3, name=c["name_or_title"], address=c["address"], known_place=(known.name if known else ""),
                   known_geonameid=r.geonameid, step3_status=res["status"], step3_place="", step3_geonameid="", by_population="", outcome="no_place", dist_km="")
        if res["status"] == "resolved":
            o = res["obj"]
            row.update(step3_place=o.name, step3_geonameid=o.geonameid, by_population=str(bool(res["by_pop"])).lower())
            if o.geonameid == r.geonameid:
                row.update(outcome="same", dist_km="0.0")
            else:
                d = hav(o.latf, o.lonf, float(r.lat), float(r.lon))
                row.update(outcome="other_lt25km" if d < 25.0 else "other_ge25km", dist_km=f"{d:.1f}")
        rows.append(row)
    if unmatched:
        raise L.BuildStop(f"{unmatched} reference records not found in the current Atlas copies")
    df = pd.DataFrame(rows)

    a.out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out_dir / "step3_accuracy_records.csv", index=False, lineterminator="\n")
    res_df = df[df["outcome"] != "no_place"]
    n_ref, n_res = len(df), len(res_df)
    cnt = res_df["outcome"].value_counts().to_dict()

    def pct(k, n):
        return f"{k / n * 100:.1f}" if n else "n/a"

    summ = []
    summ.append(dict(group="all", reference=n_ref, step3_gives_place=n_res, share_with_place=pct(n_res, n_ref), same=cnt.get("same", 0),
                     other_lt25km=cnt.get("other_lt25km", 0), other_ge25km=cnt.get("other_ge25km", 0),
                     same_pct=pct(cnt.get("same", 0), n_res), lt25_pct=pct(cnt.get("other_lt25km", 0), n_res), ge25_pct=pct(cnt.get("other_ge25km", 0), n_res),
                     within25_pct=pct(cnt.get("same", 0) + cnt.get("other_lt25km", 0), n_res)))
    for gname, mask in (("US", df["iso3"] == "USA"), ("non-US", df["iso3"] != "USA"), ("by_population=true", df["by_population"] == "true")):
        d = df[mask]
        rr = d[d["outcome"] != "no_place"]
        c2 = rr["outcome"].value_counts().to_dict()
        summ.append(dict(group=gname, reference=len(d), step3_gives_place=len(rr), share_with_place=pct(len(rr), len(d)), same=c2.get("same", 0),
                         other_lt25km=c2.get("other_lt25km", 0), other_ge25km=c2.get("other_ge25km", 0), same_pct=pct(c2.get("same", 0), len(rr)),
                         lt25_pct=pct(c2.get("other_lt25km", 0), len(rr)), ge25_pct=pct(c2.get("other_ge25km", 0), len(rr)),
                         within25_pct=pct(c2.get("same", 0) + c2.get("other_lt25km", 0), len(rr))))
    for iso, d in sorted(df.groupby("iso3"), key=lambda kv: -len(kv[1]))[:12]:
        rr = d[d["outcome"] != "no_place"]
        if len(rr) < 20:
            continue
        c2 = rr["outcome"].value_counts().to_dict()
        summ.append(dict(group=f"country {iso}", reference=len(d), step3_gives_place=len(rr), share_with_place=pct(len(rr), len(d)), same=c2.get("same", 0),
                         other_lt25km=c2.get("other_lt25km", 0), other_ge25km=c2.get("other_ge25km", 0), same_pct=pct(c2.get("same", 0), len(rr)),
                         lt25_pct=pct(c2.get("other_lt25km", 0), len(rr)), ge25_pct=pct(c2.get("other_ge25km", 0), len(rr)),
                         within25_pct=pct(c2.get("same", 0) + c2.get("other_lt25km", 0), len(rr))))
    sdf = pd.DataFrame(summ)
    sdf.to_csv(a.out_dir / "step3_accuracy_summary.csv", index=False, lineterminator="\n")
    no_place = df[df["outcome"] == "no_place"]["step3_status"].value_counts().to_dict()
    far = res_df[res_df["outcome"] == "other_ge25km"]["step3_place"].value_counts().head(10).to_dict()
    print(sdf.to_string(index=False))
    print("no place:", no_place)
    print("most frequent far places:", far)
    return 0


if __name__ == "__main__":
    sys.exit(main())
