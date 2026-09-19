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
- Catching the repack failure that looks like success: an app that installs, launches and
  renders perfectly while **every signed request is rejected**, because the client derives its
  request-signing key from its own signing certificate.
- Separating **your own mistakes from the app's or the server's problems** — a
  feature-scoped failure (login, registration, payment) is often a TLS/certificate issue on
  one code path, not a consequence of the patch you just built. Device state, a dead device
  server and clock drift masquerade the same way.
- Establishing **which architecture and which library are actually executing**, rather
  than trusting what the manifest ships or what the device claims.
- Working through **packed/hardened targets**: identifying the packer, unpacking, and turning a
  memory dump back into a patched, installable APK.
- Handling a **hardened library that terminates the process on purpose** — including the
  deliberate-crash shape (`fault addr 0x4`) that looks exactly like an ordinary null-dereference
  bug, and the "neutralise it, but never by making it *not return*" rule that decides whether the
  fix works or freezes the whole app in a way that looks nothing like the cause.
- Knowing **which tools to reach for and where each one lies** — including the ones that only
  exist as a GUI, so you ask for a human instead of silently substituting a weaker method.
- Making a patched build **stay** patched: neutralising version checks, forced-upgrade dialogs and
  self-update installers so the work cannot be switched off remotely — and recognising the
  hot-update/remote-config channel that can quietly undo it without any version change.
- Separating a **client-side sign-in gate** (patchable) from an **account-scoped resource** (empty
  because the server has nothing to answer with), and knowing that forging a session produces a state
  worse than being signed out.
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
  dart-aot.md                 Dart AOT in depth: version pinning and building a matching decompiler,
                              the object pool and reference indexes, register/boolean conventions,
                              the three signatures that identify business logic, locating, patching
  native-and-so.md            .so hosts, DT_NEEDED vs JNI_OnLoad, relocation limits,
                              relocation-free bootstrapping, replacing Java methods natively,
                              and which ABI/library is *actually loaded and executing*
  native-tamper-and-suicide.md  how a hardened library kills its own process: the visible
                              mechanisms, how to tell which one actually fires, how to find the
                              site, forged section headers, function boundaries from
                              PT_GNU_EH_FRAME, scanner traps, and neutralising safely
  toolchain.md                what to install, how to invoke it non-interactively, which tools
                              are GUI-only, version-alignment traps, working offline
  long-task-discipline.md     live record, conclusion grading, drift control, timeout and
                              wait calibration, deliverable-form drift, handover
  ad-removal.md               ad taxonomy, wrapper mapping, callback trap, global gates, verification
  updates-and-forced-upgrade.md  keeping a patched build alive: locating the version check, the
                              two-layer patch (no-op the routine, neutralise the comparison), what not
                              to touch (manifest version, installer permission, host blocking),
                              self-update and hot-update/remote-config channels, verifying that no
                              version request is issued at all
  account-gates.md            sign-in walls, forced phone binding, guest mode: telling a client-side
                              gate (patchable) apart from an account-scoped resource (not), why
                              fabricating a session is worse than staying signed out, and the
                              unavoidable session loss after a reinstall
  signature-derived-keys.md   when the app's own signing certificate is used as key material:
                              detection greps, why offline extraction is unreliable, the
                              hardcode-then-verify procedure
  membership-and-limits.md    server vs client authority; what is and is not patchable
  server-api.md               probe an app's API; prove who owns the gate
  tls-and-cert.md             feature-scoped network failures: expired certs, dual trust chains
  third-party-builds.md       auditing a "cracked"/"modded" APK before trusting it
  dex-patching.md             patch-layer table + dexlib2 technique in depth
  patch-audit.md              proving a patch *landed* and is *legal*: length-vs-bytes
                              comparison, the equal-length-replacement blind spot, verifier-level
                              legality (move-result adjacency) checked statically, text-matching
                              patch traps, and reporting a missing patch
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
  dart_pool_strings.py        recover literals from a Dart AOT snapshot (framed entries, the
                              one-byte vs UTF-16 split, file offsets, run-length noise filter)
  dart_pprefs.py              build/query the object-pool -> code-site index for a Dart snapshot
  dart_disasm.py              annotated windowed disassembly of Dart AOT code + B/BL caller index
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
  elf_plt.py                  resolve a PLT stub to its imported symbol (x86_64 + aarch64) from
                              the relocation table; list a symbol's callers; byte-diff two
                              libraries and name the symbol each changed stub belongs to
  apk_diff.py                 entry-level diff of two builds: changed / added / removed, by
                              content hash so same-size replacements are caught
  native_crash.py             locate a native death from a log or tombstone: signal, fault
                              address, registers, frames split app vs system, the faulting
                              instruction, and a flag when the fault looks *arranged*
  blob_decode.py              search, don't guess, the framing of a stored value
                              (base64/hex x rotation x deflate); re-encode the edited payload
  snap.py                     bounded burst screenshots + control-tree capture with a stall
                              detector, and a verdict on whether the tree is usable at all
  sig_probe.py                find the exact signatures[0].toCharsString() value — offline
                              candidates from an APK, or the authoritative read from a device
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

The four that hurt most:

1. Stripping the whole `META-INF/` during a repack deletes ServiceLoader registrations
   and the app dies at startup with an error that names an unrelated library.
2. Patching a byte-level string without preserving `string_ids` ordering gets the whole
   dex rejected, while checksums and signatures verify perfectly.
3. Rebuilding a dex with a whole-tree smali round-trip damages R8 output invisibly —
   class tables compare clean, and it only blows up at runtime.
4. Neutralising a native terminate path by making it **not return**. A spinning stub does not
   suppress the check; it freezes the caller and every thread behind it. The app hangs with *no
   crash record at all*, and the eventual death gets blamed on whatever killed the frozen process.

## Scope

Built for working on your own applications, on samples you are authorized to analyze,
and in CTF/competition sandboxes. It contains no vendored third-party binaries and no
target-specific data.
