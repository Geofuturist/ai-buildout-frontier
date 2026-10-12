r"""France, 18 regions (ADM1) — abf-fra v0.2.0, SPEC_FRA_layers_v0_1 r10 §11.

Run from the repo root, one layer at a time::

    python scripts\fra\build_regions_fra.py generation
    python scripts\fra\build_regions_fra.py consumption
    python scripts\fra\build_regions_fra.py transmission

Rules (SPEC_FRA §11):
- frame: the 18 FRA-1-* units of abf-boundaries-v0.1.0; unit_id = FRA-1-<INSEE region code>;
- inputs: the same files as the department layers of v0.1.0 (SHA-256 in the meta);
- the region total comes from the REGION field of the source, not from summing departments,
  so rows without a department code but with a region code are counted;
- selection rules, fields and units are those of the department layer of the same source;
- every region is cross-checked against the sum of its departments in the v0.1.0 CSV
  (data\fra\layer_<layer>_20261010.csv).
STOP (question to [ARCH]) if the source has no region field or its codes do not match the 18
FRA-1-* units.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fra_common import ADM2, OUT, PRIVATE, ROOT, dept_code, input_entry, write_layer  # noqa: E402

ADM1 = ADM2.with_name("adm1.parquet")
V010 = "20261010"                      # date of the v0.1.0 department layers
OVERSEAS_NOT_REGIONS = {"975", "977", "978"}   # excluded as in v0.1.0
UA = "ABF-observatory/0.1 (research; contact via project)"


# ------------------------------------------------------------------ common
def load_regions(geometry: bool = False):
    import geopandas as gpd
    g = gpd.read_parquet(ADM1)
    g = g[g["unit_id"].astype(str).str.startswith("FRA-1-")].copy()
    if len(g) != 18:
        sys.exit(f"СТОП: в наборе границ {len(g)} единиц FRA-1-*, ожидалось 18")
    g["code"] = g["unit_id"].str.replace("FRA-1-", "", regex=False)
    cols = ["unit_id", "code", "name"] + (["geometry"] if geometry else [])
    g = g.sort_values("unit_id")[cols].reset_index(drop=True)
    return g if geometry else pd.DataFrame(g)


def dept_to_region() -> pd.Series:
    """department code -> region code, from parent_id of the boundaries."""
    d = pd.read_parquet(ADM2, columns=["unit_id", "parent_id"])
    d = d[d["unit_id"].str.startswith("FRA-2-")]
    if len(d) != 101 or not d["parent_id"].str.startswith("FRA-1-").all():
        sys.exit("СТОП: в ADM2 Франции не у всех 101 департамента родитель FRA-1-*")
    return pd.Series(d["parent_id"].str[6:].values, index=d["unit_id"].str[6:].values)


def region_code(v) -> str | None:
    t = dept_code(v)
    return t.zfill(2) if t and t.isdigit() else t


def find_col(cols, *cands) -> str | None:
    def n(s):
        return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(s))
                      .encode("ascii", "ignore").decode().lower())
    m = {n(c): c for c in cols}
    return next((m[n(c)] for c in cands if n(c) in m), None)


def check_codes(found: set, regions: set, what: str) -> None:
    extra = sorted(found - regions)
    if extra:
        sys.exit(f"СТОП (вопрос [ARCH], SPEC_FRA §11): в источнике {what} коды региона вне 18 "
                 f"FRA-1-*: {extra}")


def dept_layer(layer: str) -> pd.DataFrame:
    p = OUT / f"layer_{layer}_{V010}.csv"
    if not p.exists():
        sys.exit(f"СТОП: нет слоя департаментов v0.1.0 {p} — нужен для сверки")
    return pd.read_csv(p, dtype={"unit_id": str})


def vs_departments(reg: pd.DataFrame, col: str, layer: str) -> pd.DataFrame:
    d = dept_layer(layer)
    d["region"] = d["unit_id"].str[6:].map(dept_to_region())
    s = pd.to_numeric(d[col], errors="coerce").groupby(d["region"]).sum(min_count=1)
    t = pd.DataFrame({"region": reg.set_index("code")[col].astype(float), "departments": s})
    t["diff"] = t["region"] - t["departments"]
    t["diff_pct"] = (t["diff"] / t["departments"] * 100).where(t["departments"] > 0)
    return t


def table(t: pd.DataFrame, unit: str) -> list[str]:
    rows = [f"| регион | итог региона, {unit} | сумма департаментов, {unit} | разница | % |",
            "|---|---|---|---|---|"]
    for k, r in t.iterrows():
        pct = "" if pd.isna(r["diff_pct"]) else f"{r['diff_pct']:.4f}"
        rows.append(f"| {k} | {r['region']:,.3f} | {r['departments']:,.3f} | {r['diff']:,.3f} | {pct} |")
    return rows


def breaks(values: pd.Series) -> list[float]:
    """Round class breaks from quartiles of the covered values (1–2 significant digits)."""
    v = values.dropna()
    v = v[v > 0]
    out = []
    for q in (0.2, 0.4, 0.6, 0.8):
        x = float(v.quantile(q))
        mag = 10 ** (len(str(int(x))) - 2) if x >= 100 else 1
        out.append(round(x / mag) * mag)
    return sorted(set(out))


# ------------------------------------------------------------------ generation
def generation() -> None:
    import build_generation_odre as g
    files = sorted(g.SRC_DIR.glob("registre-national-installation-production-stockage-electricite-agrege*.csv"))
    if not files:
        sys.exit(f"СТОП: нет CSV реестра в {g.SRC_DIR}")
    src = files[0]
    df = pd.read_csv(src, sep=";", dtype=str, encoding="utf-8-sig", low_memory=False)
    c_reg = find_col(df.columns, "codeRegion", "codeRégion", "code_region", "codeReg")
    if c_reg is None:
        sys.exit("СТОП (вопрос [ARCH], SPEC_FRA §11): в реестре нет поля кода региона. Колонки: "
                 + ", ".join(df.columns))
    # the operating rule of the department layer (build_generation_odre, approved by [RES])
    df["filiere"] = df["filiere"].map(lambda v: unicodedata.normalize("NFC", v.strip())
                                      if isinstance(v, str) else v)
    df["kw"] = pd.to_numeric(df["puisMaxInstallee"].str.replace(",", "."), errors="coerce")
    df["n"] = pd.to_numeric(df["nbInstallations"], errors="coerce")
    d_on = pd.to_datetime(df["dateMiseEnservice (format date)"], errors="coerce", format="%Y-%m-%d")
    d_off = pd.to_datetime(df["dateDeraccordement"], errors="coerce", dayfirst=True)
    df["operating"] = d_off.isna() & ~(d_on > g.SNAPSHOT) & ~df["regime"].eq("En retrait provisoire")
    df["storage"] = df["filiere"].eq(g.STORAGE_FILIERE)
    df["group"] = df["filiere"].map(g.GROUPS)
    df["dep"] = df["codeDepartement"].map(dept_code)
    df["reg"] = df[c_reg].map(region_code)

    frame = load_regions()
    codes = set(frame["code"])
    op = df[df["operating"]]
    op_other = op["dep"].isin(OVERSEAS_NOT_REGIONS)
    check_codes(set(op.loc[~op_other, "reg"].dropna()), codes, "реестра ODRÉ")
    # consistency: a row's region = region of its department
    d2r = dept_to_region()
    mism = op[~op_other & op["dep"].isin(d2r.index) & op["reg"].notna()]
    mism = mism[mism["reg"] != mism["dep"].map(d2r)]
    use = op[~op_other & op["reg"].isin(codes)]
    gen, sto = use[~use["storage"]], use[use["storage"]]

    agg = pd.DataFrame(index=sorted(codes))
    agg["installed_capacity_mw"] = gen.groupby("reg")["kw"].sum() / 1000
    agg["storage_capacity_mw"] = sto.groupby("reg")["kw"].sum() / 1000
    for grp, col in zip(("nuclear", "fossil", "hydro", "wind", "solar", "bioenergy", "other"),
                        g.GROUP_COLS):
        agg[col] = gen[gen["group"] == grp].groupby("reg")["kw"].sum() / 1000
    agg["n_installations"] = use.groupby("reg")["n"].sum()
    agg = agg.fillna(0.0)
    agg["n_installations"] = agg["n_installations"].astype(int)
    agg["data_snapshot_date"] = g.SNAPSHOT.strftime("%Y-%m-%d")
    out = frame.merge(agg, left_on="code", right_index=True, how="left")
    out["coverage_status"], out["coverage_note"] = "covered", ""

    gen_all = op[~op["storage"]]
    exc_other = gen_all[gen_all["dep"].isin(OVERSEAS_NOT_REGIONS)]
    exc_noreg = gen_all[~gen_all["dep"].isin(OVERSEAS_NOT_REGIONS) & gen_all["reg"].isna()]
    lhs = out["installed_capacity_mw"].sum() * 1000 + exc_other["kw"].sum() + exc_noreg["kw"].sum()
    rhs = gen_all["kw"].sum()
    ok = abs(lhs - rhs) < 1.0
    nodep = gen_all[gen_all["dep"].isna()]
    nodep_in = nodep[nodep["reg"].isin(codes)]
    t = vs_departments(out, "installed_capacity_mw", "generation_odre")
    # region − its departments = (rows with a region but no department)
    #                            − (rows with a department in the frame but no region)
    dep_noreg = gen_all[gen_all["dep"].isin(d2r.index) & gen_all["reg"].isna()]
    expect = ((nodep_in.groupby("reg")["kw"].sum() / 1000).reindex(t.index).fillna(0.0)
              - (dep_noreg.groupby(dep_noreg["dep"].map(d2r))["kw"].sum() / 1000)
              .reindex(t.index).fillna(0.0))
    region_ok = (t["diff"] - expect).abs().max() < 0.001

    rep = [f"# Сборка `energy_generation_odre_adm1` · {pd.Timestamp.today():%Y-%m-%d}\n",
           f"Вход: `{src.name}` ({g.EDITION}); поле региона — `{c_reg}`. Правило «действует» — как у "
           "слоя департаментов.\n",
           "## Проверки\n",
           f"- `totals_vs_source`: регионы {out['installed_capacity_mw'].sum() * 1000:,.1f} + коды 975/977/978 "
           f"{exc_other['kw'].sum():,.1f} ({len(exc_other)} строк) + без кода региона {exc_noreg['kw'].sum():,.1f} "
           f"({len(exc_noreg)} строк) = {lhs:,.1f} кВт; источник {rhs:,.1f} кВт — **{'OK' if ok else 'НЕ СХОДИТСЯ'}**;",
           f"- строк без кода департамента: {len(nodep)} ({nodep['kw'].sum() / 1000:,.1f} МВт); из них с кодом "
           f"региона и потому в регионах: {len(nodep_in)} ({nodep_in['kw'].sum() / 1000:,.1f} МВт);",
           f"- итог региона − сумма его департаментов = строки без департамента с кодом региона: "
           f"**{'OK' if region_ok else 'НЕ СХОДИТСЯ'}**;",
           f"- строк, где регион не совпадает с регионом департамента: {len(mism)} "
           f"({mism['kw'].sum() / 1000:,.1f} МВт);",
           f"- строк: {len(out)} (нужно 18); покрыто: 18.\n",
           "## Регионы против суммы департаментов v0.1.0, МВт\n"] + table(t, "МВт")
    vals = ["installed_capacity_mw", "storage_capacity_mw", *g.GROUP_COLS, "n_installations",
            "data_snapshot_date"]
    meta = {
        "source": "Registre national des installations de production et de stockage d'électricité "
                  "(agrégé), ODRÉ", "source_url": g.SOURCE_URL, "edition": g.EDITION,
        "current_through": g.SNAPSHOT.strftime("%Y-%m-%d"), "license": "Licence Ouverte v2.0 (Etalab)",
        "inputs": [input_entry(src)],
        "verification_method": (f"operating rule of energy_generation_odre_adm2; grouped by the region "
                                f"field '{c_reg}' of the register; codes 975/977/978 excluded"),
        "totals_vs_source": {"regions_kw": out["installed_capacity_mw"].sum() * 1000,
                             "excluded_975_977_978": {"rows": len(exc_other), "kw": exc_other["kw"].sum()},
                             "excluded_no_region": {"rows": len(exc_noreg), "kw": exc_noreg["kw"].sum()},
                             "source_kw": rhs, "ok": ok},
        "vs_departments": {"rows_without_department": len(nodep),
                           "of_which_with_region": len(nodep_in),
                           "mw_with_region": nodep_in["kw"].sum() / 1000, "ok": region_ok,
                           "region_mismatch_rows": len(mism)},
        "proposed_breaks_mw": breaks(out["installed_capacity_mw"]),
    }
    write_layer("generation_odre_adm1", out, vals, meta, rep)
    print("\n".join(rep[2:9]))
    print(f"Пороги (предложение): {meta['proposed_breaks_mw']}")
    if not (ok and region_ok):
        sys.exit("СТОП: проверка сумм не прошла")


# ------------------------------------------------------------------ consumption
def ore_region_dataset(c) -> Path | None:
    """Look for an Agence ORE 'par région' annual consumption dataset; download it if found."""
    dest_dir = c.SRC_DIR
    marker = dest_dir / "region_dataset.json"
    if marker.exists():
        info = json.loads(marker.read_text(encoding="utf-8"))
        return dest_dir / info["file"] if info.get("file") else None
    api = "https://opendata.agenceore.fr/data-fair/api/v1/datasets"
    rp = urllib.robotparser.RobotFileParser("https://opendata.agenceore.fr/robots.txt")
    try:
        rp.read()
    except Exception:  # noqa: BLE001
        rp = None

    def get(url, dest=None):
        if rp is not None and not rp.can_fetch(UA, url):
            print(f"  robots.txt запрещает {url}")
            return None
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}),
                                    timeout=300) as r:
            data = r.read()
        if dest:
            dest.write_bytes(data)
        return data

    hits = {}
    for q in ("consommation region", "consommation annuelle electricite region"):
        raw = get(f"{api}?q={urllib.parse.quote(q)}&size=100")
        for d in json.loads(raw or b"{}").get("results", []):
            t = unicodedata.normalize("NFKD", f"{d.get('id', '')} {d.get('title', '')}").encode(
                "ascii", "ignore").decode().lower()
            if "consommation annuelle" in t and "region" in t and "departement" not in t \
                    and "commune" not in t and "iris" not in t:
                hits[d["id"]] = d.get("title")
    print("Наборы «par région» у Agence ORE:", hits or "нет")
    info = {"searched": True, "hits": hits, "file": None}
    if hits:
        rid = sorted(hits)[0]
        get(f"{api}/{rid}/raw", dest_dir / f"{rid}.csv")
        get(f"{api}/{rid}", dest_dir / f"{rid}_meta.json")
        lic = Path.cwd() / "research" / "fra" / "licences"
        lic.mkdir(parents=True, exist_ok=True)
        get(f"https://opendata.agenceore.fr/datasets/{rid}", lic / f"agenceore_{rid}.html")
        info.update(id=rid, title=hits[rid], file=f"{rid}.csv")
    marker.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    return dest_dir / info["file"] if info["file"] else None


def consumption() -> None:
    import build_consumption_agenceore as c
    reg_file = ore_region_dataset(c)
    src = reg_file or (c.SRC_DIR / f"{c.DEPT_ID}.csv")
    mode = "region_dataset" if reg_file else "department_dataset_folded"
    df = pd.read_csv(src, sep=c.sniff_sep(src), dtype=str, encoding="utf-8-sig")
    col = {k: c.pick(df.columns, *v) for k, v in {
        "year": ("Année",), "energy": ("FILIERE",), "reg": ("Code Région",),
        "sector": ("CODE GRAND SECTEUR",), "value": ("Conso totale (MWh)",),
        "sites": ("Nb sites",)}.items()}
    if col["reg"] is None:
        sys.exit(f"СТОП (вопрос [ARCH], SPEC_FRA §11): в `{src.name}` нет поля кода региона. "
                 f"Колонки: {list(df.columns)}")
    if None in col.values():
        sys.exit(f"СТОП: не найдены колонки {[k for k, v in col.items() if v is None]} в {src.name}")
    df["year"] = pd.to_numeric(df[col["year"]], errors="coerce")
    el = df[df[col["energy"]].str.lower().str.contains("lec", na=False)].copy()
    year = int(el["year"].max())
    el = el[el["year"] == year].copy()
    el["reg"] = el[col["reg"]].map(region_code)
    el["v"] = pd.to_numeric(el[col["value"]].str.replace(",", "."), errors="coerce")
    el["sites"] = pd.to_numeric(el[col["sites"]].str.replace(",", "."), errors="coerce")
    el["sector"] = el[col["sector"]].map(c.SECTORS).fillna("unknown")

    frame = load_regions()
    codes = set(frame["code"])
    check_codes(set(el["reg"].dropna()), codes, f"`{src.name}`")
    noreg = el[el["reg"].isna()]
    agg = pd.DataFrame(index=sorted(codes))
    agg["consumption_mwh"] = el.groupby("reg")["v"].sum()
    for s, sc in zip(("residential", "tertiary", "industry", "agriculture", "unknown"), c.SECTOR_COLS):
        agg[sc] = el[el["sector"] == s].groupby("reg")["v"].sum()
    agg[["consumption_mwh", *c.SECTOR_COLS]] = agg[["consumption_mwh", *c.SECTOR_COLS]].fillna(0.0)
    agg["n_delivery_points"] = el.groupby("reg")["sites"].sum().reindex(agg.index).fillna(0).astype(int)
    agg["n_rows_without_value"] = (el[el["v"].isna()].groupby("reg").size()
                                   .reindex(agg.index).fillna(0).astype(int))
    agg["data_year"] = year
    out = frame.merge(agg, left_on="code", right_index=True, how="left")
    out["coverage_status"], out["coverage_note"] = "covered", ""

    file_sum, lay_sum = el["v"].sum(), out["consumption_mwh"].sum()
    ok = abs(file_sum - lay_sum) < 1.0
    t = vs_departments(out, "consumption_mwh", "consumption_agenceore")
    over = t[t["diff_pct"].abs() > 1.0]
    rep = [f"# Сборка `energy_consumption_agenceore_adm1` · {pd.Timestamp.today():%Y-%m-%d}\n",
           f"Вход: `{src.name}` ({'набор по регионам' if reg_file else 'набор по департаментам, свёрнут по коду региона'}); "
           f"электричество, {year}; поле региона — `{col['reg']}`.\n",
           "## Проверки\n",
           f"- `totals_vs_source` (сумма файла): файл {file_sum:,.1f}, слой {lay_sum:,.1f} МВт·ч, строк без кода "
           f"региона {len(noreg)} — **{'OK' if ok else 'НЕ СХОДИТСЯ'}**;",
           f"- регионов, где итог отличается от суммы департаментов больше чем на 1%: **{len(over)}**"
           + (f" ({', '.join(over.index)}) — вопрос [ARCH] до сдачи" if len(over) else "") + ";",
           f"- строк «регион × сектор» без значения: {int(agg['n_rows_without_value'].sum())};",
           f"- строк: {len(out)} (нужно 18); покрыто: 18.\n",
           "## Регионы против суммы департаментов v0.1.0, МВт·ч\n"] + table(t, "МВт·ч")
    vals = ["consumption_mwh", *c.SECTOR_COLS, "n_delivery_points", "n_rows_without_value", "data_year"]
    meta = {
        "source": "Agence ORE — " + ("annual consumption by region" if reg_file else
                                     "Consommation annuelle d'électricité et gaz par département, "
                                     "folded by region code"),
        "source_url": c.SOURCE_URL if not reg_file else
        f"https://opendata.agenceore.fr/datasets/{src.stem}",
        "mode": mode, "edition": f"data year {year}", "current_through": f"{year}-12-31",
        "license": "Licence Ouverte / Open Licence (Agence ORE)", "inputs": [input_entry(src)],
        "verification_method": f"electricity rows, year {year}, summed by '{col['reg']}'",
        "totals_vs_source": {"file_mwh": file_sum, "layer_mwh": lay_sum, "rows_without_region": len(noreg),
                             "ok": ok},
        "vs_departments": {"max_abs_diff_pct": float(t["diff_pct"].abs().max()),
                           "regions_over_1pct": list(over.index)},
        "proposed_breaks_mwh": breaks(out["consumption_mwh"]),
    }
    write_layer("consumption_agenceore_adm1", out, vals, meta, rep)
    print("\n".join(rep[1:7]))
    print(f"Пороги (предложение): {meta['proposed_breaks_mwh']}")
    if not ok:
        sys.exit("СТОП: totals_vs_source не сходится")
    if len(over):
        sys.exit("СТОП: расхождение с департаментами больше 1% — вопрос [ARCH] (SPEC_FRA §11)")


# ------------------------------------------------------------------ transmission
def transmission() -> None:
    import geopandas as gpd
    import build_transmission_rte as tr
    seg_files = sorted((PRIVATE / "rte_lines_segments").glob("rte_lines_segments_ddtm2023_*.gpkg"))
    if not seg_files:
        sys.exit("СТОП: нет сегментов на D:\\ — сначала build_transmission_rte.py")
    seg_path = seg_files[-1]
    seg = gpd.read_file(seg_path, layer="segments").to_crs(2154)
    oper = seg[seg["state"].eq("EN EXPLOITATION")]
    not_cov = {"94", "01", "02", "03", "04", "06"}
    frame = load_regions(geometry=True).to_crs(2154)
    inter = gpd.overlay(oper[["voltage_band", "voltage_kv", "geometry"]], frame[["code", "geometry"]],
                        how="intersection", keep_geom_type=True)
    inter["km"] = inter.length / 1000
    piv = inter.pivot_table(index="code", columns="voltage_band", values="km", aggfunc="sum",
                            fill_value=0.0)
    for b in tr.BANDS:
        if b not in piv:
            piv[b] = 0.0
    out = pd.DataFrame(frame.drop(columns="geometry"))
    out = out.merge(piv[tr.BANDS].add_prefix("km_"), left_on="code", right_index=True, how="left")
    km_cols = [f"km_{b}" for b in tr.BANDS]
    out[km_cols] = out[km_cols].fillna(0.0)
    out["km_total"] = out[km_cols].sum(axis=1)
    out["max_voltage_kv"] = out["code"].map(inter.groupby("code")["voltage_kv"].max())
    out["has_any_line"] = out["km_total"] > 0
    out["frac_km_unknown_voltage"] = (out["km_unknown"] / out["km_total"]).where(out["km_total"] > 0)
    nc = out["code"].isin(not_cov)
    lines_in_nc = float(out.loc[nc, "km_total"].sum())
    out["coverage_status"] = ["not_covered" if x else "covered" for x in nc]
    out["coverage_note"] = [tr.NOT_COVERED_NOTE if x else "" for x in nc]
    vals = ["km_total", *km_cols, "max_voltage_kv", "has_any_line", "frac_km_unknown_voltage"]
    out[vals] = out[vals].astype(object)
    out.loc[nc, vals] = None

    km_reg = float(pd.to_numeric(out["km_total"], errors="coerce").sum())
    d = dept_layer("transmission_rte")
    km_dep = float(pd.to_numeric(d["km_total"], errors="coerce").sum())
    diff = abs(km_reg - km_dep) / km_dep * 100
    ok = diff <= 0.01
    t = vs_departments(out.assign(km_total=pd.to_numeric(out["km_total"], errors="coerce")),
                       "km_total", "transmission_rte")
    rep = [f"# Сборка `energy_transmission_rte_adm1` · {pd.Timestamp.today():%Y-%m-%d}\n",
           f"Вход: сегменты `{seg_path.name}` (не публикуются), собраны build_transmission_rte.py из копии "
           f"DDTM (данные на 30.06.2023); в эксплуатации {len(oper):,} сегментов.\n",
           "## Проверки\n",
           f"- сумма `km_total` по регионам {km_reg:,.1f} км; по департаментам v0.1.0 {km_dep:,.1f} км; "
           f"расхождение {diff:.4f}% (допуск 0,01%) — **{'OK' if ok else 'НЕ СХОДИТСЯ'}**;",
           f"- покрыто регионов: {int((~nc).sum())} (нужно 12); км в не покрытых (должно быть 0): {lines_in_nc:,.1f};",
           f"- строк: {len(out)} (нужно 18).\n",
           "## Регионы против суммы департаментов v0.1.0, км\n"] + table(t, "км")
    meta = {
        "source": "RTE — Lignes aériennes / souterraines RTE, copy published by DDTM de l'Eure "
                  "(data at 30.06.2023)", "source_url": tr.DDTM_URLS,
        "edition": "data at 2023-06-30 (DDTM 27 copy)", "current_through": "2023-06-30",
        "license": "Licence Ouverte v2.0 (lov2)",
        "inputs": [input_entry(z) for z in sorted(tr.SRC_DIR.glob("*.zip"))],
        "derived_input_not_published": {"file": seg_path.name, "sha256": input_entry(seg_path)["sha256"]},
        "verification_method": "segments of energy_transmission_rte_adm2 (etat = 'EN EXPLOITATION') "
                               "clipped to FRA ADM1 in EPSG:2154; length inside each region",
        "totals_vs_source": {"km_regions": km_reg, "km_departments_v010": km_dep, "diff_pct": diff,
                             "tolerance_pct": 0.01, "ok": ok},
        "proposed_breaks_km": breaks(pd.to_numeric(out.loc[~nc, "km_total"], errors="coerce")),
    }
    write_layer("transmission_rte_adm1", out, vals, meta, rep)
    print("\n".join(rep[3:6]))
    print(f"Пороги (предложение): {meta['proposed_breaks_km']}")
    if not ok or lines_in_nc > 0:
        sys.exit("СТОП: проверка не прошла")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"generation": generation, "consumption": consumption, "transmission": transmission}.get(
        cmd, lambda: sys.exit("Использование: build_regions_fra.py generation | consumption | transmission"))()
