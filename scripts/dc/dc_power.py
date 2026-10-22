r"""abf-dc: power fields and the cross-layer P9 check (SPEC_DC_world_v0_1_0 r2, section 2.4). Not run on its own.

Epoch:  power_mw = `Current power (MW)` (IT power, as defined by Epoch), power_basis = epoch_it_power. 0 MW is a value, not a gap.
Atlas:  power_class from the Atlas size class, power_basis = atlas_size_class, power_mw absent. `Unknown` -> not_found / no_basis_value.
P9:     an Epoch site whose pilot cell `epoch_dc` = found points at a pilot object with power_basis = deq_backup_gen_nameplate gets
        power_mw empty and power_status = withheld / p9_other_basis. Expected: 0.
"""

from __future__ import annotations

import csv
from pathlib import Path

CLASS_MAP = {
    "Small (<10 MW)": "lt10",
    "Large (10-99 MW)": "10_99",
    "Hyperscale (100-999 MW)": "100_999",
    "Gigascale (>999 MW)": "ge1000",
}
CLASS_ORDER = ["lt10", "10_99", "100_999", "ge1000"]


def atlas_power(capacity_type: str) -> dict:
    if capacity_type in CLASS_MAP:
        return dict(power_class=CLASS_MAP[capacity_type], power_basis="atlas_size_class", power_status="found", power_status_reason="")
    if capacity_type == "Unknown":
        return dict(power_class="", power_basis="atlas_size_class", power_status="not_found", power_status_reason="no_basis_value")
    from dc_lib import BuildStop
    raise BuildStop(f"Atlas capacity_type {capacity_type!r} is not in the class table")


def p9_withheld(pilot_dir: Path) -> tuple[dict[str, str], list[dict]]:
    """-> ({Epoch Name: pilot record_id} to withhold, the list for the report)."""
    objs = {r["record_id"]: r for r in csv.DictReader(open(Path(pilot_dir) / "objects.csv", encoding="utf-8-sig", newline=""))}
    out, rows = {}, []
    for c in csv.DictReader(open(Path(pilot_dir) / "checks.csv", encoding="utf-8-sig", newline="")):
        if c["channel"] == "epoch_dc" and c["status"] == "found":
            o = objs.get(c["record_id"])
            if o is not None and o["power_basis"] == "deq_backup_gen_nameplate":
                out[c["ref"]] = c["record_id"]
                rows.append(dict(epoch_name=c["ref"], pilot_record_id=c["record_id"], pilot_power_basis=o["power_basis"]))
    return out, rows


def epoch_power(raw_value: str, name: str, withheld: dict[str, str], source_date: str) -> dict:
    base = dict(power_basis="epoch_it_power", power_ref=name, power_source_date=source_date, power_checked_by="script:dc_power")
    if name in withheld:
        return dict(base, power_mw="", power_status="withheld", power_status_reason="p9_other_basis")
    v = raw_value.strip()
    if v == "":
        return dict(base, power_mw="", power_status="not_found", power_status_reason="no_basis_value")
    return dict(base, power_mw=v, power_status="found", power_status_reason="")
