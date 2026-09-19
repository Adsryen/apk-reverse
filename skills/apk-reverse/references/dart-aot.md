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

You need a tool that resolves the snapshot container — something that turns `libapp.so` into named
functions, class layouts and, above all, a **pool listing with `pp+0x…` offsets**. Everything in §4
onward consumes that listing; without it the workflow cannot start, and no script in this skill can
produce it (see §4 for why the mapping is not recoverable from the binary alone).

Two routes exist. Pick deliberately, because their version reporting differs.

**Route A — aotopsy: no toolchain, run it now.** A single static binary (pure Go) that parses the
snapshot binary format directly, with no Dart VM and no SDK compile. On a real Dart 3.6.0
`libapp.so` the full pipeline ran out of the box: 30,586 functions, 6,133 class layouts, 39,202 pool
entries (38,274 resolved), 175,120 call edges with 95.7% of indirect sites annotated, plus
`functions.jsonl`, `call_edges.jsonl`, `classes.jsonl`, `string_refs.jsonl`,
`dispatch_table.jsonl` and an annotated `asm/` tree. It also supports x86_64, which blutter does not.

Its `doctor` subcommand reports a Dart version that is a **structural profile label, not the SDK
version**: on the sample above it printed `3.6.2` while the engine banner, the snapshot hash and a
byte search all said `3.6.0`, and no `3.6.2` byte sequence existed in either `.so`. That matters only
if you feed the number to a VM-compiling tool — use §1's banner for that. Its own README states the
detection is structure-based, so expect the label to name the newest matching profile rather than the
compiler's version.

**Route B — blutter: full fidelity, needs a build.** It embeds a matching Dart VM and deserializes
through the VM's own code paths, which yields the canonical `pp.txt` in the `pp+0x…` space. It is a
*source tree you build*, not a binary you download: its `bin/` is gitignored and it publishes no
release artifacts, so there is nothing prebuilt to fetch for a given Dart version.

- blutter's git HEAD typically supports newer Dart than its shipped `dartsdk/` directory.
- When the target's version is missing, blutter fetches it itself: it sparse-clones
  `dart-lang/sdk` at that version tag (only `runtime`, `tools`, `third_party/double-conversion`),
  generates a source list, and builds a `dartvm` static library for the target ABI.
- That build needs `cmake` (>=3.20 is fine, including 4.x), `ninja`, `git`, and a C++ compiler with
  C++20 `<format>` support. The documented VS 2022 requirement is **over-strict** — MSVC 19.34
  (VS 17.4.3, Nov 2022) compiles and runs the `std::format` path, measured. A `vcvars64`-style
  environment must be active, and `CMakeLists` pins `cmake_minimum_required(3.20)`.
- Budget a **couple of minutes**, not "tens of minutes": the whole pipeline (clone, `init_env_win.py`,
  sparse SDK clone, cmake, nja, link) measured **≈78 s** wall clock. It uses a unity build via
  `dartvm_create_srclist.py`, which is why it is fast. The compiler log is enormous (per-file include
  trees), so read only its tail.
- **If the freshly built binary faults immediately** with `0xC0000005` and no output at all, do not
  conclude anything about the sample. Relink it (`ninja` in
  `build/blutter_dartvm<ver>_<os>_<arch>`) and try again; on the sample above the fault never
  reproduced after a relink — including for the unchanged binary — and three subsequent runs each
  completed in ~5.9 s. **One retry, then a relink, before you blame the target.**

Outputs of interest (blutter):

| Output | What it gives you | What it does *not* give |
|---|---|---|
| `pp.txt` | every object-pool entry with its `pp+0x…` offset: strings, types, closures, fields, stubs | who references what |
| `objs.txt` | reconstructed object shapes with type annotations | code |
| `asm/` | class layouts **and function bodies with full instruction listings**, pool annotations and resolved call targets | a pseudocode-level view |
| `ida_script/`, `blutter_frida.js` | symbol/annotation helpers | a finished analysis |

> `asm/` is the richest artifact in the chain. It is one file per **library URI** (mirroring the
> package path), not per class as its name suggests, and it carries annotated disassembly such as:
>
> ```
> // 0x923b3c: r0 = LinkedHashMap.from()
> //     0x923b3c: bl  #0x60165c  ; [dart:collection] LinkedHashMap::LinkedHashMap.from
> ```
>
> An earlier revision of this file claimed `asm/` contained no instructions and told the reader to
> ignore it. That was wrong and cost real time — plan around `asm/` as your primary annotated
> disassembly source.

**`product` builds carry no debug info.** Expect `no-code_comments`, no function names, and
obfuscated identifiers. That is normal; the strings still survive (see §7). Note this is a *format*
floor, not a tooling gap: the Dart compiler drops field names outside debug builds, so roughly
97-99% of instance field names are simply absent, and local/captured variable names are gone
entirely. Accessor-based recovery (`get:`/`set:` still carry the name) recovers part of the field
picture; the rest should be rendered as unknown rather than guessed.

## 3. The object pool is the whole game

Dart AOT uses **compressed pointers**: heap references are 32-bit offsets from a base held in a
dedicated register. Constants, strings, types, closures and field metadata live in one contiguous
**object pool**, reached through that register.

Two offset spaces exist and they are **not the same number** — mixing them wastes hours:

- **PP offsets** (`pp+0x…`) — what `pp.txt` and every pool-load in disassembly use.
- **file offsets** — where a byte actually sits in `libapp.so` on disk.

Keep the mapping explicit in your notes. When a tool reports "this string is at X", state which
space X is in.

**There is no constant between the two spaces — do not go looking for one.** The relationship is a
property of the *reconstructed* pool, not of the file, so it cannot be computed from `libapp.so`
alone. Measured over the 4,241 strings that appear in both the string table and `pp.txt`, there were
**4,237 distinct deltas** (range −1,361,429 to +277,654). A string recovered by file offset therefore
does not lead to its pool offset, which is exactly why §2 insists on a snapshot-decoding front end:
it is what gives you the `pp+0x…` space in the first place.

## 4. Build your own reference index (blutter will not give you this)

`pp.txt` tells you what is in the pool. To *find the code that uses it* you need pool-offset →
referencing-instruction-address. Generate it once, then query it constantly:

```
python dart_pprefs.py libapp.so pp_refs.json
python dart_pprefs.py --lookup pp_refs.json 0x1d1a8 0xc9d0
```

**Do not build this index with a full-capstone pass.** Decoding every instruction of a multi-MB
`.text` with `detail=True` and querying `regs_access()` per instruction costs minutes of CPU and
1–2 GB of peak memory, and on a 16 GB host it presents as a hang with no progress output. Only a
handful of encodings can read the pool, so decode them from the raw 32-bit words instead — the
shipped script does exactly that and finishes in seconds.

**But do not fall back to a linear capstone sweep either.** A Dart AOT `.text` begins with snapshot
metadata, not instructions — on a real `libapp.so` the section started at `0x4a0000` while the first
Dart function prologue (`stp x29, x30, [sp, #-imm]!`) was at `0x4b143c`. A linear sweep starting at
offset 0 dies on that metadata and returns **zero instructions**, which looks exactly like "this
library has no code". If you need capstone here, start at a known function address, or use
`skipdata=True`, and treat an implausibly small count as a decoding problem before you treat it as a
property of the file.

The same mask-based argument applies to building a call graph (§9): decode `B`/`BL` arithmetically
rather than by sweeping.

**A live example of why the index's completeness matters:** after this file's advice to "count the
references before editing a shared constant", one pool offset measured `[0 refs]` with the shipped
script and `[79 refs]` once a missing load family was added to the scanner. A one-sided quiet gap in
the scan reads as "nothing uses this", which is the answer that gets a shared constant edited
carelessly. If a count looks surprisingly low, suspect the scanner before believing the pool.

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
