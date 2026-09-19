#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract strings, URLs and vendor markers from dex files without a decompiler.

Fast recon: dex strings are stored as plain MUTF-8, so ASCII substrings can be found
by scanning the raw bytes. This answers most classification questions in seconds --
which dex holds the app's code, which ad SDKs ship with it, what endpoints it calls.

Usage
-----
  # all URLs across a directory of dex files
  python dex_strings.py <dex_dir> --urls

  # find which dex files contain a marker (ASCII substring)
  python dex_strings.py <dex_dir> --find 'openadsdk|com.qq.e|anythink' --per-file

  # dump a class/package inventory per dex (type descriptors)
  python dex_strings.py <dex_dir> --classes 'Lcom/example/app/'

  # raw string-table dump, length-filtered
  python dex_strings.py <dex_dir> --strings --min 8 --max 60

  # compare two dex files' string tables (what changed after a patch)
  python dex_strings.py --diff a.dex b.dex

Notes
-----
* A marker in the string table means the class/URL is *present*, not that the app
  *uses* that feature. Confirm with runtime behavior before acting.
* `--urls` output is the fastest way to see an app's whole API surface and its
  third-party endpoints at once.
"""
import argparse
import glob
import os
import re
import struct
import sys

URL_RE = re.compile(rb'https?://[A-Za-z0-9\.\-_:/%\.\?=&~#]{4,200}')
ASCII_RE = re.compile(rb'[\x20-\x7e]{4,200}')


def uleb128(data, off):
    r = 0
    s = 0
    while True:
        b = data[off]
        off += 1
        r |= (b & 0x7F) << s
        if not (b & 0x80):
            break
        s += 7
    return r, off


def dex_strings(path):
    """Yield the dex string table in table order."""
    data = open(path, 'rb').read()
    if data[:4] != b'dex\n':
        return
    n = struct.unpack('<I', data[0x38:0x3C])[0]
    off = struct.unpack('<I', data[0x3C:0x40])[0]
    for i in range(n):
        sdata = struct.unpack('<I', data[off + i * 4: off + i * 4 + 4])[0]
        ln, p = uleb128(data, sdata)
        yield bytes(data[p:p + ln])


def iter_dex(target):
    if os.path.isdir(target):
        return sorted(glob.glob(os.path.join(target, '*.dex')))
    return [target]


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('target')
    ap.add_argument('--urls', action='store_true')
    ap.add_argument('--strings', action='store_true')
    ap.add_argument('--classes', metavar='PREFIX')
    ap.add_argument('--find', metavar='REGEX')
    ap.add_argument('--per-file', action='store_true')
    ap.add_argument('--diff', nargs=2, metavar=('A', 'B'))
    ap.add_argument('--min', type=int, default=6)
    ap.add_argument('--max', type=int, default=200)
    a = ap.parse_args()

    if a.diff:
        A = set(dex_strings(a.diff[0]))
        B = set(dex_strings(a.diff[1]))
        only_a = sorted(x for x in A - B if a.min <= len(x) <= a.max)
        only_b = sorted(x for x in B - A if a.min <= len(x) <= a.max)
        print('A strings=%d  B strings=%d' % (len(A), len(B)))
        print('only in A: %d' % len(only_a))
        for x in only_a[:40]:
            print('   -', x.decode('utf-8', 'replace'))
        print('only in B: %d' % len(only_b))
        for x in only_b[:40]:
            print('   +', x.decode('utf-8', 'replace'))
        return 0

    pat = re.compile(a.find.encode()) if a.find else None
    files = iter_dex(a.target)

    if a.find and a.per_file:
        for fp in files:
            data = open(fp, 'rb').read()
            hits = len(pat.findall(data))
            if hits:
                print('%-22s hits=%d' % (os.path.basename(fp), hits))
        return 0

    seen = set()
    for fp in files:
        for raw in dex_strings(fp):
            s = raw.decode('utf-8', 'replace')
            if not (a.min <= len(s) <= a.max):
                continue
            if pat and not pat.search(s):
                continue
            if a.classes and not s.startswith(a.classes):
                continue
            if a.urls and not raw.startswith((b'http://', b'https://')):
                continue
            if s in seen:
                continue
            seen.add(s)
            if a.urls:
                print(s)
            elif a.classes:
                print('%-18s %s' % (os.path.basename(fp), s))
            else:
                print('%s' % s)

    if a.urls and not seen:
        # fall back to raw byte scan (covers URLs stored outside the string table)
        print('[note] no URLs in string tables; raw scan:')
        for fp in files:
            for m in set(URL_RE.findall(open(fp, 'rb').read())):
                print(os.path.basename(fp), m.decode('utf-8', 'replace'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
