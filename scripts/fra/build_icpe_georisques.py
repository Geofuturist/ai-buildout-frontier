r"""Layer dc_icpe_georisques (SPEC_FRA_layers_v0_1 r4 §6; RES_to_CODE_FRA_preflight_answers_v1 §4;
PROTOCOL_agent_recheck_icpe_fra_v1).

Two steps, run from the repo root::

    python scripts\fra\build_icpe_georisques.py select
        -> research\fra\icpe_candidates.csv            (all candidates + rejected sample, working file)
        -> research\fra\agent_recheck_icpe_fra.xlsx    (file for [VER-FRA], protocol §1)

    python scripts\fra\build_icpe_georisques.py apply research\fra\agent_recheck_icpe_fra_done.xlsx
        -> data\fra\layer_icpe_georisques_<date>.csv (+ .geojson, meta, report)

Selection ([RES] §4.1), names compared without case and accents:
  A  name contains data center / datacenter / data centre / datacentre / centre(s) de données
     -> candidate, any NAF;
  B  operator with DC as core business (data\fra\rules\dc_operators.csv, profile B)
     -> candidate if NAF empty or in divisions 61-63;
  C  mixed-profile operator (profile C) -> candidate only if the name has a DC marker
     (DC + number, «data», «hébergement»);
  rejected sample: 10 random records (seed SEED, see rule_changes.csv) from «NAF 62/63 or operator C» not selected.
An operator without a source_url is not used (P10).

Apply: agree = yes -> in the layer; no / unclear -> out, kept in icpe_candidates.csv with the
reason; MISSED in the rejected sample -> STOP (fix the rule, select again).

P9: only the whitelist below is written. Rubriques, regime, Seveso, equipment, inspection acts are
never read into an output, a report or the agent file.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fra_common import OUT, RES, ROOT, dept_code, input_entry, load_frame, rules_file  # noqa: E402

LAYER = "icpe_georisques"
SRC = ROOT / "georisques_icpe" / "result.csv"
# rule tables: data\fra\rules\ (in git, SPEC_FRA r5 §6 p.4); working files stay in research\fra\
OPERATORS = rules_file("dc_operators.csv")
AGENT_FILE = RES / "agent_recheck_icpe_fra.xlsx"
CANDIDATES = RES / "icpe_candidates.csv"
SITES = rules_file("dc_sites.csv")         # rule D ([RES] 10.10)
RULE_CHANGES = rules_file("rule_changes.csv")
# published column selection_rule (SPEC_FRA r6 §6): internal rule letter -> public value.
# C is the same operator list (mixed-profile operators, name with a DC marker).
SELECTION_RULE = {"A": "name", "B": "operator_list", "C": "operator_list", "D": "site_list"}
SCRIPT = "script:build_icpe_georisques"
READ_COLS = ["code_aiot", "nom_ets", "cd_insee", "num_dep", "commune", "code_naf", "x", "y",
             "code_epsg", "url_fiche"]          # P9: nothing else is read
NAME_A = re.compile(r"data ?cent(?:er|re)s?|centres? de donnees")
DC_MARK = re.compile(r"\bdc ?\d+|\bdata|hebergement")
# rejected-sample seed; changes are logged in data\fra\rules\rule_changes.csv
# (10.10: 20261010 -> 20261011 after OVHcloud C->B, [RES])
SEED = 20261011        # round n uses SEED + n - 1 (round 2 -> 20261012)
AGENT_COLS = ["agree", "agent_reason", "agent_is_dc", "agent_evidence_url", "agent_address_card",
              "agent_address_public", "agent_note"]


def plain(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9& ]", " ", s)).strip()


def naf2(v) -> str:
    t = re.sub(r"\.0+$", "", str(v)).strip()
    return t.zfill(2) if t.isdigit() else ""


def load() -> pd.DataFrame:
    if not SRC.exists():
        sys.exit(f"СТОП: нет {SRC}")
    df = pd.read_csv(SRC, sep=None, engine="python", dtype=str, usecols=lambda c: c in READ_COLS,
                     encoding="utf-8-sig")
    miss = [c for c in READ_COLS if c not in df.columns]
    if miss:
        sys.exit(f"СТОП: в выгрузке нет колонок {miss}")
    df["name_plain"] = df["nom_ets"].map(plain)
    df["naf"] = df["code_naf"].map(naf2)
    return df


def resolve_agent_sources(t: pd.DataFrame) -> pd.DataFrame:
    """source_url «agent:<AIOT>» -> agent_evidence_url of that record from an earlier round."""
    prev = previous_answers().drop_duplicates("record_id", keep="last").set_index("record_id")
    def res(u):
        if not str(u).startswith("agent:"):
            return u
        rid = str(u).split(":", 1)[1].zfill(10)
        return prev.loc[rid, "agent_evidence_url"] if rid in prev.index else ""
    t = t.copy()
    t["source_url"] = t["source_url"].map(res)
    return t


def operators() -> pd.DataFrame:
    op = resolve_agent_sources(pd.read_csv(OPERATORS, dtype=str).fillna(""))
    op = op[op["source_url"].str.startswith("http")]      # P10: no link -> not used
    return op


def classify(df: pd.DataFrame, op: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rule"], df["operator"], df["operator_source_url"] = "", "", ""
    a = df["name_plain"].str.contains(NAME_A)
    df.loc[a, "rule"] = "A"
    in_c_pool = pd.Series(False, index=df.index)
    for _, o in op.iterrows():
        m = df["name_plain"].str.contains(o["pattern"], regex=True)
        if o["profile"] == "B":
            sel = m & (df["naf"].eq("") | df["naf"].isin(["61", "62", "63"]))
        else:
            in_c_pool |= m
            sel = m & df["name_plain"].str.contains(DC_MARK)
        hit = sel & df["operator"].eq("")
        df.loc[hit, "operator"] = o["operator"]
        df.loc[hit, "operator_source_url"] = o["source_url"]
        df.loc[hit & df["rule"].eq(""), "rule"] = o["profile"]
    df["pool_rejected"] = (df["rule"].eq("") & (df["naf"].isin(["62", "63"]) | in_c_pool))
    return df


def previous_answers() -> pd.DataFrame:
    """All earlier agent rounds (research\fra\agent_recheck_icpe_fra_round*_done.xlsx)."""
    files = sorted(RES.glob("agent_recheck_icpe_fra_round*_done.xlsx"))
    parts = []
    for f in files:
        a = pd.read_excel(f, sheet_name="records", dtype=str).fillna("")
        a["round"] = re.search(r"round(\d+)", f.name).group(1)
        parts.append(a)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["record_id", "rule", "round", *AGENT_COLS])


def select(final: bool = False) -> None:
    """final=True ([RES] 10.10: no further round): rebuild the candidate list with the current
    rules and carried verdicts, no new rejected sample."""
    df = classify(load(), operators())
    df["record_id"] = df["code_aiot"].str.zfill(10)
    # rule D: listed sites (operator + commune + AIOT) with a public source
    sites = pd.read_csv(SITES, dtype=str).fillna("")
    sites = resolve_agent_sources(sites)
    sites = sites[sites["source_url"].str.startswith("http")]
    sites["record_id"] = sites["aiot"].str.zfill(10)
    d = df["record_id"].isin(sites["record_id"]) & df["rule"].eq("")
    df.loc[d, "rule"] = "D"
    smap = sites.set_index("record_id")
    df.loc[d, "operator"] = df.loc[d, "record_id"].map(smap["operator"])
    df.loc[d, "operator_source_url"] = df.loc[d, "record_id"].map(smap["source_url"])
    df.loc[d, "pool_rejected"] = False

    prev = previous_answers()
    rnd = int(prev["round"].max()) + (0 if final else 1) if len(prev) else 1
    checked = set(prev["record_id"])
    cand = df[df["rule"].ne("")]
    pool = df[df["pool_rejected"]]
    fresh_pool = pool[~pool["record_id"].isin(checked)]
    sample = fresh_pool.iloc[0:0] if final else fresh_pool.sample(
        n=min(10, len(fresh_pool)), random_state=SEED + rnd - 1)
    rows = pd.concat([cand, sample.assign(rule="rejected_sample")])

    agent = pd.DataFrame({
        "record_id": rows["record_id"], "name_public": rows["nom_ets"],
        "commune": rows["commune"], "dept": rows["num_dep"].map(dept_code),
        "card_url": rows["url_fiche"], "rule": rows["rule"], "operator": rows["operator"],
        "operator_source_url": rows["operator_source_url"]})
    for c in AGENT_COLS:
        agent[c] = ""
    # carry earlier verdicts ([RES] 10.10): a candidate already checked keeps its answer; a
    # record confirmed as MISSED in a rejected sample becomes a candidate with agree = yes
    last = prev.drop_duplicates("record_id", keep="last").set_index("record_id")
    for i, r in agent.iterrows():
        if r["rule"] != "rejected_sample" and r["record_id"] in last.index:
            p = last.loc[r["record_id"]]
            for c in AGENT_COLS:
                agent.at[i, c] = p[c]
            if str(p["agent_reason"]).upper() == "MISSED":
                agent.at[i, "agree"], agent.at[i, "agent_reason"] = "yes", "MISSED->candidate"
    agent["round"] = [str(rnd) if a == "" else last.loc[rid, "round"] if rid in last.index else str(rnd)
                      for a, rid in zip(agent["agree"], agent["record_id"])]

    RES.mkdir(parents=True, exist_ok=True)
    todo = agent[agent["agree"].eq("")]
    round_file = RES / f"agent_recheck_icpe_fra_round{rnd}{'_final_todo' if final else ''}.xlsx"
    if len(todo):
        todo.drop(columns="round").to_excel(round_file, sheet_name="records", index=False)
    agent.to_excel(RES / "agent_recheck_icpe_fra_all.xlsx", sheet_name="records", index=False)
    agent.drop(columns=AGENT_COLS).assign(naf=rows["naf"].values).to_csv(
        CANDIDATES, index=False, encoding="utf-8-sig")
    print(f"Раунд {rnd}. Кандидатов: {len(cand)} (" + ", ".join(
        f"{k} {int((cand['rule'] == k).sum())}" for k in "ABCD") + f"); пул отклонённых {len(pool)} "
          f"(не проверенных {len(fresh_pool)}), в новой выборке {len(sample)} (зерно {SEED + rnd - 1}).")
    print(f"С ответом из прошлых раундов: {int(agent['agree'].ne('').sum())}; агенту сейчас: {len(todo)}.")
    print(f"Файл для агента: {round_file}" if len(todo) else "Агенту ничего не нужно — можно apply.")
    print(todo[["record_id", "name_public", "dept", "rule", "operator"]].to_string(index=False))


def to_lonlat(df: pd.DataFrame, frame_geom) -> pd.DataFrame:
    """Per-record EPSG -> WGS84; points outside every French department (2 km) -> none."""
    import geopandas as gpd
    from shapely.geometry import Point
    out = []
    for epsg, g in df.groupby("code_epsg"):
        x, y = pd.to_numeric(g["x"], errors="coerce"), pd.to_numeric(g["y"], errors="coerce")
        pts = gpd.GeoSeries([Point(a, b) if pd.notna(a) and pd.notna(b) and (a, b) != (0, 0)
                             else None for a, b in zip(x, y)], index=g.index, crs=int(epsg))
        out.append(pts.to_crs(4326))
    s = gpd.GeoSeries(pd.concat(out).sort_index(), crs=4326)
    inside = s.to_crs(2154).within(frame_geom.buffer(2000))
    res = pd.DataFrame(index=df.index)
    res["lon"] = [p.x if p is not None and ok else None for p, ok in zip(s, inside)]
    res["lat"] = [p.y if p is not None and ok else None for p, ok in zip(s, inside)]
    res["coord_precision"] = ["city" if v is not None else "none" for v in res["lon"]]
    return res


def apply() -> None:
    """Merge every *_done round into the full list; build the layer."""
    allf = RES / "agent_recheck_icpe_fra_all.xlsx"
    ag = pd.read_excel(allf, sheet_name="records", dtype=str).fillna("")
    prev = previous_answers().drop_duplicates("record_id", keep="last").set_index("record_id")
    for i, r in ag.iterrows():
        if r["agree"] == "" and r["record_id"] in prev.index:
            for c in AGENT_COLS:
                ag.at[i, c] = prev.loc[r["record_id"], c]
    last_round = ag["round"].max()
    missed = ag[(ag["rule"] == "rejected_sample") & (ag["round"] == last_round)
                & (ag["agent_reason"].str.upper() == "MISSED")]
    # a MISSED in the last sample stops the build unless [RES] decided to publish the layer as a
    # lower bound: then rule_changes.csv holds a row «accept MISSED <AIOT>» (no new round)
    rc = pd.read_csv(RULE_CHANGES, dtype=str).fillna("")
    accepted = {m for ch in rc["change"] for m in re.findall(r"accept MISSED (\d+)", ch)}
    open_missed = [r for r in missed["record_id"] if r.lstrip("0") not in {a.lstrip("0") for a in accepted}]
    if open_missed:
        sys.exit("СТОП (протокол, приложение): в последней выборке пропуски (MISSED) — исправить правило "
                 f"и повторить select, или решение [RES] «accept MISSED <AIOT>» в rule_changes.csv: {open_missed}")
    todo = ag[(ag["rule"] != "rejected_sample") & ag["agree"].eq("")]
    if len(todo):
        sys.exit(f"СТОП: у {len(todo)} кандидатов нет ответа агента: {todo['record_id'].tolist()}")
    cand = ag[ag["rule"] != "rejected_sample"]
    keep_ids = set(cand.loc[cand["agree"].str.lower() == "yes", "record_id"])
    path = allf

    df = load()
    df["record_id"] = df["code_aiot"].str.zfill(10)
    lay = df[df["record_id"].isin(keep_ids)].copy()
    rule_of = cand.drop_duplicates("record_id", keep="last").set_index("record_id")["rule"]
    lay["selection_rule"] = lay["record_id"].map(rule_of).map(SELECTION_RULE)
    if lay["selection_rule"].isna().any():
        bad = lay.loc[lay["selection_rule"].isna(), "record_id"].tolist()
        sys.exit(f"СТОП: у записей нет правила отбора A/B/C/D: {bad}")
    frame = load_frame(geometry=True).to_crs(2154)
    lay = lay.join(to_lonlat(lay, frame.union_all()))
    lay["unit_id"] = "FRA-2-" + lay["num_dep"].map(dept_code).fillna(
        lay["cd_insee"].map(lambda v: str(v).zfill(5)[:3] if str(v).startswith("97") else str(v).zfill(5)[:2]))
    out = pd.DataFrame({
        "record_id": lay["record_id"], "name_public": lay["nom_ets"],
        "commune_insee": lay["cd_insee"], "unit_id": lay["unit_id"], "naf_code": lay["naf"],
        "selection_rule": lay["selection_rule"],
        "lon": lay["lon"], "lat": lay["lat"], "coord_source": "georisques",
        "coord_precision": lay["coord_precision"], "ref": lay["url_fiche"],
        "checked_at": dt.date.today().isoformat(), "checked_by": SCRIPT})
    rej = cand[cand["agree"].str.lower() != "yes"]
    c = pd.read_csv(CANDIDATES, dtype=str)
    c = c.merge(ag[["record_id"] + AGENT_COLS], on="record_id", how="left")
    c.to_csv(CANDIDATES, index=False, encoding="utf-8-sig")

    date = dt.date.today().strftime("%Y%m%d")
    OUT.mkdir(parents=True, exist_ok=True)
    csv = OUT / f"layer_{LAYER}_{date}.csv"
    out.sort_values("record_id").to_csv(csv, index=False, encoding="utf-8")
    import geopandas as gpd
    g = gpd.GeoDataFrame(out, geometry=gpd.points_from_xy(out["lon"], out["lat"]), crs=4326)
    g.to_file(OUT / f"layer_{LAYER}_{date}.geojson", driver="GeoJSON")
    from math import sqrt
    allp = previous_answers()
    last_r = allp["round"].max()
    s2 = allp[(allp["rule"] == "rejected_sample") & (allp["round"] == last_r)]
    k2, n2 = int((s2["agent_reason"].str.upper() == "MISSED").sum()), len(s2)
    u2 = int((s2["agree"].str.lower() == "unclear").sum())
    z = 1.96
    if n2:
        ph = k2 / n2
        den = 1 + z * z / n2
        mid = (ph + z * z / (2 * n2)) / den
        half = z * sqrt(ph * (1 - ph) / n2 + z * z / (4 * n2 * n2)) / den
        lo, hi = max(0.0, mid - half), min(1.0, mid + half)
    else:
        lo = hi = None
    smp = allp[allp["rule"] == "rejected_sample"].drop_duplicates("record_id", keep="last")  # all rounds
    n_samples, n_missed = len(smp), int((smp["agent_reason"].str.upper() == "MISSED").sum())
    # pool as drawn from: current pool + records that left it after a rule change (MISSED)
    cls = classify(df, operators())
    cls["record_id"] = cls["code_aiot"].str.zfill(10)
    pool_now = cls[cls["pool_rejected"]]
    sites_ids = set(pd.read_csv(SITES, dtype=str)["aiot"].str.zfill(10)) if SITES.exists() else set()
    pool_now = pool_now[~pool_now["record_id"].isin(sites_ids)]
    # One denominator everywhere (SPEC_FRA r5 §6 p.6): the rejected pool = records the FINAL rules
    # leave out within «NAF 62/63 or operator C». Records found MISSED became candidates and are no
    # longer in it. pool = checked_in_pool + unchecked.
    in_pool_checked = pool_now["record_id"].isin(set(smp["record_id"]))
    n_pool = len(pool_now)
    n_checked_in_pool = int(in_pool_checked.sum())
    n_unchecked = n_pool - n_checked_in_pool
    meta = {
        "layer": f"dc_{LAYER}", "snapshot_date": date, "rows": len(out),
        "source": "Géorisques — installations classées pour la protection de l'environnement (ICPE)",
        "source_url": "https://www.georisques.gouv.fr/donnees/bases-de-donnees/installations-industrielles",
        "license": "etalab-2.0", "publication_mode": "open_licence",
        "rights_basis": {"type": "license", "text": (
            "The Géorisques site states that, unless otherwise indicated, all its content is under "
            "Licence Ouverte 2.0 (etalab-2.0); the ICPE download page states no other terms."),
            "checked_by": "human:V"},
        "inputs": [input_entry(SRC), input_entry(OPERATORS), input_entry(SITES), input_entry(RULE_CHANGES),
                   input_entry(path)],
        "script_rules": "A/B/C (RES_to_CODE_FRA_preflight_answers_v1 §4.1) + D (site list "
                        "data/fra/rules/dc_sites.csv, [RES] 10.10); changes: data/fra/rules/rule_changes.csv",
        "verification_method": (
            "A record is confirmed when the operator publicly states a data center in the same commune "
            "and the address matches, or the operator has a single site there, or the register name "
            "itself says data center."),
        "verification": {"agent": "agent:VER-FRA",
                         "sample_share": {"candidates": 1.0,
                                          "rejected": round(n_checked_in_pool / n_pool, 4) if n_pool else None},
                         "rejected_pool_definition": (
                             "records left out by the final rules among those with NAF division 62 or 63 "
                             "or a mixed-profile operator name; records found to be data centers in a "
                             "sample were added by rule and are not in the pool"),
                         "rejected_pool_size": n_pool, "rejected_checked_in_pool": n_checked_in_pool,
                         "rejected_unchecked": n_unchecked,
                         "sampled_all_rounds": n_samples, "sampled_missed_moved_to_rules": n_missed,
                         "miss_estimate_last_sample": {
                             "round": last_r, "missed": k2, "checked": n2, "unclear": u2,
                             "wilson95": [round(lo, 3), round(hi, 3)] if lo is not None else None,
                             "unchecked_pool": n_unchecked,
                             "records_low_high": [round(lo * n_unchecked), round(hi * n_unchecked)]
                             if lo is not None else None,
                             "note": "lower estimate of the share: unclear records counted as not DC"
                             if u2 else ""}},
        "candidates": len(cand), "published": len(out), "rejected_by_agent": len(rej),
        "coord_precision": out["coord_precision"].value_counts().to_dict(),
        "known_gaps_draft": [  # [RES] 10.10; numbers of the second sample filled by the build
            "Data centers are selected from the register by name, by a list of data-center "
            "operators, and by a list of sites named in public operator documents; every selected "
            "record was confirmed by an independent agent check. Two random samples of 10 records "
            "left out by the rules found 3 and then 1 data centers; after each sample the sites found "
            f"were added. On the second sample, between {lo:.0%} and {hi:.0%} (95% interval) of the "
            f"{n_unchecked} unchecked left-out records may be data centers, so the layer is a lower "
            "bound of the data centers in the register.",
            "For one listed installation (Digital Realty MRS3, Marseille) the register card shows "
            "\"en fin d'exploitation\".",
            "The extract does not state the status of the installation.",
            "Coordinates are those of the register; their precision is not stated, so all points are "
            "marked city-level.",
        ],
    }
    import json
    (OUT / f"layer_{LAYER}_{date}_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Опубликовано: {len(out)} из {len(cand)}; не подтверждено агентом: {len(rej)}.")
    print("selection_rule: " + ", ".join(f"{k} {v}" for k, v in out["selection_rule"].value_counts().items()))
    print(f"Отклонённые: пул {n_pool}, проверено в пуле {n_checked_in_pool}, не проверено {n_unchecked}, "
          f"sample_share {n_checked_in_pool / n_pool:.4f}" if n_pool else "Отклонённые: пул пуст")
    if lo is not None:
        print(f"Оценка пропусков: {lo:.1%}–{hi:.1%} -> {round(lo * n_unchecked)}–{round(hi * n_unchecked)} записей")
    print(f"CSV: {csv}")


def pin_sources() -> None:
    r"""Replace «agent:<AIOT>» in the rule tables by the agent's evidence URL, so the tables in
    data\fra\rules\ stand on their own without research\ (SPEC_FRA r5 §6 p.4)."""
    prev = previous_answers().drop_duplicates("record_id", keep="last").set_index("record_id")
    for path in (OPERATORS, SITES):
        t = pd.read_csv(path, dtype=str).fillna("")
        n = 0
        for i, u in t["source_url"].items():
            if not u.startswith("agent:"):
                continue
            rid = u.split(":", 1)[1].zfill(10)
            url = prev.loc[rid, "agent_evidence_url"] if rid in prev.index else ""
            if not str(url).startswith("http"):
                sys.exit(f"СТОП: у записи {rid} нет agent_evidence_url в файлах агента ({path.name})")
            t.at[i, "source_url"] = url
            if "note" in t.columns:
                t.at[i, "note"] = (t.at[i, "note"] + f"; pinned from agent:{rid}, [VER-FRA] round "
                                   f"{prev.loc[rid, 'round']}").lstrip("; ")
            n += 1
        t.to_csv(path, index=False, encoding="utf-8")
        print(f"{path.name}: заменено ссылок agent: -> URL: {n}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "select":
        select(final="--final" in sys.argv)
    elif len(sys.argv) >= 2 and sys.argv[1] == "pin-sources":
        pin_sources()
    elif len(sys.argv) >= 2 and sys.argv[1] == "apply":
        apply()
    else:
        sys.exit("Использование: build_icpe_georisques.py select [--final] | pin-sources | apply")
