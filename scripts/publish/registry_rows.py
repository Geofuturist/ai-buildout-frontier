"""Raw records of boundaries\\boundary_registry.csv (helper module, not run directly).

Run command: none. It is imported by boundaries_build.py (check of the frozen rows) and by
patch_registry_frozen_v020.py (restore of the rows).

A "record" is one CSV row as it stands in the file (a cell may contain line breaks). Records are
compared as text after the line endings are normalised to LF: git on Windows may turn LF into CRLF
in the working copy, and that is not a change of the row.
"""
from __future__ import annotations

import csv
from pathlib import Path


def read_records(path: Path) -> tuple[str, list[str], list[tuple[str, str, list[str], str]]]:
    """Return (line ending of the file, header, records).

    Each record is (key "ISO3|LEVEL", text with LF line endings and without the final line break, cells,
    the original text of the record as it stands in the file).
    """
    raw = path.read_bytes().decode("utf-8")
    text = raw[1:] if raw.startswith("﻿") else raw
    nl = "\r\n" if "\r\n" in text else "\n"
    consumed: list[str] = []

    def feed():
        for ln in text.splitlines(keepends=True):
            consumed.append(ln)
            yield ln

    records: list[tuple[str, str, list[str], str]] = []
    header: list[str] | None = None
    for row in csv.reader(feed()):
        chunk = "".join(consumed)
        consumed.clear()
        norm = chunk.replace("\r\n", "\n").rstrip("\n")
        if header is None:
            header = row
            continue
        key = f"{row[0]}|{row[1]}" if len(row) > 1 else ""  # a blank line is kept with an empty key
        records.append((key, norm, row, chunk))
    if header is None:
        raise ValueError(f"{path}: empty file")
    return nl, header, records


def has_bom(path: Path) -> bool:
    return path.read_bytes().startswith(b"\xef\xbb\xbf")
