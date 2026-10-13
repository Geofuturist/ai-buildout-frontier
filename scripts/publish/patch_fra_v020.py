r"""Bring the layer yaml files of abf-fra v0.2.0 to the structure of the publish build. Safe to run twice.

Run command (from the repository root, Windows):
    python scripts\publish\patch_fra_v020.py

What it changes (each change is printed; a file that already has the change is reported as "already"):
  layers\energy_generation_odre_adm1.yaml        build structure, source/license texts of the department layer, checks
  layers\energy_consumption_agenceore_adm1.yaml  build structure, checks against the source file by region
  layers\energy_transmission_rte_adm1.yaml       build structure, source/license texts of the department layer
  layers\energy_transmission_rte_adm2.yaml       known_gaps: substations line as the second line (RES r4, section 6.1)
  layers\dc_icpe_georisques.yaml                 checked_by text, last sentence of verification.method, source_archive
                                                 (RES r4, section 6.2; ARCH 13.10)

The three region files are read and written again with a yaml parser: the content stays, comments inside
the file and the line breaks of long texts are not kept. Texts of the region files (descriptions, known_gaps,
verification) are not touched. The two other files are edited as text, so other edits in them stay.
"""
from __future__ import annotations

import copy
import re
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import REPO_ROOT  # noqa: E402

LAYERS = REPO_ROOT / "layers"

HEADER_NOTE = ("# Build structure (frame, checks, citation, tiles, source fields) added by [CODE-PUB] with "
               "scripts/publish/patch_fra_v020.py; texts by [CODE-PILOT] and [RES].")
SUBSTATIONS = "Substations are not included: the project does not collect their locations."
HOME_BBOX_ADM1 = {"iso3": "FRA", "level": "ADM1", "code_regex": r"1[1-9]|[2-9]\d"}  # 11..94: mainland and Corsica

ICPE_FIELD_OLD = "Script that selected the record; the independent agent check is in the verification log."
ICPE_FIELD_NEW = ("Script that selected the record. The independent agent's verdict on each record it checked is "
                  "published with the dataset in icpe_agent_verdicts.csv.")
ICPE_METHOD_END_OLD = "16 of these 193 records were checked.'"
ICPE_METHOD_END_NEW = ("16 of these 193 records were checked. The agent''s verdicts on all records it checked, selected and "
                       "left out, are published with the dataset in icpe_agent_verdicts.csv.'")
ICPE_ARCHIVE = """source_archive:
  path: 'data\\fra\\rules\\icpe_agent_verdicts.csv'
  kind: reference_csv
  publish_as: icpe_agent_verdicts.csv
  description: "Verdicts of the independent agent on the records it checked for the layer dc_icpe_georisques: the selected records and the records left out by the rules. One row per check, published as it is."
"""


def read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), eol


def write_text(path: Path, text: str, eol: str) -> None:
    path.write_bytes(text.replace("\n", eol).encode("utf-8"))


def source_of(cfg: dict[str, Any], source_id: str) -> dict[str, Any]:
    return next(s for s in cfg["sources"] if s["source_id"] == source_id)


def fill(target: dict[str, Any], key: str, value: Any, log: list[str], label: str) -> None:
    """Set target[key] if it is absent."""
    if key not in target:
        target[key] = copy.deepcopy(value)
        log.append(f"  set      {label}.{key}")


def replace(target: dict[str, Any], key: str, value: Any, log: list[str], label: str) -> None:
    """Set target[key] to value, also when another value is there."""
    if target.get(key) != value:
        target[key] = copy.deepcopy(value)
        log.append(f"  changed  {label}.{key}")


# ----------------------------------------------------------------------------- the three region layers
def adapt_region(layer_id: str, adm2_id: str, same_texts_as_adm2: bool, kind: str) -> list[str]:
    path = LAYERS / f"{layer_id}.yaml"
    text, eol = read_text(path)
    cfg = yaml.safe_load(text)
    adm2 = yaml.safe_load(read_text(LAYERS / f"{adm2_id}.yaml")[0])
    header = [l for l in text.split("\n") if l.startswith("#")]
    before = copy.deepcopy(cfg)
    log: list[str] = []

    fill(cfg["frame"], "code_regex", r"\d{2}", log, "frame")
    fill(cfg["frame"], "service_fields", ["unit_id", "name", "coverage_status"], log, "frame")
    fill(cfg["input"], "coverage_column", "coverage_status", log, "input")
    fill(cfg["input"], "coverage_note_column", "coverage_note", log, "input")

    # every field declares nullable (the meta schema requires it)
    for f in cfg["fields"]:
        if "nullable" not in f:
            f["nullable"] = False
            log.append(f"  set      fields.{f['name']}.nullable = false")

    # null_meaning_all_fields -> null_meaning of every nullable field (the build wants it field by field)
    allf = cfg.pop("null_meaning_all_fields", None)
    if allf is not None:
        log.append("  removed  null_meaning_all_fields (copied to the nullable fields)")
        for f in cfg["fields"]:
            if f.get("nullable"):
                nm = dict(f.get("null_meaning") or {})
                for k, v in allf.items():
                    if k == "covered" and v is None and "covered" in nm:
                        continue
                    nm.setdefault(k, v)
                f["null_meaning"] = nm
                log.append(f"  set      fields.{f['name']}.null_meaning")

    # sources
    for src in cfg["sources"]:
        sid = src["source_id"]
        label = f"sources.{sid}"
        if sid == "natural_earth_via_abf_boundaries":
            ref = source_of(adm2, sid)
            for k in ("publisher", "url", "edition", "retrieved_at", "current_through", "input_refs"):
                fill(src, k, ref[k], log, label)
            lic = src["license"]
            for k in ("id", "name", "url"):
                if lic.get(k) != ref["license"].get(k):
                    lic[k] = ref["license"][k]
                    log.append(f"  changed  {label}.license.{k}")
            rb_ref = ref["rights_basis"]
            replace(src, "rights_basis", {**rb_ref}, log, label)
        elif same_texts_as_adm2:
            # RES r4: attribution and rights_basis of generation and transmission are those of the department layer
            ref = source_of(adm2, sid)
            for k in ("publisher", "product", "url", "edition", "current_through", "retrieved_at", "input_refs"):
                replace(src, k, ref[k], log, label)
            replace(src, "license", ref["license"], log, label)
            replace(src, "rights_basis", ref["rights_basis"], log, label)
        else:  # Agence ORE by region: texts of RES r3; the check of the saved page is fra_license_pages.py apply
            fill(src, "retrieved_at", "legacy_meta", log, label)
            fill(src, "input_refs", ["table", "source_workbook"], log, label)
            src["license"].setdefault("url", adm2_license_url(cfg, adm2))
            rb = src["rights_basis"]
            fill(rb, "evidence_url", src["url"], log, label + ".rights_basis")

    # verification: levels as a full triple, empty sample_share
    ver = cfg["verification"]
    for k in ("script_rules", "human"):
        ver["levels"].setdefault(k, 0.0)
    ver.setdefault("sample_share", {})

    # the second block of the department layer that has no region counterpart: citation, tiles, checks, bbox
    fill(cfg, "citation", adm2["citation"], log, "layer")
    fill(cfg, "tiles", adm2["tiles"], log, "layer")
    disp = cfg["display"]
    fill(disp, "home_bbox_from", HOME_BBOX_ADM1, log, "display")

    if kind == "generation":
        checks = copy.deepcopy(adm2["checks"])
        t = checks["totals_vs_source"]
        t["code_column"] = "codeRegion"
        t["unit_prefix"] = "FRA-1-"
        t["outside"] = [
            {"name": "codes 975, 977, 978 (not regions)", "column": "codeDepartement", "codes": ["975", "977", "978"]},
            {"name": "rows without region code", "empty_code": True},
        ]
        fill(cfg, "checks", checks, log, "layer")
    elif kind == "consumption":
        checks = copy.deepcopy(adm2["checks"])
        t = checks["totals_vs_source"]
        t["source_file"] = str(adm2["checks"]["totals_vs_source"]["source_file"]).replace(
            "6l33py6xpnaolvzkckzkhcic", "8us2i1a0pj4rtmhil0z42yzu")
        t["code_column"] = "Code Région"
        t["unit_prefix"] = "FRA-1-"
        fill(cfg, "checks", checks, log, "layer")
    elif kind == "transmission":
        fill(cfg, "checks", copy.deepcopy(adm2["checks"]), log, "layer")
        for f in cfg["fields"]:  # the meta schema has no `max` (the 0..1 range is in the description)
            if "max" in f:
                del f["max"]
                log.append(f"  removed  fields.{f['name']}.max (not in the meta schema)")
        if cfg["freshness"].get("source_cadence") == "discontinued_geometry":  # schema list: discontinued
            cfg["freshness"] = copy.deepcopy(adm2["freshness"])
            log.append("  changed  freshness (as in the department layer: discontinued, no next_check)")
        gaps = cfg["coverage"]["known_gaps"]
        if SUBSTATIONS not in gaps:
            gaps.insert(1, SUBSTATIONS)
            log.append("  set      coverage.known_gaps[1] (substations line, RES r4 6.1)")

    if cfg != before:
        note = [HEADER_NOTE] if HEADER_NOTE not in header else []
        body = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, default_flow_style=False, width=110)
        write_text(path, "\n".join(header + note) + "\n" + body, eol)
    else:
        log.append("  already  nothing to change")
    # the result must load again and keep the layer id
    again = yaml.safe_load(read_text(path)[0])
    if again["layer_id"] != layer_id:
        raise SystemExit(f"STOP {layer_id}: the file does not load as intended")
    return log


def adm2_license_url(cfg: dict[str, Any], adm2: dict[str, Any]) -> str:
    """Url of the Licence Ouverte 2.0 text: the one the generation department layer already uses."""
    gen = yaml.safe_load(read_text(LAYERS / "energy_generation_odre_adm2.yaml")[0])
    return source_of(gen, "odre_registre")["license"]["url"]


# ----------------------------------------------------------------------------- text edits of shared files
def patch_adm2_rte() -> list[str]:
    path = LAYERS / "energy_transmission_rte_adm2.yaml"
    text, eol = read_text(path)
    if SUBSTATIONS in yaml.safe_load(text)["coverage"]["known_gaps"]:
        return ["  already  known_gaps substations line"]
    lines = text.split("\n")
    gi = next(i for i, l in enumerate(lines) if l == "  known_gaps:")
    first = gi + 1
    if not lines[first].startswith("  - "):
        raise SystemExit("STOP energy_transmission_rte_adm2: first known_gaps item not found")
    end = first + 1
    while end < len(lines) and lines[end].startswith("    "):  # continuation lines of the first item
        end += 1
    lines.insert(end, f'  - "{SUBSTATIONS}"')
    new = "\n".join(lines)
    gaps = yaml.safe_load(new)["coverage"]["known_gaps"]
    if gaps[1] != SUBSTATIONS:
        raise SystemExit("STOP energy_transmission_rte_adm2: the substations line is not second after the edit")
    write_text(path, new, eol)
    return ["  set      coverage.known_gaps[1] (substations line, RES r4 6.1)"]


def patch_icpe() -> list[str]:
    path = LAYERS / "dc_icpe_georisques.yaml"
    text, eol = read_text(path)
    log: list[str] = []
    if ICPE_FIELD_OLD in text:
        text = text.replace(ICPE_FIELD_OLD, ICPE_FIELD_NEW)
        log.append("  changed  fields.checked_by.description")
    elif ICPE_FIELD_NEW not in text:
        raise SystemExit("STOP dc_icpe_georisques: description of checked_by is neither the old nor the new text")
    if ICPE_METHOD_END_OLD in text:
        text = text.replace(ICPE_METHOD_END_OLD, ICPE_METHOD_END_NEW)
        log.append("  changed  verification.method (last sentence added)")
    elif "icpe_agent_verdicts.csv.'" not in text:
        raise SystemExit("STOP dc_icpe_georisques: end of verification.method is not as expected")
    if not re.search(r"^source_archive:", text, re.M):
        anchor = "\nfreshness:"
        if anchor not in text:
            raise SystemExit("STOP dc_icpe_georisques: block 'freshness:' not found")
        text = text.replace(anchor, "\n" + ICPE_ARCHIVE.rstrip("\n") + anchor, 1)
        log.append("  set      source_archive (icpe_agent_verdicts.csv)")
    doc = yaml.safe_load(text)
    if ICPE_FIELD_NEW not in [f.get("description") for f in doc["fields"]]:
        raise SystemExit("STOP dc_icpe_georisques: checked_by text is not as intended after the edit")
    if not doc["verification"]["method"].endswith("icpe_agent_verdicts.csv."):
        raise SystemExit("STOP dc_icpe_georisques: verification.method is not as intended after the edit")
    if doc["source_archive"]["publish_as"] != "icpe_agent_verdicts.csv":
        raise SystemExit("STOP dc_icpe_georisques: source_archive is not as intended after the edit")
    if not log:
        return ["  already  nothing to change"]
    write_text(path, text, eol)
    return log


def main() -> int:
    jobs = [
        ("energy_generation_odre_adm1", lambda: adapt_region("energy_generation_odre_adm1", "energy_generation_odre_adm2", True, "generation")),
        ("energy_consumption_agenceore_adm1", lambda: adapt_region("energy_consumption_agenceore_adm1", "energy_consumption_agenceore_adm2", False, "consumption")),
        ("energy_transmission_rte_adm1", lambda: adapt_region("energy_transmission_rte_adm1", "energy_transmission_rte_adm2", True, "transmission")),
        ("energy_transmission_rte_adm2", patch_adm2_rte),
        ("dc_icpe_georisques", patch_icpe),
    ]
    for name, job in jobs:
        print(f"== layers\\{name}.yaml")
        print("\n".join(job()))
    print("\nDone. Next: python scripts\\publish\\fra_license_pages.py apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
