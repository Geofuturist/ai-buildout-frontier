r"""Check the phrases of the abf-dc texts against the saved source pages (RES_texts_DC_v0_1_0.md r2, section 10).

The public texts of abf-dc quote the licence and method pages of the Atlas of Data Center Politics, of Epoch AI and
of GeoNames. Before the final build every phrase must be found, by code, in the page that was saved when the text
was written; a phrase that is not found means STOP and a question to [RES]. The text is never edited by eye.

Run command (from the repository root, Windows):
    python scripts\publish\check_dc_phrases.py --pages "D:\GISData\AI\DC\abf-scratch-dc\research\dc_world\inputs\licence_pages" --geonames-readme "D:\GISData\AI\DC\abf-scratch-dc\research\dc_world\inputs\geonames\Readme.txt"

What it does:
  1. looks for every phrase in the visible text of its page (HTML pages are cut to visible text; quotes, dashes and
     spaces are normalized; capitals do not matter);
  2. for the phrases that the layer yamls quote word for word (licence sentences, citations), checks that the yaml
     text really contains the phrase, so the text and the check cannot drift apart;
  3. prints FOUND / MISSING for each phrase, writes the same to --report (default: dc_phrases.txt in the current folder).
Exit code: 0 all phrases found, 1 something is missing, 2 a page or a yaml is not found.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from common import iter_strings  # noqa: E402
from license_phrases import page_text  # noqa: E402

LAYER_YAMLS = ("dc_atlas_points.yaml", "dc_epoch_points.yaml", "dc_atlas_count_adm0.yaml")

# (key, page file name, phrase, quoted word for word in the layer yamls?)
PHRASES: list[tuple[str, str, str, bool]] = [
    ("atlas_licence", "atlas_LICENSE-DATA.html",
     "The Atlas datasets are licensed under the Creative Commons Attribution 4.0 International Licence (CC BY 4.0).", True),
    ("atlas_citation", "infrastructurelab_atlas_project.html",
     "Kollar, Justin. Atlas of Data Center Politics. Version 0.1.0. Infrastructure Lab, National University of Singapore, 2026.", True),
    ("atlas_adapt", "atlas_LICENSE-DATA.html", "Where you adapt or filter the data, say so", False),
    ("atlas_automated_access", "atlas_LICENSE-DATA.html", "A REQUEST ABOUT AUTOMATED ACCESS - NOT A LICENCE CONDITION", False),
    ("atlas_absence", "infrastructurelab_atlas_project.html",
     "Absence from the Atlas should therefore not be interpreted as evidence that a facility", False),
    ("atlas_coverage", "infrastructurelab_atlas_project.html", "Coverage is broad but uneven", False),
    ("atlas_confidence", "infrastructurelab_atlas_project.html",
     "Positional confidence describes the precision of that location rather than the overall reliability of the record.", False),
    ("atlas_incomplete", "atlas_LICENSE-DATA.html", "It is incomplete, it contains errors, and it changes between versions.", False),
    ("epoch_licence", "data-centers_page.html",
     "free to use, distribute, and reproduce provided the source and authors are credited under the Creative Commons Attribution license", True),
    ("epoch_citation", "data-centers_page.html", "Epoch AI, 'AI data centers'. Published online at epoch.ai.", True),
    ("epoch_priority", "doc_methodology.html", "We mostly prioritize AI data centers by computing capacity", False),
    ("epoch_us_share", "doc_methodology.html", "The database mostly consists of data centers in the United States", False),
    ("epoch_it_power", "doc_records.html",
     "IT power is the power available to GPU servers, network infrastructure and storage, excluding cooling and other facility overhead.", False),
    ("epoch_facility_power", "data-centers_page.html", "Total facility power is 20-50% higher", False),
    ("epoch_models", "doc_methodology.html",
     "we apply well-vetted models to estimate key metrics such as IT power capacity, AI compute, and capital costs", False),
    ("epoch_coverage_44", "doc_methodology.html",
     "coverage of global deployed AI computing capacity to be 44% as of October 14, 2026 (90% CI: 23% to 81%)", False),
    ("geonames_licence", "Readme.txt", "This work is licensed under a Creative Commons Attribution 4.0 License", True),
]


def norm(text: str) -> str:
    """Quotes, dashes and spaces in one form (no space before punctuation); lower case."""
    t = (text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
         .replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-").replace("\u00a0", " "))
    t = " ".join(t.split())
    return re.sub(r"\s+([.,;:!?])", r"\1", t).lower()   # a tag boundary leaves "Politics ." in the visible text


def find_page(pages: Path, name: str, geonames_readme: Path | None) -> Path | None:
    if name == "Readme.txt":
        return geonames_readme if geonames_readme and geonames_readme.exists() else None
    found = sorted(pages.rglob(name)) if pages.exists() else []
    return found[0] if found else None


def yaml_text(layers_dir: Path) -> tuple[str, list[str]]:
    """All strings of the layer yamls as one normalized text; the names of yamls that are missing."""
    parts, missing = [], []
    for name in LAYER_YAMLS:
        path = layers_dir / name
        if not path.exists():
            missing.append(name)
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        parts += [s for _, s in iter_strings(data)]
    return norm(" ".join(parts)), missing


def run_check(pages: Path, geonames_readme: Path | None, layers_dir: Path) -> tuple[list[str], list[str], list[str]]:
    """-> (report lines, phrases not found, problems that stop the check: pages or yamls missing)."""
    lines: list[str] = []
    not_found: list[str] = []
    problems: list[str] = []
    texts: dict[Path, str] = {}
    ytext, ymissing = yaml_text(layers_dir)
    if ymissing:
        problems.append(f"layer yamls not found in {layers_dir}: {ymissing}")
    for key, page_name, phrase, quoted in PHRASES:
        page = find_page(pages, page_name, geonames_readme)
        if page is None:
            problems.append(f"page {page_name} not found under {pages}")
            lines.append(f"NO PAGE  {key}: {page_name}")
            continue
        if page not in texts:
            raw = page.read_bytes()
            texts[page] = page_text(raw) if page.suffix.lower() in (".html", ".htm") else raw.decode("utf-8", errors="replace")
        text = norm(texts[page])
        needle = norm(phrase)
        hit = needle in text
        yaml_ok = (needle in ytext) if (quoted and not ymissing) else None
        state = "FOUND  " if hit else "MISSING"
        if not hit:
            not_found.append(key)
        extra = ""
        if quoted and not ymissing:
            extra = "  [yaml quotes it]" if yaml_ok else "  [YAML DOES NOT CONTAIN IT]"
            if not yaml_ok:
                not_found.append(f"{key} (yaml)")
        lines.append(f"{state} {key}: {page.name}{extra}")
        if hit:
            i = text.index(needle)
            lines.append(f"         ...{text[max(0, i - 60): i + len(needle) + 60]}...")
    return lines, not_found, problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Check the quoted phrases of the abf-dc texts against the saved pages.")
    ap.add_argument("--pages", required=True, type=Path, help="folder licence_pages (atlas/, epoch/)")
    ap.add_argument("--geonames-readme", type=Path, help="Readme.txt of the GeoNames download")
    ap.add_argument("--layers", type=Path, default=Path("layers"), help="folder with the layer yamls (default: layers)")
    ap.add_argument("--report", type=Path, default=Path("dc_phrases.txt"))
    a = ap.parse_args()
    lines, not_found, problems = run_check(a.pages, a.geonames_readme, a.layers)
    head = [f"checked (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}", f"pages: {a.pages}", ""]
    tail = [""]
    if problems:
        tail.append("STOP, not found: " + "; ".join(problems))
    tail.append("RESULT: " + ("ALL PHRASES FOUND" if not not_found and not problems else f"STOP, missing: {not_found}"))
    report = "\n".join(head + lines + tail)
    print(report)
    a.report.write_text(report + "\n", encoding="utf-8", newline="\n")
    if problems:
        return 2
    return 1 if not_found else 0


if __name__ == "__main__":
    sys.exit(main())
