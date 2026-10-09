"""Shared helpers of the publication scripts (helper module, not run directly).

Run command: none. This is a helper module, it is imported by the other
scripts in scripts/publish/.

Everything here is deterministic on purpose: the same inputs must give
byte-identical outputs (SPEC_META_publish_v0_1 section 9, P5).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable, Iterator

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "schemas"

# G3: P9, field names. Case-insensitive. Copied verbatim from SPEC_META section 7.
P9_FIELD_REGEX = re.compile(
    r"fuel|tank|gallon|runtime|hour|redundan|autonomy|n_plus|\b2n\b|ratio|battery|"
    r"\bups\b|backup.*load|rubrique|regime",
    re.IGNORECASE,
)
# P9 in text values: only the provenance fields, whole words ([ARCH] 09.10). Names of counties and
# owners are not scanned ("Gratiot", "CORPORATION" are noise).
P9_VALUE_FIELDS = ("search_method", "ref", "notes")
P9_VALUE_REGEX = re.compile(
    r"\b(?:fuel|tank|gallon|runtime|hour|redundan\w*|autonomy|n_plus|2n|ratio|battery|ups|"
    r"backup\b.*\bload|rubrique|regime)\b",
    re.IGNORECASE,
)
CYRILLIC_REGEX = re.compile(r"[Ѐ-ӿ]")
DOI_REGEX = re.compile(r"^10\.5281/zenodo\.\d+$")
HASH_CHUNK = 8 * 1024 * 1024

log = logging.getLogger("publish")


def setup_logging(verbose: bool = False) -> None:
    """Configure the root logger once."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


class GateError(Exception):
    """A gate (G1..G12) failed. The build must stop."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"{gate}: {message}")
        self.gate = gate
        self.message = message


@dataclass
class Report:
    """Collects what goes into release_report.md (not published)."""

    title: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sections: dict[str, list[str]] = field(default_factory=dict)

    def warn(self, text: str) -> None:
        log.warning(text)
        self.warnings.append(text)

    def note(self, text: str) -> None:
        log.info(text)
        self.notes.append(text)

    def section(self, name: str, lines: Iterable[str]) -> None:
        self.sections.setdefault(name, []).extend(lines)

    def to_markdown(self) -> str:
        out = [f"# {self.title}", ""]
        out.append(f"Errors: {len(self.errors)}. Warnings: {len(self.warnings)}.")
        out.append("")
        for head, items in (("Errors", self.errors), ("Warnings", self.warnings), ("Notes", self.notes)):
            out.append(f"## {head}")
            out.extend([f"- {x}" for x in items] or ["- none"])
            out.append("")
        for name, lines in self.sections.items():
            out.append(f"## {name}")
            out.extend(lines or ["- none"])
            out.append("")
        return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- paths
def resolve_path(value: str | os.PathLike[str], base: Path | None = None) -> Path:
    """Turn a path from a yaml file into a real Path.

    Windows paths with backslashes work on any system. Relative paths are
    relative to the repository root.
    """
    text = str(value)
    if os.sep == "/" and "\\" in text:
        text = str(PureWindowsPath(text).as_posix())
    drive_root = os.environ.get("ABF_DRIVE_ROOT")  # tests on Linux: map 'D:/x' to '<root>/D:/x'
    if drive_root and re.match(r"^[A-Za-z]:", text):
        return Path(drive_root) / text
    path = Path(text)
    if not path.is_absolute() and not re.match(r"^[A-Za-z]:", text):
        path = (base or REPO_ROOT) / path
    return path


# --------------------------------------------------------------------------- hashing
def sha256_file(path: Path) -> str:
    """SHA-256 of a file, streamed."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_ref(path: Path, rel_path: str | None = None) -> dict[str, Any]:
    """Manifest-style reference: path, bytes, sha256."""
    return {
        "path": rel_path if rel_path is not None else path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


# --------------------------------------------------------------------------- files
def gzip_deterministic(src: Path, dst: Path) -> None:
    """Gzip a file with mtime=0 and no stored file name (same bytes every run)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as fin, dst.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as gz:
            shutil.copyfileobj(fin, gz, length=HASH_CHUNK)


def write_json(path: Path, obj: Any) -> None:
    """Write JSON in a fixed layout: UTF-8, 2 spaces, LF, no BOM, trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: yaml root must be a mapping")
    return data


def dump_yaml_value(text_path: Path, key: str, value: str) -> None:
    """Set one top-level `key: value` line in a yaml file, keeping comments.

    Used only to freeze built_at / locked inputs on the first build. The key
    must already exist as a line `key: ...` at column 0.
    """
    lines = text_path.read_text(encoding="utf-8").splitlines()
    pattern = re.compile(rf"^{re.escape(key)}\s*:")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key}: {value}"
            text_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            return
    raise KeyError(f"{text_path}: no top-level key '{key}'")


# --------------------------------------------------------------------------- text checks
def iter_strings(obj: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Yield (json-path, string) for every string value in a nested object."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for key, val in obj.items():
            yield from iter_strings(val, f"{path}.{key}" if path else str(key))
    elif isinstance(obj, (list, tuple)):
        for i, val in enumerate(obj):
            yield from iter_strings(val, f"{path}[{i}]")


def find_cyrillic(obj: Any, allowed_paths: tuple[str, ...] = ("title_ru",)) -> list[str]:
    """G7: json-paths of strings with Cyrillic, except the allowed ones."""
    bad = []
    for path, text in iter_strings(obj):
        if path in allowed_paths:
            continue
        if CYRILLIC_REGEX.search(text):
            bad.append(path)
    return bad


def p9_hits(names: Iterable[str]) -> list[str]:
    """G3: the names that match the P9 regular expression."""
    return [n for n in names if P9_FIELD_REGEX.search(n)]


def utc_iso(dt) -> str:  # noqa: ANN001
    """datetime -> 'YYYY-MM-DDTHH:MM:SSZ' (UTC)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def channel_prefix(channel: str) -> str:
    """Key prefix of a channel: 'dev/' or ''."""
    if channel not in ("dev", "final"):
        raise ValueError(f"channel must be dev or final, got {channel!r}")
    return "dev/" if channel == "dev" else ""


def content_headers(key: str) -> dict[str, str]:
    """Content-Type / Cache-Control / Content-Disposition by object key (SPEC section 4.1).

    Final files are immutable for a year. Manifests under manifest/ and
    everything under dev/ live for 60 seconds because they can be overwritten.
    """
    name = key.rsplit("/", 1)[-1]
    short_lived = key.startswith("dev/") or key.startswith("manifest/")
    headers = {
        "Cache-Control": "public, max-age=60" if short_lived else "public, max-age=31536000, immutable"
    }
    lower = name.lower()
    if lower.endswith(".parquet"):
        headers["Content-Type"] = "application/vnd.apache.parquet"
        headers["Content-Disposition"] = f'attachment; filename="{name}"'
    elif lower.endswith(".geojson.gz"):
        headers["Content-Type"] = "application/gzip"
        headers["Content-Disposition"] = f'attachment; filename="{name}"'
    elif lower.endswith(".csv"):
        headers["Content-Type"] = "text/csv; charset=utf-8"
        headers["Content-Disposition"] = f'attachment; filename="{name}"'
    elif lower.endswith(".pmtiles"):
        headers["Content-Type"] = "application/octet-stream"
    elif lower.endswith(".json"):
        headers["Content-Type"] = "application/json"
    elif lower.endswith(".xml"):
        headers["Content-Type"] = "application/xml"
        headers["Content-Disposition"] = f'attachment; filename="{name}"'
    elif lower.endswith(".zip"):
        headers["Content-Type"] = "application/zip"
        headers["Content-Disposition"] = f'attachment; filename="{name}"'
    elif lower.endswith(".geojson"):
        headers["Content-Type"] = "application/geo+json"
        headers["Content-Disposition"] = f'attachment; filename="{name}"'
    else:
        headers["Content-Type"] = "application/octet-stream"
    return headers


def p9_value_hits(values: Iterable[str]) -> list[str]:
    """G3 (text part): the text values that contain a P9 word as a whole word."""
    return [v for v in values if P9_VALUE_REGEX.search(v)]
