r"""Find the license phrases of the 15 national sources of abf-boundaries v0.3.0 in the saved pages and files (RES_texts_BND_v0_3_0 section 9,
ARCH7 19 November, item 7). Read-only: it changes nothing and prints a report.

Run command (from the repository root, Windows):
    python scripts\publish\check_bnd_phrases.py > check_bnd_phrases.txt

Exit code 0 when every required phrase is found; 1 when one is missing (the final build must not start until it is 0).
In the dev channel a missing phrase is a warning for [CODE-PUB]; in final it is a stop.

Where it looks, for each country:
  - the saved pages, folder  D:\GISData\AI\Administrative units\<ISO3>\  (option --pages);
  - the pre-flight of CODE-BND, folder _preflight_v030 (looked for next to --work, in --work, in the repository; option --extra adds
    more folders): results.json is read per country when it names the country, otherwise it is NOT counted (it is shown as a hint);
  - the downloaded archives of the publisher in --work\sources (small text members only: xml, txt, json, html, md);
  - a saved answer of the publisher's API (HDX package_show: license_id cc-by-igo) is found as an ordinary .json file.
Text is read in several forms because pages keep their data as escaped JSON: as it is, HTML-unescaped, URL-decoded, \uXXXX-decoded.

Second part (information, does not change the exit code): the numbers of known_gaps 12-14 against the numbers inside
diag_outside_adm0_v030.json and national_adm1_report_v030.json of the output (--out), as "found / not found among the numbers
of the file". A number that is not found is a reason to look, not a proof of an error.
"""
from __future__ import annotations

import argparse
import html
import io
import json
import os
import re
import sys
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PAGES = r"D:\GISData\AI\Administrative units"
DEFAULT_WORK = r"D:\GISData\Boundaries"
DEFAULT_OUT = r"D:\GISData\Boundaries\out\abf-boundaries-v0.3.0"
TEXT_EXT = (".htm", ".html", ".mhtml", ".mht", ".pdf", ".xml", ".txt", ".json", ".md")
ZIP_KEYS = {"MEX": ["mex"], "PHL": ["phl"], "THA": ["tha"], "VNM": ["vnm"], "NZL": ["statsnz"], "IRL": ["tailte", "counties"]}
HDX_RX = r"cc-by-igo|CC BY-IGO|CC-BY-IGO|Attribution for Intergovernmental"
CC4_RX = r"Creative Commons Attribution 4\.0 International"

# country -> [(label, regex, must be found)]; files = which saved files count ("*" all, or a regex on the file name)
PHRASES: dict[str, list[tuple[str, str, bool, str]]] = {
    "COL": [("DANE citation", r"Fuente:\s*Departamento Administrativo Nacional de Estad[ií]stica", True, "*")],
    "EST": [("open data", r"on avaandmed", True, "*"), ("data date to be named", r"märkida andmete seisu kuupäev", True, "*")],
    "HKG": [("indemnify", r"indemnify", True, "*")],
    "IDN": [("no 'Hak Cipta' in the BIG metadata", r"Hak Cipta", False, r"BATAS_.*\.xml$"),
            ("no copyright sign in the BIG metadata", r"©", False, r"BATAS_.*\.xml$"),
            ("no 'Copyright' in the BIG metadata", r"Copyright", False, r"BATAS_.*\.xml$"),
            ("no 'dilindungi' in the BIG metadata", r"dilindungi", False, r"BATAS_.*\.xml$"),
            ("no 'lisensi' in the BIG metadata", r"lisensi", False, r"BATAS_.*\.xml$"),
            ("UU 28/2014 Pasal 43", r"Pasal\s+43", True, r"UU Nomor 28.*"),
            ("UU 28/2014 Pasal 35", r"Pasal\s+35", True, r"UU Nomor 28.*")],
    "IRL": [("CC BY 4.0 International", CC4_RX, True, "*")],
    "KOR": [("no restriction", r"제한\s*없음|no restriction", True, "*"),
            ("Act No. 21446 (supplementary provisions)", r"제21446호", True, "*")],
    "LUX": [("CC0", r"Creative Commons Zero|CC0", True, "*")],
    "LVA": [("CC-BY-4.0", r"CC-BY-4\.0|CC BY 4\.0", True, "*")],
    "MEX": [("HDX license CC BY-IGO", HDX_RX, True, "*")],
    "NZL": [("CC BY 4.0", r"CC BY 4\.0|" + CC4_RX, True, "*")],
    "PER": [("ODC-By", r"ODC-By|Open Data Commons Attribution", True, "*")],
    "PHL": [("HDX license CC BY-IGO", HDX_RX, True, "*"),
            ("RA 12000: Negros Island Region", r"Negros Island Region", True, r"R\.?A\.? No\. 12000.*"),
            ("EO 91: Sulu", r"Sulu", True, r"Executive Order No\. 91.*")],
    "THA": [("HDX license CC BY-IGO", HDX_RX, True, "*")],
    "TWN": [("OGDL", r"Open Government Data License", True, "*"),
            ("annex form of the attribution", r"政府資料開放授權條款|data\.gov\.tw/license", True, "*")],
    "VNM": [("HDX license CC BY-IGO", HDX_RX, True, "*")],
}

# what to save when a phrase is missing (exact addresses where they are known)
SAVE_HINT = {
    "IRL": "Save the dataset page again (Ctrl+S, 'Webpage, complete') or the item JSON: https://data-osi.opendata.arcgis.com/ (Counties - National Statutory Boundaries - Ungeneralised - 2024)",
    "NZL": "Save the Stats NZ Datafinder pages of 'Regional Council 2025 (clipped)' and 'Territorial Authority 2025 (clipped)' (the license box), https://datafinder.stats.govt.nz/",
    "MEX": "Save https://data.humdata.org/api/3/action/package_show?id=cod-ab-mex (file name package_show_cod-ab-mex.json)",
    "PHL": "Save https://data.humdata.org/api/3/action/package_show?id=cod-ab-phl (file name package_show_cod-ab-phl.json)",
    "THA": "Save https://data.humdata.org/api/3/action/package_show?id=cod-ab-tha (file name package_show_cod-ab-tha.json)",
    "VNM": "Save https://data.humdata.org/api/3/action/package_show?id=cod-ab-vnm (file name package_show_cod-ab-vnm.json)",
}

# numbers of known_gaps 12-14 and 17: (label, value, kind). kind: 'exact' = rounded as printed, 'about' = within 5 %
NUMBERS = [
    ("VNM Spratly area outside the outline, km2", 3367, "exact"), ("VNM Paracel area outside, km2", 715, "exact"),
    ("PHL Kalayaan area outside, km2", 166, "exact"), ("Khanh Hoa / Kaohsiung overlap, km2", 0.44, "exact"),
    ("Khanh Hoa / Mimaropa overlap, km2", 0.40, "exact"), ("Diaoyutai area, km2", 5.6, "exact"),
    ("Dokdo area, km2", 0.16, "exact"), ("IDN gaps total, km2", 3.90, "exact"), ("IDN gap pieces", 3124, "exact"),
    ("IDN overlap per pair up to, km2", 0.9, "exact"), ("IDN overlaps total, km2", 2.2, "exact"),
    ("HKG districts cut to the frame coastline, km2", 1036, "exact"), ("HKG districts official area, km2", 2755, "exact"),
    ("IDN outside the outline, km2", 32300, "about"), ("LVA outside the outline, km2", 70, "about"),
]


def variants(text: str) -> list[str]:
    """The text as it is and in the forms in which pages keep escaped data."""
    out = [text]
    un = html.unescape(text)
    uq = urllib.parse.unquote(un)
    uni = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), uq)
    for t in (un, uq, uni, html.unescape(uni)):
        if t not in out:
            out.append(t)
    return out


def page_text(path: Path, raw: bytes | None = None) -> str:
    raw = path.read_bytes() if raw is None else raw
    suf = path.suffix.lower()
    if suf == ".pdf":
        try:
            from pypdf import PdfReader
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(raw)).pages)
        except Exception as e:  # noqa: BLE001
            return f"[pdf not read: {e}]"
    if suf in (".mhtml", ".mht"):
        import email
        from email import policy
        msg = email.message_from_bytes(raw, policy=policy.default)
        parts = []
        for part in msg.walk():
            if part.get_content_type() in ("text/html", "text/plain"):
                try:
                    parts.append(part.get_content())
                except Exception:  # noqa: BLE001
                    parts.append(part.get_payload(decode=True).decode("utf-8", "replace"))
        return "\n".join(parts)
    text = raw.decode("utf-8", "replace")
    return text      # scripts stay in the text: pages keep their data there


def squash(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", t))


SKIP_EXT = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".gpkg", ".parquet", ".gdb", ".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff",
            ".webp", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".mp4", ".sbn", ".sbx", ".atx", ".gdbtable", ".gdbtablx", ".freelist",
            ".spx", ".gz", ".7z", ".rar", ".xlsx", ".xls", ".docx", ".doc"}
MAX_TEXT = 40_000_000


def find_country_dirs(pages: Path, iso: str) -> list[Path]:
    """Folders of the country in the saved pages: the name is the ISO3 code in any letter case (MEX, mex, Mex)."""
    if not pages.exists():
        return []
    return [d for d in sorted(pages.iterdir()) if d.is_dir() and d.name.lower() == iso.lower()]


def find_preflight_dirs(roots: list[Path]) -> list[Path]:
    """Folders named _preflight_v030 (any letter case) within four levels below the roots."""
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists() or root in seen:
            continue
        seen.add(root)
        base = len(root.parts)
        for cur, dirs, _ in os.walk(root):
            if len(Path(cur).parts) - base >= 4:
                dirs[:] = []
            for d in list(dirs):
                if d.lower() == "_preflight_v030":
                    found.append(Path(cur) / d)
                    dirs.remove(d)
    return found


def read_member(path: Path, raw: bytes) -> str | None:
    suf = path.suffix.lower()
    if suf in SKIP_EXT:
        return None
    try:
        return page_text(path, raw)
    except Exception:  # noqa: BLE001
        return None


def collect(iso: str, pages: Path, work: Path, extra: list[Path], notes: list[str]) -> list[dict]:
    """Every file found for the country: dict(key, text or None, size, note). Looks at ALL files of the country folder,
    whatever their folder (Pages, pages, files, ...) or letter case; zip archives are opened."""
    recs: list[dict] = []

    def add(label: str, name: str, size: int, text: str | None, note: str = "") -> None:
        recs.append({"key": f"{label}:{name}", "label": label, "name": name, "size": size, "text": text, "note": note})

    dirs = find_country_dirs(pages, iso)
    if not dirs:
        have = sorted(d.name for d in pages.iterdir() if d.is_dir()) if pages.exists() else []
        notes.append(f"{iso}: no folder named {iso} in {pages}; folders there: {have}")
    for d in dirs:
        for p in sorted(d.rglob("*")):
            if not p.is_file():
                continue
            rel = str(p.relative_to(d))
            size = p.stat().st_size
            if p.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(p) as zf:
                        n = 0
                        for m in zf.infolist():
                            if m.file_size < 5_000_000 and not m.is_dir():
                                t = read_member(Path(m.filename), zf.read(m))
                                if t is not None:
                                    add("page", f"{rel}!{m.filename}", m.file_size, t)
                                    n += 1
                        add("page", rel, size, None, f"zip archive, {n} readable member(s) listed separately")
                except Exception as e:  # noqa: BLE001
                    add("page", rel, size, None, f"zip not read: {e}")
            elif p.suffix.lower() in SKIP_EXT:
                add("page", rel, size, None, "not text (type skipped)")
            elif size > MAX_TEXT:
                add("page", rel, size, None, f"too large to read (over {MAX_TEXT // 1_000_000} MB)")
            else:
                try:
                    add("page", rel, size, page_text(p))
                except Exception as e:  # noqa: BLE001
                    add("page", rel, size, None, f"not read: {e}")
    roots = [work / "_preflight_v030", work / "out" / "_preflight_v030", Path("_preflight_v030"),
             pages.parent / "_preflight_v030", pages / "_preflight_v030"] + extra
    roots += find_preflight_dirs([pages, pages.parent, work, Path.cwd(), Path.cwd().parent])
    seen_dirs: set[Path] = set()
    for r in roots:
        if not r.exists() or r.resolve() in seen_dirs:
            continue
        seen_dirs.add(r.resolve())
        for p in sorted(r.rglob("*")):
            if not p.is_file() or p.suffix.lower() in SKIP_EXT or p.stat().st_size > 200_000_000:
                continue
            if p.name.lower() == "results.json":
                try:
                    data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                except Exception as e:  # noqa: BLE001
                    notes.append(f"{p}: not JSON: {e}")
                    continue
                parts = _country_parts(data, iso)
                if parts:
                    add("preflight", f"{p.parent.name}/results.json[{iso}]", p.stat().st_size, json.dumps(parts, ensure_ascii=False))
                else:
                    notes.append(f"{iso}: {p} does not name the country: not counted")
            elif iso.lower() in p.name.lower() or iso.lower() in [x.lower() for x in p.parts]:
                try:
                    add("preflight", str(p.relative_to(r)), p.stat().st_size, page_text(p))
                except Exception as e:  # noqa: BLE001
                    notes.append(f"{iso}: {p} not read: {e}")
    src = work / "sources"
    if src.exists():
        for z in sorted(src.glob("*.zip")):
            if not any(k in z.name.lower() for k in ZIP_KEYS.get(iso, [])):
                continue
            try:
                with zipfile.ZipFile(z) as zf:
                    for m in zf.infolist():
                        if m.file_size < 5_000_000 and m.filename.lower().endswith((".xml", ".txt", ".json", ".htm", ".html", ".md")):
                            add("archive", f"{z.name}!{m.filename}", m.file_size, page_text(Path(m.filename), zf.read(m)))
            except Exception as e:  # noqa: BLE001
                notes.append(f"{iso}: archive {z.name} not read: {e}")
    return recs


def _country_parts(data, iso: str):
    """Sub-objects of a pre-flight JSON that belong to the country."""
    hits = []

    def walk(o, key=None):
        if isinstance(o, dict):
            if key == iso or any(str(o.get(k, "")).upper() == iso for k in ("iso3", "country", "iso", "id")):
                hits.append(o)
                return
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, list):
            for v in o:
                walk(v, key)
    walk(data)
    return hits


def hit_count(rx: str, text: str) -> int:
    return max((len(re.findall(rx, v, re.I)) for v in variants(text) + [squash(t) for t in variants(text)]), default=0)


def check_phrases(pages: Path, work: Path, extra: list[Path]) -> int:
    bad = 0
    notes: list[str] = []
    to_save: dict[str, list[str]] = {}
    for iso, specs in PHRASES.items():
        recs = collect(iso, pages, work, extra, notes)
        print(f"\n{iso}: {len(recs)} file(s) looked at")
        for r in recs:
            if r["text"] is None:
                print(f"    {r['key']} | {r['size']} bytes | {r['note']}")
                continue
            hits = [f"{label}={n}" for label, rx, _, _ in specs if (n := hit_count(rx, r["text"]))]
            print(f"    {r['key']} | {r['size']} bytes | " + ("found: " + "; ".join(hits) if hits else "no phrase of this country"))
        for label, rx, must, files in specs:
            where = []
            in_scope = 0
            for r in recs:
                if r["text"] is None:
                    continue
                base = r["name"].split("!")[0].split("/")[-1].split("\\")[-1]
                if files != "*" and not re.search(files, base, re.I):
                    continue
                in_scope += 1
                if hit_count(rx, r["text"]):
                    where.append(r["key"])
            ok = bool(where) if must else (not where and in_scope > 0)
            bad += not ok
            if not ok and must:
                to_save.setdefault(iso, []).append(label)
            state = "FOUND" if where else ("not found" if in_scope else "no file to look in")
            print(f"  [{'OK' if ok else 'MISSING'}] {label}: {state}" + (f" in {where[:3]}" if where else ""))
            if not ok and must and files != "*":
                # a phrase tied to one file: show what the program could read from that file
                words = re.findall(r"[A-Za-z]{5,}", rx)
                word = words[0] if words else ""
                for r in recs:
                    base = r["name"].split("!")[0].split("/")[-1].split("\\")[-1]
                    if r["text"] is None or not re.search(files, base, re.I):
                        continue
                    t = squash(r["text"])
                    m = re.search(re.escape(word), t, re.I) if word else None
                    ctx = t[max(0, m.start() - 60): m.end() + 80] if m else ""
                    print(f"      read from {r['key']}: {len(t)} characters of text; '{word}' x{len(re.findall(re.escape(word), t, re.I)) if word else 0}"
                          + (f"; context: ...{ctx}..." if ctx else "; the file has no text layer or the word is written differently"))
    if to_save:
        print("\n== pages to save by hand (only for what was not found above) ==")
        for iso, labels in to_save.items():
            print(f"  {iso}: missing {labels}")
            hint = SAVE_HINT.get(iso, 'Save the page that states the license or the law into the folder of the country.')
            if iso == "PHL" and any(l.startswith("RA 12000") for l in labels) and not any(l.startswith("HDX") for l in labels):
                hint = ("The HDX license is already found. For RA 12000 open 'R.A. No. 12000.pdf' and look for 'Negros Island Region'; "
                        "if the PDF is a scan (see the characters line above), save the text of the act as R.A. No. 12000.txt next to it.")
            print(f"      {hint}")
            print(f"      Put the file anywhere under D:\\GISData\\AI\\Administrative units\\{iso}\\ (any subfolder).")
    if notes:
        print("\nnotes:")
        for n in notes:
            print("  -", n)
    return bad


def all_numbers(o, out: list[float]) -> None:
    if isinstance(o, bool):
        return
    if isinstance(o, (int, float)):
        out.append(float(o))
    elif isinstance(o, dict):
        for v in o.values():
            all_numbers(v, out)
    elif isinstance(o, list):
        for v in o:
            all_numbers(v, out)
    elif isinstance(o, str):
        for m in re.findall(r"-?\d+(?:\.\d+)?", o):
            out.append(float(m))


def check_numbers(out_dir: Path) -> None:
    print("\n\n== numbers of known_gaps against the diagnostics of the output (information only) ==")
    nums: list[float] = []
    for name in ("diag_outside_adm0_v030.json", "national_adm1_report_v030.json"):
        p = out_dir / name
        if not p.exists():
            print(f"  {name}: not found in {out_dir}")
            continue
        try:
            all_numbers(json.loads(p.read_text(encoding="utf-8")), nums)
        except Exception as e:  # noqa: BLE001
            print(f"  {name}: not read: {e}")
    if not nums:
        return
    pool = nums + [n / 1e6 for n in nums if n > 1e5]     # areas given in m2
    for label, val, kind in NUMBERS:
        if kind == "about":
            hit = [n for n in pool if abs(n - val) <= 0.05 * val]
        else:
            dec = len(str(val).split(".")[1]) if "." in str(val) else 0
            half = 0.5 * 10 ** -dec
            hit = [n for n in pool if abs(n - val) <= half + 1e-9]
        print(f"  {'found    ' if hit else 'NOT FOUND'} {label}: {val}" + (f"  (e.g. {hit[0]:g})" if hit else ""))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pages", default=DEFAULT_PAGES)
    ap.add_argument("--work", default=DEFAULT_WORK)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--extra", action="append", default=[], help="another folder with saved files (repeatable)")
    args = ap.parse_args(argv[1:])
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    print("check_bnd_phrases: license phrases of the 15 national sources of abf-boundaries 0.3.0")
    bad = check_phrases(Path(args.pages), Path(args.work), [Path(x) for x in args.extra])
    check_numbers(Path(args.out))
    print(f"\nRESULT: {bad} required phrase(s) missing" + ("; the final build must wait." if bad else "; phrases are in place."))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
