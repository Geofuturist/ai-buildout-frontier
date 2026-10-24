r"""abf-dc: network helpers (SPEC_DC_world_v0_1_0 r2, section 9 Q5/Q6). Not run on its own.

Rules:
  * robots.txt of a host is read BEFORE the first request to that host, through one function (`Fetcher.allowed`);
    a disallowed path is never requested and is recorded in the log as `robots_disallow`;
  * robots.txt is evaluated per RFC 9309 (group by product token, `*` and `$` wildcards, longest match wins,
    Allow wins a tie); 404/410 = no restrictions; any other non-200 answer = everything disallowed;
  * a pause between requests to one host (Zenodo: >= 10 s, its Crawl-delay);
  * a blocked request (403/429) is not worked around.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

UA = "AIBuildoutFrontier-DC-build/0.1.0 (+https://github.com/Geofuturist/ai-buildout-frontier)"
PRODUCT = "aibuildoutfrontier-dc-build"
HOST_PAUSE = {"zenodo.org": 10.5, "www2.census.gov": 2.0}
DEFAULT_PAUSE = 2.0


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_hashes(p: Path) -> tuple[str, str]:
    s, m = hashlib.sha256(), hashlib.md5()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            s.update(chunk)
            m.update(chunk)
    return s.hexdigest(), m.hexdigest()


def _rule_regex(pattern: str) -> re.Pattern:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    return re.compile("^" + rx + ("$" if anchored else ""))


class RobotsRules:
    """Parsed robots.txt for one host."""

    def __init__(self, text: str | None, allow_all: bool = False, deny_all: bool = False):
        self.allow_all, self.deny_all = allow_all, deny_all
        self.groups: list[tuple[list[str], list[tuple[bool, str]], float | None]] = []
        if text is None:
            return
        agents: list[str] = []
        rules: list[tuple[bool, str]] = []
        delay: float | None = None
        in_rules = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            k, v = (x.strip() for x in line.split(":", 1))
            k = k.lower()
            if k == "user-agent":
                if in_rules:
                    self.groups.append((agents, rules, delay))
                    agents, rules, delay, in_rules = [], [], None, False
                agents.append(v.lower())
            elif k in ("allow", "disallow"):
                in_rules = True
                if v:
                    rules.append((k == "allow", v))
            elif k == "crawl-delay":
                in_rules = True
                try:
                    delay = float(v)
                except ValueError:
                    pass
        if agents:
            self.groups.append((agents, rules, delay))

    def _group(self):
        best, best_len = None, -1
        for agents, rules, delay in self.groups:
            for a in agents:
                if a != "*" and a in PRODUCT and len(a) > best_len:
                    best, best_len = (rules, delay), len(a)
        if best is None:
            for agents, rules, delay in self.groups:
                if "*" in agents:
                    return rules, delay
            return [], None
        return best

    def allowed(self, path_query: str) -> bool:
        if self.deny_all:
            return False
        if self.allow_all:
            return True
        rules, _ = self._group()
        hit_len, hit_allow = -1, True
        for allow, pat in rules:
            if _rule_regex(pat).match(path_query):
                L = len(pat.rstrip("$"))
                if L > hit_len or (L == hit_len and allow):
                    hit_len, hit_allow = L, allow
        return hit_allow

    def crawl_delay(self) -> float | None:
        return self._group()[1]


class Fetcher:
    """requests wrapper: robots check first, pauses, a log of every request (-> sources_manifest.json)."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.robots: dict[str, RobotsRules] = {}
        self.last: dict[str, float] = {}
        self.log: list[dict] = []
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA

    def _pause(self, host: str, extra: float | None = None) -> None:
        need = max(HOST_PAUSE.get(host, DEFAULT_PAUSE), extra or 0.0)
        wait = self.last.get(host, 0.0) + need - time.time()
        if wait > 0:
            time.sleep(wait)
        self.last[host] = time.time()

    def _load_robots(self, host: str, scheme: str) -> RobotsRules:
        if host in self.robots:
            return self.robots[host]
        url = f"{scheme}://{host}/robots.txt"
        self._pause(host)
        try:
            r = self.s.get(url, timeout=60)
            code = r.status_code
        except requests.RequestException as e:
            self.log.append(dict(url=url, retrieved_at=now_utc(), http_status="error", note=repr(e)))
            rules = RobotsRules(None, deny_all=True)
            self.robots[host] = rules
            return rules
        self.log.append(dict(url=url, retrieved_at=now_utc(), http_status=code, bytes=len(r.content),
                             sha256=hashlib.sha256(r.content).hexdigest(), note="robots.txt"))
        if code == 200:
            rules = RobotsRules(r.text)
        elif code in (404, 410):
            rules = RobotsRules(None, allow_all=True)
        else:
            rules = RobotsRules(None, deny_all=True)
        self.robots[host] = rules
        return rules

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        if p.path == "/robots.txt":
            return True
        rules = self._load_robots(p.netloc, p.scheme)
        return rules.allowed(p.path + (("?" + p.query) if p.query else ""))

    def get(self, url: str, dest: Path | None = None, *, expect_md5: str | None = None, note: str = "") -> requests.Response | None:
        """GET after the robots check. Returns the response, or None if disallowed / failed."""
        p = urlparse(url)
        if not self.allowed(url):
            self.log.append(dict(url=url, retrieved_at=now_utc(), http_status="robots_disallow",
                                 note=(note + " robots.txt disallows; no request was made").strip()))
            return None
        extra = self.robots[p.netloc].crawl_delay() if p.netloc in self.robots else None
        self._pause(p.netloc, extra)
        try:
            r = self.s.get(url, timeout=300)
        except requests.RequestException as e:
            self.log.append(dict(url=url, retrieved_at=now_utc(), http_status="error", note=(note + " " + repr(e)).strip()))
            return None
        row = dict(url=url, retrieved_at=now_utc(), http_status=r.status_code, bytes=len(r.content),
                   sha256=hashlib.sha256(r.content).hexdigest(), md5=hashlib.md5(r.content).hexdigest(), note=note)
        if r.status_code != 200:
            self.log.append(row)
            return None                                   # 403/429/...: not worked around
        if expect_md5 and row["md5"] != expect_md5:
            row["note"] = (note + f" md5 mismatch: expected {expect_md5}").strip()
            self.log.append(row)
            raise SystemExit(f"STOP: md5 of {url} is {row['md5']}, expected {expect_md5}")
        if dest is not None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            row["saved_as"] = str(dest)
        self.log.append(row)
        return r
