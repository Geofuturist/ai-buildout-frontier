#!/usr/bin/env python3
"""Makes public/index-preview/ from the CSV of the index branch (data/index/<set>/): gzips each country file and adm0_other.csv,
copies meta.json. PREVIEW ONLY: the files are not published data. Usage: make-index-preview.py <data/index dir> [out dir]"""
import gzip, os, shutil, sys

src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'public', 'index-preview')
for s in sorted(os.listdir(src)):
    d = os.path.join(src, s)
    if not os.path.isfile(os.path.join(d, 'meta.json')):
        continue
    o = os.path.join(out, s)
    os.makedirs(o, exist_ok=True)
    shutil.copy(os.path.join(d, 'meta.json'), os.path.join(o, 'meta.json'))
    for f in sorted(os.listdir(d)):
        if f.endswith('.csv') and f != 'summary.csv':
            with open(os.path.join(d, f), 'rb') as a, gzip.GzipFile(os.path.join(o, f + '.gz'), 'wb', mtime=0) as b:
                shutil.copyfileobj(a, b)
    print(s, len(os.listdir(o)), 'files')
