# Advanced Unpacking — Extraction Shells, Active Invocation, and the VMP Boundary

Load this when a memory dump of a packed app has already landed on your desk and the
dump itself is the problem: the image parses, the classes are there, and the method
bodies are empty. The neighbouring files each own one stage — `packers.md` owns
*identifying* a shell and mapping what it validates, `recon.md` §Unpacking a dex-level
packer owns the whole-image memory dump and its first-pass filtering, and
`dynamic-frida.md` owns the runtime environment those dumps need. This file owns what
comes after: recognizing that a "successful" dump is only a skeleton, recovering the
missing code, and knowing where that recovery honestly stops.

**Strength note, read this first:** the repository's verification target carried no
extraction shell and no VMP, so nothing here was exercised end to end against a live
hardened sample by this skill's own verification pass. The FART/Youpk mechanisms and
the Android 12-16 failure analysis are **inferred** from public work (FART/Youpk
release notes and a 2026-08 Kanxue thread, `thread-292312`, on why classic
active-invocation hooks die on modern ART). The one **measured** element is the
detection metric: the trivial-body statistic was exercised by
`scripts/dex_dump_validate.py` against a surgical fixture derived from a real hardened
sample (see `docs/tool-verification/EXTENSION-unpacking.md`). Label your own results
the same way.

Two parts of this file have since been exercised against live hardened targets on a
rooted device. The **root-side memory route** (§Dumping when frida is refused) was run
end to end: 17 ART dex mappings exported from `/proc/<pid>/mem`, page-alignment trim
included, validated with `scripts/dex_dump_validate.py`; the evidence, the device-shell
traps and the throughput numbers are recorded in
`docs/tool-verification/EXTENSION-rootdump.md`. The `frida-dexdump` refusal that
motivates that section is in `docs/tool-verification/EXTENSION-device-run.md`. The
FART/active-invocation half of the file is still **inferred** — no extraction-shell
target has been spliced end to end here.

## The four shapes a dump can be

Diagnose before choosing a route. Run `scripts/dex_dump_validate.py` over the dump
directory and read the `stub%` column — the four shapes separate on it.

| The dumped image | `stub%` | Diagnosis | Route |
|---|---|---|---|
| Parses, many classes, real bodies | near-baseline | First-generation landing shell; the whole-dex dump **is** the original | Done — filter (`recon.md` §Unpacking a dex-level packer) and proceed to patching |
| Parses, many classes, most bodies are `return-void` stubs or nop fills | high | **Extraction shell skeleton** — bodies are decrypted only on invocation | FART loop, this file |
| Whole classes appear as bare `native` declarations | n/a | dex2c / JNI sink — the code left the dex entirely | `code-virtualization-and-custom-linkers.md` |
| Parses, bodies present but instruction streams are nonsense to a dalvik disassembler | baseline | **Real Dex VMP** — private opcodes behind a native interpreter | Last section of this file, and be honest about the cost |

Two supporting signals worth recording while you are here (the second is measured on
this repo's hardened sample): a shipped shell `classes.dex` can be megabytes in size
yet define only a handful of classes — the bytes are payload, not code, so class count
and file size move independently under a packer. And a dump whose signature field
disagrees with its own contents while the checksum agrees is not necessarily corrupt;
a shell that never verifies its own header can ship it that way, so treat
checksum/signature results from `verify_dex_header` as evidence about *who touched the
image*, not as a pass/fail gate on usability.

## Measuring extraction instead of guessing

The metric that separates shape 2 from shape 1 is the **trivial-body ratio**: among
methods that *have* a `code_item` (`code_off != 0`), the fraction whose instruction
stream, with plain `nop` units skipped, contains nothing but a single `return*`.
`code_off == 0` methods are abstract or native declarations — that absence is normal
and is excluded from the ratio. A method with a `code_item`, real `insns_size`, and a
lone `return-void` inside is what an extraction shell leaves behind.

```bash
python scripts/dex_dump_validate.py <dump_dir> --find 'Lcom/example/app/'
```

The script dedupes by sha256 (never by size — same-size dumps of one dex have been
measured to differ in ~73% of their bytes), rejects structurally impossible images
(bad magic, `file_size` mismatch, ids out of range), counts classes and stub bodies,
and ranks which surviving image is the most likely original.

Calibration, **inferred** from field reports rather than measured across a population:
ordinary app code carries a few percent of genuinely trivial bodies (constructors that
do nothing, interface stubs); a ratio in the tens of percent or higher is a skeleton,
not code. A ratio that is high *and* the image parses is the extraction-shell
signature — a first-generation dump of the same app would show the same classes with
real bodies.

## The FART loop: skeleton, invocation, splice

Extraction shells decrypt a method body only when that method first executes. A dump
taken at any fixed moment therefore holds whatever the app happened to invoke before
you dumped — mostly stubs. Waiting for the UI to wander into every method is not a
plan (thousands of methods, many on paths a user never triggers). The FART family of
tools closes the loop with three steps, **inferred** (not run by this repo against a
live extraction shell):

1. **Dump the whole image.** Class definitions, field and method signatures, string
   tables — the skeleton is complete even when every body is a stub. This is the
   ordinary `recon.md` dump; it gives you the address map for step 3.
2. **Actively invoke every method.** Walk the dumped class list reflectively and call
   each method (dummy arguments; most will throw, which is fine — the point is that
   the *shell* decrypts and installs the body as the method is entered). Hook inside
   ART at the interpreter's entry so that, as each method begins executing, the
   method's `code_item` — now holding the decrypted body — is written to disk,
   tagged with its `method_idx`. These per-method records are the "bin" files of a
   FART dump.
3. **Splice the bodies back into the skeleton.** For each record, overwrite the
   stub body in the whole-dex image at the offset the skeleton gives you, fix the
   header (`scripts/dexutil.py` `fix_dex_header` — signature first, checksum last),
   and **accept nothing until jadx or baksmali parses the result** and the method
   count matches the skeleton. "It assembled" is not "it repaired".

## The code_item length trap

Splicing fails in a specific place often enough to deserve its own section: the
computed length of a `code_item`. The full layout is

```
registers u16, ins u16, outs u16, tries u16,          -- 8 B
debug_info_off u32, insns_size u32,                   -- 8 B  (header = 16 B)
insns[insns_size] u2,                                 -- the instruction stream
[padding u2]        -- ONLY if tries_size > 0 AND insns_size is odd
try_item[tries_size]  { start_addr u32, insn_count u16, handler_off u16 },  -- 8 B each
encoded_catch_handler_list  { uleb size; per handler: sleb offs... }        -- variable
```

Two segments are routinely dropped: the odd-`insns_size` padding before `tries`, and
the whole `encoded_catch_handler_list`, which is LEB128-variable and sits *after* the
try table. Drop either and the splice boundary slides — the rebuilt method swallows
bytes from its neighbour or leaves the handler table pointing past the image, and the
failure surfaces later as a dex that half-parses. Walk the handler list with
`read_uleb` to its true end (`scripts/dexutil.py`); do not estimate it. This trap is
**inferred** from repair-tool post-mortems, and it is the first place to look when a
spliced dex parses worse than the skeleton did.

## Why the classic hooks die on Android 12-16

The original FART-era hooks assumed method entry flows through
`art::interpreter::Execute`. On Android 12-16 that assumption fails for five
independent reasons (**inferred**, from the Kanxue `thread-292312` analysis, 2026-08).
Any one of them produces the same symptom — the dumper runs, logs everything, and the
output directory stays thin:

1. **Invoke dispatch splits away from `Execute`.** A quick-entry call goes to Nterp,
   AOT or JIT code, or a bridge — none of them pass through the old `Execute` hook.
   Forcing the interpreter is not a fix either: the entry point then switches to
   Nterp, which *also* bypasses it. *Repair:* move the dump point up to
   `EnterInterpreterFromInvoke`, which sits ahead of the Nterp/interpreter split, and
   keep fallback points (special invoke branches, ClassLinker load paths, DexFile
   open, Frida ClassLoader enumeration) for the methods that still slip through.
2. **`ArtMethod` layout drift.** Field offsets and pointer-sized members changed
   across releases; a hardcoded offset reads the wrong field and the dump silently
   mislabels everything after it. *Repair:* derive offsets at runtime (probe
   `access_flags` / `quickCode` / `jniCode` on a known method) instead of compiling
   them in.
3. **Scoped Storage breaks the output quietly.** Writes to `/sdcard` fail, the log
   reads like a completed run, and the directory is empty. *Repair:* write under
   `/sdcard/Android/data/<pkg>/files/` (or app-private storage) and **check the
   `open()` return value** — the silent variant of this failure wastes a whole round.
4. **The shell fights back.** Junk classes that exit inside their initializer,
   detection of reflective enumeration, deliberate dex-header corruption in memory,
   decryption deferred to the true execution point, fingerprinting of known dumper
   thread names and paths. *Repair:* randomize your thread names and output paths,
   filter junk classes (few methods, throwaway names) before invoking, and expect the
   counter-measure list to differ per vendor.
5. **Compilation policy shifts the entry under you.** A just-installed app and one
   that has run for a while present different entry mixes (profile-guided
   compilation, Mainline module updates). *Repair:* re-probe the entry type every
   run; never cache yesterday's hook decision.

The debugging order that isolates all five in the fewest rounds: print the entry and
flags for a known method → force the interpreter → observe what the entry became →
place the dump point accordingly → force only the target package (`ignore` lists for
`androidx.*`, `com.google.*`, `kotlin.*` — forcing the framework too freezes or kills
the app) → compare a method's `code_item` before and after invocation → splice →
verify with jadx/baksmali.

## Youpk in one paragraph

Youpk is the ROM-level descendant of the same idea (**inferred**): a modified ART
performs the active invocation *inside* the runtime at class-link and interpret time,
so the reflective caller script, the entry-point guessing, and most shell
counter-measures against host-side tooling drop out — at the cost of building and
flashing a customized runtime per Android version. Choose it when the target's
anti-instrumentation defeats host-side loops entirely, and you control the device.

## The frida-dexdump route and where it stops

`frida-dexdump` walks the live ClassLoaders and writes every dex-shaped memory range.
Environment setup and its two time sinks (the `-o` directory must pre-exist, and
`-D` does not take remote devices) are recorded in `recon.md` §Unpacking a dex-level
packer; the Frida environment itself is `dynamic-frida.md`. What it hands you is a
pile of images of the four shapes above — dedupe, reject and rank them with
`scripts/dex_dump_validate.py` before touching any by hand. Its hard limit: against
an extraction shell it can only ever produce the **skeleton**, because the missing
bodies exist nowhere in memory until invoked. No amount of re-dumping fixes that;
only the invocation loop recovers them.

## Dumping when frida is refused

A hardened target can refuse instrumentation outright: the dump tool dies with
`script has been destroyed` and the process is gone before the error can be read.
That is a *protocol* refusal, not a timeout, and re-running the same attach with a
different flag is the wrong response — twice-identical failure on one variable is a
stop signal, not a hint to try a third flag. What remains is the route that never
touches the process's instrumentation interface at all: **root reads the target's own
memory** through `/proc/<pid>/maps` and `/proc/<pid>/mem`. No agent, no ptrace
attach, no server process for the shell to find.

**Read the signals carefully, because one of them lies.** The refusal presents as
(a) the dump tool's attach failing with `script has been destroyed` while the app is
otherwise healthy, and (b) pid churn. But **pid churn alone is not evidence that
frida was detected.** A 360-jiagu sample on this repository's test device was
measured exiting every 7-18 s and being restarted by the platform, with *no*
instrumentation process anywhere on the device, logging
`Process <pkg> (pid N) has died: fg TOP` and no crash, tombstone or ANR record — a
clean self-exit, i.e. the packer's own environment check. Attribution needs the
control run, and the control run needs a window longer than one restart period: a
12-second observation lands inside a 17-second cycle and reports "stable" about a
process that is not. If the sample self-exits on that cadence, every step below must
fit inside a single lifetime.

### Read the map before choosing the bytes

```bash
adb shell 'su -c "pidof <PKG>"'                       # may return nothing mid-restart
adb shell 'su -c "ps -A -o PID,NAME | grep -w <PKG>"' # more robust: matches either way
adb shell 'su -c "cat /proc/<pid>/maps"' > maps.txt
```

ART names its in-memory dex mappings for you — this is the cheapest win on the whole
route, because a mapping called
`[anon:dalvik-classes*.dex extracted in memory from <src>]` *is* a dex image, already
located, already sized, no search required:

```
7129d8c000-712a60f000 r--p  [anon:dalvik-classes.dex extracted in memory from /data/app/~~…/base.apk]
```

Copy those ranges first. Everything else — anonymous `rw-p`, `libc_malloc`, `.bss` —
is a *search* target, and searching is the expensive half.

### Address arithmetic is where this route silently breaks

Three device-shell traps cost real time on the first run, and each one produces a
plausible-looking result rather than an error:

| Trap | Symptom | Fix |
|---|---|---|
| mksh arithmetic is 32-bit | `$((16#7129d9a000))` yields `702128128` (the low 32 bits) — `skip=` then seeks to the wrong address and the dump looks like zeros | convert hex to decimal with `awk` (double precision handles 48-bit addresses exactly) |
| A VMA is page aligned | the dump is 0..4095 bytes longer than the image; a validator rejects it with `file_size=8923752 actual=8925184` (17 of 17 files on the measured run) | trim to the `file_size` at dex header offset 32 before validating |
| `grep` is line oriented | the magic contains a `0A`, so no line-oriented pattern can ever match `dex\n035\0`; `-F` with a real newline in the pattern fails too | `grep -z -a -o -b -E 'dex.035'` — with `-z`, records are NUL separated and `.` matches the newline byte; the reported offset is stream-relative, add the segment start |

One more that only bites in scripts: **toybox `awk` cannot be trusted with
`/regex/ && $0 !~ /…/`** — a filter written that way selected all 808 map lines,
including `r--p` system libraries. Filter the map with `grep` and keep `awk` for
arithmetic only.

### Export, then prove it is a dex

```bash
# inside one lifetime of the process: export a candidate range
dd if=/proc/<pid>/mem iflag=skip_bytes,count_bytes skip=<DEC_START> count=<SIZE> \
   of=/data/local/tmp/seg_<n>.bin bs=256k
adb pull /data/local/tmp/seg_<n>.bin <dumpdir>/<n>.bin      # trim first, see above

# or, without writing to the device at all: search a range in place
dd if=/proc/<pid>/mem iflag=skip_bytes,count_bytes skip=<DEC_START> count=<SIZE> bs=1M \
 | grep -z -a -o -b -E 'dex.035' | head -5
```

Then the same acceptance gate the frida route uses: `scripts/dex_dump_validate.py`
over the dump directory — sha256 dedupe, header and `file_size` validation, class
counts, `stub%`, ranking. Rename to `*.dex` first; the validator selects on extension.
Pass `--trim` when the captures come straight from VMAs: a page-aligned region is always
longer than the image it holds, so without it every file is rejected on
`file_size=… actual=…` — 17 of 17 on the measured run, all of them recoverable.

When you do **not** already know which region holds the payload —
`scripts/dex_mem_scan.py <region_dir> --dump <out_dir>` does the search and the cut in one
step: it scans the captures for the magic in bounded chunks, reads each hit's own header,
and writes exactly `file_size` bytes from there. That is the anonymous-mapping case, where
no `maps` entry names the buffer. The division of labour matches the rest of this kit:
that script **finds and cuts**, `dex_dump_validate.py` **judges**. On the measured device
the scan of 142 anonymous regions returned zero hits while the named ART mappings returned
17 images — a negative from a cheap scan is worth having before committing to a heap sweep.

Measured on the test device, this route **works**: 17 ART dex mappings exported in
one pass, all 17 parsing after the page-alignment trim, `stub%` 0.9-3.2 % (real
bodies, SDK plugins), and one of them — the mapping that came from the app's own
`base.apk` — defining exactly **4 classes** on 8.9 MB. That last image is the landing
shell skeleton, and the class count is what says so; the size says nothing. Note what
the route did *not* produce: no second application dex ever appeared in the map
across 22 s of sampling, so the packer's real payload was not sitting in memory as a
loaded ART dex while the observer watched — which is the honest boundary of every
`/proc/<pid>/mem` dump, not a defect of the tooling.

### Limits to budget for

- **The process must stay alive and keep the same pid.** A VMA map and a page table
  both belong to a live process, and every `dd` after the restart reads the wrong
  address space or nothing. On a sample that self-exits every 7-18 s, a dump routine
  must be atomic within one window and re-entrant (re-read `maps` after every
  restart) rather than a long batch.
- **Throughput is the binding constraint, not correctness.** Reading
  `/proc/<pid>/mem` through `grep -z -E` measured about **10 MB/s** on this device.
  A 1 GB ART heap is therefore a ~100 s scan — several lifetimes — so scanning the
  Java heap for a decrypted buffer is the *last* resort, not the first. Named ART dex
  mappings are free; a heap sweep is not.
- **`/proc/<pid>/map_files/` is not a shortcut on this ROM.** The directory exists
  and is root-owned, but its entries are absent/unreadable, so `dd
  if=/proc/<pid>/map_files/<start>-<end>` returns a few dozen bytes of error text.
  Use the `mem` + decimal-offset form.
- **Memcpy dumps of `.so` files are not the `.so` files.** A range lifted from
  `/proc/<pid>/mem` usually carries `PT_LOAD` contents and no section header table;
  a real ELF on disk has both. That difference is how to tell a *disk copy* of a
  library from a *memory-extracted* one — and it is why a leftover `.so` in a work
  directory must be matched against the APK it claims to come from before it is used
  as evidence.
- **In-memory dex bodies can be non-contiguous.** A decrypted image stitched across
  two VMAs (or a payload the packer splits) will not be recovered by dumping ranges
  independently; the `code_off` cross-check and the class-count sanity check in
  §Measuring extraction are what catch that, not the magic search.

## The honest boundary: real Dex VMP

The last shape is the one to say out loud: if the dump's method bodies are intact but
decode as private opcodes — rare-opcode density off the charts, unknown opcode slots,
and a large native interpreter loop behind them — the code has been virtualized, and
nothing in this repository will hand it back to you decompiled. Distinguish it from
the JNI sink first (`code-virtualization-and-custom-linkers.md`): there the methods
are `native` stubs and the logic lives as native code; here the bodies are present
and *re-encoded*.

What recovery looks like when someone does it, **all inferred**, no fixture exists in
this repo, treat as a research plan rather than a recipe:

1. **Differential hardening as a black-box oracle.** Build sample APKs containing
   every dalvik opcode in known, labeled sequences; submit them to the *same*
   hardening platform as the target; dump the returned dexes; align each original
   method with its hardened counterpart and read off the opcode substitution table.
2. **Handler map recovery.** Locate the native interpreter's dispatch table; each
   handler implements one virtual opcode; the differential table names them.
3. **A private disassembler.** Feed the substitution table into an existing dalvik
   decode layer (`scripts/dexutil.py`'s format table is the shape of the thing) and
   re-disassemble the bodies; decompilation is then ordinary tooling on the output.

Budget honestly: this is weeks, not an afternoon, and it redone per vendor per
version. The cheaper question is usually whether the behaviour you need survives
outside the virtualized island — a hook at the method's Java boundary
(`dynamic-frida.md`) or a server-side answer often reaches the goal without paying
for the island itself.

## Decision summary

| Observation | Action | Where |
|---|---|---|
| Dump parses, stub% near baseline | Filter, verify with jadx, move on to patching | `recon.md` |
| stub% high, image parses | FART loop: skeleton + active invocation + splice | this file |
| Splice produces a half-parsing dex | Re-check code_item length (padding, handler list) | §The code_item length trap |
| Dumper runs, output dir empty | Storage path + `open()` check, then entry-type probe | §Why the classic hooks die on Android 12-16 |
| App dies under the invoker | Shell counter-measures; narrow the force list | §Why the classic hooks die on Android 12-16, and `detection-and-anti-analysis.md` |
| frida attach refused (`script has been destroyed`) | Root-side `/proc/<pid>/mem` dump, atomic inside one process lifetime | §Dumping when frida is refused |
| Sample self-exits and restarts with no instrumenter present | The packer's own check, not your hook; shorten every step to one lifetime | §Dumping when frida is refused |
| Methods are `native` stubs | dex2c / JNI sink | `code-virtualization-and-custom-linkers.md` |
| Bodies present, decode as nonsense | Real VMP — differential oracle or walk away | §The honest boundary: real Dex VMP |
