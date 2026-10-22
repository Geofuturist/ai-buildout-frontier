r"""abf-dc: shared helpers (SPEC_DC_world_v0_1_0 r2). Not run on its own.

Text normalisation, the address parser (rules of the scouting run, ported without changes of meaning),
loaders for the inputs. Everything is exact matching: no fuzzy comparison anywhere (SPEC section 2.3).
"""

from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd


class BuildStop(SystemExit):
    """A build check failed: the run stops (SPEC section 2.9)."""

    def __init__(self, msg: str):
        super().__init__("STOP: " + msg)


# ----------------------------------------------------------------------------------------------- text

def norm(s) -> str:
    """NFKD, no diacritics, casefold, non-alphanumerics -> space; 'St.'/'Ste.' -> saint/sainte (the only replacement)."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"\bst\b\.?", "saint", s)
    s = re.sub(r"\bste\b\.?", "sainte", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def ws(s) -> str:
    """NFC, whitespace collapsed and trimmed (record_id normalisation)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s))).strip()


def sha12(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def slug(s: str) -> str:
    t = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", t)).strip("-")


def one_line(s: str) -> str:
    """Line breaks -> ' | ' (SPEC r2 section 9 Q8)."""
    parts = [p.strip() for p in re.split(r"[\r\n]+", str(s)) if p.strip()]
    return " | ".join(parts)


# ----------------------------------------------------------------------------------------------- address parser
US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY",
    "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC"}
US_ABBR = set(US_STATES.values())
AU_STATES = {"new south wales": "NSW", "victoria": "VIC", "queensland": "QLD", "south australia": "SA", "western australia": "WA",
             "tasmania": "TAS", "northern territory": "NT", "australian capital territory": "ACT"}
AU_ABBR = set(AU_STATES.values())
CA_PROV = {"alberta": "AB", "british columbia": "BC", "manitoba": "MB", "new brunswick": "NB", "newfoundland and labrador": "NL", "nova scotia": "NS",
           "ontario": "ON", "prince edward island": "PE", "quebec": "QC", "québec": "QC", "saskatchewan": "SK", "northwest territories": "NT",
           "nunavut": "NU", "yukon": "YT"}
CA_ABBR = set(CA_PROV.values())
COUNTRY_TOKENS = {  # extended from countryInfo.txt and the alias table by `extend_country_tokens`
    "united states of america": "US", "united states": "US", "usa": "US", "us": "US", "u.s.a.": "US", "uk": "GB", "uae": "AE"}
STREET_WORDS = re.compile(
    r"\b(st|street|rd|road|ave|avenue|blvd|boulevard|dr|drive|ln|lane|pkwy|parkway|way|hwy|highway|route|rue|ct|court|cir|circle|pl|place|"
    r"terrace|trail|park|loop|pike|expressway|fwy|freeway|suite|unit|level|building|floor|campus|industrial|estate|business|centre|center|"
    r"chemin|avenue|boulevard|impasse|allée|zone|zi|za|po box|route|county|co rd|cr|sh|bldg)\b", re.I)
LEAD_NUM = re.compile(r"^\s*(#?\d)")


def looks_street(tok: str) -> bool:
    return bool(LEAD_NUM.match(tok) or STREET_WORDS.search(tok))


def extend_country_tokens(country_info_names: dict[str, str], aliases: dict[str, str]) -> None:
    """Names of countries (GeoNames countryInfo) and accepted aliases become 'country tail' tokens (name -> ISO2)."""
    for name, iso2 in country_info_names.items():
        if name.casefold() not in US_STATES:          # 'Georgia' is also a US state
            COUNTRY_TOKENS.setdefault(name.casefold(), iso2)
    for name, iso2 in aliases.items():
        if name.casefold() not in US_STATES:
            COUNTRY_TOKENS.setdefault(name.casefold(), iso2)


def parse_address(addr: str, iso2_hint: str = "") -> dict:
    """-> dict(country_iso, region, postcode, locality, locality_candidates, rule, status). Rules: see the scouting run
    (PREFLIGHT_DC_world_v0_2 section 4): US_STATE(_ZIP), FR_POSTCODE, AU_STATE_POST, CA_PROV, IE_COUNTY_DISTRICT, GENERIC_POSTCODE, GENERIC_LAST."""
    out = dict(country_iso="", region="", postcode="", locality="", locality_candidates="", rule="", status="")
    a = (addr or "").strip()
    if not a:
        out["status"] = "no_address"
        return out
    toks = [t.strip() for t in re.split(r",|\s/\s", a) if t.strip()]
    posts: list[str] = []
    while toks and re.fullmatch(r"[0-9]{4,6}", toks[-1]):
        posts.append(toks.pop())
    iso = ""
    if toks and toks[-1].casefold() in COUNTRY_TOKENS:
        iso = COUNTRY_TOKENS[toks.pop().casefold()]
    while toks and re.fullmatch(r"[0-9]{4,6}", toks[-1]):
        posts.append(toks.pop())
    if not iso and iso2_hint:
        iso = iso2_hint
    out["country_iso"] = iso
    if posts:
        out["postcode"] = posts[0]
    if not toks:
        out.update(status="no_locality", rule="COUNTRY_ONLY")
        return out
    if iso == "US" or (not iso and any(re.search(r"\b(" + "|".join(US_ABBR) + r")\s*\d{5}", t) for t in toks)):
        st_pat = re.compile(r"^(?P<pre>.*?)\s*\b(?P<st>" + "|".join(sorted([k.title() for k in US_STATES] + list(US_ABBR), key=len, reverse=True))
                            + r")\b\.?\s*(?P<zip>\d{5}(?:-\d{4})?)?$", re.I)
        for idx in range(len(toks) - 1, -1, -1):
            m = st_pat.match(toks[idx])
            if m and (m.group("st").upper() in US_ABBR or m.group("st").casefold() in US_STATES):
                st = m.group("st")
                st = st.upper() if st.upper() in US_ABBR else US_STATES[st.casefold()]
                out["region"], out["country_iso"] = st, "US"
                if m.group("zip"):
                    out["postcode"] = m.group("zip")
                pre = m.group("pre").strip()
                cand = pre if pre else (toks[idx - 1] if idx > 0 else "")
                if not pre and re.fullmatch(r"\d{5}", cand) and idx > 1:
                    out["postcode"] = cand
                    cand = toks[idx - 2]
                ok = (not LEAD_NUM.match(cand)) if pre else (not looks_street(cand))
                if cand and ok:
                    out.update(locality=cand, rule="US_STATE_ZIP" if m.group("zip") else "US_STATE", status="parsed")
                else:
                    out.update(rule="US_STATE", status="no_locality", locality_candidates=cand)
                return out
        out.update(rule="US_NO_STATE", status="no_locality", locality_candidates=" | ".join(reversed(toks[-3:])))
        return out
    if iso == "FR":
        hits = [(i, re.match(r"^(\d{5})\s+(.+?)(?:\s+Cedex(?:\s+\d+)?)?$", t)) for i, t in enumerate(toks)]
        hits = [(i, m) for i, m in hits if m]
        if len(hits) == 1:
            i, m = hits[0]
            out.update(postcode=m.group(1), locality=m.group(2).strip(), rule="FR_POSTCODE", status="parsed")
            if i + 1 < len(toks):
                out["region"] = toks[i + 1]
            return out
        if len(hits) > 1:
            out.update(postcode=hits[0][1].group(1), locality_candidates=" | ".join(m.group(2) for _, m in hits), rule="FR_POSTCODE", status="ambiguous")
            return out
        out.update(rule="FR_NO_POSTCODE", status="no_locality", locality_candidates=" | ".join(reversed(toks[-3:])))
        return out
    if iso == "AU":
        for t in reversed(toks):
            m = re.match(r"^(?P<loc>.+?)\s+(?P<st>" + "|".join(AU_ABBR) + r")(?:\s+(?P<pc>\d{4}))?$", t)
            if m and not LEAD_NUM.match(m.group("loc")):
                out.update(locality=m.group("loc"), region=m.group("st"), postcode=m.group("pc") or "", rule="AU_STATE_POST", status="parsed")
                return out
        out.update(rule="AU_STATE_POST", status="no_locality", locality_candidates=" | ".join(reversed(toks[-3:])))
        return out
    if iso == "CA":
        prov_names = "|".join(sorted(CA_PROV, key=len, reverse=True))
        prov_abbr = "|".join(CA_ABBR)
        pc = r"(?:[A-Z]\d[A-Z]\s?\d[A-Z]\d)?"
        for idx in range(len(toks) - 1, -1, -1):
            m = re.match(r"^(?P<pre>.*?)\s*\b(?P<pv>" + prov_names + "|" + prov_abbr + r")\b\s*(?P<pc>" + pc + r")$", toks[idx], re.I)
            if m:
                pre = m.group("pre").strip()
                cand = pre if pre else (toks[idx - 1] if idx else "")
                pv = m.group("pv")
                out["region"] = CA_PROV.get(pv.casefold(), pv.upper())
                out["postcode"] = m.group("pc") or out["postcode"]
                if cand and ((not LEAD_NUM.match(cand)) if pre else (not looks_street(cand))):
                    out.update(locality=cand, rule="CA_PROV", status="parsed")
                else:
                    out.update(rule="CA_PROV", status="no_locality", locality_candidates=cand)
                return out
        out.update(rule="CA_PROV", status="no_locality")
        return out
    if iso == "IE":
        t2 = [t for t in toks if not re.fullmatch(r"[A-Z]\d{2}\s?[A-Z0-9]{4}", t)]
        if len(t2) != len(toks):
            out["postcode"] = [t for t in toks if t not in t2][0]
        if t2:
            last = t2[-1]
            m = re.match(r"^(.+?)\s+(\d{1,2}W?)$", last)
            cand = m.group(1) if m else last
            if m:
                out["region"] = "district " + m.group(2)
            if cand and not looks_street(cand):
                out.update(locality=cand, rule="IE_COUNTY_DISTRICT", status="parsed")
                return out
        out.update(rule="IE_COUNTY_DISTRICT", status="no_locality")
        return out
    for t in reversed(toks):
        m = re.match(r"^\d{4,6}\s+(.+)$", t) or re.match(r"^\d{2,3}\s\d{2,3}\s+(.+)$", t) or re.match(r"^(.+?)\s+\d{4,6}$", t)
        if m and not looks_street(m.group(1)):
            pm = re.match(r"^(\d{4,6})\s", t)
            out.update(locality=m.group(1).strip(), rule="GENERIC_POSTCODE", status="parsed", postcode=(pm.group(1) if pm else out["postcode"]))
            return out
    out.update(rule="GENERIC_LAST", status="no_locality",
               locality_candidates=" | ".join(reversed([t for t in toks if not looks_street(t)][-3:])))
    return out


# ----------------------------------------------------------------------------------------------- GeoNames
GN_COLS = ["geonameid", "name", "asciiname", "alternatenames", "lat", "lon", "fclass", "fcode", "cc", "cc2", "adm1", "adm2", "adm3", "adm4", "pop",
           "elev", "dem", "tz", "moddate"]


class GeoNames:
    """cities500 + admin1CodesASCII + countryInfo. Indices: (cc, norm(name|asciiname)) and (cc, norm(alternatename))."""

    def __init__(self, gdir: Path):
        import zipfile
        gdir = Path(gdir)
        with zipfile.ZipFile(gdir / "cities500.zip") as z:
            with z.open("cities500.txt") as fh:
                g = pd.read_csv(fh, sep="\t", header=None, names=GN_COLS, dtype=str, keep_default_na=False, quoting=3)
        g["pop"] = pd.to_numeric(g["pop"], errors="coerce").fillna(0).astype(int)
        g["latf"] = g["lat"].astype(float)
        g["lonf"] = g["lon"].astype(float)
        self.df = g
        self.by_id = {r.geonameid: r for r in g.itertuples(index=False)}
        self.by_main: dict = defaultdict(list)
        self.by_alt: dict = defaultdict(list)
        for r in g.itertuples(index=False):
            for n in {norm(r.name), norm(r.asciiname)}:
                if n:
                    self.by_main[(r.cc, n)].append(r)
            for n in {norm(x) for x in r.alternatenames.split(",") if x}:
                if n:
                    self.by_alt[(r.cc, n)].append(r)
        self.a1: dict = {}                              # (cc, norm(name)) -> code
        self.a1_name: dict = {}                         # (cc, code) -> name
        for line in (gdir / "admin1CodesASCII.txt").read_text(encoding="utf-8").splitlines():
            p = line.split("\t")
            if len(p) >= 2:
                cc, code = p[0].split(".", 1)
                self.a1_name[(cc, code)] = p[1]
                for k in {norm(p[1])} | ({norm(p[2])} if len(p) >= 3 else set()):
                    self.a1.setdefault((cc, k), set()).add(code)
        self.countries: dict[str, tuple[str, str]] = {}   # norm(name) -> (iso3, iso2)
        self.iso3_to_2: dict[str, str] = {}
        self.country_names: dict[str, str] = {}           # name -> iso2
        for line in (gdir / "countryInfo.txt").read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            c = line.split("\t")
            self.countries[norm(c[4])] = (c[1], c[0])
            self.iso3_to_2[c[1]] = c[0]
            self.country_names[c[4]] = c[0]

    _SUFFIX = re.compile(r"\b(province|prefecture|region|county|oblast|krai|state|governorate|district|municipality|autonomous region|"
                         r"special administrative region|metropolis|city)\b")

    def region_code(self, cc: str, region_text: str):
        """admin1 code for a region name (record `adm1` or a state abbreviation); None if not exactly one."""
        if not region_text or region_text.startswith("district"):
            return None
        rt = region_text.strip()
        if cc == "US" and rt.upper() in US_ABBR:
            return rt.upper()
        if cc == "US" and rt.casefold() in US_STATES:
            return US_STATES[rt.casefold()]
        if cc == "AU" and rt.upper() in AU_ABBR:
            rt = next(k for k, v in AU_STATES.items() if v == rt.upper())
        if cc == "CA" and rt.upper() in CA_ABBR:
            rt = next(k for k, v in CA_PROV.items() if v == rt.upper() and k != "québec")
        n = norm(rt)
        s = self.a1.get((cc, n))
        if s and len(s) == 1:
            return next(iter(s))
        n2 = re.sub(r"\s+", " ", self._SUFFIX.sub(" ", n)).strip()           # same name after dropping a type word on the record side
        if n2 and n2 != n:
            s = self.a1.get((cc, n2))
            if s and len(s) == 1:
                return next(iter(s))
        cands = {code for (c2, k), codes in self.a1.items() if c2 == cc and re.sub(r"\s+", " ", self._SUFFIX.sub(" ", k)).strip() == (n2 or n) for code in codes}
        return next(iter(cands)) if len(cands) == 1 else None


# ----------------------------------------------------------------------------------------------- aliases and countries

def load_aliases(path: Path) -> dict[str, dict]:
    """Accepted rows only: norm(name_in_source) -> row. A row that is not `accepted` is a build stop."""
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig", newline="")):
        if r["status"] != "accepted":
            raise BuildStop(f"alias {r['name_in_source']!r} has status {r['status']!r}, not accepted ({path.name})")
        out[norm(r["name_in_source"])] = r
    return out


class Countries:
    """Name -> iso3 -> exactly one ADM0 unit of the frame."""

    def __init__(self, gn: GeoNames, aliases: dict[str, dict], adm0_units: pd.DataFrame):
        self.gn, self.aliases = gn, aliases
        self.adm0 = {r.iso3: r for r in adm0_units.itertuples(index=False)}
        if len(self.adm0) != len(adm0_units):
            raise BuildStop("frame ADM0 iso3 are not unique")
        self.frame_names = defaultdict(list)
        for r in adm0_units.itertuples(index=False):
            self.frame_names[norm(r.name)].append(r.iso3)

    def iso3(self, name: str):
        """-> (iso3 | None, how)."""
        n = norm(name)
        if n in self.aliases:
            return self.aliases[n]["iso3"], "alias"
        if n in self.gn.countries:
            return self.gn.countries[n][0], "geonames_countryInfo"
        if len(self.frame_names.get(n, [])) == 1:
            return self.frame_names[n][0], "frame_name"
        return None, "unmapped"

    def iso2(self, iso3: str) -> str:
        return self.gn.iso3_to_2.get(iso3, "")
