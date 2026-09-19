#!/usr/bin/env python3
"""Redirect a native library load by rewriting an isolated string constant in place.

Why this exists
---------------
Protected targets frequently name a *checker* library at a single call site
(``System.loadLibrary("X")`` reached from a JNI constant pool) rather than through
``DT_NEEDED``. When that checker does the integrity validation, deleting the loader
deadlocks you: keep it and validation kills the process, delete it and the load
throws.

Rewriting the *name* is the way out. Point that call at a library that is guaranteed
already mapped (on Android, ``android`` / ``libandroid.so``): the load succeeds, the
checker is never mapped, and **no byte offsets move** because the replacement is
exactly the same length. Nothing for an integrity check to notice about layout, and
no death path to neutralize.

Usage
-----
    # inspect: where does this name occur, and is it an isolated constant?
    python so_constpatch.py libfoo.so --find apkhuan

    # patch a bare .so
    python so_constpatch.py libfoo.so --replace apkhuan=android -o libfoo.patched.so

    # patch inside an APK (rebuilds the zip, entry order preserved)
    python so_constpatch.py app.apk --entry lib/arm64-v8a/libfoo.so \
        --replace apkhuan=android -o app.patched.apk

    # only patch occurrences that sit in an ELF constant-pool section
    python so_constpatch.py libfoo.so --replace apkhuan=android --section-aware

Design notes
------------
* Equal length is mandatory and enforced; there is no padding mode that can be safe
  when the next constant lives immediately after the NUL.
* ``--find`` reports whether each hit is isolated (NUL on both sides). Patching a
  substring of a longer identifier corrupts that identifier, so non-isolated hits are
  refused unless ``--allow-nonisolated`` is given explicitly.
* The ELF section map is only used for *reporting* which constant pool a hit lives in.
  It never gates a patch on section validity, because hardened libraries ship forged
  section headers (see references/native-tamper-and-suicide.md) while the bytes you
  need are still exactly where the loader reads them.
"""
from __future__ import annotations

import argparse
import io
import os
import struct
import sys
import zipfile


# ---------------------------------------------------------------- ELF helpers

def elf_sections(data: bytes):
    """Return [(name, sh_type, addr, offset, size)] or [] if unusable.

    Deliberately tolerant: forged/truncated section headers are common in this
    domain, and a failed parse must not stop the string scan.
    """
    try:
        if data[:4] != b'\x7fELF':
            return []
        e_shoff = struct.unpack_from('<Q', data, 0x28)[0]
        e_shentsize = struct.unpack_from('<H', data, 0x3a)[0]
        e_shnum = struct.unpack_from('<H', data, 0x3c)[0]
        e_shstrndx = struct.unpack_from('<H', data, 0x3e)[0]
        if e_shoff == 0 or e_shnum == 0 or e_shoff >= len(data):
            return []
        raw = []
        for i in range(e_shnum):
            o = e_shoff + i * e_shentsize
            if o + 0x40 > len(data):
                break
            name, stype, _flags, addr, offset, size = struct.unpack_from('<IIQQQQ', data, o)
            raw.append([name, stype, addr, offset, size])
        if e_shstrndx >= len(raw):
            return []
        base = raw[e_shstrndx][3]
        out = []
        for name, stype, addr, offset, size in raw:
            try:
                end = data.index(b'\x00', base + name)
                nm = data[base + name:end].decode('ascii', 'replace')
            except Exception:
                nm = '?'
            out.append((nm, stype, addr, offset, size))
        return out
    except Exception:
        return []


def section_of(sections, off: int):
    for nm, stype, _addr, soff, ssize in sections:
        if stype != 8 and soff <= off < soff + ssize:
            return nm
    return None


POOLS = ('.rodata', '.data', '.data.rel.ro', '.rodata.str1.1', '.dynstr', '.strtab')


def occurrences(data: bytes, needle: bytes):
    """Yield (offset, isolated, section_name, context)."""
    sections = elf_sections(data)
    start = 0
    while True:
        i = data.find(needle, start)
        if i < 0:
            return
        prev = data[i - 1:i]
        nxt = data[i + len(needle):i + len(needle) + 1]
        isolated = (prev == b'\x00' or i == 0) and (nxt == b'\x00')
        yield i, isolated, section_of(sections, i), data[max(0, i - 24):i + len(needle) + 24]
        start = i + 1


def describe(ctx: bytes) -> str:
    return ''.join(chr(b) if 32 <= b < 127 else ('\\0' if b == 0 else '.') for b in ctx)


# ---------------------------------------------------------------- operations

def do_find(data: bytes, needle: bytes) -> int:
    hits = list(occurrences(data, needle))
    if not hits:
        print('no occurrence of %r' % needle.decode('utf-8', 'replace'))
        return 1
    print('%d occurrence(s) of %r:' % (len(hits), needle.decode('utf-8', 'replace')))
    for off, iso, sec, ctx in hits:
        print('  0x%-8x isolated=%-5s section=%-12s | %s' % (off, iso, sec or '-', describe(ctx)))
    n_iso = sum(1 for _, iso, _, _ in hits if iso)
    print('\nisolated (safe to rewrite in place): %d / %d' % (n_iso, len(hits)))
    return 0


def do_replace(data: bytes, old: bytes, new: bytes, section_aware: bool,
               allow_nonisolated: bool, force: bool) -> tuple[bytes, list]:
    if len(old) != len(new):
        raise SystemExit(
            'REFUSING: %r (%d bytes) -> %r (%d bytes).\n'
            'Equal length is mandatory - a different length shifts every byte after it '
            'and invalidates the ELF.\nPass a same-length name (e.g. pad with a shorter '
            'already-loaded library name).' % (
                old.decode('utf-8', 'replace'), len(old),
                new.decode('utf-8', 'replace'), len(new)))

    hits = list(occurrences(data, old))
    if not hits:
        raise SystemExit('REFUSING: %r not present' % old.decode('utf-8', 'replace'))

    selected = []
    for off, iso, sec, ctx in hits:
        if not iso and not allow_nonisolated:
            print('  skip 0x%-8x not an isolated constant (would corrupt a neighbour)' % off)
            continue
        if section_aware and (sec not in POOLS):
            print('  skip 0x%-8x section=%s (not a constant pool; --section-aware)' % (off, sec))
            continue
        selected.append(off)

    if not selected:
        raise SystemExit('REFUSING: no eligible occurrence (see remarks above)')

    if len(selected) > 1 and not force:
        print('\n%d eligible occurrence(s). Re-run with --force to patch all of them, '
              'or narrow the search.' % len(selected))
        for off in selected:
            print('  0x%x' % off)
        raise SystemExit(2)

    out = bytearray(data)
    applied = []
    for off in selected:
        before = bytes(out[off:off + len(old)])
        out[off:off + len(old)] = new
        applied.append((off, before, bytes(new)))
        print('  patched 0x%-8x %r -> %r' % (off, before.decode('utf-8', 'replace'),
                                             new.decode('utf-8', 'replace')))

    print('\n%d byte(s) changed, file length unchanged (%d).' % (len(applied) * len(old), len(data)))
    return bytes(out), applied


# ---------------------------------------------------------------- containers

def load_target(path: str, entry: str | None):
    if path.lower().endswith('.apk') or path.lower().endswith('.zip'):
        if not entry:
            raise SystemExit('--entry is required when patching an APK '
                             '(e.g. --entry lib/arm64-v8a/libfoo.so)')
        z = zipfile.ZipFile(path)
        if entry not in z.namelist():
            cands = [n for n in z.namelist() if n.endswith('.so')]
            raise SystemExit('entry %r not in %s\navailable .so entries:\n  %s'
                             % (entry, path, '\n  '.join(cands[:40])))
        return z.read(entry), 'apk'
    with open(path, 'rb') as f:
        return f.read(), 'file'


def write_target(path: str, kind: str, src_path: str, entry: str | None,
                 new_data: bytes, out_path: str):
    if kind == 'file':
        with open(out_path, 'wb') as f:
            f.write(new_data)
        return
    src = zipfile.ZipFile(src_path)
    total = 0
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            blob = new_data if item.filename == entry else src.read(item.filename)
            dst.writestr(zipfile.ZipInfo(item.filename, date_time=item.date_time),
                         blob, item.compress_type)
            total += 1
    print('  rebuilt %s (%d entries)' % (out_path, total))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description='In-place same-length rewrite of a string constant (library-load redirection).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='examples:\n'
               '  so_constpatch.py libfoo.so --find checkername\n'
               '  so_constpatch.py libfoo.so --replace checkername=android -o libfoo.patched.so\n'
               '  so_constpatch.py app.apk --entry lib/arm64-v8a/libfoo.so '
               '--replace checkername=android -o app.patched.apk\n')
    ap.add_argument('target', help='.so file or .apk')
    ap.add_argument('--entry', default=None, help='zip entry path when target is an APK')
    ap.add_argument('--find', default=None, metavar='STR', help='report occurrences and exit')
    ap.add_argument('--replace', default=None, metavar='OLD=NEW',
                    help='same-length rewrite of OLD with NEW')
    ap.add_argument('-o', '--out', default=None, help='output path (required for --replace)')
    ap.add_argument('--section-aware', action='store_true',
                    help='only patch hits inside known constant-pool sections')
    ap.add_argument('--allow-nonisolated', action='store_true',
                    help='permit patching a substring of a longer identifier (dangerous)')
    ap.add_argument('--force', action='store_true', help='patch every eligible occurrence')
    args = ap.parse_args()

    data, kind = load_target(args.target, args.entry)
    print('loaded %s (%s, %d bytes)\n' % (args.target, kind, len(data)))

    if args.find:
        sys.exit(do_find(data, args.find.encode()))

    if not args.replace:
        ap.error('one of --find or --replace is required')

    if '=' not in args.replace:
        ap.error('--replace expects OLD=NEW')
    old_s, new_s = args.replace.split('=', 1)
    old, new = old_s.encode(), new_s.encode()

    if not args.out and kind == 'file':
        args.out = args.target + '.patched'
    if not args.out:
        ap.error('-o/--out is required when patching an APK')
    if os.path.abspath(args.out) == os.path.abspath(args.target):
        ap.error('refusing to overwrite the input in place; choose a different -o')

    patched, applied = do_replace(data, old, new, args.section_aware,
                                 args.allow_nonisolated, args.force)
    write_target(args.out, kind, args.target, args.entry, patched, args.out)
    print('\nwrote %s' % args.out)
    print('next: re-sign, then verify the loader\'s log tag count is 0 on a cold start '
          '(see references/code-virtualization-and-custom-linkers.md).')


if __name__ == '__main__':
    main()
