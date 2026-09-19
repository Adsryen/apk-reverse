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
- Deciding **what form the deliverable must take** before any work starts — an
  unrooted, self-contained artifact is a different problem from "make it work on this
  machine", and confusing the two is the most expensive drift in this domain.
- Choosing the **safest patch layer** for a given change, and avoiding the layers that
  break the app.
- Separating **your own mistakes from the app's or the server's problems** — a
  feature-scoped failure (login, registration, payment) is often a TLS/certificate issue on
  one code path, not a consequence of the patch you just built. Device state, a dead device
  server and clock drift masquerade the same way.
- Establishing **which architecture and which library are actually executing**, rather
  than trusting what the manifest ships or what the device claims.
- Working through **packed/hardened targets**: identifying the packer, unpacking, and turning a
  memory dump back into a patched, installable APK.
- Keeping a **long task honest**: a live record, graded conclusions, calibrated timeouts, and
  bounded waits, so progress is not lost and the same mistake is not made twice.
- Avoiding the specific mistakes that produce an APK that builds perfectly and dies at
  runtime.

## Structure

```
SKILL.md                  decision tree, workflow, hard constraints, indexes
references/               loaded on demand, one topic each
  recon.md                    identify packer, SDKs, code location, tamper checks; unpacking
  packers.md                  hardened targets: rejection signals, measuring the validation
                              boundary with single-variable tests, choosing a native host
  framework-runtimes.md       Flutter / React Native / Unity: which layer owns the UI, and how to
                              find logic when there are no symbols (string encoding traps)
  native-and-so.md            .so hosts, DT_NEEDED vs JNI_OnLoad, relocation limits,
                              relocation-free bootstrapping, replacing Java methods natively,
                              and which ABI/library is *actually loaded and executing*
  long-task-discipline.md     live record, conclusion grading, drift control, timeout and
                              wait calibration, deliverable-form drift, handover
  ad-removal.md               ad taxonomy, wrapper mapping, callback trap, global gates, verification
  membership-and-limits.md    server vs client authority; what is and is not patchable
  server-api.md               probe an app's API; prove who owns the gate
  tls-and-cert.md             feature-scoped network failures: expired certs, dual trust chains
  third-party-builds.md       auditing a "cracked"/"modded" APK before trusting it
  dex-patching.md             patch-layer table + dexlib2 technique in depth
  repack-and-sign.md          repack rules, unpack-and-repack, signing, post-install hazards
  runtime-data.md             DataStore / SharedPreferences / SQLite / protobuf; when the app
                              rewrites your edit, and decoding a value that looks encrypted
  dynamic-frida.md            Frida setup, version pinning, the four-layer probe, hook strategy
  environment.md              device/emulator setup, root, ADB, offline devices, log signals,
                              emulator console control and recovery, preflight, look-at-the-screen
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
  repack.py                   rebuild APK, strip only signatures, sign, verify
  devsh.py                    quoting-safe ADB shell helper
  usb_net_proxy.py            give an offline device network over USB
  datastore_inject.py         encode/inject AndroidX DataStore preferences safely
  probe_api.py                probe an HTTP API with the right headers
  grab_crash.py               recover stacks hidden by a crash-reporter SDK
  install_test.py             install + launch health check with logcat signal scan
  frida_probe.js              four-layer runtime probe (app net layer + OkHttp + java.net + exceptions)
  run_probe.py                inject the probe, stream it to a log file, stay resident
  tls_check.py                strict certificate check for one or more hosts
  preflight.py                environment check before every experiment block (device, root,
                              ABI/translation, clock skew, leftover proxy/forwards, dead server)
  lib_map.py                  what is *actually mapped* into a live process: per-library path,
                              base, architecture, and whether it came from the APK or was
                              materialized at runtime
  blob_decode.py              search, don't guess, the framing of a stored value
                              (base64/hex x rotation x deflate); re-encode the edited payload
  snap.py                     bounded burst screenshots + control-tree capture with a stall
                              detector, and a verdict on whether the tree is usable at all
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
