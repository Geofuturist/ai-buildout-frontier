r"""Two checks for the region texts of abf-fra v0.2.0 (RES_texts_FRA_regions_v0_2_0 r2).

Run from the repo root:
    python scripts\fra\finalize_regions_fra.py

1. Attribution of the Agence ORE dataset by region: from the saved page
   research\fra\licences\agenceore_8us2i1a0pj4rtmhil0z42yzu.html the script reads the dataset
   title, the licence link (version 1.0 or 2.0) and the date of the last update, and writes them
   into layers\energy_consumption_agenceore_adm1.yaml in place of {VERSION}, {UPDATED} and
   {LICENSE_ID}. Anything not found -> STOP, question to [RES]; the yaml is not changed.
2. «Aggregated rows»: the operating generation rows of the ODRÉ register without a department code
   (49 in v0.1.0; 36 with a region code, 13 without). Prints how many are aggregates of
   installations under 36 kW and lists any other row (name, region, MW).
"""

from __future__ import annotations

import datetime as dt
import html
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fra_common import dept_code  # noqa: E402

REPO = Path.cwd()
PAGE = REPO / "research" / "fra" / "licences" / "agenceore_8us2i1a0pj4rtmhil0z42yzu.html"
YAML = REPO / "layers" / "energy_consumption_agenceore_adm1.yaml"
TITLE = "Consommation annuelle d'électricité et gaz par région"
V1 = r"Licence_Ouverte\.pdf|wp-content/uploads/2014/05|lov1|licence-ouverte-v1|open-licence-v1"
V2 = r"ETALAB-Licence-Ouverte-v2\.0|wp-content/uploads/2017/04|lov2|etalab-2\.0|licence-ouverte-v2"


def norm(t: str) -> str:
    t = unicodedata.normalize("NFC", html.unescape(t)).replace("’", "'").replace("\\u0027", "'")
    return re.sub(r"\s+", " ", t)


def licence() -> None:
    if not PAGE.exists():
        sys.exit(f"СТОП: нет сохранённой страницы {PAGE}")
    t = norm(PAGE.read_bytes().decode("utf-8", errors="replace"))
    problems = []
    if TITLE.lower() not in t.lower():
        problems.append(f"нет названия «{TITLE}»")
    if not re.search(r"licence ouverte", t, re.I):
        problems.append("нет «Licence Ouverte»")
    hrefs = re.findall(r'(?:href|"href")\s*[=:]\s*"([^"]+)"', t)
    v1 = [h for h in hrefs if re.search(V1, h, re.I)]
    v2 = [h for h in hrefs if re.search(V2, h, re.I)]
    # this page links to the generic Etalab page; the version is in the link's own text
    named = sorted(set(re.findall(r"Licence Ouverte / Open Licence version (\d\.\d)", t)))
    how = "link to the versioned text"
    if v1 and v2:
        problems.append(f"ссылки и на 1.0, и на 2.0: {v1[:2]} / {v2[:2]}")
    version = "1.0" if v1 and not v2 else "2.0" if v2 and not v1 else None
    if version is None and len(named) == 1:
        version, how = named[0], "version named in the licence link"
    if named and version and named != [version]:
        problems.append(f"версия в ссылке {version}, в тексте {named}")
    if version is None:
        problems.append(f"версия лицензии не определена (ссылки: {hrefs[:0]}, в тексте: {named})")
    MONTHS = {"janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
              "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12}
    m = re.search(r"Dernière mise à jour des données\s*:\s*(?:<[^>]+>\s*)*(\d{1,2}) (\w+) (\d{4})", t)
    updated = None
    if m and m.group(2).lower() in MONTHS:
        updated = f"{int(m.group(1)):02d}/{MONTHS[m.group(2).lower()]:02d}/{m.group(3)}"
    if not updated:
        m2 = re.search(r'"dataUpdatedAt"\s*:\s*"(\d{4})-(\d{2})-(\d{2})', t)
        updated = f"{m2.group(3)}/{m2.group(2)}/{m2.group(1)}" if m2 else None
    if not updated:
        problems.append("нет даты обновления данных")
    print("## 1. Атрибуция набора Agence ORE по регионам\n")
    print(f"- название: {'FOUND' if TITLE.lower() in t.lower() else 'MISSING'}")
    print(f"- лицензия: {'версия ' + version + ' (' + how + ')' if version else 'MISSING'}")
    print(f"- дата обновления данных: {updated or 'MISSING'}")
    if problems:
        sys.exit("СТОП, вопрос [RES]: " + "; ".join(problems) + ". yaml не изменён.")
    y = YAML.read_text(encoding="utf-8")
    if "{VERSION}" not in y:
        print("yaml уже заполнен — не трогаю.")
        return
    lic_id = "LicenseRef-etalab-1.0" if version == "1.0" else "etalab-2.0"
    y = y.replace("# {VERSION}/{UPDATED}/{LICENSE_ID}: filled by",
                  f"# licence version, date and id filled {dt.date.today().isoformat()} by")
    y = y.replace("{VERSION}", version).replace("{UPDATED}", updated).replace("{LICENSE_ID}", lic_id)
    if how != "link to the versioned text":
        # [RES] text says «links to version X of its text»; this page names the version instead
        y = re.sub(rf"and\s+links\s+to\s+version\s+{re.escape(version)}\s+of\s+its\s+text\.",
                   f"and names version {version} in its licence link ([RES] to confirm).", y)
    YAML.write_text(y, encoding="utf-8")
    print(f"\nВписано в {YAML.name}: version {version}, last updated {updated}, id {lic_id}.")


def aggregates() -> None:
    import build_generation_odre as g
    src = sorted(g.SRC_DIR.glob("registre-national-installation-production-stockage-electricite-agrege*.csv"))[0]
    df = pd.read_csv(src, sep=";", dtype=str, encoding="utf-8-sig", low_memory=False)
    name_col = next((c for c in ("nomInstallation", "nom_installation") if c in df.columns), None)
    df["kw"] = pd.to_numeric(df["puisMaxInstallee"].str.replace(",", "."), errors="coerce")
    d_on = pd.to_datetime(df["dateMiseEnservice (format date)"], errors="coerce", format="%Y-%m-%d")
    d_off = pd.to_datetime(df["dateDeraccordement"], errors="coerce", dayfirst=True)
    op = d_off.isna() & ~(d_on > g.SNAPSHOT) & ~df["regime"].eq("En retrait provisoire")
    gen = df[op & ~df["filiere"].fillna("").str.strip().eq(g.STORAGE_FILIERE)]
    nod = gen[gen["codeDepartement"].map(dept_code).isna()].copy()
    reg_col = next(c for c in df.columns if c.lower().replace("é", "e") in ("coderegion",))
    nod["has_region"] = nod[reg_col].fillna("").str.strip().ne("")
    name = nod[name_col].fillna("") if name_col else pd.Series("", index=nod.index)
    nod["aggregate"] = name.str.contains(r"agr[ée]g|< ?36|moins de 36", case=False, regex=True) | \
        (pd.to_numeric(nod.get("nbInstallations"), errors="coerce") > 1)
    print("\n## 2. Строки генерации без кода департамента\n")
    for lbl, part in (("с кодом региона", nod[nod["has_region"]]), ("без кода региона", nod[~nod["has_region"]])):
        print(f"- {lbl}: {len(part)} строк, {part['kw'].sum() / 1000:,.1f} МВт; агрегатов до 36 кВт: "
              f"{int(part['aggregate'].sum())}; прочих: {int((~part['aggregate']).sum())}")
    other = nod[~nod["aggregate"]]
    if len(other):
        print("\nПрочие строки (не агрегаты):")
        print(other[[c for c in (name_col, reg_col, "filiere") if c] + ["kw"]].to_string(index=False))
    else:
        print("\nВсе строки без департамента — агрегаты: слово «aggregated» в known_gaps верно.")
    if name_col:
        print("\nНазвания строк (как в реестре):", ", ".join(sorted(name.unique())[:10]))


if __name__ == "__main__":
    aggregates()
    licence()
