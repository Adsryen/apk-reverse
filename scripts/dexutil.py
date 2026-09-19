#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal, dependency-free dex reader: structure walk + exact instruction decode.

WHY THIS EXISTS
---------------
Locating the exact byte offset of one instruction is where byte-level patching
either works or wastes an afternoon. Two shortcuts do not work and are worth
naming so nobody re-derives them:

  * Reconstructing offsets from a baksmali listing. `.line` directives track
    SOURCE lines, and one source line can span several instructions, so the
    values repeat and do not map 1:1 onto code offsets.
  * Matching a guessed byte sequence. Encodings vary with register numbers and
    operand widths, and a plausible-looking opcode can belong to a different
    format than you assume (0x38 is `if-test`, 22t/4 bytes -- not `if-testz`).

So: walk class -> class_data_item -> method -> code_item, then decode forward with
a complete format table, and match on decoded semantics instead of bytes.

Three details in the walk that silently produce wrong answers:

  * `class_data_item` member indices are DELTAS against the previous entry in the
    same list. Reading a raw uleb as an absolute index yields real-looking wrong
    members.
  * dalvik encodes switch/array payloads as `00 <ident> <size>` with ident 1..3.
    A plain `00 00` is an ordinary one-unit nop; treating every 00 as a payload
    swallows the next instruction and desynchronises the rest of the method.
  * The header field order is easy to mis-remember. See OFFSETS below, and always
    sanity-check the parsed sizes against the file.

Pure standard library. Import it, or run it for a per-method dump:

    python dexutil.py <dex-or-apk> <Class/Name;> <method> <descriptor>
"""

import hashlib
import struct
import sys
import zipfile

# Verified dex header offsets. After magic(8) + checksum(4) + signature(20):
OFFSETS = {
    "file_size": 0x20, "header_size": 0x24, "endian_tag": 0x28,
    "link_size": 0x2C, "link_off": 0x30, "map_off": 0x34,
    "string_ids_size": 0x38, "string_ids_off": 0x3C,
    "type_ids_size": 0x40, "type_ids_off": 0x44,
    "proto_ids_size": 0x48, "proto_ids_off": 0x4C,
    "field_ids_size": 0x50, "field_ids_off": 0x54,
    "method_ids_size": 0x58, "method_ids_off": 0x5C,
    "class_defs_size": 0x60, "class_defs_off": 0x64,
    "data_size": 0x68, "data_off": 0x6C,
}

OP_NAMES = {
    0x00: "nop", 0x01: "move", 0x02: "move/from16", 0x03: "move/16",
    0x04: "move-wide", 0x05: "move-wide/from16", 0x06: "move-wide/16",
    0x07: "move-object", 0x08: "move-object/from16", 0x09: "move-object/16",
    0x0A: "move-result", 0x0B: "move-result-wide", 0x0C: "move-result-object",
    0x0D: "move-exception", 0x0E: "return-void", 0x0F: "return",
    0x10: "return-wide", 0x11: "return-object", 0x12: "const/4",
    0x13: "const/16", 0x14: "const", 0x15: "const/high16",
    0x16: "const-wide/high16", 0x17: "const-wide/16", 0x18: "const-wide/32",
    0x19: "const-string", 0x1A: "const-string/jumbo", 0x1B: "const-class",
    0x1C: "monitor-enter", 0x1D: "monitor-exit", 0x1E: "check-cast",
    0x1F: "instance-of", 0x20: "array-length", 0x21: "new-instance",
    0x22: "new-array", 0x23: "filled-new-array", 0x24: "filled-new-array/range",
    0x25: "fill-array-data", 0x26: "throw", 0x27: "goto",
    0x28: "goto/16", 0x29: "goto/32", 0x2A: "packed-switch",
    0x2B: "sparse-switch",
    0x32: "if-eq", 0x33: "if-ne", 0x34: "if-lt", 0x35: "if-ge",
    0x36: "if-gt", 0x37: "if-le",
    0x38: "if-eqz", 0x39: "if-nez", 0x3A: "if-ltz", 0x3B: "if-gez",
    0x3C: "if-gtz", 0x3D: "if-lez",
    0x52: "iget", 0x53: "iget-wide", 0x54: "iget-object", 0x55: "iget-boolean",
    0x56: "iget-byte", 0x57: "iget-char", 0x58: "iget-short",
    0x59: "iput", 0x5A: "iput-wide", 0x5B: "iput-object", 0x5C: "iput-boolean",
    0x5D: "iput-byte", 0x5E: "iput-char", 0x5F: "iput-short",
    0x60: "sget", 0x61: "sget-wide", 0x62: "sget-object", 0x63: "sget-boolean",
    0x64: "sget-byte", 0x65: "sget-char", 0x66: "sget-short",
    0x67: "sput", 0x68: "sput-wide", 0x69: "sput-object", 0x6A: "sput-boolean",
    0x6B: "sput-byte", 0x6C: "sput-char", 0x6D: "sput-short",
    0x6E: "invoke-virtual", 0x6F: "invoke-super", 0x70: "invoke-direct",
    0x71: "invoke-static", 0x72: "invoke-interface",
    0x74: "invoke-virtual/range", 0x75: "invoke-super/range",
    0x76: "invoke-direct/range", 0x77: "invoke-static/range",
    0x78: "invoke-interface/range",
}

# Opcode groups whose operands are a pair of registers plus an int16 offset.
IF_TEST = set(range(0x32, 0x38))    # 22t: 2 register nibbles + int16
IF_TESTZ = set(range(0x38, 0x3E))   # 21t: 1 register nibble + int16
RETURN_OPS = (0x0F, 0x10, 0x11)
MOVE_RESULT_OPS = (0x0A, 0x0B, 0x0C)
INVOKE_OPS = tuple(range(0x6E, 0x73)) + tuple(range(0x74, 0x79))
# opcodes that read an instance field: (dest_reg, object_reg, field_idx)
IFIELD_OPS = tuple(range(0x52, 0x59))
# opcodes that write an instance field: (value_reg, object_reg, field_idx)
PFIELD_OPS = tuple(range(0x59, 0x60))
SFIELD_OPS = tuple(range(0x60, 0x6E))


def u16(b, o):
    return b[o] | (b[o + 1] << 8)


def u32(b, o):
    return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)


def s16(v):
    return v - 0x10000 if v > 0x7FFF else v


def read_uleb(b, o):
    """ULEB128 -> (value, new_offset). Member indices in class_data are deltas."""
    result = 0
    shift = 0
    while True:
        x = b[o]
        o += 1
        result |= (x & 0x7F) << shift
        if (x & 0x80) == 0:
            break
        shift += 7
    return result, o


def insn_units(op, data, pos, end):
    """Instruction length in 16-bit code units.

    One wrong width desynchronises everything after it, and the failure is quiet:
    the decode keeps producing plausible-looking instructions, just shifted, so
    every offset you derive from that point is wrong. Two width traps are common
    enough to call out:

      * `0x32`-`0x3D` (if-test 22t / if-testz 21t) are **2** units, not 1. Treating
        them as 1 invents a fake second instruction at every branch.
      * `0x1A` (const-string/jumbo) is emitted as a **4-byte** form (op, register,
        uint16 string index) by real toolchains and read that way by ART and
        baksmali, even though the reference format for the opcode is 31c. Counting
        it as 3 units is the single most costly width error -- it shifts the rest
        of the method by one unit per occurrence.
      * `0x28` is `goto` (10t, **1** unit), `0x29` is `goto/16` (2 units) and
        `0x2A` is `goto/32` (3 units). Do not read 0x28 as a two-unit form.

    Whenever a decode is used to derive a patch offset, assert that the walk ends
    exactly on `insns_off + insns_size*2`. See `decode_all`.
    """
    if op == 0x00:
        # payload nop: `00 <ident> <size>` with ident 1..3; a plain `00 00` is a
        # one-unit nop. Never treat every 00 as a payload.
        if pos + 4 <= end and (data[pos + 1] & 0xFF) in (0x01, 0x02, 0x03):
            return 1 + int.from_bytes(data[pos + 2:pos + 4], "little")
        return 1
    # -- 1 unit -------------------------------------------------------------
    if op in (0x01, 0x04, 0x07, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10,
              0x11, 0x12,                      # 12x / 11x / 11n / 10x
              0x1C, 0x1D, 0x26, 0x27):         # monitor-enter/exit, throw, goto
        return 1
    if 0x7B <= op <= 0x8F:                     # 12x unop
        return 1
    if 0xB0 <= op <= 0xCF:                     # 12x binop/2addr
        return 1
    if 0xE3 <= op <= 0xFC:                     # 10x family
        return 1
    # -- 2 units ------------------------------------------------------------
    if op in (0x02, 0x05, 0x08):               # 22x move/from16 variants
        return 2
    if op in (0x13, 0x15, 0x16, 0x17, 0x19, 0x1A, 0x1B, 0x1E, 0x1F,
              0x20, 0x21, 0x23, 0x24):         # 21s/21h/21c/22c/35c/3rc
        return 2
    if 0x2C <= op <= 0x31:                     # 23x cmp
        return 2
    if op in IF_TEST or op in IF_TESTZ:        # 22t / 21t  <-- 2, not 1
        return 2
    if 0x44 <= op <= 0x51:                     # 23x aget/aput
        return 2
    if 0x52 <= op <= 0x5F:                     # 22c iget/iput
        return 2
    if 0x60 <= op <= 0x6D:                     # 21c sget/sput
        return 2
    if 0x90 <= op <= 0xAF:                     # 23x binop
        return 2
    if 0xD0 <= op <= 0xD7:                     # 22s binop/lit16
        return 2
    if 0xD8 <= op <= 0xE2:                     # 22b binop/lit8
        return 2
    if op == 0x29:                             # goto/16 (20t)
        return 2
    # -- 3 units ------------------------------------------------------------
    if op in (0x03, 0x06, 0x09,               # 32x
              0x14, 0x18,                     # 31i const, const-wide/32
              0x22, 0x25,                     # 22c new-array, 31t fill-array
              0x2A, 0x2B,                     # 31t packed/sparse-switch
              0x6E, 0x6F, 0x70, 0x71, 0x72,   # 35c invoke
              0x74, 0x75, 0x76, 0x77, 0x78):  # 3rc invoke/range
        return 3
    # -- payloads / unknown -------------------------------------------------
    return 1


class Dex(object):
    """Structural reader for one dex image."""

    def __init__(self, data, name="classes.dex"):
        self.d = data
        self.name = name
        self.header = {k: u32(data, v) for k, v in OFFSETS.items()}

    # ---- sanity -----------------------------------------------------------
    def check(self):
        """Return a list of structural complaints; empty means it parses."""
        problems = []
        size = len(self.d)
        if self.d[:4] != b"dex\n":
            problems.append("not a dex: magic=%r" % self.d[:4])
        for key in ("string_ids_off", "type_ids_off", "proto_ids_off",
                    "field_ids_off", "method_ids_off", "class_defs_off"):
            off = self.header[key]
            if not (0 < off < size):
                problems.append("%s=0x%x out of range (file size %d)"
                                % (key, off, size))
        declared = self.header["file_size"]
        if declared and declared != size:
            problems.append("header file_size=%d but actual=%d" % (declared, size))
        return problems

    # ---- index tables -----------------------------------------------------
    def string(self, idx):
        p = u32(self.d, self.header["string_ids_off"] + idx * 4)
        _utf16_len, p = read_uleb(self.d, p)
        end = self.d.index(b"\x00", p)
        return self.d[p:end].decode("utf-8", "replace")

    def string_safe(self, idx):
        """Like string() but never raises -- a desynced decode passes junk index.

        A renderer that throws on a bad index hides the very symptom the caller is
        looking for (a decode that has drifted), so return a marker instead.
        """
        try:
            if idx >= self.header["string_ids_size"]:
                return "<string_idx %d out of range>" % idx
            return self.string(idx)
        except Exception:
            return "<string_idx %d unreadable>" % idx

    def type_(self, idx):
        return self.string(u32(self.d, self.header["type_ids_off"] + idx * 4))

    def proto(self, idx):
        o = self.header["proto_ids_off"] + idx * 12
        ret = self.type_(u32(self.d, o + 4))
        poff = u32(self.d, o + 8)
        params = []
        if poff:
            n = u32(self.d, poff)
            p = poff + 4
            for _ in range(n):
                params.append(self.type_(u16(self.d, p)))
                p += 2
        return "(" + "".join(params) + ")" + ret

    def field(self, idx):
        o = self.header["field_ids_off"] + idx * 8
        return (self.type_(u16(self.d, o)), self.string(u32(self.d, o + 4)),
                self.type_(u16(self.d, o + 2)))

    def method(self, idx):
        o = self.header["method_ids_off"] + idx * 8
        return (self.type_(u16(self.d, o)), self.string(u32(self.d, o + 4)),
                self.proto(u16(self.d, o + 2)))

    def find_class(self, fqcn):
        """Return the class_def_item offset for a 'Lpkg/Name;' FQCN, or None."""
        for i in range(self.header["class_defs_size"]):
            o = self.header["class_defs_off"] + i * 32
            if self.type_(u32(self.d, o)) == fqcn:
                return o
        return None

    def methods_of(self, fqcn):
        """Yield (section, method_idx, class, name, descriptor, code_off)."""
        cd = self.find_class(fqcn)
        if cd is None:
            raise KeyError("class not found: %s" % fqcn)
        p = u32(self.d, cd + 24)
        if p == 0:
            return
        sf, p = read_uleb(self.d, p)
        inf, p = read_uleb(self.d, p)
        dm, p = read_uleb(self.d, p)
        vm, p = read_uleb(self.d, p)
        for _ in range(sf + inf):                     # skip field lists
            _i, p = read_uleb(self.d, p)
            _a, p = read_uleb(self.d, p)
        for section, count in (("direct", dm), ("virtual", vm)):
            running = 0
            for _ in range(count):
                diff, p = read_uleb(self.d, p)
                running += diff                        # indices are delta-encoded
                _acc, p = read_uleb(self.d, p)
                code_off, p = read_uleb(self.d, p)
                cls, name, desc = self.method(running)
                yield section, running, cls, name, desc, code_off

    def find_method(self, fqcn, name, desc):
        """Return (section, method_idx, code_off) or None."""
        for section, idx, _cls, nm, ds, code_off in self.methods_of(fqcn):
            if nm == name and ds == desc:
                return section, idx, code_off
        return None

    def find_methods_named(self, fqcn, name):
        """All overloads of a name -> list of (section, idx, desc, code_off)."""
        out = []
        for section, idx, _cls, nm, ds, code_off in self.methods_of(fqcn):
            if nm == name:
                out.append((section, idx, ds, code_off))
        return out

    def class_names(self):
        for i in range(self.header["class_defs_size"]):
            o = self.header["class_defs_off"] + i * 32
            yield self.type_(u32(self.d, o))

    # ---- code -------------------------------------------------------------
    def code_info(self, code_off):
        return {
            "registers": u16(self.d, code_off),
            "ins": u16(self.d, code_off + 2),
            "outs": u16(self.d, code_off + 4),
            "tries": u16(self.d, code_off + 6),
            "debug_info_off": u32(self.d, code_off + 8),
            "insns_size": u32(self.d, code_off + 12),
            "insns_off": code_off + 16,
        }

    def decode(self, code_off):
        """Yield dicts describing each instruction of one method body.

        Callers should assert the walk ends exactly on insns_off+insns_size*2;
        landing short or long means the format table is wrong somewhere.
        """
        info = self.code_info(code_off)
        pos = info["insns_off"]
        end = pos + info["insns_size"] * 2
        while pos < end:
            op = self.d[pos]
            units = insn_units(op, self.d, pos, end)
            if units < 1 or pos + units * 2 > end:
                return
            yield {
                "off": pos, "op": op, "units": units,
                "name": OP_NAMES.get(op, "op_%02x" % op),
                "raw": bytes(self.d[pos:pos + units * 2]),
                "registers": info["registers"],
            }
            pos += units * 2

    def decode_all(self, code_off):
        """Full listing as a list, plus a verdict on whether it ended cleanly."""
        insns = list(self.decode(code_off))
        info = self.code_info(code_off)
        expected = info["insns_off"] + info["insns_size"] * 2
        ended = insns[-1]["off"] + insns[-1]["units"] * 2 if insns else info["insns_off"]
        return insns, (ended == expected), expected

    def insn_at(self, code_off, target_off):
        for insn in self.decode(code_off):
            if insn["off"] == target_off:
                return insn
        return None

    # ---- operand helpers --------------------------------------------------
    def branch_target(self, insn):
        """Absolute target of a branch, or None if the instruction is not one."""
        op, pos, raw = insn["op"], insn["off"], insn["raw"]
        if op in IF_TEST or op in IF_TESTZ:
            return pos + s16(u16(self.d, pos + 2)) * 2
        if op == 0x27:                       # goto (10t, signed byte)
            off = raw[1]
            if off > 127:
                off -= 256
            return pos + off * 2
        if op == 0x28:
            return pos + s16(u16(self.d, pos + 2)) * 2
        if op == 0x29:
            off = u32(self.d, pos + 2)
            if off > 0x7FFFFFFF:
                off -= 0x100000000
            return pos + off * 2
        return None

    def branch_regs(self, insn):
        """(regs_read, kind) for a conditional branch."""
        if insn["op"] in IF_TEST:
            return [insn["raw"][1] >> 4, insn["raw"][1] & 0xF], "if-test"
        if insn["op"] in IF_TESTZ:
            return [insn["raw"][1] & 0xF], "if-testz"
        return [], None

    def all_targets(self, code_off):
        """Set of every absolute branch target in one method."""
        targets = set()
        for insn in self.decode(code_off):
            t = self.branch_target(insn)
            if t is not None:
                targets.add(t)
        return targets

    # ---- description ------------------------------------------------------
    def describe(self, insn):
        """One-line human rendering with resolved field/method/string names."""
        op, pos, raw = insn["op"], insn["off"], insn["raw"]
        text = "0x%x: %-14s %s" % (pos, raw.hex(), insn["name"])
        if op in IF_TEST:
            text += " v%d,v%d -> 0x%x" % (raw[1] >> 4, raw[1] & 0xF,
                                          self.branch_target(insn))
        elif op in IF_TESTZ:
            text += " v%d -> 0x%x" % (raw[1] & 0xF, self.branch_target(insn))
        elif op in (0x27, 0x28, 0x29):
            text += " -> 0x%x" % self.branch_target(insn)
        elif op in IFIELD_OPS:
            cls, nm, ty = self.field(u16(self.d, pos + 2))
            text += " v%d <- v%d.%s:%s" % (raw[1] & 0xF, raw[1] >> 4, nm, ty)
        elif op in PFIELD_OPS:
            cls, nm, ty = self.field(u16(self.d, pos + 2))
            text += " v%d -> v%d.%s:%s" % (raw[1] & 0xF, raw[1] >> 4, nm, ty)
        elif op in SFIELD_OPS:
            cls, nm, ty = self.field(u16(self.d, pos + 2))
            text += " %s.%s:%s" % (cls, nm, ty)
        elif op in INVOKE_OPS:
            cls, nm, ds = self.method(u16(self.d, pos + 2))
            text += " %s.%s%s" % (cls, nm, ds)
        elif op in (0x19, 0x1A):
            # Both forms carry the string index as a uint16 at byte offset 2.
            # Reading a uint32 here gives a huge index that walks off the table.
            text += ' "%s"' % self.string_safe(u16(self.d, pos + 2))
        elif op == 0x12:
            lit = raw[1] & 0xF
            text += " v%d, %d" % (raw[1] >> 4, lit - 16 if lit > 7 else lit)
        return text


# ---------------------------------------------------------------------------
# dex header integrity
# ---------------------------------------------------------------------------

def fix_dex_header(data):
    """Recompute a dex header's checksum and signature IN THE CORRECT ORDER.

    Order is not cosmetic:
        bytes 12..32 = sha1(data[32:])      -- signature first
        bytes  8..12 = adler32(data[12:])   -- checksum last, covers the signature

    Reversed, the adler32 is taken while the signature field is still zeroed, so
    the header never verifies. Android logs
    `Failure to verify dex file ...: Bad checksum (computed, expected)` -- the
    real value shows up as "expected" -- and falls back to interpreting the dex,
    which can surface as an unrelated ClassNotFoundException at startup.

    Accepts and returns a bytearray; also returns the before/after values so a
    caller can print them.
    """
    before_checksum = int.from_bytes(data[8:12], "little")
    before_signature = bytes(data[12:32])

    data[12:32] = hashlib.sha1(bytes(data[32:])).digest()
    after_signature = bytes(data[12:32])

    import zlib
    after_checksum = zlib.adler32(bytes(data[12:])) & 0xFFFFFFFF
    data[8:12] = after_checksum.to_bytes(4, "little")

    return {
        "before_checksum": before_checksum, "after_checksum": after_checksum,
        "before_signature": before_signature, "after_signature": after_signature,
    }


def verify_dex_header(data):
    """Return (checksum_ok, signature_ok) for a bytearray/bytes dex."""
    import zlib
    stored_c = int.from_bytes(data[8:12], "little")
    calc_c = zlib.adler32(bytes(data[12:])) & 0xFFFFFFFF
    return stored_c == calc_c, bytes(data[12:32]) == hashlib.sha1(bytes(data[32:])).digest()


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_dex(source, entry=None):
    """Load a Dex from a .dex path, an .apk/.zip path, or raw bytes.

    For an archive, `entry` picks a member (default: the first classes*.dex).
    Returns (Dex, entry_name).
    """
    if isinstance(source, (bytes, bytearray)):
        return Dex(bytes(source), entry or "<bytes>"), entry or "<bytes>"
    path = str(source)
    if path.lower().endswith((".apk", ".zip", ".jar", ".xapk", ".apks", ".apkm")):
        with zipfile.ZipFile(path) as z:
            if entry:
                return Dex(z.read(entry), entry), entry
            candidates = sorted(n for n in z.namelist()
                                if n.startswith("classes") and n.endswith(".dex"))
            if not candidates:
                raise ValueError("no classes*.dex in %s" % path)
            name = candidates[0]
            return Dex(z.read(name), name), name
    with open(path, "rb") as fh:
        return Dex(fh.read(), path), path


def main(argv):
    if len(argv) != 5:
        print(__doc__)
        return 2
    target, fqcn, name, desc = argv[1:5]
    dex, entry = load_dex(target)
    print("== %s (entry %s, %d bytes)" % (target, entry, len(dex.d)))
    problems = dex.check()
    for p in problems:
        print("  [structure] %s" % p)
    if problems:
        print("  refusing to continue on a structurally broken read")
        return 1

    found = dex.find_method(fqcn, name, desc)
    if not found:
        print("method not found: %s->%s%s" % (fqcn, name, desc))
        print("methods in class:")
        for section, idx, _c, nm, ds, code_off in dex.methods_of(fqcn):
            print("  [%s] %s%s code_off=0x%x" % (section, nm, ds, code_off))
        return 1

    section, idx, code_off = found
    info = dex.code_info(code_off)
    insns, clean, expected = dex.decode_all(code_off)
    print("== %s.%s%s  [%s] method_idx=%d" % (fqcn, name, desc, section, idx))
    print("   code_off=0x%x insns_off=0x%x insns_size=%d registers=%d"
          % (code_off, info["insns_off"], info["insns_size"], info["registers"]))
    print("   decoded %d instructions; ended cleanly: %s" % (len(insns), clean))
    if not clean:
        print("   WARNING: decode did not land on 0x%x -- offsets below are suspect"
              % expected)

    regs = info["registers"]
    over = [i for i in insns if _max_reg(i) >= regs]
    if over:
        print("   WARNING: %d instruction(s) reference a register >= %d; "
              "desync likely" % (len(over), regs))

    targets = dex.all_targets(code_off)
    print("   branch targets: %s" % ", ".join(sorted("0x%x" % t for t in targets)))
    print("-- listing --")
    for insn in insns:
        mark = " <== branch target" if insn["off"] in targets else ""
        print("  " + dex.describe(insn) + mark)
    return 0


def _max_reg(insn):
    """Highest register number named by an instruction (rough but sufficient)."""
    raw, op = insn["raw"], insn["op"]
    if op in IF_TEST or op in IFIELD_OPS or op in PFIELD_OPS:
        return max(raw[1] >> 4, raw[1] & 0xF)
    if op in IF_TESTZ:
        return raw[1] & 0xF
    if op == 0x12:
        return raw[1] >> 4
    if op in (0x01, 0x04, 0x07, 0x0A, 0x0B, 0x0C, 0x0D, 0x0F, 0x10, 0x11,
              0x1C, 0x1D, 0x1E):
        return raw[1] & 0xF
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
