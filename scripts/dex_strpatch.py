#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字节级定点 patch dex 里的字符串常量，完全不做 smali 往返。

为什么不用 smali 往返：实测 classes7.dex 经 baksmali->smali 整树重建后，
`io.ktor.client.engine.HttpClientEngine` 的 synthetic access bridge 被破坏，
运行时报 IncompatibleClassChangeError（Found interface, but class was expected）。
class_def 的 access_flags 看不出问题，所以只能改用"只改字节"的方式。

本脚本做法（对 dex 结构零改动）：
  1. 把目标字符串替换成**等长**的另一个字符串 —— 长度相同则 string_data_item
     的 uleb128 长度前缀不变，dex 的偏移、索引、表全部不变；
  2. 重算 dex header 的 signature(SHA-1, 从 offset 32 起) 与 checksum(adler32, 从 offset 12 起)。

用法：python dex_strpatch.py <in.dex> <out.dex> <old_str> <new_str>
要求 len(new) == len(old)，且 old 在 dex 中出现次数恰好为 1。
"""
import hashlib
import struct
import sys
import zlib


def _uleb128(data, off):
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


def _read_strings(data):
    off = struct.unpack('<I', data[0x3C:0x40])[0]
    size = struct.unpack('<I', data[0x38:0x3C])[0]
    out = []
    for i in range(size):
        sdata_off = struct.unpack('<I', data[off + i * 4: off + i * 4 + 4])[0]
        n, p = _uleb128(data, sdata_off)
        out.append((sdata_off, bytes(data[p:p + n])))
    return out


def _order_ok(data, off, ob, nb):
    """检查把 ob 换成 nb 后是否仍满足 string_ids 的字典序约束。

    注意：string_ids 里存的是 string_data_item 的偏移，也就是**长度前缀**的位置
    （在 UTF-8 数据前若干字节），所以不能直接拿字符串数据偏移去匹配 ——
    这里改为按内容匹配目标条目。
    """
    entries = _read_strings(data)
    idx = None
    for i, (_sdata_off, raw) in enumerate(entries):
        if raw == ob:
            idx = i
            break
    if idx is None:
        print('[order] target string not found in string_ids, skip check')
        return True
    prev = entries[idx - 1][1] if idx > 0 else None
    nxt = entries[idx + 1][1] if idx + 1 < len(entries) else None
    if prev is not None and nb <= prev:
        print('[order] FAIL: new %r <= prev %r' % (nb, prev))
        return False
    if nxt is not None and nb >= nxt:
        print('[order] FAIL: new %r >= next %r' % (nb, nxt))
        return False
    print('[order] OK: %r < %r < %r' % (prev, nb, nxt))
    return True


def main():
    src, dst, old, new = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    ob, nb = old.encode('utf-8'), new.encode('utf-8')
    if len(ob) != len(nb):
        print('[FAIL] length mismatch: %d vs %d (must be equal)' % (len(ob), len(nb)))
        return 1
    data = bytearray(open(src, 'rb').read())
    if data[:8] != b'dex\n035\x00' and data[:4] != b'dex\n':
        print('[warn] unexpected magic: %r' % bytes(data[:8]))
    n = data.count(ob)
    print('[info] occurrences of %r = %d' % (old, n))
    if n != 1:
        print('[FAIL] expected exactly 1 occurrence')
        return 1
    off = data.find(ob)

    # 关键：dex 规范要求 string_ids 表按字符串内容有序。等长替换虽然不动偏移，
    # 但会改变该条目在表中的字典序位置 —— 一旦越界，整个 dex 会被 ClassLoader
    # 拒绝（表现为 ClassNotFoundException: <Application>）。所以这里先做区间校验。
    if not _order_ok(data, off, ob, nb):
        print('[FAIL] replacement would break string_ids ordering. '
              'Pick a string that stays between its two neighbours.')
        return 1

    data[off:off + len(ob)] = nb
    print('[ok] patched at offset 0x%x: %r -> %r' % (off, old, new))

    # signature = SHA-1 over data[32:], stored at 12..32
    sig = hashlib.sha1(bytes(data[32:])).digest()
    data[12:32] = sig
    # checksum = adler32 over data[12:], stored at 8..12 (little endian)
    chk = zlib.adler32(bytes(data[12:])) & 0xFFFFFFFF
    data[8:12] = struct.pack('<I', chk)
    print('[ok] signature=%s checksum=0x%08x' % (sig.hex(), chk))

    open(dst, 'wb').write(bytes(data))
    print('[ok] wrote %s (%d bytes)' % (dst, len(data)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
