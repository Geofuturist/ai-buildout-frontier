"""Check saved source pages for the license and description sentences quoted in the layer texts.

SPEC_META_publish_v0_1 section 13 item 11: the paragraph is cut out by code, not retold.

Run commands (from the repository root, Windows):
    python scripts\\publish\\license_phrases.py lbnl
    python scripts\\publish\\license_phrases.py oedi

lbnl reads  research\\publish\\licences\\lbnl_queues.html or .htm  (V saves the page by hand: Ctrl+S, "Webpage, HTML only")
oedi reads  research\\publish\\licences\\nrel_oedi_8562_1.html  (saved earlier by fetch_licences.py)

Every required sentence must be found. The script prints each hit with its surroundings, writes the
same into research\\publish\\licences\\<key>_phrases.txt, and exits with 1 if a required sentence is
missing. In that case the public text is not changed by this script: ask [ARCH].
"""
from __future__ import annotations

import logging
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

log = logging.getLogger("license_phrases")

OUT_DIR = Path("research") / "publish" / "licences"

# key -> (file patterns, [(label, regex, required)])
CHECKS: dict[str, tuple[list[str], list[tuple[str, str, bool]]]] = {
    "lbnl": (
        ["lbnl_queues.html", "lbnl_queues.htm", "lbnl_queued_up_*.html"],
        [
            ("license sentence", r"Queued Up data file is licensed CC BY 4\.0", True),
            ("attribution sentence", r"attribute it to Lawrence Berkeley National Laboratory and GridTracker", True),
            ("edition", r"Queued Up 2026 Data File", False),
            ("file name", r"LBNL_Ix_Queue_Data_File_thru2025\.xlsx", False),
        ],
    ),
    "oedi": (
        ["nrel_oedi_8562_*.html", "oedi_8562*.html"],
        [
            ("license", r"CC BY 4\.0|Creative Commons Attribution 4\.0", True),
            ("retail sales", r"retail sales", True),
            ("allocation by population", r"share of (the )?state population", True),
            ("DOI", r"10\.25984/3366592", False),
            ("submitted date", r"Nov(ember)?\.? 5, 2025", False),
            ("last updated date", r"Jun(e)?\.? 2, 2026", False),
        ],
    ),
}


class _Text(HTMLParser):
    """Visible text of a page, scripts and styles dropped."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def page_text(raw: bytes) -> str:
    """Visible text with quotes and spaces normalised."""
    parser = _Text()
    parser.feed(raw.decode("utf-8", errors="replace"))
    text = " ".join(" ".join(parser.parts).split())
    return (text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
            .replace(" ", " "))


class _Links(HTMLParser):
    """All <a href> with their visible text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((" ".join(" ".join(self._buf).split()), self._href))
            self._href = None


def license_link_hrefs(raw: bytes) -> list[str]:
    """href values of every link whose visible text is 'License' / 'Licence'."""
    parser = _Links()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return [h for t, h in parser.links if re.fullmatch(r"licen[cs]e", t, re.I)]


OEDI_LICENSE_HREF = "https://creativecommons.org/licenses/by/4.0/"


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(argv) != 2 or argv[1] not in CHECKS:
        print("usage: python scripts\\publish\\license_phrases.py lbnl|oedi")
        return 2
    key = argv[1]
    patterns, phrases = CHECKS[key]
    page = next((p for pat in patterns for p in sorted(OUT_DIR.glob(pat))), None)
    if page is None:
        print(f"STOP: no saved page found in {OUT_DIR} (looked for {patterns})")
        return 2
    text = page_text(page.read_bytes())
    lines = [f"page: {page}", f"checked (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
             f"visible text length: {len(text)} characters", ""]
    missing = []
    for label, regex, required in phrases:
        m = re.search(regex, text, re.I)
        if m:
            lo, hi = max(0, m.start() - 250), min(len(text), m.end() + 250)
            lines.append(f"FOUND   {label}: ...{text[lo:hi]}...")
        else:
            lines.append(f"MISSING {label} ({'required' if required else 'optional'}): {regex}")
            if required:
                missing.append(label)
    if key == "oedi":
        hrefs = license_link_hrefs(page.read_bytes())
        lines.append("")
        lines.append(f"License link href(s) found: {hrefs}")
        if any(h.rstrip("/") + "/" == OEDI_LICENSE_HREF for h in hrefs):
            lines.append(f"HREF OK: the License link points to {OEDI_LICENSE_HREF}")
        else:
            lines.append(f"HREF MISMATCH: expected {OEDI_LICENSE_HREF}; STOP and ask RES")
            missing.append("license link href")
    lines.append("")
    lines.append("RESULT: " + ("ALL REQUIRED SENTENCES FOUND" if not missing else f"STOP, missing: {missing}"))
    report = "\n".join(lines)
    print(report)
    (OUT_DIR / f"{key}_phrases.txt").write_text(report + "\n", encoding="utf-8", newline="\n")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
