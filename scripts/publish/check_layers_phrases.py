r"""Check the phrases of the abf-layers texts against the pages saved by hand (RES_texts_USA_states_v0_2_0.md r1, section 9;
abf-layers 0.3.0: RES_texts_USA_AKHI_v0_3_0.md r1, section 9 item 1).

Two statements of the texts rest on pages the cloud machine cannot open:
  - OEDI submission 8562 (demand): "sales ... totaled to the state level" and "allocated to counties by each county's
    share of state population". The text that depends on them: "The state is therefore closer than the county ..." in
    known_gaps of energy_demand_nrel8562_adm1.
  - EIA-860 page: the threshold "1 megawatt or greater" (known_gaps of both EIA layers) and the release date.
  - (0.3.0) the Queued Up 2026 report, a PDF saved by hand: "No data collected for Hawaii or Alaska". The text that depends
    on it: "the Queued Up report states that no data was collected for them" in known_gaps of both queue layers. The PDF is
    read with pypdf (python -m pip install pypdf) or pdfminer.six; without either, the check reports a problem.
V saves the pages in the browser (Save as, "Webpage, HTML only" or "Complete") and the release yaml names the files:

    phrase_check:
      kind: layers
      pages: {oedi_8562: 'D:\GISData\...\oedi_8562.html', eia860: 'D:\GISData\...\eia860.html',
              queued_up: 'D:\GISData\...\queued_up_2026.pdf'}

A phrase that is not found is a stop in final, a warning in dev; then the text that depends on it is removed from the
yaml (RES section 9). The check also proves that the dependent text is in the yamls, so that text and check cannot drift
apart. Exit code (as a script): 0 all found, 1 something missing, 2 a page or a yaml is not found.

Run command (from the repository root, Windows):
    python scripts\publish\check_layers_phrases.py --page oedi_8562=<file> --page eia860=<file>
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from check_dc_phrases import norm  # noqa: E402
from common import iter_strings  # noqa: E402
from license_phrases import page_text  # noqa: E402

# (key, page key, phrase in the page, text in the layer yamls that depends on it or None, blocks final?)
PHRASES: list[tuple[str, str, str, str | None, bool]] = [
    ("oedi_state_level", "oedi_8562", "to the state level",
     "retail sales reported by utilities are totaled by state", True),
    ("oedi_population_share", "oedi_8562", "each county's share of state population",
     "The state is therefore closer than the county", True),
    ("eia_threshold", "eia860", "1 megawatt or greater", "combined nameplate capacity of 1 MW or more", True),
    ("eia_release_date", "eia860", "September 10, 2026", None, False),
    ("queued_up_ak_hi", "queued_up", "No data collected for Hawaii or Alaska",
     "the Queued Up report states that no data was collected for them", True),
]


def yaml_text(layers_dir: Path) -> tuple[str, list[str]]:
    parts: list[str] = []
    missing: list[str] = []
    files = sorted(layers_dir.glob("*.yaml")) if layers_dir.exists() else []
    if not files:
        missing.append(str(layers_dir))
    for path in files:
        parts += [s for _, s in iter_strings(yaml.safe_load(path.read_text(encoding="utf-8")))]
    return norm(" ".join(parts)), missing


def pdf_text(path: Path) -> str:
    """Text of a PDF with pypdf, or pdfminer.six when pypdf is not installed. RuntimeError when neither is."""
    try:
        from pypdf import PdfReader
        return " ".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages)
    except ImportError:
        pass
    try:
        from pdfminer.high_level import extract_text
        return extract_text(str(path))
    except ImportError:
        raise RuntimeError("to read a PDF install pypdf: python -m pip install pypdf") from None


def read_page(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return pdf_text(path)
    raw = path.read_bytes()
    return page_text(raw) if path.suffix.lower() in (".html", ".htm", ".mhtml") else raw.decode("utf-8", errors="replace")


def run_check(pages: dict[str, Path], layers_dir: Path) -> tuple[list[str], list[str], list[str]]:
    """-> (report lines, phrases not found that block final, problems: pages or yamls missing)."""
    lines: list[str] = []
    not_found: list[str] = []
    problems: list[str] = []
    ytext, ymissing = yaml_text(layers_dir)
    if ymissing:
        problems.append(f"layer yamls not found in {layers_dir}")
    texts: dict[str, str] = {}
    for key, page_key, phrase, dependent, blocks in PHRASES:
        path = pages.get(page_key)
        if path is None or not Path(path).exists():
            problems.append(f"page {page_key} not found ({path})")
            lines.append(f"NO PAGE  {key}: {page_key}")
            continue
        if page_key not in texts:
            try:
                texts[page_key] = norm(read_page(Path(path)))
            except RuntimeError as exc:
                problems.append(f"page {page_key} cannot be read: {exc}")
                lines.append(f"NO TEXT  {key}: {page_key}")
                continue
        text, needle = texts[page_key], norm(phrase)
        hit = needle in text
        if not hit and blocks:
            not_found.append(key)
        state = "FOUND  " if hit else ("MISSING" if blocks else "MISSING (not quoted in the texts)")
        extra = ""
        if dependent and not ymissing:
            ok = norm(dependent) in ytext
            extra = "  [dependent text is in the yaml]" if ok else "  [DEPENDENT TEXT IS NOT IN THE YAML]"
            if not ok:
                not_found.append(f"{key} (yaml)")
            if not hit and ok:
                extra += f"  -> REMOVE from the yaml: {dependent!r}"
        lines.append(f"{state} {key}: {Path(path).name}{extra}")
        if hit:
            i = text.index(needle)
            lines.append(f"         ...{text[max(0, i - 80): i + len(needle) + 80]}...")
    return lines, not_found, problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Check the phrases of the abf-layers texts against the saved pages.")
    ap.add_argument("--page", action="append", default=[], help="key=file, keys: oedi_8562, eia860, queued_up (repeat)")
    ap.add_argument("--layers", type=Path, default=Path("layers"))
    ap.add_argument("--report", type=Path, default=Path("layers_phrases.txt"))
    a = ap.parse_args()
    pages = {k: Path(v) for k, _, v in (p.partition("=") for p in a.page)}
    lines, not_found, problems = run_check(pages, a.layers)
    head = [f"checked (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}", ""]
    tail = [""] + (["STOP, not found: " + "; ".join(problems)] if problems else [])
    tail.append("RESULT: " + ("ALL PHRASES FOUND" if not not_found and not problems else f"STOP, missing: {not_found}"))
    report = "\n".join(head + lines + tail)
    print(report)
    a.report.write_text(report + "\n", encoding="utf-8", newline="\n")
    return 2 if problems else (1 if not_found else 0)


if __name__ == "__main__":
    sys.exit(main())
