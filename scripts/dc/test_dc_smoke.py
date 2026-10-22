r"""Smoke tests for abf-dc (no network, no input files). Run from the repo root::

    python scripts\dc\test_dc_smoke.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dc_checks as K  # noqa: E402
import dc_http as H  # noqa: E402
import dc_lib as L  # noqa: E402

ZENODO = """User-agent: *
Disallow: /search
Disallow: /api
Allow: /api/records/*/files
Disallow: /api/records/*/files-archive
Crawl-delay: 10
"""
CENSUS = """User-agent: Googlebot
Crawl-delay: 30
User-agent: MegaIndex
Disallow: /
"""


class Robots(unittest.TestCase):
    def test_zenodo_rules(self):
        r = H.RobotsRules(ZENODO)
        self.assertFalse(r.allowed("/api/records/23454136"))
        self.assertTrue(r.allowed("/api/records/23454136/files"))
        self.assertFalse(r.allowed("/api/records/23454136/files-archive"))
        self.assertTrue(r.allowed("/records/23454136/files/units.csv?download=1"))
        self.assertEqual(r.crawl_delay(), 10.0)

    def test_named_groups_do_not_apply_to_us(self):
        r = H.RobotsRules(CENSUS)
        self.assertTrue(r.allowed("/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_place_national.zip"))

    def test_deny_all(self):
        self.assertFalse(H.RobotsRules(None, deny_all=True).allowed("/x"))


class Text(unittest.TestCase):
    def test_one_line(self):
        self.assertEqual(L.one_line("- a\n- b\r\n\n- c\n"), "- a | - b | - c")

    def test_slug(self):
        self.assertEqual(L.slug("Google Pryor (North)"), "google-pryor-north")

    def test_address_key(self):
        a = K.addr_key("5502 Spinks Rd, Abilene, TX 79601")
        b = K.addr_key("5502 Spinks Road, Abilene, Texas 79601, United States")
        self.assertEqual(a, b)
        self.assertNotEqual(a, K.addr_key("5503 Spinks Road, Abilene, Texas 79601, United States"))

    def test_parse_us(self):
        p = L.parse_address("4581 Webb St, Pryor, OK 74361", "US")
        self.assertEqual((p["locality"], p["region"]), ("Pryor", "OK"))


if __name__ == "__main__":
    unittest.main()
