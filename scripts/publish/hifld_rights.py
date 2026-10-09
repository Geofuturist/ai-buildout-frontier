"""HIFLD rights check in the build (SPEC_META_publish_v0_1 section 10).

Run command: none. This is a helper module, it is imported by build_release.py.

Decision tree (rule of [ARCH], 07.10):
* The archive XML counts as dataset metadata only if it has a description
  section: ISO ``identificationInfo`` or FGDC ``idinfo``. An Esri service file
  (``<metadata><Esri>...``, element ``dataIdInfo``) does not count.
* Description section present: the three rights fields must match the expected
  text, else the build stops (rights_metadata_xml).
* No description section (or no XML): the three fields are cut from the saved
  HTML copy of the publisher's metadata (PSU Data Commons) and must match, else
  the build stops (rights_metadata_external_copy).
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from common import GateError

log = logging.getLogger("publish.hifld")


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _texts(root: ET.Element, name: str) -> list[str]:
    out = []
    for el in root.iter():
        if _local(el.tag) == name:
            text = " ".join("".join(el.itertext()).split())
            if text:
                out.append(text)
    return out


@dataclass
class RightsResult:
    """What the check found. `mode` is 'xml' or 'external_copy'."""

    mode: str
    check_id: str
    check_description: str
    fields: dict[str, Any] = field(default_factory=dict)
    published_xml: bytes | None = None
    published_xml_name: str | None = None
    known_gap: str | None = None
    warnings: list[str] = field(default_factory=list)


def classify_xml(raw: bytes) -> dict[str, Any]:
    """Root tag, top-level tags and whether the XML has a description section."""
    root = ET.fromstring(raw)
    tags = {_local(e.tag) for e in root.iter()}
    return {
        "root": _local(root.tag),
        "top_level": [_local(c.tag) for c in root],
        "iso": "identificationInfo" in tags,
        "fgdc": "idinfo" in tags,
        "esri_stub": _local(root.tag) == "metadata" and "Esri" in {_local(c.tag) for c in root},
        "root_element": root,
    }


def _iso_fields(root: ET.Element) -> dict[str, list[str]]:
    originators: list[str] = []
    for party in root.iter():
        if _local(party.tag) != "CI_ResponsibleParty":
            continue
        role = None
        for el in party.iter():
            if _local(el.tag) == "CI_RoleCode":
                role = el.attrib.get("codeListValue") or "".join(el.itertext()).strip()
        if role == "originator":
            originators += _texts(party, "organisationName")
    access = _texts(root, "accessConstraints") + _texts(root, "otherConstraints")
    for el in root.iter():
        if _local(el.tag) == "MD_RestrictionCode" and el.attrib.get("codeListValue"):
            access.append(el.attrib["codeListValue"])
    return {"originator": originators, "constraints": access, "use": _texts(root, "useLimitation")}


def _fgdc_fields(root: ET.Element) -> dict[str, list[str]]:
    return {
        "originator": _texts(root, "origin"),
        "constraints": _texts(root, "accconst"),
        "use": _texts(root, "useconst"),
    }


class _Blocks(HTMLParser):
    """Visible text of an HTML page, one string per block-level element."""

    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "div", "tr", "td", "th", "br",
             "dd", "dt", "section", "article", "blockquote", "pre"}
    SKIP = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._buf: list[str] = []
        self._skip = 0

    def _flush(self) -> None:
        text = " ".join("".join(self._buf).split())
        if text:
            self.blocks.append(text)
        self._buf = []

    def handle_starttag(self, tag, attrs) -> None:  # noqa: ANN001
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self._flush()

    def handle_endtag(self, tag) -> None:  # noqa: ANN001
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._buf.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def check_external_copy(html: str, expected: dict[str, str]) -> dict[str, Any]:
    """Cut the three rights fields out of the saved publisher page and compare."""
    parser = _Blocks()
    parser.feed(html)
    parser.close()
    blocks = parser.blocks
    low = [b.lower() for b in blocks]
    exp = {k: v.lower() for k, v in expected.items()}

    originator_block = None
    for i, b in enumerate(low):
        if re.search(r"role:\s*originator", b) and i + 1 < len(low) and exp["originator"] in low[i + 1]:
            originator_block = blocks[i + 1]
            break
    other_block = next((blocks[i] for i, b in enumerate(low)
                        if "other constraints" in b and exp["otherConstraints"] in b), None)
    use_block = next((blocks[i] for i, b in enumerate(low) if exp["useLimitation"] in b), None)
    edition_seen = any(re.search(r"2024-09-30|30 sep(tember)? 2024|09/30/2024", b) for b in low)
    return {
        "originator": originator_block,
        "otherConstraints": other_block,
        "useLimitation": use_block,
        "edition_date_seen": edition_seen,
    }


def check_hifld_rights(
    archive: Path,
    external_html: Path | None,
    expected: dict[str, str],
) -> RightsResult:
    """Run the section 10 check. Raises GateError when [ARCH] must be asked."""
    xml_name: str | None = None
    raw: bytes | None = None
    with zipfile.ZipFile(archive) as zf:
        xmls = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if xmls:
            xml_name = xmls[0]
            raw = zf.read(xml_name)

    if raw is not None:
        info = classify_xml(raw)
        log.info("HIFLD archive XML %s: root=%s top=%s iso=%s fgdc=%s", xml_name, info["root"],
                 info["top_level"], info["iso"], info["fgdc"])
        if info["iso"] or info["fgdc"]:
            fields = _iso_fields(info["root_element"]) if info["iso"] else _fgdc_fields(info["root_element"])
            joined = {
                "originator": " | ".join(fields["originator"]),
                "otherConstraints": " | ".join(fields["constraints"]),
                "useLimitation": " | ".join(fields["use"]),
            }
            for key, want in expected.items():
                if want.lower() not in joined[key].lower():
                    raise GateError(
                        "HIFLD section 10",
                        f"archive metadata has a description section but field {key} is "
                        f"{joined[key]!r}, expected {want!r}. STOP: ask [ARCH].",
                    )
            archive_stem = archive.name
            return RightsResult(
                mode="xml",
                check_id="rights_metadata_xml",
                check_description=(
                    "Originator, access constraints and use limitation read from the XML metadata "
                    "inside the HIFLD archive and compared with the expected public-domain wording."
                ),
                fields=joined,
                published_xml=raw,
                published_xml_name=f"{archive_stem}.metadata.xml",
            )
        log.info("HIFLD archive XML has no description section (Esri stub: %s): external copy is used",
                 info["esri_stub"])
    else:
        log.info("HIFLD archive has no XML: external copy is used")

    result = RightsResult(
        mode="external_copy",
        check_id="rights_metadata_external_copy",
        check_description=(
            "Originator, other constraints and use limitation cut from the saved copy of the "
            "publisher's metadata for the same edition (PSU Data Commons) and compared with the "
            "expected public-domain wording."
        ),
        known_gap=(
            "The archive carries no dataset metadata; licence status is taken from the publisher's "
            "metadata for the same edition (30 Sep 2024)."
        ),
    )
    if external_html is None or not external_html.exists():
        result.warnings.append(
            "External copy of the HIFLD metadata is not saved (research/publish/licences/"
            "hifld_transmission_lines.html): the rights check could not run."
        )
        result.check_id = ""
        return result
    found = check_external_copy(external_html.read_text(encoding="utf-8", errors="replace"), expected)
    for key in expected:
        if not found[key]:
            raise GateError(
                "HIFLD section 10",
                f"the saved copy of the publisher metadata does not contain the expected {key} "
                f"text {expected[key]!r}. STOP: ask [ARCH].",
            )
    if not found["edition_date_seen"]:
        result.warnings.append("The saved publisher page does not show the 30 Sep 2024 edition date.")
    result.fields = {k: found[k] for k in expected}
    return result
