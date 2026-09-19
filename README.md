# apk-reverse

An Agent Skill for Android APK reverse engineering, debloating, ad removal, surgical
dex patching, repacking, and runtime/server analysis.

It is a **skill**, not a tutorial: it is written to be loaded by an agent (Claude Code,
Codex, or any harness that supports the Agent Skills format) while it works, so it is
organized for progressive disclosure — a short decision-oriented `SKILL.md`, detailed
references loaded only when a step needs them, and parameterized scripts you can run
directly.

## How an agent is expected to consume this

`SKILL.md` is deliberately written as a **procedure with gates** rather than as advice, because the
observed failure mode is not ignorance — it is a model reading the whole thing, agreeing with it, and
then reasoning from first principles anyway.

So there are four things in the body that are meant to be *acted on*, not read:

- **Four override rules (R1–R4).** Where they conflict with the current plan, they win until evidence
  overrides them.
- **A symptom index.** Each row is a failure that has already been paid for. **A matching row is a
  stop signal**: load that file before running another command, rather than after a few more attempts.
  Reasoning past a known symptom is how the same hours get spent twice.
- **Four gates (G1–G4),** each an action with a pass criterion. "I understand the idea" does not clear
  a gate. They exist so that classification, environment truth and a control build happen *before*
  the first patch, not after the third failure.
- **A two-strike rule and stop conditions.** Two failures of the same shape mean the model is wrong,
  not the parameters. The third variant of a hypothesis that already failed twice is where rounds go
  to die.

And one thing at the end that is meant to be *withheld*: **"done"** has a definition (six items). A
clean log is not one of them. Anything short of all six is a checkpoint, and should be reported as a
checkpoint with what remains.

If you are an agent reading this: the cheapest possible first command is
`python skills/apk-reverse/scripts/doctor.py`. It tells you which of these tools exist here, which
scripts can actually run, and whether something in the environment is already poisoning your
measurements.

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

`SKILL.md`, `references/` and `scripts/` are all inside the skill directory, `skills/apk-reverse/`.
Everything at the repository root is maintenance tooling shared across skills, not part of an
installed skill.

```
SKILL.md                  a procedure with gates, not background reading:
                          how-to-use  -> four override rules (R1-R4)
                          symptom index (a matching row is a stop signal)
                          four gates (G1-G4, actions with pass criteria)
                          thirteen classification questions
                          the workflow, with a per-step skip condition and a two-strike rule
                          what "done" means  ->  stop conditions  ->  constraints  ->  indexes
references/               loaded on demand, one topic each
  recon.md                    identify packer, SDKs, code location, tamper checks; unpacking
  server-config-and-updates.md
                              the most common shape of "ad" and the one usually mis-diagnosed:
                              the server supplies UI the client renders (launch screen, popup,
                              announcement, tab set). The two-layer fetch that proves it, how to
                              find the config DTOs by the field names data classes keep, why you
                              patch the decision and not the data, deciding the scope of "remove",
                              and remote re-enable / cached config durability
  byte-level-patching.md      equal-length byte edits: why they beat method rebuilding (measured),
                              locating an instruction's exact offset without scraping listings,
                              the instruction width traps that desynchronise a decode, neutralise
                              a branch vs redirect it, dex header integrity field order, and the
                              verifier's move-result rule
  packers.md                  hardened targets: rejection signals, measuring the validation
                              boundary with single-variable tests, choosing a native host
  code-virtualization-and-custom-linkers.md
                              the layer between "packed" and "clean": whole classes turned into
                              `native` declarations, a private loader whose SONAME does not match
                              its filename, an embedded self-decrypting payload, a Java-layer
                              "signature killer" that logs success while a native check kills you.
                              The keep-it/drop-it deadlock, how to separate the *checker* from the
                              *implementation*, and the string-redirect technique that ends it
                              without neutralizing anything
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
  detection-and-anti-analysis.md  when the app fights back or the tool cannot run here: telling
                              detection apart from a broken environment, deciding by cost instead
                              of escalating, recognising an environment where dynamic analysis
                              simply does not work, and keeping the "blocks my analysis" question
                              separate from "blocks the deliverable"
  toolchain.md                what to install, how to invoke it non-interactively, which tools
                              are GUI-only, version-alignment traps, working offline,
                              **"not on PATH" is not "not installed"**, and which signer to use
  long-task-discipline.md     live record, conclusion grading, drift control, timeout and
                              wait calibration, deliverable-form drift, captures-you-never-looked-at,
                              long-context decay, handover
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
  doctor.py                   run this first: capability report + per-script runnability, finds
                              tools installed off-PATH or as runnable jars, and surfaces the
                              environment facts that poison experiments (clock skew, leftover
                              adb forward / proxy, a device-side frida process already running)
  dexutil.py                  dependency-free dex reader: structural walk + exact instruction
                              decode, dex header recompute/verify (correct checksum/signature
                              order), branch-target and operand helpers. Library shared by the
                              dex scripts, also runs standalone to dump one method with offsets
  dex_find_insn.py            locate an instruction by decoded semantics and print its exact byte
                              offset with context and both sides of any branch -- how you find a
                              patch site instead of guessing offsets
  dex_patch_bytes.py          equal-length byte patches from a JSON spec: semantic match, polarity
                              pin via expect_next, equal-length enforcement, verifier check, dex
                              header recompute, re-decode to prove it landed (--dry-run first)
  dex_check_verifier.py       tier-3 check: does any conditional branch target a move-result
                              (bypassing its producer)? Compares two builds and separates
                              pre-existing findings from regressions your patch introduced
  coldstart.py                cold-launch capture: timed screenshot burst + logcat signals +
                              installed-build facts + launch timing, and warns when the foreground
                              activity is not your app
  so_constpatch.py            same-length in-place rewrite of an isolated string constant, for
                              redirecting a library load instead of defeating a check
  smtool.py                   baksmali/smali wrapper with a configurable classpath
  dexpatch/                   dexlib2 method-level rewriter (for changes that need new instructions)
  patch_smali.py              method-body replacement in a smali tree
  dex_strpatch.py             byte-level string patch with a string_ids ordering guard
  dex_classdiff.py            prove a dex edit was surgical
  dex_strings.py              strings/URLs/SDK markers without a decompiler
  dart_pool_strings.py        recover literals from a Dart AOT snapshot (framed entries, the
                              one-byte vs UTF-16 split, file offsets, run-length noise filter)
  dart_pprefs.py              build/query the object-pool -> code-site index for a Dart snapshot
  dart_disasm.py              annotated windowed disassembly of Dart AOT code + B/BL caller index
  find_refs.py                count callers of a method before patching it
  repack.py                   rebuild APK, strip only signatures, keep META-INF/services/, write a
                              4-byte-aligned archive (resources.arsc STORED+aligned), sign, verify
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

This repository is a **skills repository**: the skill lives at `skills/apk-reverse/`, which is the
layout the `skills` CLI resolves, and it is installed by name rather than by copying a directory:

```
npx skills add newliver666/apk-reverse              # install every skill in the repo
npx skills add newliver666/apk-reverse --list       # list what is here, install nothing
npx skills add newliver666/apk-reverse --skill apk-reverse -y
npx skills use  newliver666/apk-reverse@apk-reverse # use it once, without installing
```

The CLI symlinks the skill into your agent's skills directory by default (`--copy` makes independent
copies instead), and `-g` installs for every project rather than the current one. With one skill in
the repository, `--skill apk-reverse` is redundant today; it is written out here because it is what
selects a single skill once a second one exists.

Once installed, the agent loads `SKILL.md` when a task matches its description, and pulls in
`references/*` only as needed. No global state, no machine-specific paths, and no build step.

## Requirements

Nothing is mandatory; each script checks what it needs. `skills/apk-reverse/scripts/doctor.py` reports
which of these are present here, which scripts can therefore run, and — usefully — which tools exist
somewhere other than PATH.

If your toolchain lives outside PATH (a project-local `tools/` directory, a versioned SDK folder, a
runnable `.jar` instead of a command), set `APKREV_TOOLS` to one or more directories and `doctor.py`
will find them:

```
set APKREV_TOOLS=<dir>;<dir>                     # Windows, e.g. an SDK or project-local tools dir
export APKREV_TOOLS=<dir>:<dir>                  # POSIX
```

The scripts themselves are plain `python3` and are intended to work identically on Windows, macOS and
Linux; where a snippet is POSIX-only it is labelled. Nothing here assumes a Unix shell.

| Tool | Used for |
|---|---|
| Python 3.9+ | all scripts |
| `ddc` (optional but recommended) | single-binary dex→Java decompiler with query subcommands (`info`, `findrefs`, `strings --with-locations`, per-class decompile). No JVM. Turns string cross-referencing from a crawl into a lookup, and reports package identity reliably — see `skills/apk-reverse/references/toolchain.md` |
| `baksmali` / `smali` + `dexlib2` jars | disassembly, assembly, surgical patching |
| JDK (`javac`, `java`) | building/running the dexlib2 patcher; also provides `keytool`/`jarsigner` |
| Android SDK build-tools (`aapt`, `zipalign`, `apksigner`) | manifest info, alignment, signing. **`apksigner` is the signer to use** — `jarsigner` rewrites the archive and breaks the alignment Android R+ requires |
| `uber-apk-signer` (optional) | one-step align + sign |
| ADB | device work |
| Frida (host package + matching on-device server) | dynamic analysis |
| a rooted device or emulator | anything beyond static analysis |

None of these need to be on `PATH`: every script accepts an explicit path for the
tools it shells out to, and `skills/apk-reverse/references/toolchain.md` covers finding
an install that `PATH` does not know about (the common case for `apksigner` and
`keytool`).

## Read this first

`skills/apk-reverse/references/pitfalls.md`. It is the most valuable file here — every entry is a
failure that produced a broken artifact while looking completely healthy.

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

What it covers, and what it deliberately does not, is stated at the top of `SKILL.md`
under **Coverage**. The short version: Android only (no iOS), and deep on the layers
that have been worked through for real — dex patching, repacking, packers and custom
loaders, native tamper response, and Flutter/Dart AOT. Unity/IL2CPP logic recovery,
React Native/Hermes bytecode internals, and defeating a server-side authority are **not**
covered, and the skill is written to say so and stop rather than apply the nearest
documented procedure to a target it was not written for.

## Repository maintenance

Three tools live at the root and are not part of the installed skill:

```
check_repo.py      every skill discovered, frontmatter valid, scripts runnable,
                   documented paths resolve, README paths explicit and existing
check_refs.py      every `file.md` §section cross-reference reaches a real heading
build_scripts.py   audit for machine-specific leftovers (absolute paths, credentials)
```
