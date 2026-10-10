r"""Pre-flight for the France layers (SPEC_FRA_layers_v0_1 r2, §9). Reads only, builds nothing.

Run from the repo root, after V has put F1-F3 in place and after download_fra.py::

    python scripts\fra\preflight_fra.py

Writes:
  research\fra\preflight_fra.md          - the report (sections = SPEC_FRA §9 items 1-8)
  research\fra\preflight_fra.json        - the numbers
  research\fra\icpe_candidates.csv       - every ICPE record caught by any selection rule
                                           (working file, never published - SPEC_FRA §6)
  research\fra\licences\<source>.txt     - licence paragraphs cut by code from the raw HTML

Column names of the sources are not hard-coded: each field is looked up by a list of
candidate names, and the report says which column was used (or that none was found -
then the section lists all columns so the rule can be fixed before the build).

P9: ICPE classification headings (rubriques), regime letters, volumes and equipment are
never printed - only the names of such columns, so CODE-PUB knows what to drop.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(r"D:\GISData\Energy\France")
SRC = {"F1": ROOT / "odre_registre", "F2": ROOT / "odre_rte_lignes",
       "F3": ROOT / "georisques_icpe", "ORE": ROOT / "agenceore_consommation",
       # fallback for F2 (SPEC_FRA §5): DDTM de l'Eure copy on data.gouv.fr, 30.06.2023
       "F2b": ROOT / "ddtm27_rte_lignes"}
ADM2 = Path(r"D:\GISData\Boundaries\out\abf-boundaries-v0.1.0\display\adm2.parquet")
REPO = Path.cwd()
RES = REPO / "research" / "fra"
LIC = RES / "licences"
ORE_DEPT_ID = "6l33py6xpnaolvzkckzkhcic"  # «Consommation annuelle d'électricité et gaz par département»
DATA_EXT = {".csv", ".parquet", ".geoparquet", ".zip", ".json", ".geojson", ".xlsx", ".txt"}

md: list[str] = []
num: dict = {}


# ------------------------------------------------------------------ helpers
def h(t: str, lvl: int = 2) -> None:
    md.append(f"\n{'#' * lvl} {t}\n")


def table(df: pd.DataFrame, max_rows: int = 60) -> None:
    if df is None or df.empty:
        md.append("_нет строк_\n")
        return
    df = df.head(max_rows)
    md.append("| " + " | ".join(map(str, df.columns)) + " |")
    md.append("|" + "---|" * len(df.columns))
    for _, r in df.iterrows():
        cells = []
        for v in r:
            if isinstance(v, float):
                cells.append("" if pd.isna(v) else f"{v:,.1f}")
            else:
                cells.append(str(v).replace("|", "/").replace("\n", " ")[:80])
        md.append("| " + " | ".join(cells) + " |")
    md.append("")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def pick(df: pd.DataFrame, *cands: str) -> str | None:
    """First column whose normalized name equals, then contains, a candidate."""
    cols = {norm(c): c for c in df.columns}
    for c in cands:
        if norm(c) in cols:
            return cols[norm(c)]
    for c in cands:
        if len(norm(c)) < 4:  # short names ('x', 'id', 'nom'): exact match only
            continue
        for k, v in cols.items():
            if norm(c) in k:
                return v
    return None


def sha256(p: Path) -> str:
    hh = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            hh.update(chunk)
    return hh.hexdigest()


def read_csv_any(src, **kw) -> pd.DataFrame:
    """CSV with unknown separator and encoding (ODRÉ uses ';')."""
    raw = src.read() if hasattr(src, "read") else Path(src).read_bytes()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = raw[:20000].decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sep = max([";", ",", "\t", "|"], key=lambda s: text.splitlines()[0].count(s))
    return pd.read_csv(io.BytesIO(raw), sep=sep, encoding=enc, low_memory=False, **kw)


def read_table(p: Path) -> pd.DataFrame | None:
    s = p.suffix.lower()
    if s in (".parquet", ".geoparquet"):
        try:
            import geopandas as gpd
            return gpd.read_parquet(p)
        except Exception:  # noqa: BLE001 - plain parquet without geo metadata
            return pd.read_parquet(p)
    if s in (".csv", ".txt"):
        return read_csv_any(p)
    if s in (".geojson", ".json"):
        import geopandas as gpd
        try:
            return gpd.read_file(p)
        except Exception:  # noqa: BLE001
            return pd.read_json(p)
    if s == ".xlsx":
        return pd.read_excel(p)
    return None


def profile(df: pd.DataFrame, label: str, low_card: int = 25) -> None:
    """Columns, non-null counts, examples; value lists for low-cardinality text columns."""
    md.append(f"**{label}** — строк: {len(df):,}, колонок: {len(df.columns)}\n")
    rows = []
    for c in df.columns:
        if str(c) == "geometry":
            rows.append({"колонка": c, "тип": "geometry", "заполнено": int(df[c].notna().sum()),
                         "уникальных": "", "примеры": ""})
            continue
        s = df[c]
        ex = ", ".join(map(str, s.dropna().astype(str).unique()[:3]))
        rows.append({"колонка": c, "тип": str(s.dtype), "заполнено": int(s.notna().sum()),
                     "уникальных": int(s.nunique(dropna=True)), "примеры": ex})
    table(pd.DataFrame(rows), max_rows=200)


def values(df: pd.DataFrame, col: str, weight: str | None = None, top: int = 40) -> pd.DataFrame:
    g = df.groupby(df[col].astype(str).fillna("∅"), dropna=False)
    out = pd.DataFrame({"записей": g.size()})
    if weight:
        out["сумма"] = g[weight].sum()
    return out.sort_values("записей", ascending=False).head(top).reset_index().rename(
        columns={col: "значение"})


def files_in(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in DATA_EXT
                  and not p.name.startswith("~$"))


def dept_code(v) -> str | None:
    """INSEE department code as a string: 01-95, 2A, 2B, 971-976."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    t = str(v).strip().upper()
    if t in ("", "NAN", "NONE", "NULL"):
        return None
    t = re.sub(r"\.0+$", "", t)
    if t in ("2A", "2B"):
        return t
    if t.isdigit():
        return t.zfill(2) if len(t) <= 2 else t
    return t


def dept_from_commune(v) -> str | None:
    t = re.sub(r"\.0+$", "", str(v).strip().upper())
    if not t or t in ("NAN", "NONE"):
        return None
    t = t.zfill(5)
    if t.startswith("97"):
        return t[:3]
    return t[:2]


# ------------------------------------------------------------------ §9.6 frame
def frame_codes() -> set[str]:
    try:
        import geopandas as gpd
        g = gpd.read_parquet(ADM2)
    except Exception as exc:  # noqa: BLE001
        md.append(f"_Не прочитан набор границ {ADM2}: {exc}_\n")
        return set()
    g = g[g["unit_id"].astype(str).str.startswith("FRA-2-")]
    codes = set(g["unit_id"].str.replace("FRA-2-", "", regex=False))
    num["frame_n"] = len(codes)
    return codes


def compare_codes(found: set[str], frame: set[str], label: str) -> None:
    extra, missing = sorted(found - frame), sorted(frame - found)
    md.append(f"- **{label}:** кодов в источнике {len(found)}; совпали с рамкой "
              f"{len(found & frame)}; нет в рамке: {', '.join(extra) or '—'}; "
              f"рамка без значений источника ({len(missing)}): {', '.join(missing) or '—'}")
    num.setdefault("codes", {})[label] = {"found": len(found), "extra": extra, "missing": missing}


# ------------------------------------------------------------------ §9.1 files
def files_section() -> dict[str, list[Path]]:
    h("1. Файлы")
    out = {}
    rows = []
    for k, folder in SRC.items():
        fs = files_in(folder)
        out[k] = fs
        if not fs:
            rows.append({"источник": k, "файл": f"нет файлов в {folder}", "МБ": "", "SHA-256": "",
                         "изменён": ""})
        for p in fs:
            rows.append({"источник": k, "файл": str(p.relative_to(ROOT)),
                         "МБ": round(p.stat().st_size / 1e6, 2), "SHA-256": sha256(p)[:16] + "…",
                         "изменён": pd.Timestamp(p.stat().st_mtime, unit="s").strftime("%Y-%m-%d %H:%M")})
    table(pd.DataFrame(rows), max_rows=200)
    num["files"] = rows
    # LICENSE.txt / NOTE.txt written by V next to the data
    for k, folder in SRC.items():
        for n in ("LICENSE.txt", "NOTE.txt"):
            p = folder / n
            if p.exists():
                md.append(f"**{k} · {n}** (дословно):\n\n```\n"
                          f"{p.read_text(encoding='utf-8', errors='replace').strip()[:3000]}\n```\n")
    return out


# ------------------------------------------------------------------ §9.2 ODRÉ
FILIERE_GROUPS = [  # proposal for [RES]; keyword (normalized) -> group, first match wins
    ("nucleaire", "nuclear"), ("stockage", "storage"), ("batterie", "storage"),
    ("hydraulique", "hydro"), ("eolien", "wind"), ("solaire", "solar"),
    ("photovolt", "solar"), ("bioenergie", "bioenergy"), ("biomasse", "bioenergy"),
    ("biogaz", "bioenergy"), ("dechet", "bioenergy"), ("thermique", "fossil"),
    ("fossile", "fossil"), ("gaz", "fossil"), ("charbon", "fossil"), ("fioul", "fossil"),
    ("petrole", "fossil"), ("marin", "other"), ("energiemarine", "other"),
    ("geotherm", "other"),
]


def group_of(v: str) -> str:
    n = norm(v)
    for k, g in FILIERE_GROUPS:
        if k in n:
            return g
    return "other"


def odre(fs: list[Path], frame: set[str]) -> None:
    h("2. Генерация · ODRÉ (F1)")
    csvs = [p for p in fs if p.suffix.lower() in (".csv", ".parquet", ".xlsx")]
    if not csvs:
        md.append("_Файла F1 нет._\n")
        return
    df = read_table(max(csvs, key=lambda p: p.stat().st_size))
    profile(df, csvs[0].name)
    c_dep = pick(df, "codeDepartement", "code_departement", "departement")
    c_com = pick(df, "codeINSEECommune", "code_insee_commune", "codeinsee")
    c_pw = pick(df, "puisMaxInstallee", "puissance_maximale_installee", "puisMaxInstal",
                "puissanceMaxInstallee", "puissance")
    c_fil = pick(df, "filiere")
    c_tech = pick(df, "technologie")
    c_stock = [c for c in df.columns if re.search(r"stock", norm(c))]
    c_dates = [c for c in df.columns if norm(c).startswith("date")]
    c_nb = pick(df, "nbInstallations", "nombre_installations", "nbinstall")
    c_reg = pick(df, "regime")
    md.append(f"Поля, найденные по именам: департамент `{c_dep}`, коммуна `{c_com}`, мощность "
              f"`{c_pw}`, филиера `{c_fil}`, технология `{c_tech}`, число установок `{c_nb}`, "
              f"режим `{c_reg}`; даты: {', '.join(f'`{c}`' for c in c_dates) or '—'}; "
              f"поля хранения: {', '.join(f'`{c}`' for c in c_stock) or '—'}.\n")
    num["odre_fields"] = {"dep": c_dep, "commune": c_com, "power": c_pw, "filiere": c_fil,
                          "tech": c_tech, "nb": c_nb, "dates": c_dates, "storage": c_stock}
    if not c_pw:
        md.append("**СТОП: нет поля мощности — нужно имя колонки.**\n")
        return
    df["_kw"] = pd.to_numeric(df[c_pw], errors="coerce")
    md.append(f"Сумма `{c_pw}` по файлу: **{df['_kw'].sum() / 1000:,.1f} МВт** "
              f"(предполагаем кВт; нечисловых значений: {int(df['_kw'].isna().sum())}).\n")

    if c_fil:
        md.append("**Филиеры и предлагаемые группы** (таблицу утверждает [RES]):\n")
        v = values(df, c_fil, "_kw", top=100)
        v["МВт"] = v.pop("сумма") / 1000
        v["группа (предложение)"] = v["значение"].map(group_of)
        table(v, max_rows=100)
        num["odre_filiere"] = v.to_dict("records")
    if c_tech:
        md.append("**Технологии** (для разделения хранения и ГАЭС):\n")
        v = values(df, c_tech, "_kw", top=60)
        v["МВт"] = v.pop("сумма") / 1000
        table(v, max_rows=60)

    md.append("**Даты** — заполненность и диапазон (для правила «действует на дату среза»):\n")
    rows = []
    for c in c_dates:
        d = pd.to_datetime(df[c], errors="coerce", dayfirst=True)
        rows.append({"поле": c, "заполнено": int(d.notna().sum()), "пусто": int(d.isna().sum()),
                     "мин": str(d.min())[:10], "макс": str(d.max())[:10]})
    table(pd.DataFrame(rows))
    for c in [x for x in df.columns if re.search(r"statut|etat|regime|mode", norm(x))]:
        md.append(f"Значения `{c}`:\n")
        table(values(df, c, "_kw", top=30))

    if c_dep:
        df["_dep"] = df[c_dep].map(dept_code)
    elif c_com:
        df["_dep"] = df[c_com].map(dept_from_commune)
    else:
        md.append("**Нет поля департамента и коммуны — привязка по коду невозможна.**\n")
        return
    nod = df[df["_dep"].isna()]
    md.append(f"**Строки без кода департамента:** {len(nod):,}, {nod['_kw'].sum() / 1000:,.1f} МВт. "
              "Примеры:\n")
    keep = [c for c in (c_fil, c_tech, c_com, pick(df, "nomInstallation", "nom_installation"),
                        c_pw) if c]
    table(nod[keep].head(10))
    num["odre_no_dept"] = {"rows": len(nod), "mw": float(nod["_kw"].sum() / 1000)}
    compare_codes(set(df["_dep"].dropna()), frame, "ODRÉ")
    md.append("")
    snap = pd.Timestamp.today().normalize()
    d_on = pd.to_datetime(df.get("dateMiseEnservice (format date)", df.get(c_dates[0] if c_dates else c_pw)),
                          errors="coerce", format="%Y-%m-%d")
    d_off = pd.to_datetime(df["dateDeraccordement"], errors="coerce", dayfirst=True) \
        if "dateDeraccordement" in df else pd.Series(pd.NaT, index=df.index)
    reg = df[c_reg].astype(str) if c_reg else pd.Series("", index=df.index)
    flags = {
        "отключены (dateDeraccordement заполнена)": d_off.notna(),
        "ввод в эксплуатацию позже сегодняшней даты": d_on > snap,
        "без даты ввода": d_on.isna(),
        "regime = En retrait provisoire": reg.eq("En retrait provisoire"),
        "regime пусто (строки-агрегаты <36 кВт и прочие)": df[c_reg].isna() if c_reg else d_on.isna() & False,
    }
    md.append("**К правилу «действует на дату среза»** — сколько строк задевает каждое условие:\n")
    table(pd.DataFrame([{"условие": k, "строк": int(m.sum()), "МВт": float(df.loc[m, "_kw"].sum() / 1000)}
                        for k, m in flags.items()]))
    op = ~flags["отключены (dateDeraccordement заполнена)"] & ~(d_on > snap) & \
        ~flags["regime = En retrait provisoire"]
    stor = df[c_fil].eq("Stockage non hydraulique") if c_fil else pd.Series(False, index=df.index)
    md.append(f"Предложение: действует = нет `dateDeraccordement`, ввод не позже даты среза, "
              f"не «En retrait provisoire»; строки без даты ввода и без `regime` остаются. "
              f"Тогда: генерация без хранения **{df.loc[op & ~stor, '_kw'].sum() / 1000:,.1f} МВт**, "
              f"хранение (филиера «Stockage non hydraulique») {df.loc[op & stor, '_kw'].sum() / 1000:,.1f} МВт; "
              f"ГАЭС (технология «Pompage turbinage») остаются в гидро: "
              f"{df.loc[op & df[c_tech].eq('Pompage turbinage'), '_kw'].sum() / 1000:,.1f} МВт.\n" if c_tech else "")
    if "typeStockage" in df:
        md.append("`typeStockage` по филиерам (строк):\n")
        table(df[df["typeStockage"].notna()].groupby([c_fil, "typeStockage"]).size()
              .reset_index(name="строк"))
    out = df[~df["_dep"].isin(frame) & df["_dep"].notna()]
    md.append(f"Коды вне рамки (заморские общины вне 101 департамента): {len(out):,} строк, "
              f"{out['_kw'].sum() / 1000:,.1f} МВт — по кодам: "
              + ", ".join(f"{k} {v / 1000:,.1f} МВт" for k, v in out.groupby('_dep')['_kw'].sum().items()) + ".\n")
    num["odre_operating_proposal"] = {"gen_mw": float(df.loc[op & ~stor, "_kw"].sum() / 1000),
                                      "storage_mw": float(df.loc[op & stor, "_kw"].sum() / 1000)}
    if c_nb:
        md.append(f"Поле числа установок `{c_nb}` есть: сумма {pd.to_numeric(df[c_nb], errors='coerce').sum():,.0f}.\n")
    num["_odre_dept_mw"] = (df.dropna(subset=["_dep"]).groupby("_dep")["_kw"].sum() / 1000).to_dict()


# ------------------------------------------------------------------ §9.3 Agence ORE
def ore(fs: list[Path], frame: set[str]) -> None:
    h("3. Потребление · Agence ORE")
    cat = RES / "agenceore_catalogue" / "candidates.json"
    if cat.exists():
        rows = json.loads(cat.read_text(encoding="utf-8"))
        md.append("Каталог Agence ORE (поиск «consommation …»):\n")
        table(pd.DataFrame(rows)[["id", "title", "updated", "license"]], max_rows=40)
        dept = [r for r in rows if r["id"] == ORE_DEPT_ID] or \
            [r for r in rows if "depart" in norm(f"{r['id']}{r['title']}")
             and "consommation" in norm(f"{r['id']}{r['title']}") and "gaz" in norm(r["title"])]
        md.append(f"Набор по департаментам: **{'есть — ' + dept[0]['id'] if dept else 'нет'}**.\n")
        num["ore_dept_dataset"] = dept[0]["id"] if dept else None
    else:
        md.append("_Каталог не скачан: сначала `download_fra.py`._\n")
    csvs = [p for p in fs if p.suffix.lower() == ".csv"]
    if not csvs:
        md.append("_Файла потребления нет._\n")
        return
    p = next((q for q in csvs if q.stem == ORE_DEPT_ID), None) or \
        sorted(csvs, key=lambda q: q.stat().st_size)[0]
    meta = p.with_name(p.stem + "_meta.json")
    if meta.exists():
        j = json.loads(meta.read_text(encoding="utf-8"))
        lic = j.get("license") or {}
        md.append(f"Метаданные набора (data-fair): «{j.get('title')}»; лицензия «{lic.get('title')}» "
                  f"({lic.get('href')}); данные обновлены {j.get('dataUpdatedAt')}; издатель "
                  f"{(j.get('owner') or {}).get('name')}.\n")
        num["ore_meta"] = {"title": j.get("title"), "license": lic, "updated": j.get("dataUpdatedAt")}
    md.append(f"Разбираю `{p.name}` ({p.stat().st_size / 1e6:,.0f} МБ).\n")
    df = read_csv_any(p)
    profile(df, p.name)
    c_year = pick(df, "annee", "année", "year")
    c_fil = pick(df, "filiere", "energie")
    c_sec = pick(df, "code_grand_secteur", "libelle_grand_secteur", "grand_secteur", "secteur",
                 "categorie_consommation")
    c_val = pick(df, "conso", "consommation", "conso_totale_mwh", "consototale")
    c_pdl = pick(df, "pdl", "nombre_points", "nb_points", "points_de_livraison")
    c_dep = pick(df, "code_departement", "codedepartement", "departement")
    c_com = pick(df, "code_commune", "codecommune", "code_insee")
    md.append(f"Поля: год `{c_year}`, энергия `{c_fil}`, сектор `{c_sec}`, значение `{c_val}`, "
              f"точки поставки `{c_pdl}`, департамент `{c_dep}`, коммуна `{c_com}`.\n")
    num["ore_fields"] = {"year": c_year, "energy": c_fil, "sector": c_sec, "value": c_val,
                         "pdl": c_pdl, "dep": c_dep, "commune": c_com}
    for c in (c_year, c_fil, c_sec):
        if c:
            md.append(f"Значения `{c}`:\n")
            table(values(df, c, top=40))
    if not c_val:
        md.append("**Нет поля значения — нужно имя колонки.**\n")
        return
    raw = df[c_val]
    v = pd.to_numeric(raw.astype(str).str.replace(",", ".").str.replace(" ", ""), errors="coerce")
    masked = raw.notna() & v.isna()
    md.append(f"**Тайна / нечисловые значения в `{c_val}`:** пусто {int(raw.isna().sum()):,}, "
              f"текст {int(masked.sum()):,}; текстовые значения: "
              f"{', '.join(map(str, raw[masked].astype(str).unique()[:10])) or '—'}.\n")
    df["_v"] = v
    if c_fil:
        el = df[c_fil].astype(str).str.lower().str.contains("lec")
        md.append(f"Строк электричества: {int(el.sum()):,} из {len(df):,}.\n")
        df = df[el]
    if c_year:
        yrs = sorted(df[c_year].dropna().unique())
        md.append(f"Годы электричества: {', '.join(map(str, yrs))}.\n")
        last = yrs[-1]
        df = df[df[c_year] == last]
        num["ore_last_year"] = str(last)
        md.append(f"Последний год {last}: {len(df):,} строк, сумма {df['_v'].sum():,.0f} "
                  "(единица — из описания полей, ожидается МВт·ч).\n")
    if c_dep:
        df["_dep"] = df[c_dep].map(dept_code)
    elif c_com:
        df["_dep"] = df[c_com].map(dept_from_commune)
    if "_dep" in df:
        compare_codes(set(df["_dep"].dropna()), frame, "Agence ORE")
        md.append("")
        num["_ore_dept"] = df.groupby("_dep")["_v"].sum().to_dict()
    # how the rows split - to rule out double counting (sub-totals) before the build
    for c in [x for x in df.columns if norm(x) in ("codecategorieconsommation", "codesecteurnaf2",
                                                   "operateur")]:
        md.append(f"Последний год, электричество — разбивка по `{c}` (строк, МВт·ч):\n")
        g = df.groupby(df[c].astype(str))["_v"].agg(["size", "sum"]).sort_values("sum", ascending=False)
        table(g.reset_index().head(25))
    c_sec_n = pick(df, "nombre_de_mailles_secretisees", "mailles_secretisees")
    if c_sec_n:
        m = pd.to_numeric(df[c_sec_n], errors="coerce").fillna(0)
        md.append(f"**Статистическая тайна** (`{c_sec_n}`): строк с тайной > 0 — {int((m > 0).sum()):,}, "
                  f"сумма скрытых ячеек {int(m.sum()):,}; строк с пустым значением потребления "
                  f"{int(df['_v'].isna().sum()):,}. По департаментам (топ-10 по числу скрытых):\n")
        if "_dep" in df:
            t = df.assign(_m=m).groupby("_dep").agg(cells=("_m", "sum"), mwh=("_v", "sum"))
            table(t.sort_values("cells", ascending=False).head(10).reset_index())


# ------------------------------------------------------------------ §9.4 RTE
def read_lines(p: Path):
    """GeoParquet, or an Opendatasoft parquet without geo metadata (geometry as GeoJSON
    text, WKB bytes or WKT in a column such as geo_shape)."""
    import geopandas as gpd
    from shapely import wkb, wkt
    from shapely.geometry import shape
    if p.suffix.lower() == ".geojson":
        return gpd.read_file(p)
    if p.suffix.lower() == ".zip":
        import zipfile as zf
        shp = [n for n in zf.ZipFile(p).namelist() if n.lower().endswith(".shp")]
        if not shp:
            raise ValueError("в архиве нет .shp")
        parts = [gpd.read_file(f"zip://{p}!{n}") for n in shp]
        g = pd.concat([x.to_crs(4326) for x in parts], ignore_index=True)
        md.append(f"  - `{p.name}`: shapefile(ы) {', '.join(shp)}; исходная CRS `{parts[0].crs}`")
        return gpd.GeoDataFrame(g, geometry="geometry", crs=4326)
    try:
        return gpd.read_parquet(p)
    except Exception:  # noqa: BLE001 - fall back to plain parquet
        pass
    df = pd.read_parquet(p)
    gcol = next((c for c in df.columns if norm(c) in ("geoshape", "geometry", "geom", "shape",
                                                      "geometrie")), None)
    if gcol is None:
        raise ValueError(f"нет колонки геометрии; колонки: {list(df.columns)}")
    v = df[gcol].dropna().iloc[0]

    def conv(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        if isinstance(x, (bytes, bytearray, memoryview)):
            return wkb.loads(bytes(x))
        if isinstance(x, dict):
            return shape(x.get("geometry", x))
        t = str(x).strip()
        if t.startswith("{"):
            j = json.loads(t)
            return shape(j.get("geometry", j))
        return wkt.loads(t)
    geom = df[gcol].map(conv)
    md.append(f"  - `{p.name}`: геометрия из колонки `{gcol}` ({type(v).__name__}), "
              "без geo-метаданных; CRS принят EPSG:4326 (Opendatasoft отдаёт WGS84)")
    return gpd.GeoDataFrame(df.drop(columns=[gcol]), geometry=list(geom), crs=4326)


def rte(fs: list[Path], frame: set[str]) -> None:
    h("4. ЛЭП · RTE (F2)")
    import geopandas as gpd
    pq = [p for p in fs if p.suffix.lower() in (".parquet", ".geoparquet", ".geojson", ".zip")]
    # prefer the GeoJSON export when both exist (the parquet export carries no geometry)
    gj = {p.stem for p in pq if p.suffix.lower() == ".geojson"}
    pq = [p for p in pq if p.suffix.lower() == ".geojson" or p.stem not in gj]
    if not pq:
        md.append("_Файлов F2 нет._\n")
        return
    parts = []
    for p in pq:
        try:
            g = read_lines(p)
        except Exception as exc:  # noqa: BLE001
            md.append(f"- `{p.name}`: не прочитан ({type(exc).__name__}: {exc})")
            continue
        n_geom = int(g.geometry.notna().sum() - g.geometry.is_empty.fillna(False).sum())
        md.append(f"- `{p.name}`: {len(g):,} объектов, с геометрией {n_geom:,}, CRS `{g.crs}`, "
                  f"типы {', '.join(g.geom_type.dropna().value_counts().index.astype(str)) or '—'}")
        if n_geom == 0:
            md.append(f"  - **у `{p.name}` нет ни одной геометрии** — файл не годится для слоя")
            continue
        g["_file"] = p.name
        parts.append(g)
    md.append("")
    if not parts:
        return
    for g in parts:
        profile(g.drop(columns="_file"), g["_file"].iloc[0])
    g = pd.concat([x.to_crs(2154) for x in parts], ignore_index=True)
    g = gpd.GeoDataFrame(g, geometry="geometry", crs=2154)
    c_volt = pick(g, "tension", "voltage")
    c_id = pick(g, "code_ligne", "identifiant", "id_ligne", "id")
    c_state = pick(g, "etat", "statut", "proprietaire", "owner")
    md.append(f"Поля: идентификатор `{c_id}`, напряжение `{c_volt}`, состояние/владелец `{c_state}`.\n")
    g["_km"] = g.length / 1000
    md.append(f"Длина всех сегментов (EPSG:2154): **{g['_km'].sum():,.1f} км**.\n")
    if c_volt:
        md.append(f"Значения `{c_volt}` (км):\n")
        table(values(g, c_volt, "_km", top=40))
    dc = [c for c in g.columns if g[c].dtype == object and c != "geometry"
          and g[c].astype(str).str.contains(r"continu|\bDC\b|HVDC|CC\b", case=False, regex=True).any()]
    md.append(f"Колонки с пометкой постоянного тока: {', '.join(dc) or 'не найдено'}.\n")
    num["rte"] = {"n": len(g), "km": float(g["_km"].sum()), "id": c_id, "voltage": c_volt,
                  "dc_columns": dc}
    try:
        b = gpd.read_parquet(ADM2)
        b = b[b["unit_id"].astype(str).str.startswith("FRA-2-")].to_crs(2154)
        b["_dep"] = b["unit_id"].str.replace("FRA-2-", "", regex=False)
        inter = gpd.overlay(g[["_km", "geometry"]], b[["_dep", "geometry"]], how="intersection",
                            keep_geom_type=True)
        inter["_kmin"] = inter.length / 1000
        per = inter.groupby("_dep")["_kmin"].sum()
        md.append(f"Внутри департаментов: {per.sum():,.1f} км ({100 * per.sum() / g['_km'].sum():.2f}% "
                  f"всех сегментов); департаментов с линиями: {len(per)}.\n")
        compare_codes(set(per.index), frame, "RTE (по геометрии)")
        md.append("")
        num["_rte_dept_km"] = per.to_dict()
    except Exception as exc:  # noqa: BLE001
        md.append(f"_Пересечение с департаментами не посчитано: {exc}_\n")


# ------------------------------------------------------------------ §9.5 ICPE
NAME_RE = re.compile(r"data\s*-?\s*cent(?:er|re)s?|datacent(?:er|re)|centres?\s+de\s+donn[ée]es",
                     re.I)
P9_COLS = re.compile(r"rubri|regime|r[ée]gime|quantit|volume|alin[ée]a|seveso|puiss|unite", re.I)


def naf_norm(v) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(v).upper())


def icpe(fs: list[Path], frame: set[str]) -> None:
    h("5. ЦОД · ICPE (F3)")
    tables: list[tuple[str, pd.DataFrame]] = []
    for p in fs:
        try:
            if p.suffix.lower() == ".zip":
                with zipfile.ZipFile(p) as z:
                    for n in z.namelist():
                        if n.lower().endswith((".csv", ".txt")):
                            with z.open(n) as fh:
                                tables.append((f"{p.name}:{n}", read_csv_any(fh)))
            else:
                t = read_table(p)
                if t is not None:
                    tables.append((p.name, t))
        except Exception as exc:  # noqa: BLE001
            md.append(f"- `{p.name}`: не прочитан ({exc})")
    if not tables:
        md.append("_Файлов F3 нет._\n")
        return
    md.append("Таблицы: " + "; ".join(f"`{n}` ({len(t):,} строк)" for n, t in tables) + "\n")
    # the installations table = the one with a NAF column and the most rows
    cand = [(n, t) for n, t in tables if pick(t, "code_naf", "naf", "activite_principale")]
    if not cand:
        md.append("**Нет таблицы с кодом NAF.** Колонки всех таблиц:\n")
        for n, t in tables:
            md.append(f"- `{n}`: {', '.join(map(str, t.columns))}")
        return
    name, df = max(cand, key=lambda x: len(x[1]))
    p9 = [c for c in df.columns if P9_COLS.search(str(c))]
    safe = df.drop(columns=p9)
    md.append(f"Таблица установок: `{name}`. Колонки, которые **не публикуются** (P9; значения "
              f"в отчёт не выводятся): {', '.join(f'`{c}`' for c in p9) or '—'}.\n")
    profile(safe, name)
    num["icpe_p9_columns"] = p9

    c_id = pick(df, "code_aiot", "aiot", "num_aiot", "code_s3ic", "s3ic")
    c_naf = pick(df, "code_naf", "naf", "activite_principale")
    c_name = pick(df, "raison_sociale", "nom_ets", "nom_etablissement", "nom", "libelle")
    c_com = pick(df, "code_insee", "insee", "code_commune")
    c_dep = pick(df, "code_departement", "departement", "num_dep")
    c_state = pick(df, "etat_activite", "etat", "statut", "situation")
    c_x = pick(df, "longitude", "lon", "x")
    c_y = pick(df, "latitude", "lat", "y")
    c_prec = pick(df, "precision", "precision_geo", "code_precision", "geoloc")
    c_url = pick(df, "url_fiche", "fiche", "url")
    f = {"aiot": c_id, "naf": c_naf, "name": c_name, "commune": c_com, "dept": c_dep,
         "state": c_state, "x": c_x, "y": c_y, "precision": c_prec, "url": c_url}
    num["icpe_fields"] = f
    md.append("Поля по именам: " + ", ".join(f"{k} `{v}`" for k, v in f.items()) + ".\n")
    for c in (c_state, c_prec):
        if c:
            md.append(f"Значения `{c}`:\n")
            table(values(df, c, top=30))
    if c_x and c_y:
        x = pd.to_numeric(df[c_x], errors="coerce")
        md.append(f"Координаты: заполнено {int(x.notna().sum()):,} из {len(df):,}; диапазон "
                  f"`{c_x}` {x.min():,.3f}…{x.max():,.3f} (градусы или Lambert-93 — по диапазону).\n")

    md.append(f"Формат `{c_naf}`: примеры {', '.join(map(str, df[c_naf].dropna().unique()[:8]))} — "
              f"длина кода NAF после очистки: "
              + ", ".join(f"{k} знаков: {v:,}" for k, v in
                          df[c_naf].dropna().map(lambda v: len(naf_norm(re.sub(r'\.0$', '', str(v)))))
                          .value_counts().sort_index().items()) + ".\n")
    c_epsg = pick(df, "code_epsg", "epsg")
    if c_epsg:
        md.append(f"Системы координат по записям (`{c_epsg}`):\n")
        table(values(df, c_epsg, top=10))
        if c_x:
            x = pd.to_numeric(df[c_x], errors="coerce")
            y = pd.to_numeric(df[c_y], errors="coerce")
            l93 = df[c_epsg].astype(str).eq("2154")
            ok = l93 & x.between(100_000, 1_300_000) & y.between(6_000_000, 7_200_000)
            md.append(f"Lambert-93: записей {int(l93.sum()):,}, из них в пределах метрополии "
                      f"{int(ok.sum()):,}; нулевые или за пределами — {int((l93 & ~ok).sum()):,}.\n")
    df["_naf"] = df[c_naf].map(lambda v: naf_norm(re.sub(r"\.0$", "", str(v))) if pd.notna(v) else "")
    df["_name"] = df[c_name].astype(str) if c_name else ""
    r1 = df["_naf"] == "6311Z"
    rname = df["_name"].str.contains(NAME_RE, na=False)
    r2 = rname & df["_naf"].str[:2].isin(["62", "63"]) & ~r1
    rej_name = rname & ~r1 & ~r2          # name matches, NAF outside 62/63
    md.append("**Правила отбора** (SPEC_FRA §6; утверждает [RES]):\n")
    rules = pd.DataFrame([
        {"правило": "1 · NAF 63.11Z", "записей": int(r1.sum())},
        {"правило": "2 · название + NAF 62/63 (без правила 1)", "записей": int(r2.sum())},
        {"правило": "в слой (1 или 2)", "записей": int((r1 | r2).sum())},
        {"правило": "отклонено: название есть, NAF не 62/63", "записей": int(rej_name.sum())},
        {"правило": "из правила 1: название с «data center»", "записей": int((r1 & rname).sum())},
        {"правило": "NAF 62.xx/63.xx всего (справочно)",
         "записей": int(df["_naf"].str[:2].isin(["62", "63"]).sum())},
    ])
    table(rules)
    num["icpe_rules"] = rules.to_dict("records")
    show = [c for c in (c_id, c_name, c_naf, c_com, c_dep, c_state, c_prec) if c]
    for lbl, m in (("правило 1", r1), ("правило 2", r2), ("отклонённые по названию", rej_name)):
        md.append(f"Примеры — {lbl} (до 10):\n")
        table(df.loc[m, show].head(10))
    if c_state:
        md.append("Состояние у отобранных (1 или 2):\n")
        table(values(df[r1 | r2], c_state, top=20))
    if c_prec:
        md.append("Точность координат у отобранных:\n")
        table(values(df[r1 | r2], c_prec, top=20))
    ops = {"equinix": r"equinix", "interxion / digital realty": r"interxion|digital\s*realty",
           "data4": r"\bdata\s*4\b", "telehouse": r"telehouse", "global switch": r"global\s*switch",
           "ovh": r"\bovh", "scaleway": r"scaleway", "ntt": r"\bntt\b", "nlighten": r"nlighten",
           "cyrusone": r"cyrusone", "vantage": r"vantage\s*data", "stack": r"stack\s*infra",
           "free / iliad": r"\biliad\b|\bfree\s*pro", "thésée": r"thes[ée]e", "ikoula": r"ikoula",
           "sungard": r"sungard", "orange": r"orange", "colt": r"\bcolt\b",
           "hébergement": r"h[ée]bergement"}
    md.append("**Справочно для [RES]: известные операторы ЦОД в названиях** (все записи, без "
              "правил; это не отбор):\n")
    table(pd.DataFrame([{"оператор": k, "записей": int(df["_name"].str.contains(v, case=False, regex=True, na=False).sum()),
                         "из них NAF 62/63": int((df["_name"].str.contains(v, case=False, regex=True, na=False)
                                                 & df["_naf"].str[:2].isin(["62", "63"])).sum()),
                         "NAF пусто": int((df["_name"].str.contains(v, case=False, regex=True, na=False)
                                          & df["_naf"].eq("")).sum())} for k, v in ops.items()]))
    md.append("Записи с NAF 62/63 (справочно, до 40):\n")
    table(df.loc[df["_naf"].str[:2].isin(["62", "63"]), show].head(40))
    out = df.loc[r1 | r2 | rej_name, show].copy()
    out["rule"] = ["1" if a else "2" if b else "rejected_name"
                   for a, b in zip(r1[r1 | r2 | rej_name], r2[r1 | r2 | rej_name])]
    out.to_csv(RES / "icpe_candidates.csv", index=False, encoding="utf-8-sig")
    md.append(f"Рабочий файл кандидатов (не публикуется): `research\\fra\\icpe_candidates.csv`, "
              f"{len(out):,} строк.\n")
    if c_dep:
        compare_codes(set(df[c_dep].map(dept_code).dropna()), frame, "ICPE (все записи)")
    elif c_com:
        compare_codes(set(df[c_com].map(dept_from_commune).dropna()), frame, "ICPE (по коммуне)")
    md.append("")


# ------------------------------------------------------------------ §9.7 licences
def licences() -> None:
    h("7. Лицензии — выписки из сырого HTML")
    LIC.mkdir(parents=True, exist_ok=True)
    pages = sorted(LIC.glob("*.html")) + sorted(LIC.glob("*.json")) + \
        sorted(q for k in ("F1", "F2") for q in SRC[k].glob("*_meta.json") if SRC[k].exists())
    if not pages:
        md.append("_Страниц нет: сначала `download_fra.py`._\n")
        return
    for p in pages:
        raw = p.read_text(encoding="utf-8", errors="replace")
        if p.suffix == ".json" and "metas" in raw[:20000]:
            try:
                d = json.loads(raw).get("metas", {}).get("default", {})
                txt = json.dumps({k: d.get(k) for k in ("title", "publisher", "license",
                                                         "license_url", "modified",
                                                         "data_processed", "attributions")},
                                 ensure_ascii=False, default=str)
            except ValueError:
                txt = raw[:2000]
        elif p.suffix == ".json":
            try:
                j = json.loads(raw)
                txt = json.dumps({k: j.get(k) for k in ("title", "license", "last_modified",
                                                         "last_update", "organization")
                                  if k in j}, ensure_ascii=False, default=str)
            except ValueError:
                txt = raw[:2000]
        else:
            text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
            text = html.unescape(re.sub(r"<[^>]+>", "\n", text))
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            hits = [i for i, ln in enumerate(lines)
                    if re.search(r"licen[cs]e|conditions? (g[ée]n[ée]rales )?d.utilisation|"
                                 r"etalab|odbl|cc[- ]by|r[ée]utilisation", ln, re.I)]
            keep = sorted({j for i in hits for j in range(max(0, i - 1), min(len(lines), i + 3))})
            txt = "\n".join(lines[j] for j in keep)[:4000]
            if not txt:
                txt = ("(в сыром HTML абзаца лицензии нет — страница, вероятно, собирается "
                       "JavaScript; нужен LICENSE.txt от V)")
        (LIC / f"{p.stem}.txt").write_text(txt, encoding="utf-8")
        md.append(f"**{p.stem}** (`{p.name}`):\n\n```\n{txt[:1500]}\n```\n")


# ------------------------------------------------------------------ §9.8 thresholds
def breaks(s: pd.Series, k: int = 4) -> list[float]:
    s = s[s > 0].sort_values()
    if len(s) < 5:
        return []
    qs = [s.quantile(q) for q in (0.2, 0.4, 0.6, 0.8)][:k]
    out = []
    for q in qs:
        mag = 10 ** max(0, int(f"{q:e}".split("e")[1]) - 1)
        out.append(float(round(q / mag) * mag))
    return sorted(set(out))


def thresholds() -> None:
    h("8. Предлагаемые пороги классов (предварительно, по квантилям 20/40/60/80%)")
    rows = []
    for key, name, field in (("_odre_dept_mw", "energy_generation_odre_adm2",
                              "installed_capacity_mw (все строки файла, до фильтра «действует» и без вычета хранения)"),
                             ("_ore_dept", "energy_consumption_agenceore_adm2",
                              "consumption_mwh (последний год)"),
                             ("_rte_dept_km", "energy_transmission_rte_adm2", "km_total")):
        d = num.pop(key, None)
        if d:
            rows.append({"слой": name, "поле": field,
                         "breaks": breaks(pd.Series(d, dtype=float)), "единиц": len(d)})
    table(pd.DataFrame(rows))
    num["breaks"] = rows
    md.append("Окончательные пороги — после сборки, тем же правилом, что у слоёв США (SPEC_META §5).\n")


# ------------------------------------------------------------------ main
def main() -> None:  # noqa: C901
    RES.mkdir(parents=True, exist_ok=True)
    md.append("# Pre-flight · слои Франции (SPEC_FRA_layers_v0_1 r2, §9)\n")
    md.append("Скрипт `scripts/fra/preflight_fra.py`, только чтение. Номера разделов — пункты §9.\n")
    fs = files_section()
    h("6. Коды департаментов (рамка `abf-boundaries-v0.1.0`)")
    frame = frame_codes()
    md.append(f"В наборе границ `FRA-2-*`: **{len(frame)}** (ожидается 101). Сверка источников — в их "
              "разделах ниже, строкой «совпали с рамкой».\n")
    fs["F2"] = fs["F2"] + fs.get("F2b", [])
    for fn, key in ((odre, "F1"), (ore, "ORE"), (rte, "F2"), (icpe, "F3")):
        try:
            fn(fs[key], frame)
        except Exception as exc:  # noqa: BLE001 - one source must not stop the others
            md.append(f"\n**Ошибка в разделе {key}: {type(exc).__name__}: {exc}** — пришлите эту "
                      "строку.\n")
    licences()
    thresholds()
    (RES / "preflight_fra.md").write_text("\n".join(md), encoding="utf-8")
    (RES / "preflight_fra.json").write_text(
        json.dumps(num, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("Готово:", RES / "preflight_fra.md")


if __name__ == "__main__":
    sys.exit(main())
