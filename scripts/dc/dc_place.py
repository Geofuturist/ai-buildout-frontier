r"""abf-dc: place chain (SPEC_DC_world_v0_1_0 r2, section 2.3). Not run on its own.

The first step that works gives the place:
  1 geonames_address  city    place from the address; exact name match with cities500 in the record's country and its ADM1
                              (name/asciiname first, then alternatenames, as in the scouting run that gave 63 of 94 for Epoch)
  2 census_place      city    US: place of the address that cities500 does not have; Census Gazetteer 2023, INTPTLAT/INTPTLONG
  3 geonames_name     city    place from the record name; name/asciiname only; a match equal to the region name only for PPLA/PPLC;
                              in the US only if the place lies in the record's county (adm2)
  4 census_county     county  US: adm2 -> ADM2 unit_id by exact name inside the state; a name that two units share = ambiguous
  5 none              none    no place: unit_id = ADM0 of iso3_source
"Population rule": several GeoNames objects with one name in one ADM1 and population > 0 for exactly one -> that one,
resolved_by_population = true. Otherwise ambiguous -> next step.
Contested zones: if iso3_source is a side of a `contested_areas` zone, the place is also searched in the other country of the
pair, only inside the zone. No geocoders, no fuzzy matching, no Google Earth links.
"""

from __future__ import annotations

import re
from pathlib import Path

import warnings

import geopandas as gpd
import pandas as pd
from pyproj import Geod
from shapely.geometry import Point
from shapely.ops import nearest_points
from shapely.prepared import prep

import dc_lib as L

GEOD = Geod(ellps="WGS84")
warnings.filterwarnings("ignore", message=".*sjoin_nearest.*")   # used only to pick a candidate; the 1 000 m test is geodesic

STOP = set("""data center centre centres centers cloud edge core digital tech technology technologies solutions services network networks telecom group
 holdings holding park campus tower hub site zone area region county city town village island lake river mountain valley hill hills bay beach coast port
 bridge garden gardens new old great upper lower near east west north south northern southern eastern western central first second third one two three
 four five six seven eight nine ten phase stage building block unit floor level operating construction expansion planned existing retired proposal
 proposed project facility facilities hyperscale ai national international global world europe asia africa america american australia pacific atlantic
 nordic baltic bank university college school hospital government ministry office industrial estate business enterprise express direct prime over march
 naast meer poli cento road come from street power energy solar wind green blue red white black gold silver sun star sky sea ocean air fire stone rock
 iron steel inc llc ltd corp corporation co company the of and for in at on colocation infrastructure""".split())

CENSUS_SUFFIX = {"city", "town", "village", "cdp", "borough", "municipality", "comunidad", "urbana", "zona", "township", "plantation", "balance",
                 "government", "unified", "metropolitan", "consolidated", "metro", "county", "and", "of", "city-county"}
ADM2_TYPE_WORD = re.compile(r"\s+(county|parish|borough|census area|municipality|municipio)$", re.I)


class Frame:
    """ADM0 / contested zones / US ADM2 geometry and names from abf-boundaries v0.2.0."""

    def __init__(self, fdir: Path):
        fdir = Path(fdir)
        self.units = pd.read_csv(fdir / "units.csv", dtype=str, keep_default_na=False)
        self.adm0 = gpd.read_parquet(fdir / "adm0.parquet")[["unit_id", "iso3", "name", "geometry"]]
        self.zones = gpd.read_parquet(fdir / "contested_areas.parquet")
        us2 = gpd.read_parquet(fdir / "analysis_usa_adm2.parquet")[["unit_id", "parent_id", "geometry"]]
        nm = self.units.set_index("unit_id")["name"]
        us2["name"] = us2["unit_id"].map(nm)
        self.us2 = us2.reset_index(drop=True)
        us1 = self.units[(self.units["iso3"] == "USA") & (self.units["level"] == "ADM1")]
        self.us_state_unit = {L.norm(r.name): r.unit_id for r in us1.itertuples(index=False)}
        self.adm2_idx: dict[str, dict[str, list[str]]] = {}
        for r in self.us2.itertuples(index=False):
            self.adm2_idx.setdefault(r.parent_id, {}).setdefault(L.norm(r.name), []).append(r.unit_id)
        self.us2_by_id = self.us2.set_index("unit_id")
        self.zone_pairs: dict[str, list[tuple[str, object]]] = {}
        for z in self.zones.itertuples(index=False):
            poly = prep(z.geometry)
            self.zone_pairs.setdefault(z.controlled_by, []).append((z.claimed_by, poly))
            self.zone_pairs.setdefault(z.claimed_by, []).append((z.controlled_by, poly))
        self._county_cache: dict = {}

    def county_of(self, lon: float, lat: float):
        key = (round(lon, 5), round(lat, 5))
        if key not in self._county_cache:
            pt = Point(lon, lat)
            hits = self.us2.sindex.query(pt, predicate="within")
            self._county_cache[key] = self.us2.iloc[hits[0]]["unit_id"] if len(hits) else None
        return self._county_cache[key]

    def assign_frame(self, pts: pd.DataFrame, iso3_source: pd.Series):
        """pts: columns lon, lat (index = record index). -> DataFrame(iso3_frame, control_iso3, frame_how)."""
        g = gpd.GeoDataFrame(pts[["lon", "lat"]].copy(), geometry=gpd.points_from_xy(pts["lon"], pts["lat"]), crs="EPSG:4326")
        j = gpd.sjoin(g, self.adm0[["iso3", "geometry"]], how="left", predicate="within")
        res = {}
        for idx, grp in j.groupby(level=0):
            isos = sorted(set(grp["iso3"].dropna()))
            if not isos:
                res[idx] = ("", "none")
            elif len(isos) == 1:
                res[idx] = (isos[0], "within")
            else:                                          # overlap of two ADM0 (tolerated up to 0.05 km2): prefer iso3_source
                src = iso3_source.loc[idx]
                res[idx] = (src if src in isos else isos[0], "within_overlap")
        out = pd.DataFrame(index=pts.index, columns=["iso3_frame", "frame_how", "control_iso3"], dtype=object)
        for idx in pts.index:
            iso, how = res.get(idx, ("", "none"))
            out.at[idx, "iso3_frame"], out.at[idx, "frame_how"] = iso, how
        # nearest country within 1 000 m (ADR section 10): geodesic distance to the nearest polygon point
        miss = [i for i in pts.index if out.at[i, "iso3_frame"] == ""]
        if miss:
            sub = g.loc[miss]
            near = gpd.sjoin_nearest(sub, self.adm0[["iso3", "geometry"]], how="left", max_distance=0.05, distance_col="deg")
            near = near[~near.index.duplicated(keep="first")]
            geom_by_iso = self.adm0.set_index("iso3")["geometry"]
            for idx, r in near.iterrows():
                if pd.isna(r["iso3"]):
                    continue
                p = g.at[idx, "geometry"]
                q = nearest_points(p, geom_by_iso[r["iso3"]])[1]
                d = GEOD.inv(p.x, p.y, q.x, q.y)[2]
                if d <= 1000.0:
                    out.at[idx, "iso3_frame"], out.at[idx, "frame_how"] = r["iso3"], f"nearest_{round(d)}m"
        zg = gpd.sjoin(g, self.zones[["controlled_by", "geometry"]], how="left", predicate="within")
        zc = zg[~zg.index.duplicated(keep="first")]["controlled_by"]
        for idx in pts.index:
            v = zc.get(idx)
            out.at[idx, "control_iso3"] = v if isinstance(v, str) else ""
        return out


class Census:
    """Gazetteer 2023 places: (USPS, norm(base name)) -> rows."""

    def __init__(self, path: Path):
        z = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
        z.columns = [c.strip() for c in z.columns]
        self.idx: dict = {}
        for r in z.itertuples(index=False):
            toks = L.norm(r.NAME).split()
            while len(toks) > 1 and toks[-1] in CENSUS_SUFFIX:
                toks.pop()
            self.idx.setdefault((r.USPS, " ".join(toks)), []).append(r)

    def find(self, usps: str, text: str):
        c = self.idx.get((usps, L.norm(text)), [])
        return c


class PlaceResolver:
    def __init__(self, gn: L.GeoNames, countries: L.Countries, frame: Frame, census: Census):
        self.gn, self.countries, self.frame, self.census = gn, countries, frame, census

    # ---- helpers
    def _decide(self, cands: list):
        """-> (obj | None, status, by_population)."""
        if not cands:
            return None, "none", False
        if len(cands) == 1:
            return cands[0], "resolved", False
        pos = [c for c in cands if c.pop > 0]
        same_adm1 = len({(c.cc, c.adm1) for c in cands}) == 1
        if same_adm1 and len(pos) == 1:
            return pos[0], "resolved", True
        return None, "ambiguous", False

    def _lookup(self, texts: list[str], cc: str, a1code, zone_extra: list, use_alt: bool):
        """First text with candidates decides. -> (obj, status, by_pop, text, via)."""
        for text in texts:
            n = L.norm(text)
            if not n:
                continue
            stages = [("name", self.gn.by_main)] + ([("alternatenames", self.gn.by_alt)] if use_alt else [])
            for via, idx in stages:
                c = list(idx.get((cc, n), []))
                if a1code:
                    c = [x for x in c if x.adm1 == a1code]
                for cc2, poly in zone_extra:
                    c += [x for x in idx.get((cc2, n), []) if poly.contains(Point(x.lonf, x.latf))]
                if c:
                    obj, st, bp = self._decide(c)
                    return obj, st, bp, text, via
        return None, "none", False, "", ""

    # ---- the chain
    def resolve(self, rec: dict) -> dict:
        iso3, cc = rec["iso3"], rec["cc"]
        out = dict(step=5, coord_source="", coord_precision="none", lon="", lat="", unit_id=iso3, resolved_by_population=False, location_state="",
                   geonameid="", place="", via="", basis_text="", county_unit_id="")
        if not cc:
            out["location_state"] = "no_address" if not rec["address"].strip() else "unresolved"
            return out
        zone_extra = [(self.countries.iso2(o), poly) for o, poly in self.frame.zone_pairs.get(iso3, [])]
        zone_extra = [(c2, p) for c2, p in zone_extra if c2]
        addr = rec["address"].strip()
        parsed = L.parse_address(addr, cc) if addr else dict(status="no_address", region="", locality="", locality_candidates="")
        region_text = parsed["region"] or rec.get("adm1", "")
        a1code = self.gn.region_code(cc, region_text) if region_text else None
        ambiguous = False
        name_candidate = False

        # step 1
        texts = [parsed["locality"]] if parsed["locality"] else [t.strip() for t in parsed["locality_candidates"].split("|") if t.strip()]
        obj, st, bp, text, via = self._lookup(texts, cc, a1code, zone_extra, use_alt=True) if texts else (None, "none", False, "", "")
        if st == "resolved":
            return self._city(out, obj, 1, "geonames_address", bp, text, via)
        if st == "ambiguous":
            ambiguous = True

        # step 2 (US)
        if cc == "US" and texts and st == "none":
            usps = parsed["region"] if parsed["region"] in L.US_ABBR else L.US_STATES.get((rec.get("adm1") or "").casefold(), "")
            if usps:
                for t in texts:
                    hit = self.census.find(usps, t)
                    if len(hit) == 1:
                        h = hit[0]
                        out.update(step=2, coord_source="census_place", coord_precision="city", lon=round(float(h.INTPTLONG), 6), lat=round(float(h.INTPTLAT), 6),
                                   unit_id="", place=h.NAME, via="census", basis_text=t, geonameid="census:" + h.GEOID)
                        return out
                    if len(hit) > 1:
                        ambiguous = True
                        break

        # step 3
        s3 = self._step3(rec, cc, a1code, zone_extra)
        if s3["status"] == "resolved":
            return self._city(out, s3["obj"], 3, "geonames_name", s3["by_pop"], s3["text"], "name")
        if s3["status"] == "ambiguous":
            ambiguous = True
        if s3["status"] in ("blocked_county",):
            name_candidate = True

        # step 4
        if cc == "US" and rec.get("adm1") and rec.get("adm2"):
            su = self.frame.us_state_unit.get(L.norm(rec["adm1"]))
            ids = []
            if su:
                idx = self.frame.adm2_idx.get(su, {})
                ids = idx.get(L.norm(rec["adm2"]), [])
                if not ids:
                    stripped = ADM2_TYPE_WORD.sub("", rec["adm2"])
                    if stripped != rec["adm2"]:
                        ids = idx.get(L.norm(stripped), [])
                        if len(ids) == 1:
                            out["via"] = "adm2_type_word_stripped"
            if len(ids) == 1:
                out.update(step=4, coord_source="census_county", coord_precision="county", unit_id=ids[0], county_unit_id=ids[0], basis_text=rec["adm2"])
                out["location_state"] = self._state(ambiguous, addr, name_candidate)
                return out
            if len(ids) > 1:
                ambiguous = True
        out["location_state"] = self._state(ambiguous, addr, name_candidate)
        return out

    @staticmethod
    def _state(ambiguous: bool, addr: str, name_candidate: bool) -> str:
        if ambiguous:
            return "ambiguous"
        if addr or name_candidate:
            return "unresolved"
        return "no_address"

    def _city(self, out: dict, obj, step: int, source: str, by_pop: bool, text: str, via: str) -> dict:
        out.update(step=step, coord_source=source, coord_precision="city", lon=round(obj.lonf, 6), lat=round(obj.latf, 6), unit_id="",
                   resolved_by_population=by_pop, geonameid=obj.geonameid, place=obj.name, via=via, basis_text=text)
        return out

    def _step3(self, rec: dict, cc: str, a1code, zone_extra: list) -> dict:
        toks = L.norm(rec["name"]).split()
        optoks = set(L.norm(rec.get("operator", "")).split())
        region_norm = L.norm(rec.get("adm1", ""))
        spans = []
        blocked = False
        for n in (3, 2, 1):
            for i in range(len(toks) - n + 1):
                g = " ".join(toks[i:i + n])
                part = toks[i:i + n]
                if len(g) < 4 or g in STOP or any(t in STOP for t in part) or set(part) <= optoks:
                    continue
                c = list(self.gn.by_main.get((cc, g), []))
                if a1code:
                    c = [x for x in c if x.adm1 == a1code]
                for cc2, poly in zone_extra:
                    c += [x for x in self.gn.by_main.get((cc2, g), []) if poly.contains(Point(x.lonf, x.latf))]
                if g == region_norm:
                    c = [x for x in c if x.fcode in ("PPLA", "PPLC")]
                if not c:
                    continue
                if cc == "US":                                   # US: the place must lie in the record's county
                    if not rec.get("adm2"):
                        blocked = True
                        continue
                    cc_ok = [x for x in c if self._in_record_county(x, rec["adm2"], rec.get("adm1", ""))]
                    if not cc_ok:
                        blocked = True
                        continue
                    c = cc_ok
                obj, st, bp = self._decide(c)
                spans.append((i, i + n, g, obj, st, bp))
        spans.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
        kept: list = []
        for s in spans:
            if all(s[1] <= k[0] or s[0] >= k[1] for k in kept):
                kept.append(s)
        if len(kept) == 1 and kept[0][3] is not None:
            return dict(status="resolved", obj=kept[0][3], by_pop=kept[0][5], text=kept[0][2])
        if kept:
            return dict(status="ambiguous")
        return dict(status="blocked_county" if blocked else "none")

    def _in_record_county(self, x, adm2_text: str, adm1_text: str) -> bool:
        uid = self.frame.county_of(x.lonf, x.latf)
        if not uid:
            return False
        want = L.norm(adm2_text)
        want2 = L.norm(ADM2_TYPE_WORD.sub("", adm2_text))
        have = L.norm(self.frame.us2_by_id.at[uid, "name"])
        return have in (want, want2)
