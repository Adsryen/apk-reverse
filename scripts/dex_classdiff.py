#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diff two dex files at the class_defs level: class names + access_flags.
The interesting flag is ACC_INTERFACE (0x200).

Use it to prove that a disassemble -> reassemble round-trip did not damage the dex's
interface/class relationships. The classic symptom of that damage is
IncompatibleClassChangeError ("Found interface X, but class was expected") at runtime.

Important limitation: this check compares tables only. It cannot see code-item damage —
see references/patch-audit.md for the checks that can.

Usage: python dex_classdiff.py <a.dex> <b.dex> [filter-substring]
"""
import struct
import sys


def uleb128(data, off):
    result = 0
    shift = 0
    while True:
        b = data[off]
        off += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, off


def read_strings(data):
    off = struct.unpack('<I', data[0x3C:0x40])[0]
    size = struct.unpack('<I', data[0x38:0x40][:4])[0]
    size = struct.unpack('<I', data[0x38:0x3C])[0]
    out = []
    for i in range(size):
        sdata_off = struct.unpack('<I', data[off + i * 4: off + i * 4 + 4])[0]
        n, p = uleb128(data, sdata_off)
        raw = data[p:p + n]
        try:
            out.append(raw.decode('utf-8', 'replace'))
        except Exception:
            out.append('')
    return out


def class_map(path):
    data = open(path, 'rb').read()
    strings = read_strings(data)
    type_ids_off = struct.unpack('<I', data[0x44:0x48])[0]
    n_types = struct.unpack('<I', data[0x40:0x44])[0]
    types = []
    for i in range(n_types):
        idx = struct.unpack('<I', data[type_ids_off + i * 4: type_ids_off + i * 4 + 4])[0]
        types.append(strings[idx] if idx < len(strings) else '')
    class_defs_size = struct.unpack('<I', data[0x60:0x64])[0]
    class_defs_off = struct.unpack('<I', data[0x64:0x68])[0]
    out = {}
    for i in range(class_defs_size):
        base = class_defs_off + i * 32
        class_idx, access_flags = struct.unpack('<II', data[base:base + 8])
        name = types[class_idx] if class_idx < len(types) else '?'
        out[name] = access_flags
    return out


def main():
    a, b = sys.argv[1], sys.argv[2]
    filt = sys.argv[3] if len(sys.argv) > 3 else None
    A = class_map(a)
    B = class_map(b)
    print('A classes=%d  B classes=%d' % (len(A), len(B)))
    only_a = sorted(set(A) - set(B))
    only_b = sorted(set(B) - set(A))
    print('only_in_A=%d  only_in_B=%d' % (len(only_a), len(only_b)))
    for n in only_a[:10]:
        print('  A-only:', n)
    for n in only_b[:10]:
        print('  B-only:', n)

    diff_iface = []
    diff_flags = []
    for name in sorted(set(A) & set(B)):
        fa, fb = A[name], B[name]
        ia, ib = bool(fa & 0x200), bool(fb & 0x200)
        if ia != ib:
            diff_iface.append((name, hex(fa), hex(fb)))
        elif fa != fb:
            diff_flags.append((name, hex(fa), hex(fb)))

    print('\n*** ACC_INTERFACE mismatch: %d ***' % len(diff_iface))
    for name, fa, fb in (diff_iface if not filt else [x for x in diff_iface if filt in x[0]]):
        print('  %-70s A=%s B=%s' % (name, fa, fb))
    print('\naccess_flags diff (same interface-ness): %d' % len(diff_flags))
    shown = 0
    for name, fa, fb in diff_flags:
        if filt and filt not in name:
            continue
        if shown < 25:
            print('  %-70s A=%s B=%s' % (name, fa, fb))
            shown += 1


if __name__ == '__main__':
    main()
