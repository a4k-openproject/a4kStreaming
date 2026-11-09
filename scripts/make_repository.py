# -*- coding: utf-8 -*-
# Dev-time only: builds packages/a4kStreaming-repository.zip (committed, linked from the README) from the tracked
# source packages/repository.a4kstreaming/. Stdlib only. Deterministic: entries sorted, every stamp 2026-01-01 00:00,
# fixed modes, no extra fields, so the same source always gives the same bytes. Run: python3 scripts/make_repository.py

import os
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SRC = os.path.join(ROOT, 'packages', 'repository.a4kstreaming')
OUT = os.path.join(ROOT, 'packages', 'a4kStreaming-repository.zip')
FOLDER = 'a4kStreaming-repository/'
STAMP = (2026, 1, 1, 0, 0, 0)

def entry(name, mode):
    info = zipfile.ZipInfo(name, STAMP)
    info.create_system = 3  # unix, so the mode below is read
    info.external_attr = mode << 16
    return info

def build(out=OUT, src=SRC):
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr(entry(FOLDER, 0o40755), b'')
        for name in sorted(os.listdir(src), key=str.lower):
            with open(os.path.join(src, name), 'rb') as f:
                z.writestr(entry(FOLDER + name, 0o100644), f.read(), zipfile.ZIP_DEFLATED)

if __name__ == '__main__':
    build()
