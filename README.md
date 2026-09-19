# apk-reverse

An Agent Skill for Android APK reverse engineering, debloating, ad removal, surgical
dex patching, repacking, and runtime/server analysis.

It is a **skill**, not a tutorial: it is written to be loaded by an agent (Claude Code,
Codex, or any harness that supports the Agent Skills format) while it works, so it is
organized for progressive disclosure — a short decision-oriented `SKILL.md`, detailed
references loaded only when a step needs them, and parameterized scripts you can run
directly.

## What it is good at

- Deciding **fast** whether a request is even achievable client-side, instead of
  burning hours on a paywall that is enforced by a server.
- Choosing the **safest patch layer** for a given change, and avoiding the layers that
  break the app.
- Avoiding the specific mistakes that produce an APK that builds perfectly and dies at
  runtime.

## Structure

```
SKILL.md                  decision tree, workflow, hard constraints, indexes
references/               loaded on demand, one topic each
  recon.md                    identify packer, SDKs, code location, tamper checks
  ad-removal.md               ad taxonomy, wrapper mapping, callback trap, verification
  membership-and-limits.md    server vs client authority; what is and is not patchable
  server-api.md               probe an app's API; prove who owns the gate
  dex-patching.md             patch-layer table + dexlib2 technique in depth
  repack-and-sign.md          repack rules, signing, install, post-install hazards
  runtime-data.md             DataStore / SharedPreferences / SQLite / protobuf
  dynamic-frida.md            Frida setup, hooking strategy, anti-instrumentation
  environment.md              device/emulator setup, ADB, offline devices, log signals
  verification.md             the claim ladder; what "done" means
  pitfalls.md                 the failure catalogue -- read before building
scripts/                  parameterized, path-agnostic
  smtool.py                   baksmali/smali wrapper with a configurable classpath
  dexpatch/                   dexlib2 method-level surgical rewriter (preferred tool)
  patch_smali.py              method-body replacement in a smali tree
  dex_strpatch.py             byte-level string patch with a string_ids ordering guard
  dex_classdiff.py            prove a dex edit was surgical
  dex_strings.py              strings/URLs/SDK markers without a decompiler
  find_refs.py                count callers of a method before patching it
  repack.py                   rebuild APK, strip only signatures, sign
  devsh.py                    quoting-safe ADB shell helper
  usb_net_proxy.py            give an offline device network over USB
  datastore_inject.py         encode/inject AndroidX DataStore preferences safely
  probe_api.py                probe an HTTP API with the right headers
  grab_crash.py               recover stacks hidden by a crash-reporter SDK
  install_test.py             install + launch health check with logcat signal scan
```

## Install

Drop this directory where your agent finds skills, e.g.:

```
<skills-dir>/apk-reverse/SKILL.md
```

The agent loads `SKILL.md` when a task matches its description, and pulls in
`references/*` only as needed. No global state, no machine-specific paths.

## Requirements

Nothing is mandatory; each script checks what it needs.

| Tool | Used for |
|---|---|
| Python 3.9+ | all scripts |
| `baksmali` / `smali` + `dexlib2` jars | disassembly, assembly, surgical patching |
| JDK (`javac`, `java`) | building/running the dexlib2 patcher |
| Android SDK build-tools (`aapt`, `zipalign`, `apksigner`) | manifest info, alignment, signing |
| `uber-apk-signer` (optional) | one-step align + sign |
| ADB | device work |
| Frida (host package + matching on-device server) | dynamic analysis |
| a rooted device or emulator | anything beyond static analysis |

## Read this first

`references/pitfalls.md`. It is the most valuable file here — every entry is a failure
that produced a broken artifact while looking completely healthy.

The three that hurt most:

1. Stripping the whole `META-INF/` during a repack deletes ServiceLoader registrations
   and the app dies at startup with an error that names an unrelated library.
2. Patching a byte-level string without preserving `string_ids` ordering gets the whole
   dex rejected, while checksums and signatures verify perfectly.
3. Rebuilding a dex with a whole-tree smali round-trip damages R8 output invisibly —
   class tables compare clean, and it only blows up at runtime.

## Scope

Built for working on your own applications, on samples you are authorized to analyze,
and in CTF/competition sandboxes. It contains no vendored third-party binaries and no
target-specific data.
