"""Updates the pinned SHA-256 of validation_report.json in releases/abf-boundaries-v0.3.0.yaml
(CODE-BND, addition 19.11-b: the report was rewritten after the disputed layer was added).
Safe to run twice. Run from the repository root."""
import sys
from pathlib import Path

P = Path("releases/abf-boundaries-v0.3.0.yaml")
OLD = "ed0634bbde7d08a5850af935a3dca55125b0098dfc65fbd99ac8894715b97720"
NEW = "565015e7d1dc56ff5f7a50557f809c786b882d39d69af60dc4723a81514d722b"

s = P.read_bytes().decode("utf-8")
if s.count(NEW) == 1 and OLD not in s:
    print("already updated")
elif s.count(OLD) == 1:
    P.write_bytes(s.replace(OLD, NEW).encode("utf-8"))
    print("updated: validation_report sha256 =", NEW)
else:
    sys.exit(f"STOP: expected the old pin exactly once, found {s.count(OLD)}; nothing changed")
