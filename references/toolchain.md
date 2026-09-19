# Toolchain — What to Use, How to Invoke It, and Where It Lies

Load this when you are choosing tools, when a tool produces an answer that smells wrong, or when
something is not installed. It is a map, not a tutorial: each entry says what the tool is *for*, how
to drive it non-interactively, and the failure mode that wastes time.

**Prefer tools you can drive from a command line.** An agent cannot click. Tools that exist only as
a GUI are listed where they matter, marked as requiring a human, so you can ask for that instead of
stalling or silently substituting a weaker method.

## Tier 0 — present on almost any machine, no install

Use these before reaching for anything heavier. They answer structure questions in seconds and
cannot be broken by a missing dependency.

| Tool | Use it for |
|---|---|
| `file`, `readelf -h/-l/-d/-r`, `objdump -d`, `nm -D`, `strings` | ELF structure, program headers, dynamic section, relocations, dynamic symbols |
| `unzip -l`, `zipinfo` | what is actually inside an APK, entry sizes and compression |
| `sha256sum` / `Get-FileHash` | identity. **Always hash before and after; never trust "it should be the same file"** |
| `xxd` / `hexdump` | byte-level ground truth when a tool disagrees with another tool |
| `python3` | all the scripts here; the standard library alone covers most parsing |

`readelf`/`objdump` walk **section** headers. If a target's section table is forged (see
`native-tamper-and-suicide.md` §Forged section headers) they will print confidently wrong output —
cross-check with the program headers.

## Tier 1 — dex and Java

| Tool | Invoke | Why this one |
|---|---|---|
| `baksmali` / `smali` (jars) | `java -cp <jars> org.jf.baksmali.Main d <dex> -o <dir>` | round-tripping, reading a method precisely |
| `dexlib2` | small Java program | method-level rewrite, leaves everything else untouched (`dex-patching.md`) |
| **`ddc`** | `ddc app.apk -c <Class>` | **fastest read of dex as Java, plus query subcommands** — see below |
| `apktool` | `java -jar apktool.jar d/b` | whole-app decode including resources |
| `jadx` | `jadx --no-res -d <out> <apk>` | readable Java for orientation; **not** a source of truth (see below) |
| `aapt2` | `aapt2 dump badging <apk>` | manifest facts, package name, versions |
| `zipalign`, `apksigner` | from build-tools | alignment and signing |

### ddc — dex-to-Java with query subcommands (worth adopting)

A single-file Rust binary, no install, no JVM. Two things make it more useful than
"a decompiler":

```bash
ddc info app.apk                     # label, package, version, launcher, sdk, per-dex counts
ddc findrefs app.apk string "SomeToken"    # every reference site, class#method
ddc strings app.apk -f "splash" --with-locations
ddc app.apk -c com.example.Foo       # one class as Java
ddc app.apk -o out/                  # full decompile, a few seconds for a normal APK
```

Measured on a 4.7 MB APK (4,070 classes / 30k methods): `info` ~0.13 s, `findrefs`
~0.11 s, one class ~0.25 s, full decompile ~2.8 s producing ~4,000 files.

Why the query subcommands matter more than the speed: **string cross-referencing
becomes a lookup instead of a crawl.** Asking "which class mentions this config
field name" is a sub-second command here and easily an hour of smali grepping by
hand. That single property is what turns "find the convergence point" from
exploration into a query.

`info` also **prevents a specific, costly mistake**: reading the package identity
out of the binary manifest by hand. Hand-extracted AXML strings are ambiguous —
class-name fragments look exactly like package names, and picking the wrong one
sends every later `pm`/`dumpsys`/data-dir query to a package that does not exist.
Let the tool report `package`, `label` and `launcher`, and cross-check with
`aapt2 dump badging` when available.

Limits to plan around: types are erased (no generics); R8 short names stay short,
so you still need string cross-references to infer meaning; output is a **reading
aid, not compilable source** (occasional declaration/use ordering is inverted, and
numeric resource ids appear as decimal integers); very large methods produce
thousands of lines and are better approached via `findrefs`/`getmethod` first.

**Classpath gotcha.** `baksmali`/`smali` need their dependency jars on the classpath together
(`smali`, `antlr-runtime`, `stringtemplate`, `baksmali`, `dexlib2`, `util`, `jcommander`, `guava`).
Missing one produces `ClassNotFoundException` that reads like a broken target. `scripts/smtool.py`
carries the classpath so you pass it once.

**Entry-point gotcha.** The main class has moved between versions — `org.jf.*` in older builds,
`com.android.tools.smali.*` in newer ones. If `ClassNotFoundException` names the **main class**, it
is a version mismatch, not a missing jar.

**jadx is for reading, not for concluding.** Decompiled Java reorders and rewrites control flow;
line numbers and even which branch is which can differ from the bytecode. When a decision depends on
it, verify in smali or at runtime. `jadx` writing `(unknown)`/empty method bodies means it failed,
not that the method is empty.

**`smali` assembling can abort silently** — the tree produces no dex while the process still exits
0. Never treat exit code as proof of a build. Assert the artifact exists, is fresh, and is non-empty
(`patch-audit.md`).

## Tier 2 — native

| Tool | Invoke | Notes |
|---|---|---|
| `radare2` / `rizin` | `r2 -q -c '<cmds>' file` | scriptable disassembly/analysis; the practical choice when no GUI is available |
| `Ghidra` (headless) | `analyzeHeadless <proj> <name> -import <file> -postScript <s>` | decompiler without a GUI; slower to script but far better output than a raw disassembler |
| `capstone` (python) | library | decoding in your own scripts — see the silent-stop trap below |
| `keystone` (python) | library | assembling a short patch when you are editing bytes by hand |
| `pyelftools` (python) | library | **section-based — unreliable on hardened targets.** Prefer hand-walking `PT_LOAD`/`PT_DYNAMIC`, as `scripts/elf_plt.py` does |
| IDA Pro | GUI | human-driven. Ask for it when decompiler output is genuinely needed; do not pretend a raw disassembly is equivalent |
| `x64dbg` | GUI, Windows | human-driven live debugging of a native Windows target |
| `gdb` / `lldb` | CLI | live debugging where a device or emulator allows it |

**capstone can stop silently.** Decoding a buffer that does not begin at an instruction boundary may
return a few instructions and then nothing, with no error. A scan built on that reports "no matches"
for a library full of matches. Use byte-pattern search or a resynchronising scan for anything where
completeness matters (`native-tamper-and-suicide.md` §Scanner traps).

**Disassembler output is a hypothesis.** Fixed-width architectures (aarch64) decode almost any
4-byte window into *some* instruction, so a wrong start offset yields plausible-looking garbage.
Bound your window with a known entry point or a known call site.

## Tier 3 — runtime and network

| Tool | Invoke | Notes |
|---|---|---|
| `frida` (host) + `frida-server` (device) | `frida -U -f <pkg> -l script.js` | **host and device versions must match** — skew produces errors that look like a broken target (`pitfalls.md` P15) |
| `objection` | `objection -g <pkg> explore` | quick Java-layer poking on top of Frida |
| `mitmproxy` | `mitmproxy --mode regular` | request/response inspection; a device proxy is usually faster to set up than a transparent one |
| `adb` | everything | the primary device interface |

Version alignment for Frida is a **hard gate**, not a nicety. Check both sides before writing a
script, and check the device architecture — the server binary is per-ABI.

## Tier 4 — cross-platform runtimes

| Runtime | Identifier | Tool |
|---|---|---|
| Flutter / Dart | `libflutter.so` + `libapp.so` | `blutter` (needs the **matching Dart version**) — `dart-aot.md` |
| Unity / IL2CPP | `libil2cpp.so` + `global-metadata.dat` | Il2CppDumper + a native decompiler |
| React Native | `libhermes.so` / `index.android.bundle` | Hermes bytecode tooling, or plain JS if the bundle is unminified |
| Cordova / hybrid | WebView + `assets/www` | read the JS directly; Java layer is usually thin |

**A version mismatch here wastes the most time of any tool in this file.** A Dart decompiler built
for a different engine version produces output that is subtly wrong rather than obviously broken.
Pin the version first (`dart-aot.md` §1) and do not "try it and see".

## "Not on PATH" is not "not installed"

`doctor.py` and `preflight.py` report whether each tool resolves on `PATH`. That
is a statement about `PATH`, not about the machine, and the difference has cost
real time: a full custom zip writer was built to work around a missing
`apksigner` that was already installed in an SDK directory nothing had added to
`PATH`.

**Before treating a tool as absent, search the filesystem once:**

```bash
# POSIX
find / -name apksigner -o -name zipalign -o -name baksmali.jar 2>/dev/null | head

# Windows (PowerShell) -- list every drive letter first, then search each
(Get-PSDrive -PSProvider FileSystem).Root |
  ForEach-Object { Get-ChildItem -Path $_ -Recurse -Depth 5 -ErrorAction SilentlyContinue `
      -Include apksigner.bat,zipalign.exe,keytool.exe }
```

Common places that are *not* on `PATH`:

| Artefact | Typical location |
|---|---|
| `apksigner`, `zipalign`, `aapt2` | any `build-tools/<ver>/` under an Android SDK, and portable tool bundles |
| `apksigner.jar` | inside those same directories (runnable as `java -jar`) |
| `keytool`, `jarsigner`, `javac` | a JDK install whose `bin` was never added to `PATH`; `java -XshowSettings:properties -version 2>&1 \| grep java.home` reveals the JDK root even when `keytool` does not resolve |
| `uber-apk-signer.jar`, `baksmali*.jar` | bundled with portable APK toolkits |

Record the resolved absolute paths once, in your running notes, and pass them to
the scripts that accept `--apksigner` / `--zipalign` / `--ks` style flags. Every
script in this repository takes an explicit path for this reason.

**A useful asymmetry:** missing `apksigner` is survivable (a v2-only signature
block can be appended without reordering the archive), but missing `zipalign` is
not a reason to hand-roll alignment either -- write the archive aligned in the
first place, as `scripts/repack.py` does. Prefer producing a correct archive over
repairing one afterwards: post-hoc alignment tools rewrite the file, which
changes every offset and can break a target that fingerprints its own layout.

## Signing: pick the signer deliberately

Two signers, and the choice changes the output bytes:

- **`apksigner`** (build-tools) appends the v2/v3 signature block after the zip
  content. It does **not** reorder entries, so a carefully aligned archive stays
  aligned. This is the default choice.
- **`jarsigner`** (JDK) rewrites the archive as a side effect of adding the v1 JAR
  signature, which recompresses entries and **destroys the alignment** that
  Android R+ requires. A build signed this way can fail to install with
  `Failure [-124] ... resources.arsc ... aligned on a 4-byte boundary` even though
  the same archive installed fine moments earlier, and `jarsigner -verify` reports
  success. If you have run `jarsigner` on an archive and a previously-working
  install starts failing, re-pack and sign with `apksigner` before investigating
  anything else.

Enable **v1 + v2 + v3**. v1 keeps very old devices working; v2/v3 are what modern
platforms actually verify, and v1-only builds are rejected in more configurations
than people expect.

## The general trap: a tool's failure is not a finding about the target

A missing jar, a version skew, a forged section header, and a genuinely absent symbol all produce
**empty or partial output**. The output looks the same; the conclusions are completely different.

Before reporting "there is nothing there", confirm the tool was actually capable of finding it:

- Did it read the file at all? (entry count, segment count, non-zero output somewhere)
- Does a **known-present** item show up? (search for something you already know exists — a symbol
  you saw in the dynamic table, a string you read in the hex dump)
- Would a different method see it? (byte pattern vs decoded scan)

**This is `pitfalls.md` P25 and P26 in tool form.** A self-built analyser that fails quietly reads
exactly like a clean target, and it removes routes from consideration for free.

## Working without a network

Assume nothing can be downloaded. What still works, in order of usefulness:

1. Tier 0 in full, plus the Python standard library — enough for structure, strings, hashing, and
   most ELF/dex parsing.
2. Whatever jars and binaries are already present. **Locate them once and reuse the paths** rather
   than re-searching on every command.
3. A local package cache or an offline mirror, if the environment has one.

If a tool genuinely cannot be obtained, say which step is blocked and **what a substitute would
give up** — do not silently substitute a weaker method and report its result as equivalent.

## Recording the toolchain actually used

When you report, name the tools and versions that produced each finding. Two agents with different
tool versions will reach different conclusions about the same binary, and without the version that
difference is unresolvable later.
