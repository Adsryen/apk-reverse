# Dart AOT (Flutter) — reaching the layer that actually owns the logic

Load this when: the target is a Flutter app (`libflutter.so` + `libapp.so`) and the behaviour you
must change is decided **inside** the Dart snapshot, not in the dex. The Java side of a Flutter app
is a thin plugin shell; a dex-only plan will stall (`framework-runtimes.md` §the layer trap).

Everything below assumes you already confirmed the runtime is Flutter and that Java hooks fire
**zero times** while the UI plainly works.

---

## 1. Pin the Dart version before choosing any tool

The snapshot format is version-specific. A decompiler built for another Dart version may run and
produce plausible-but-wrong output, which is worse than failing.

```python
import re
blob = open('libflutter.so', 'rb').read()          # the engine, not libapp.so
m = re.search(rb'(\d+\.\d+\.\d+ \(stable\)[^\x00]{0,60})', blob)
print(m.group(1).decode() if m else 'not found')   # e.g. b'3.9.0 (stable) (Mon ...) on "android_arm64"'
```

If the string is absent, fall back to the snapshot hash the loader reports at runtime, or to the
engine build id in `libflutter.so`'s version string.

## 2. Get a decompiler that matches that version

**blutter** is the practical choice for Android `libapp.so` (arm64). It reconstructs the object pool
and per-class declarations. It is a *source tree you build*, not a binary you download — and its
prebuilt outputs only cover the Dart versions someone already built.

The version question is the first obstacle, and it has a clean answer:

- blutter's git HEAD typically supports newer Dart than its shipped `dartsdk/` directory.
- When the target's version is missing, blutter fetches it itself: it sparse-clones
  `dart-lang/sdk` at that version tag (only `runtime`, `tools`, `third_party/double-conversion`),
  generates a source list, and builds a `dartvm` static library for the target ABI.
- That build needs a real toolchain: `cmake` (>=3.20 is fine, including 4.x), `ninja`, `git`, and a
  C++ compiler with C++20 `<format>` support (VS 2022 on Windows, gcc>=13 / clang>=16 elsewhere).
  A `vcvars64`-style environment must be active before the build, and `CMakeLists` in the tree pins
  `cmake_minimum_required(3.20)`.
- Budget **tens of minutes** for the first build of a new version and run it as a background job;
  the compiler log is enormous (per-file include trees), so read only its tail.

Outputs of interest:

| Output | What it gives you | What it does *not* give |
|---|---|---|
| `pp.txt` | every object-pool entry with its `pp+0x…` offset: strings, types, closures, fields, stubs | who references what |
| `objs.txt` | reconstructed object shapes with type annotations | code |
| `asm/` | per-class declarations | **instructions — there are none here** |
| `ida_script/`, `blutter_frida.js` | symbol/annotation helpers | a finished analysis |

> `asm/` having one file per (obfuscated) class invites the assumption that it holds disassembly.
> It does not. Do not plan around it.

**`product` builds carry no debug info.** Expect `no-code_comments`, no function names, and
obfuscated identifiers. That is normal; the strings still survive (see §7).

## 3. The object pool is the whole game

Dart AOT uses **compressed pointers**: heap references are 32-bit offsets from a base held in a
dedicated register. Constants, strings, types, closures and field metadata live in one contiguous
**object pool**, reached through that register.

Two offset spaces exist and they are **not the same number** — mixing them wastes hours:

- **PP offsets** (`pp+0x…`) — what `pp.txt` and every pool-load in disassembly use.
- **file offsets** — where a byte actually sits in `libapp.so` on disk.

Keep the mapping explicit in your notes. When a tool reports "this string is at X", state which
space X is in.

## 4. Build your own reference index (blutter will not give you this)

`pp.txt` tells you what is in the pool. To *find the code that uses it* you need pool-offset →
referencing-instruction-address. Generate it once, then query it constantly:

```
python dart_pprefs.py libapp.so pp_refs.json
python dart_pprefs.py --lookup pp_refs.json 0x1d1a8 0xc9d0
```

**Do not build this index with a full-capstone pass.** Decoding every instruction of a multi-MB
`.text` with `detail=True` and querying `regs_access()` per instruction costs minutes of CPU and
1–2 GB of peak memory, and on a 16 GB host it presents as a hang with no progress output. Only three
encodings can read the pool, so decode them from the raw 32-bit words instead — the shipped script
does exactly that and finishes in seconds. The same argument applies to building a call graph
(§9): decode `B`/`BL` arithmetically.

## 5. What the registers mean

Stable across Dart 3.x arm64 AOT. Verify once on a known function, then rely on it.

| Register | Role |
|---|---|
| `x27` | **object pool base (PP)** — every constant/string/type load goes through it |
| `x26` | current thread (`[x26,#0x38]` stack limit, `[x26,#0x68]` isolate group) |
| `x28` | heap base — how compressed pointers are decompressed |
| `x22` | **null/base for booleans** (see §6) |
| `x15` | Dart's own stack pointer (not the system SP) |
| `x21` | class dispatch table (virtual calls load a target from it) |

## 6. Booleans are not 0/1

`true` and `false` are objects immediately adjacent to null, so they appear as small fixed offsets
from `x22`:

```asm
add  x0, x22, #0x20      ; construct TRUE
add  x0, x22, #0x30      ; construct FALSE
tbnz w0, #4, <label>     ; test bit 4 of the value
tbz  w0, #4, <label>
```

The bit-4 test is the standard "is this the false object" check, and it is the cheapest place to
force a decision: replacing the conditional branch with an unconditional one, or replacing a
constructed constant, flips the outcome without changing structure.

## 7. String encoding — get this exactly right

Pool string entries are serialized as:

```
[ tag byte ][ payload ]

tag = 0x80 | (len << 1) | two_byte_bit
```

- **one-byte strings** (ASCII / Latin-1): `payload` is the raw bytes.
- **two-byte strings**: `payload` is **UTF-16LE**.

Consequences that decide whether your search works:

- An **ASCII** literal (`/api/foo`, `isVip`, a URL) is found by a **UTF-8 byte search**. It is a
  one-byte string — searching UTF-16 for it will miss.
- A **CJK / non-Latin** literal is a two-byte string: a UTF-8 search returns **zero**, a UTF-16LE
  search hits. This is the case that makes people wrongly conclude "the strings were stripped".
- Therefore: **search ASCII as UTF-8 and non-ASCII as UTF-16LE**, rather than forcing one encoding
  on everything. (This is the concrete form of `pitfalls.md` P25.)
- A raw byte scan for the tag pattern finds many false candidates. Accept a candidate only when
  entries **chain** — the previous entry's `tag+payload` must end exactly where the next candidate
  begins. Without that constraint you get order-of-magnitude more garbage than strings; a
  per-byte scan of a multi-MB snapshot once produced ~880k "strings" of which essentially all were
  misaligned noise, and a "no such feature present" conclusion was drawn from it.

```
python dart_pool_strings.py libapp.so strings.tsv --min 3
```

## 8. Reading AOT code: three signatures that carry most of the weight

Once you can disassemble a window with pool annotations, most business logic resolves into these
shapes.

**A — reading a map / JSON object (`map[key]`)**
```asm
ldur x3, [x29, #-8]        ; the Map
ldur x0, [x3, #-1]         ; compressed class id sits at offset -1
ubfx x0, x0, #0xc, #0x14   ; decode class id
mov  x1, x3
...  x2 = <pool string>    ; <- the key, annotated by your pool map
add  x30, x0, #0x342
ldr  x30, [x21, x30, lsl #3]
blr  x30                   ; this is map[key]
```
Remember the quartet: `ldur [..,#-1]` + `ubfx #0xc,#0x14` + `add x30,x0,...` + `blr`.

**B — writing a map (`map[key] = value`)**
```asm
...  x16 = <pool string>   ; the key
stur w16, [x0, #0xf]       ; key stored into the freshly built map
...  ; then the value at the next slot
```
`stur` writes, `blr` reads. Confusing the two means patching a serializer that never touches the UI.

**C — function entry**
```asm
stp x29, x30, [x15, #-0x10]!
mov x29, x15
sub x15, x15, #0x20
ldr x16, [x26, #0x38]
cmp x15, x16
b.ls <stack-overflow handler>
```
Use this to find function boundaries when you need to delimit one.

## 9. The locating workflow

1. **Anchor on a string.** Search the pool for the shortest distinctive token — a field name, an
   endpoint path, a label. Prefer identifiers over sentences (a sentence may be assembled from
   fragments).
2. **Find its referencing instructions** via your index (§4).
3. **Disassemble a window** around each reference with pool annotations:
   ```
   python dart_disasm.py libapp.so --pp pp.txt --refs pp_refs.json 0x26e390
   python dart_disasm.py libapp.so --pp pp.txt --refs pp_refs.json --range 0x64f310 0x64f3e0
   ```
4. **Classify the site**: read (A) or write (B)? For writes, check whether the value is a constant
   from the pool — that is a "send this flag" site, not a "decide locally" site.
5. **Walk outward.** Find the enclosing function entry (§8C), then find its callers:
   ```
   python dart_disasm.py libapp.so --index callers.json --build-index
   python dart_disasm.py libapp.so --index callers.json 0x26e230
   ```
6. **Cross-validate by clustering.** Related strings usually sit **adjacent in the pool** and are
   referenced from **adjacent code**. If two field names are a few bytes apart in the pool and their
   reference sites are a few instructions apart, you are looking at one coherent piece of logic —
   strong evidence you are in the right place.

## 10. Patching this layer

- **Prefer changing the data source over the decision point.** Locate the chain
  "read field from map → type conversion → store to stack slot" and replace the middle with a load
  of a pool constant. One edit then feeds every consumer, instead of chasing each comparison. This
  has produced clean results where per-condition patches did not.
- **Boolean sites** are the cheapest: `tbnz`/`tbz` → `nop` (always fall through) or → an
  unconditional branch; `add xD, x22, #0x20` ↔ `#0x30` to flip a constructed constant.
- **A pool string may be shared.** Before editing one, count its references. If the same entry is
  read by several sites, changing it changes all of them — self-consistent and therefore useless
  for splitting behaviour. Prefer editing code over shared data.
- **Assert your addresses.** Patch with the original bytes asserted first and re-read the result
  afterwards; an address that is off by one instruction will happily corrupt a snapshot into
  something that still loads.
- **`libapp.so` inside an APK is usually deflate-compressed**, so in-place byte patching of the zip
  entry is not possible — patch the extracted file, then replace the whole entry
  (`repack-and-sign.md`).

## 11. Traps specific to this layer

- **Identifiers are ambiguous across layers.** A pool string that reads like a domain concept can
  belong to a standard library or a wire protocol instead. A near-miss example worth remembering:
  the token `expires` resolved to HTTP **response-header** parsing (its siblings were `date`,
  `host`, `connection`), not to a subscription expiry field. **Read the surrounding strings and the
  code shape before assigning meaning** — one misleading identifier can send a whole analysis down
  the wrong branch.
- **Obfuscated names are not identities.** Symbol names are mangled (`_abc@12345` shapes are
  common) and change between builds. String literals do survive, so anchor on those.
- **Clusters reveal structure.** Adjacent pool entries plus adjacent reference sites indicate one
  subsystem; use it to avoid guessing what a function is for.
- **A write-only flag is usually an outbound parameter, not a local switch.** If a string is
  referenced exactly once, at a site that stores a constant into a map that is then sent, the client
  is *reporting* a value — changing it does not change local behaviour. Confirm whether the value is
  ever read before treating it as a gate.
- **Full-file disassembly is not a debugging tool** (§4). Windowed disassembly is.

## 12. Verification

Static: asserted patch bytes, re-read from the built artifact, plus structural checks
(`verification.md`). Runtime: the changed behaviour must be observed in the app's own UI — for this
layer that means an actual launch, because nothing about Dart AOT code proves itself statically.
If the snapshot drives a decision that a server also enforces, see `membership-and-limits.md`:
getting the client side right does not make the outcome reachable.
