---
name: apk-reverse
description: "Reverse engineer, debloat, de-ad, patch, or re-sign Android APKs, and analyze their runtime and server-side behavior. Use when a task involves an .apk/.aab/.dex/.so sample, smali or dex patching, Frida/objection runtime hooking, repacking and re-signing, removing ads or SDK trackers, probing a mobile app's HTTP API, or deciding whether a client-side patch is even capable of achieving the goal. Covers recon, anti-tamper, ad removal, membership/paywall limits, dex-level surgical patching, repack pitfalls, device and emulator setup, and a hard-won failure catalogue. Load the body before planning any patch work: it opens with a symptom index and four gates that must be cleared first."
---

# APK Reverse Engineering & Patching

Goal: reach a **verified, installable, still-working artifact** fast — and avoid the whole class of
mistakes that destroy an APK while looking completely healthy.

## Immediate — the four things to do before anything else

Placed at the top on purpose: the longer this file gets, the less its middle is read, and everything
below is explanation for these four moves.

**1. Classify before choosing a route** (§Start here's thirteen questions; **R4** decides whether you
are editing the right layer at all — a wrong branch produces an artifact that builds, runs, and does
the wrong thing). **2. Clear the four gates in order, with their pass criteria** (§Gates: G1 names the
deliverable form in one testable sentence *before* any work, G2 the machine's real capability, G3 the
code location, G4 baseline and control — "I understand the idea" is not clearing one). **3. A symptom
you cannot explain is a stop signal** — search §Symptom index for the shape *before your next attempt*
and load the row's file; those rows cost hours precisely because the answer was already written down.
**4. Two strikes on one shape of attempt → back to classification**, not a third variant
(§Stop conditions), and never report done without §What "done" means.

## How to use this file

This file is a **procedure with gates**, not background reading. Three things are mandatory:

- Before you patch anything, clear the **four gates** in §Gates. They are actions with pass criteria,
  not attitudes.
- When anything fails in a way your current plan does not explain, **stop and check the symptom
  index**. If a row matches, load that file before running another command.
- When this file and your own reasoning disagree, **this file wins** until you have evidence that
  overrides it. Every rule here is the residue of a failure that cost hours; your current intuition is
  the intuition of someone who has not hit it yet.

## Four rules that override everything else

**R1 — Write the deliverable as a testable sentence before you touch the target.**
"It works" is not the goal; "it works under the stated constraint" is. Root-assisted, live-
instrumentation, host-proxy and patched-device results frequently do **not** satisfy a request for an
installable artifact that works on a normal phone — and it is easy to present such a result as
finished. Write the sentence, re-read it at every checkpoint, and if you cannot meet it, say so
plainly and label the privileged workaround a **fallback**, never the deliverable.
→ `references/long-task-discipline.md` §the most expensive drift

**R2 — Change one variable at a time, and keep a control build.**
An experiment that flips two things teaches nothing when it fails, and a failure you cannot attribute
will be attributed to the wrong cause. Every "the app rejects X" claim needs its own run, and every
patch needs a same-pipeline control that still fails the old way.
→ `references/long-task-discipline.md` §single-variable discipline

**R3 — Never ship or claim an unverified artifact.**
"It assembles" is not "it works"; "the process started" is not "the feature works"; "no error in the
log" is not "the check is gone". Install it, launch it, exercise the exact feature you changed, and
look at the screen. Prove the device is running the build you made — hash it, do not trust the
filename.
→ `references/verification.md`

**R4 — Identify the owning layer before patching, and re-classify when reality disagrees.**
Ads, paywalls, feature gates, integrity checks and update gates live in different layers (Java, dex,
native, Dart/Unity, server). Patching the wrong layer either does nothing or breaks the app. If a
patch "had no effect", the diagnosis was wrong — go back to classification instead of patching harder.
→ `references/recon.md`, then the layer-specific file the symptom index points at

## Tooling — what to reach for, in order, and how to notice what you are missing

Most wasted rounds in this domain are not bad reasoning about the target. They are **the right question
asked of a tool too weak to answer it**: an hour of `grep` over a hand-exported smali tree where one
indexed query would do, or a full manual ELF walk where a decompiler was one `pip install` away. The
failure is invisible from the inside, because the weak route still produces output.

Four obligations. These are instructions, not preferences:

- **Orient with an indexer, not with an export.** Before reading code, build the ability to *ask the
  artifact questions* — `droidasc findrefs` (string/type/method → every reference site, sub-second) or
  `ddc findrefs`. A full decompile is for reading a class you have **already located**; it is not the
  way you locate it. Treat `jadx` as a readable viewer of last resort, never as the source of truth, and
  never as the entry point of a recon. → `references/toolchain.md` §Tier 1 — dex and Java
- **When the hot layer has no working tool here, installing one is part of the task.** A missing arm64
  decompiler is not a constraint to route around; it is the next step. Route around it and you pay in
  hours for a result a decompiler gives in minutes. Ask a human only when installation is genuinely
  impossible. → `references/toolchain.md` §Closing a capability gap
- **Name the gap before you spend against it.** State the capability the current blocker requires, and
  whether this machine has it. This is a G2 item, not a note to yourself.
- **Reach for a script here before writing a new one.** The kit exists precisely so that parsing,
  hashing, alignment and hot-plug probes are not re-derived per task; a bespoke script written in place
  of `scripts/dex_find_insn.py` is how offsets get guessed instead of computed.
  → `references/toolchain.md` §Using the kit's scripts instead of writing your own
- **Pick the instrument for the layer the question lives on — the heavier one is not the safer one.**
  A dex in memory wants `dex_mem_scan.py` (find and cut) plus `dex_dump_validate.py` (judge), not a
  full decompiler pointed at a fragment; an algorithm you only have to *call* wants
  `references/emulation-and-rpc.md`, not a week of reading a flattened function
  (`references/native-dbi-and-deobfuscation.md`); "does this class ever get loaded at runtime" wants a
  hook that fires or does not, not more reading. Reaching one layer up because the correct instrument
  is unfamiliar is how a ten-minute answer becomes a day — and it usually produces a *plausible* result,
  which is worse than none.

A capability you have not checked for is not a capability you lack. Run
`python skills/apk-reverse/scripts/doctor.py` and read what it finds **off-PATH** before concluding
that anything is unavailable.

## Coverage — what this skill claims, and what it does not

The failure this section prevents is not ignorance. It is **a confident wrong answer produced by
applying the nearest available procedure to a target it was never written for.** A documented method
that almost fits is more dangerous than no method at all, because it arrives with a plan, a
vocabulary and a set of reassuring numbers.

**Covered, by verified mechanisms:**

- Client-side ads, promos and splash/popup/tab configuration, including server-issued UI config that
  has no SDK to find (`ad-removal.md`, `server-config-and-updates.md`).
- Whether a membership, paywall or feature gate is *client-enforceable* at all — and saying so
  plainly when it is not (`membership-and-limits.md`, `account-gates.md`).
- dex-level surgical patching: equal-length byte edits, dexlib2 method rewrites, and the header,
  verifier and alignment rules that decide whether the build loads (`dex-patching.md`,
  `byte-level-patching.md`, `patch-audit.md`).
- Repacking, signing, installing, and the install refusals that look like a broken build
  (`repack-and-sign.md`).
- Packers, custom loaders and code virtualization — identification, the validation boundary, and the
  routes that survive it (`packers.md`, `code-virtualization-and-custom-linkers.md`).
- **Java2C versus an extraction shell versus JNI sinking** — the misdiagnosis that sends an agent
  hunting a decrypted DEX that never exists (`java2c-and-jni-sinking.md`, `scripts/java2c_probe.py`).
- The native layer: `.so` hosts, tamper-triggered self-termination, forged ELF structure, and
  neutralising a terminate path without making it not return (`native-and-so.md`,
  `native-tamper-and-suicide.md`).
- Flutter / Dart AOT — analysing and patching `libapp.so` **given a snapshot dump** (`dart-aot.md`).
- Runtime analysis with Frida, server-side API probing, feature-scoped TLS failures, update and
  forced-upgrade neutralisation, and the verification discipline everything above rests on.

**Also covered, by documented routes — mostly *inferred* rather than measured:** module-side
delivery when a repack is refused (`lsposed-and-modules.md`) · extraction shells and the VMP boundary,
including how to *measure* that the bodies are empty (`advanced-unpacking.md`) · calling a routine
instead of reading it — emulation and Frida-RPC (`emulation-and-rpc.md`) · instruction-level tracing
and de-obfuscation (`native-dbi-and-deobfuscation.md`) · protocol reversing beyond REST
(`protocol-reverse.md`) · what to do when userspace hooking provably cannot reach the check
(`kernel-and-environment-hardening.md`) · split APK / App Bundle sets (`split-apk.md`) · schema-free
protobuf decoding (`protocol-reverse.md`) · Dex-VMP differential analysis
(`vmp-differential-analysis.md`) · kernel-module templates and their version gate
(`kernelsu_syscall_mask.py`) · working from the phone itself (`on-device-tooling.md`) · publishing what
you learned without publishing the target, and reading a graded precedent before repeating work
(`desensitization-and-leak-scans.md`, `scripts/scan_leaks.py`, `precedents/`).

**Dependencies this skill does not ship** — the Dart AOT workflow needs a snapshot dump this skill
cannot produce, and naming which front end you used matters. Details:
`references/coverage-and-limits.md`.

**How strong these claims are:** every item above carries one of three labels — `observed` (a command
and its output exist behind it), `inferred` (reasoned from mechanism or a neighbouring measurement),
`unverified` (assumed, or reported elsewhere). Treat the distinction as load-bearing rather than
cosmetic, and label your own results the same way. The evidence behind each label, the extension
pass's own footing (*the tool was measured, the route was not*), and the list of scripts that have
never been run all live in `references/coverage-and-limits.md`.

**Not covered — say so rather than improvise:** Unity / IL2CPP logic recovery · React Native /
Hermes bytecode and Cordova internals · iOS of any kind · defeating a server-side authority · an
off-the-shelf unpacker, or an anti-detection arms race · building and shipping a kernel module · a
Stalker trace guaranteed to work on every device. Each of these has a reason and, where one exists,
an evidence boundary — both are in `references/coverage-and-limits.md`.

**What was never exercised, and which scripts have never been run**, is recorded in
`references/coverage-and-limits.md` — read it before treating "this was measured" as covering the
route you are about to take. Silence in the record is not support.

**The fallback, as an instruction:** if the target does not match that list, or no symptom-index row
matches, **stop and classify before choosing a branch.** Answer the thirteen questions first. If the
shape still does not fit — an unknown runtime, a mechanism you cannot name — say exactly that, and
propose the cheapest experiment that would identify it, rather than taking the closest documented
route and applying it anyway. A wrong branch here does not fail loudly: it produces an artifact that
builds, runs, and does the wrong thing.

## Hand-off points — where this skill ends and another view begins

Four boundaries that are easy to walk into without noticing. Each names what the other side owns
rather than restating it, because two copies of the same advice drift apart. The JNI form table and
the per-form verification table live in `references/handoff-boundaries.md`.

1. **JNI** — a Java `native` declaration and its implementation are two views of one function, and
   this skill reads each with a different tool. A symbol search fails **silently** on dynamic
   registration. Authoritative treatment: `java2c-and-jni-sinking.md` §The JNI boundary — why a
   symbol search fails silently.
2. **Hardening** — a dex-side packer observation is a native-side implementation question.
   `packers.md` owns the dex-side identification; the deep dive belongs on the other side.
3. **Native anomalies** — read them *from the APK side*, because the judgement is whether your patch
   caused the death. Restoring a symbol or reversing an OLLVM function is a different activity with a
   different toolchain: point across instead of extending `native-and-so.md` into it.
4. **Deliverable form** — when the artifact stops being an APK, the verification question changes with
   it. G1's other three forms each move the evidence somewhere else, and the failure is quiet: a
   privileged result reported in the language of a finished build.

## Symptom index — a matching row is a stop signal

You arrive at a symptom, not at a file name. Each row below is a failure that has already been paid
for. **If any row matches what you are observing, load the file before your next command** — not after
your next three attempts. Reasoning from first principles at this point is how the same hours get
spent twice; more than one entry here is a lesson that was re-derived by hand while the answer sat
unread in this repository.

| What you observe | Load first |
|---|---|
| A repackaged/re-signed build **dies before your code runs**; `SIGSEGV`, all registers zero, `pc=0`, `fault addr` near `0x0` | `native-tamper-and-suicide.md` (deliberate crash), then `code-virtualization-and-custom-linkers.md` |
| **No packer** (Application is the app's own, dex readable) **and it still dies** | `code-virtualization-and-custom-linkers.md` §a loader is still a possibility; but if the same build also dies on a *second, unrelated* device you are looking at an ordinary startup fault, not a hardened one |
| The app dies at startup on **every** device, packed or not, with **no tombstone** while `crash_dump` says `already traced` and logcat says `exited cleanly (0)` | a bundled crash reporter has taken the signal handlers, so the platform's own trail is gone. Frida spawn-gating is the recovery route |
| A `FORTIFY: pthread_mutex_lock called on a destroyed mutex` abort in a Flutter app, on the **main** thread, before the first frame completes | `dart-aot.md` — check `libapp.so` is actually being loaded; Flutter's engine bootstrap is the usual place a native lifecycle fault surfaces |
| Log says a **Java-layer** signature/integrity check **passed**, yet the process dies | `code-virtualization-and-custom-linkers.md` §a Java-layer "signature killer" is a decoy |
| Deleting a library fixes validation but yields `UnsatisfiedLinkError: dlopen failed: library "X" not found` | `code-virtualization-and-custom-linkers.md` §the deadlock that eats hours |
| Whole classes appear as bare `native` declarations with no body | `java2c-and-jni-sinking.md` — read it **before** dumping memory: if this is Java2C there is no DEX to find, at any point in the process lifetime. A handful of `native` methods in an otherwise ordinary dex is JNI sinking, not this |
| A `Java_*` search over a hardened library returns nothing at all | `java2c-and-jni-sinking.md` §The JNI boundary — why a symbol search fails silently — dynamic registration, or `-fvisibility=hidden`. The check that works is "exports `JNI_OnLoad` and zero `Java_*`" |
| You are about to publish an evidence file, a transcript or a README that quotes real work | `references/desensitization-and-leak-scans.md` — run `scripts/scan_leaks.py` **before** it is committed; the hit list is a set of lines to look at, and `--show-exempt` is where the wrong suppressions show |
| A hooking module appears to have run but its log tag is silent, and you are about to record "it never loaded" | `references/precedents/logd-broken-module-never-ran-case-3.md` — a broken `logd` delivers nothing on `logcat` while the module's whole run sits in LSPosed's file log; read both channels |
| A library's **SONAME does not match its filename** | `code-virtualization-and-custom-linkers.md`, `native-and-so.md` |
| Your edit had **no effect at all**, with no error | `server-config-and-updates.md` §3 (the value may be server-sent), then `packers.md` §map the validation boundary |
| Process **hangs** with no crash record, or dies to a `uid 0` killer | `native-tamper-and-suicide.md` §the rule (you probably made a terminate path *not return*) |
| Death looks like an ordinary null dereference in a hardened library | `native-tamper-and-suicide.md` §deliberate-crash stubs |
| The app dies **only while you are attached/rooted** | `detection-and-anti-analysis.md`; run the unmodified original under identical conditions first |
| **Install fails with `[-124]` and mentions `resources.arsc` / alignment** | `repack-and-sign.md` §2a — STORED **and** 4-byte aligned, both required |
| **Install fails with a bare numeric code (e.g. `[-99]`) and no `INSTALL_FAILED_*`** | `repack-and-sign.md` §vendor install interception — a device-side interceptor, not your build. Use the root `pm install` path |
| **After an install, `am start` does nothing / screenshots show another app / `am start -W` hangs** | `repack-and-sign.md` §the installer may still own the screen |
| Log shows `Failure to verify dex file ...: Bad checksum` and a startup `ClassNotFoundException` for an ordinary class | `byte-level-patching.md` §the dex header has two integrity fields — order matters |
| An install "succeeded" but nothing changed, or the version did not move | `long-task-discipline.md` §keep the observation window clean |
| Evidence contradicts itself, or a capture looks like two states mixed | `long-task-discipline.md` §keep the observation window clean |
| You took screenshots but drew the conclusion from logs or from the patch itself | `long-task-discipline.md` §captures you never looked at are not evidence |
| You are about to re-run an experiment whose result you already recorded | `long-task-discipline.md` §long-context decay |
| A script will not start, or a tool "is missing" | `scripts/doctor.py`, then `toolchain.md` §"not on PATH" is not "not installed" |
| A hook or probe reports **no events at all**, and you are about to call it detection | `scripts/anti_detect_probe.js` for the environment self-report first, then `detection-and-anti-analysis.md` §Step 3: locating the check — the order of search from Stage 0 |
| `attach` hangs and then fails **while the process is still in `ps`** | `detection-and-anti-analysis.md` §Step 3 Stage 0 — check for `D` in `/proc/<pid>/stat`, and attach a *different* pid as a one-line control before blaming the target |
| The app exits with no tombstone, no crash and no ANR record | `detection-and-anti-analysis.md` §Step 3 — a clean self-exit means the check ran before your hooks existed; the branch conditions there say which Stage |
| A dump region validates as the wrong thing, or an `r--s` view of `base.apk` looks like a dex | `advanced-unpacking.md` §What this route cannot do, and how to tell before you spend the window |
| Feature-scoped network failure (login/register/pay) while the rest works | `tls-and-cert.md` — do not assume your patch caused it |
| Everything works but **every signed request fails** after repack | `signature-derived-keys.md` |
| A re-signed build **runs fine, renders its whole UI and logs no error — but one feature silently never loads**, and `dumpsys`/DNS/logcat show **no request for it at all** (not a rejected request: *no request*) | `code-virtualization-and-custom-linkers.md` §what the native check actually reads — refusing **before** the request is built. Not the row above: "sent and rejected" and "never sent" have different owners |
| You cannot tell whether a missing feature is **your patch's fault or the target's own behaviour** | `long-task-discipline.md` §single-variable discipline. Run the **zero-change control through the same pipeline**, and the decisive variant: the unmodified original with the patch applied **in memory only**, same device, same network |
| Under Frida `spawn`, the UI never appears — `mCurrentFocus` stays `null`, screenshots come back blank, the Activity stack never builds | `dynamic-frida.md` §spawn keeps the Activity stack down: write the patch into memory, **detach**, then start the Activity normally |
| `frida-server` keeps disappearing mid-experiment, or the device reboots itself while you are working | `dynamic-frida.md` §when the ROM hunts your instrumentation |
| Ads still appear after a patch that should have killed them | `server-config-and-updates.md` §6 (cached config / remote re-enable), then `ad-removal.md` §step 4 (count the SDK's own log lines; n -> 0, not "I did not see it") |
| A forced-update or "must update" gate blocks the build | `updates-and-forced-upgrade.md` §step 6 |
| The dialog is gone but the feature is still locked | `membership-and-limits.md` / `account-gates.md` — decide server vs client authority before patching again |
| You are about to discard a route as "blocked" | `packers.md` — re-read it before writing any route off; mis-attributed failures have removed viable routes for hours |
| The task has run long and you are unsure what is already proven | `long-task-discipline.md` §keep a live record |
| A dumped dex parses in full, the classes are all there, and most method bodies are `return-void` stubs or nop fills | `references/advanced-unpacking.md` — an extraction shell: measure the `stub%` with `scripts/dex_dump_validate.py` before trusting any of it, and know that recovering the bodies is a different route |
| Your `frida` dump dies mid-write (`script has been destroyed`), or the process you are dumping keeps changing pid | `advanced-unpacking.md` §dumping when frida is refused — rule out memory pressure first; a reclaim-and-relaunch needs no instrumentation |
| A repack is refused by several independent checks, or the build has to keep working through store updates | `references/lsposed-and-modules.md` — deliver a module instead of an APK; G1's form table says when |
| A hook module is installed, enabled and scoped, yet its log tag never appears — and you are about to conclude it never ran | `lsposed-and-modules.md` §Deploy, enable, and verify — **a `logcat`-only verdict has already been wrong here**: on one ROM `logd` is broken and output reaches only `/data/adb/lspd/log/modules_<ts>.log` |
| A module's entry class is missing from its own dex (so it can never load), yet the package installs, enables and looks healthy | `references/lsposed-and-modules.md` — check `assets/xposed_init` against the dex's actual classes; installation is not evidence of anything |
| You only need to **call** the target's own routine (sign, token, encrypt) rather than change the app | `references/emulation-and-rpc.md` — emulate it, or service-ify the live function over Frida RPC |
| A native function is a many-thousand-line `switch` state machine, or the decompiler's output is meaningless | `references/native-dbi-and-deobfuscation.md` — OLLVM shapes, a Stalker trace, and how far a trace actually gets you |
| `Stalker.follow` installs but no events arrive, or following a hot libc export crashes the process | `references/native-dbi-and-deobfuscation.md` §6 failure modes — this repository measured both |
| The traffic is protobuf/gRPC/QUIC, or a proxy sees TLS but requests still fail on a Flutter app | `references/protocol-reverse.md` — schema-less protobuf, frame capture, and native-side pinning |
| Userspace hooks land and the app still dies: the check reads `/proc/self/status` through a raw `svc`, or runs before `JNI_OnLoad` | `references/kernel-and-environment-hardening.md` — what the next layer up and down can actually do, and when to stop |
| You must edit, repack, sign or inspect the APK **from the phone itself** | `references/on-device-tooling.md`, `scripts/mt_mcp_probe.py` |
| A captured body decodes to nothing readable, or you cannot tell whether a length-delimited field is a string, a nested message or a packed array | `protocol-reverse.md` §1. Protobuf on the wire (measured) — run `scripts/protobuf_decode_raw.py`; the candidate list and its `tie:` lines are the answer |
| Method bodies are present but decode as **private opcodes**, and you need the mapping rather than an explanation of why VMP is hard | `vmp-differential-analysis.md`, then `advanced-unpacking.md` for the shape diagnosis |
| A store build arrives as `base.apk` + `split_config.*.apk`, or a rebuilt build is refused **as a set** although every file verifies on its own | `split-apk.md` — one keystore across every member for `pm install-multiple`, and check that a merge is legal before trusting a merged single APK |

## Gates — clear these before you patch, in order

Each gate is an **action with a pass criterion**. Do not proceed past a gate you have not cleared, and
do not treat "I understand the idea" as clearing it. Skipping a gate is not a shortcut; it is how the
work gets redone.

**G1 · Deliverable form — and the cost ceiling on it.** State, in one sentence you could hand to
someone else, what artifact must exist at the end and under what constraints (rooted or not,
installable on a stock device or not, must survive updates or not, online or offline). *Pass:* the
sentence names a testable constraint, not an activity. *Fail:* you are solving a problem in an
environment the deliverable will never see.

Then name the **form** that sentence implies. "A rebuilt, self-contained APK" is only one of four, and
this is where the choice belongs — not after the repack has already failed:

| Form | Right answer when | What it costs you |
|---|---|---|
| **Rebuilt, installable APK** | The client owns the behaviour; no multi-point integrity check; no extraction shell | Repack, re-sign, and a device to verify on |
| **LSPosed / Xposed module** | The logic is client-side but the app fights repacks (multi-point signature checks, shell self-verification), or the result only has to work on rooted devices you control | A rooted device, module scaffolding, and an app that must not detect the hooking framework → `references/lsposed-and-modules.md` |
| **Local RPC / emulation service** | You do not need to change the app — you need to **call** it: a signing routine, a token, an encryption function | A live device or an emulated loader plus a call harness → `references/emulation-and-rpc.md` |
| **Analysis report with a stated boundary** | The authority is server-side, or the target is a real VMP / extraction shell whose recovery cost exceeds the value of the task | Nothing ships — and that is the honest answer, not a failure → `references/advanced-unpacking.md`, `references/server-api.md` |

*Decision trigger for leaving the first column:* switch off "rebuilt APK" as soon as the evidence shows
**(a)** more than one independent integrity check that must all pass, **(b)** an extraction shell whose
method bodies exist only at invocation time, or **(c)** any body that decodes as private opcodes. At
that point the repack route is not merely expensive — it is blocked, and the deliverable sentence
should say which form replaced it. **A form chosen here and re-read at every checkpoint is the guard
against the most expensive drift in this skill** (`references/long-task-discipline.md`).

**G2 · Environment truth and capability inventory.** Run `scripts/doctor.py` (and `scripts/preflight.py`
if a device is in play). *Pass:* you know which toolchains and scripts can actually run here, you have
seen the environment warnings — clock skew, leftover `adb forward`/proxy, a device-side frida process
already running, a tool installed off-PATH — **and you have written down the capability this target will
demand against the capability this machine has.** Name the two or three layers the task will almost
certainly reach (for example "arm64 native decompilation", "Dart AOT snapshot dumping", "device-side
TLS inspection", "dex-wide cross-referencing") and mark each available / missing-but-installable /
genuinely out of reach. *Fail:* you are about to attribute to the target a failure caused by your own
setup — or to spend a day routing around a tool that installs in ten minutes. A layer whose tool is
missing is a **task item**, not a constraint to design around. → `references/toolchain.md` §Closing a
capability gap

**G3 · Code location.** From the manifest and dex, answer: is there a packer, where does the app's own
code live (dex / native / Dart / Unity / server), and is any of it virtualized to native. *Pass:* you
can name the class that owns the behaviour you intend to change, or you have an explicit plan to find
it. *Fail:* you are about to patch a layer you have not located. If recon says "no packer", still
check the virtualization shape — see the index rows above.

**G4 · Baseline and control.** *Pass:* you have a control run — the unmodified original, or a
zero-change repack through the same pipeline — and you have recorded the observed failure (including
**time-to-death**, if it dies). *Fail:* when the patched build misbehaves you will have nothing to
compare against, and every later measurement is unfalsifiable.


## Start here: classify the target in thirteen questions

Answer these before touching a tool. Every one of them changes the whole plan.

1. **Is the app packed/hardened?** → `references/recon.md`
   Read the manifest's `application android:name`. If it is a third-party shell class rather than the app's own Application, you have a packer and must handle it first.
2. **Where does the behavior you want to change actually live?**
   - Ad SDK (Pangle/GDT/AnyThink/Kuaishou/Baidu/Sigmob…) → usually **client-side and removable** → `references/ad-removal.md`
   - **Server-issued config for UI the client renders** (launch screen, popup, announcement, tab set, sponsored card on a home feed) → **the client decides, the server supplies the data** → `references/server-config-and-updates.md` (this is the most common shape of "ad" in a modern app, and there is no SDK to find — decide this question early, because hunting an SDK that does not exist costs hours)
   - Membership / VIP / paid content → **usually server-authorized, client patch is cosmetic** → `references/membership-and-limits.md` (read this *before* spending hours)
   - Feature flag, UI gate, debug switch → usually client-side
   - Anything decided by an API response → server-side → `references/server-api.md`
3. **Is the app's own code in plain dex, or moved to native/Flutter/Unity?**
   Plain dex → you can patch. Flutter (`libflutter.so` + `libapp.so`) / Unity (`libil2cpp.so`) / pure native → different toolchain entirely. See `references/recon.md` §Where does the app's own code live and `references/framework-runtimes.md`.
      **Runtime check (cheap -- do it before committing to a layer):** hook the obvious Java classes for the UI you care about, then reproduce that UI. If those hooks fire, the behavior is Java-owned. If they fire **zero times** while the UI is plainly on screen, the behavior is drawn by the runtime or by native code, and a dex-only plan will stall. Do not keep hunting in dex after a zero-hit probe -- that is the most expensive wrong turn in this skill's history.
4. **What must the deliverable be able to do?** Write the answer as a testable sentence before
   planning anything, then re-read it at every checkpoint. This is the drift guard, and the drift it
   guards against is the most expensive one in this skill: a runtime-only result (a data edit, a live
   hook, a blocked hostname, a host proxy) can look like success while failing the actual requirement.
   The axes that decide it: **privilege** (unrooted?), **modification form** (a rebuilt, installable
   artifact, or is live instrumentation acceptable?), **ABI/device class**, **network** (must it work
   online?), **persistence** (survives restart / upgrade / fresh install?), **distribution** (must the
   shipped file be self-contained?). → `references/long-task-discipline.md` §the most expensive drift.
   **If the evidence already shows a deep extraction shell, a VMP, or more than one independent
   integrity check, re-answer this question against G1's four forms** — the repack column may be
   blocked rather than expensive, and the answer may be a module, an RPC service, or a report.
5. **Does the app verify its own signature, or does the server?**
   App-side → you must bypass it. Server-side → re-signing silently breaks the app later. See `references/repack-and-sign.md` and `references/server-api.md`.
6. **What is your device situation?** → `references/environment.md`
   Rooted real device (best), emulator with root, or no device (static only). Also: this determines whether Frida is usable. **Run `scripts/preflight.py` before your first experiment**, and again whenever a failure surprises you — device state, a dead device server, a leftover proxy, and clock drift all masquerade as a broken patch (`pitfalls.md` P9).
7. **Which architecture is actually executing?** → `references/native-and-so.md` §Cross-architecture
   `getprop` reports what the device claims and `primaryCpuAbi` reports what the package manager chose — neither is what is running. Only the live mapping is ground truth (`scripts/lib_map.py`). If the library you meant to patch is not mapped, a translator is in play, or the ABI differs from your assumption, that changes the plan more than any patch will.
8. **Is one *specific feature* failing at runtime — login, registration, payment, an API-backed screen — while the rest of the app works?**
   → `references/tls-and-cert.md`. A feature-scoped network failure is very often a **TLS/certificate problem on one code path**, not a consequence of your patch. The app can even carry two independent trust chains, so "other requests work" proves nothing. Rule this out in minutes before hunting for a signature check.
9. **Was the input a build you did not produce** (a "cracked"/"modded" APK circulating online)?
   → `references/third-party-builds.md`. Audit it before adopting it: such builds are frequently re-protected (sometimes with *more* layers than the original) and may carry injected components or endpoints. Never use one as a patching workbench.

   **Long-task rule:** if this is likely to run long, open `references/long-task-discipline.md` now
   and keep its record updated as you go. Re-read the refuted-conclusions and dead-routes sections
   before starting any new experiment. Losing earlier findings is the most expensive failure in this
   skill, and it is entirely preventable.
10. **Does the client sign its requests with its own signing certificate?**
    → `references/signature-derived-keys.md`. Grep for `toCharsString()` / `signatures[0]` /
    `getPackageInfo(..., 64)` **before the first repack**. If that value feeds a native HMAC/DES
    routine, the rebuilt APK must hardcode the *original* certificate value at every read site, or
    every signed request fails while the app still launches and looks healthy. This is the single
    most expensive silent failure in a repack, and 15 minutes of grep prevents it.
11. **Does the app die on its own after a while — with no Java stack trace, or with a native
    crash that looks like a bug?**
    → `references/native-tamper-and-suicide.md`. A hardened library that decides the build is
    tampered rarely calls `kill`. It more often **arranges a fault** (load a small constant, use it
    as a pointer) so the death looks like an ordinary defect, and the system then reports it as an
    app "crash" or "abnormal" dialog. Two rules before you touch anything: **enumerate which
    mechanism actually fires** (the signal and the tombstone split them apart), and **neutralise by
    returning, never by making it not return** — a spinning stub freezes the process and produces a
    symptom that looks nothing like the cause.
12. **Will this build still be usable in a week?** → `references/updates-and-forced-upgrade.md`
    If the app has any version check, upgrade prompt, or self-update path, an unpatched build can be
    turned off remotely or replaced by the official package. This is one or two edits and it decides
    whether the work is durable — do it as part of the build, not as a follow-up. Also check for a
    **hot-update / remote-config** channel, which can restore behaviour you removed without any version
    change at all.
13. **Does the request touch sign-in or phone binding — "no login required", "skip binding", "guest ok"?**
    → `references/account-gates.md`. The whole difficulty here is separating a **client-side gate**
    (patchable) from an **account-scoped resource** (the screen is empty because the server has no
    account to answer for — not patchable). Classify first; and never fabricate a session to satisfy a
    gate, which produces a state worse than being signed out.

## The workflow, end to end

Steps are ordered. **Skip a step only when its stated skip condition is met** — "it seems
unnecessary" is not a condition, and it is the reason most of the failures in `pitfalls.md` happened.

**Two-strike rule.** If the *same kind* of attempt fails twice, stop and go back to classification.
Do not run a third variation of a hypothesis that has already failed twice. Two failures of one shape
means the model is wrong, not that the parameters need tuning — and the third attempt is where an
entire round gets spent confirming what the first two already said. Re-read the symptom index at that
point; it exists for exactly this moment.

1. **Preflight, then Recon** — `scripts/doctor.py` is the cheapest possible first command: it reports which toolchains and scripts can actually run here, and surfaces the environment facts that poison experiments (clock skew, leftover `adb forward`/proxy, a device-side frida process already running, a tool installed off-PATH). Then `scripts/preflight.py` before anything else if a device is involved (it takes seconds and prevents a whole class of false conclusions), then `references/recon.md`. Manifest, package name, version, ABI, dex count, packer, embedded SDKs, where the app's own code lives. Ten minutes here saves hours. **If it is packed, unpack before anything else** (`references/recon.md` §unpacking): you cannot patch code you cannot read, the encrypted payload lengths tell you which dumped dex is the original, and a memory dump must be de-duplicated by hash and structurally validated before any of it is trusted.
   **If recon says there is no packer but a re-signed build still dies**, you are in the layer `references/code-virtualization-and-custom-linkers.md` covers — do not proceed on the assumption that "no packer" means "editable".
   **If the app already dies on its own** — especially at a roughly constant time after launch, or with a native crash — locate the mechanism *before* planning any patch (`references/native-tamper-and-suicide.md`, `scripts/native_crash.py`). Record the observed time-to-death: it is the baseline every later attempt is measured against, and without it a surviving run cannot be told from a changed schedule.
   *Skip condition:* never skipped. G2/G3 in §Gates are cleared here or not at all.
2. **Extract strings and endpoints** — build a picture of the app's API surface and SDK inventory from the dex string tables. No decompiler needed for this, and it is fast. Scripts: `scripts/dex_strings.py`.
3. **Trace to the owning class** — find the class that wraps the behavior (the app almost always wraps third-party SDKs in one helper). Reverse-lookup instructions: `references/dex-patching.md` §finding-the-call-site.
4. **Decide the patch layer** — client SDK call / client rendering / client data consumption / server contract. See the table in `references/ad-removal.md`.
5. **Patch surgically** — `references/dex-patching.md` and `references/byte-level-patching.md`.
   Two techniques, and picking the right one is a decision, not a preference:
   **equal-length byte edits** (`scripts/dex_patch_bytes.py`, located with
   `scripts/dex_find_insn.py`) when the change fits in an existing instruction slot
   or constant — nothing moves, so no offset, try/catch block or debug pointer can
   be invalidated. **dexlib2 method rewriting** (`scripts/dexpatch/`) only when the
   change genuinely needs new instructions. Whole-tree smali round-trip damages
   R8-optimized dex in ways that only show up at runtime; a method rebuild also
   inflates the file (measured: `debug_info` 924 B -> 22.8 KB, dex 4.32 MB ->
   7.73 MB on one sample). Whichever you use, recompute the dex header integrity
   fields (**signature first, checksum last**) — `references/byte-level-patching.md`
   §the dex header has two integrity fields.
6. **Repack and sign** — `references/repack-and-sign.md`. **Do not strip the whole `META-INF/`.** This single mistake destroys otherwise-correct builds.
6b. **Neutralise the update path — before you call the build done.** If the app checks for updates at all, add the two-layer patch (`references/updates-and-forced-upgrade.md`): no-op the update routine's entry, and force the version comparison to its "no update" side. A build that can be switched off or replaced remotely is not a deliverable, and this costs minutes here versus a rebuild later. Do the same for any **remote-config or hot-update** channel that could restore the behaviour you removed.
6c. **Handle account gates only after classifying them** — if the request mentions sign-in or binding, apply `references/account-gates.md` and state plainly which guarded screens become usable and which stay empty because their content is account-scoped.
7. **Verify on device** — `references/environment.md` + `references/verification.md`. Check: launches, the changed behavior actually changed, nothing unrelated broke, and **the app reaches its normal UI with no blocking dialog**. First prove the artifact actually changed on the device -- a package manager reporting success does not prove an interposed confirmation was accepted (P18). Capture continuously for the first ~20 seconds after launch, **and look at the captures** — sampling gaps are how a blocking modal goes unseen (P20), and a burst of images that were never inspected is not evidence. If the accessibility tree is empty, the image is the primary evidence rather than a fallback.
8. **Log what you learned** — if a failure cost you more than thirty minutes, add it to `references/pitfalls.md`. That file is the most valuable artifact in this skill.

## What "done" means — do not claim it earlier

Every item below must be true before you report completion. Anything less is a **checkpoint** and must
be labelled as one, out loud, with what remains. Premature "done" is the most damaging thing you can
report, because it ends the investigation while the user believes the problem is solved.

1. **The artifact exists and its identity is recorded** — path plus hash, not a filename.
2. **It was installed and launched on the environment the deliverable sentence names** (G1/R1). If
   that environment was not available to you, say so and label the result accordingly.
3. **The behaviour you changed is verified changed** — by direct observation of the feature, not by
   the absence of an error message. "The log is clean" is not evidence; "the screen shows X" is.
4. **The features it touches still work.** You exercised them. A build that starts but whose affected
   feature is dead is not a result.
5. **The original limitation is stated if any survives** — with the coupling that causes it, so the
   next person can decide whether to accept it.
6. **Nothing you did leaves the target or the device in a broken state** unless that was the goal, and
   any privileged workaround is labelled a fallback rather than the deliverable.

If items 1–4 hold but the environment was wrong, you have a **prototype**, not a deliverable. Say
"prototype" and name the gap.

## Stop conditions — halt and re-classify, do not retry

These are moments where continuing to push forward is the wrong move. Each has cost hours somewhere.

- **The same shape of attempt failed twice.** See the two-strike rule above.
- **A patch had no effect and you were about to try a third variant of it.** No effect means the
  diagnosis was wrong, not that the patch was unlucky. Re-classify the layer.
- **A new failure has no place in your current model.** That is the symptom index's trigger condition.
- **You are about to write off a route as "blocked"** without a control build proving the block is
  the app's doing rather than your pipeline's. Mis-attributed blocks have removed viable routes.
- **You are about to claim success on absence of errors.** See §What "done" means.
- **A measurement disagrees with a conclusion you already recorded as settled.** Re-open the
  conclusion; do not explain the measurement away.

## Non-negotiable constraints

- **Read-only inputs.** Keep the original APK/dex untouched; work on copies. Always keep a known-good baseline to diff against.
- **One variable at a time.** If you change two things and it breaks, you learn nothing. Build a control (same pipeline, zero patches) and compare.
- **Verify structure after every dex edit.** `scripts/dex_classdiff.py` must report zero differences in class set and access flags for classes you did not intend to change.
- **Do not patch a method that is widely shared.** Before patching any helper, count its callers (`scripts/find_refs.py`). A `Long.valueOf` wrapper with 30 callers is not an ad-specific hook.
- **Do not make an API fail to suppress a UI element.** A 404/400 on an endpoint that other features depend on takes the whole screen down with it. Suppress at the data-consumption or render layer instead.
- **Neutralise a native terminate path by returning, never by making it not return.** A stub, stub patch, or function entry replaced with a spin or a self-branch does not suppress the check — it freezes the caller, holding whatever lock it had, and unrelated threads wedge behind it. The symptom (a hang, an external kill, a restart loop) looks nothing like the cause, and there is no crash record to explain it. Return a benign value, and prefer success (0) over failure (-1). Never touch the ordinary-path symbols (`pthread_exit`, `exit`, `abort`, `snprintf`, `closedir`). `references/native-tamper-and-suicide.md`
- **Look before you conclude — and look while you wait.** Execute, capture, and **inspect**; do not drive and sleep blind. A screen that is actually looked at answers in one step what coordinate-guessing cannot answer in five: the layout moved, a different dialog is up, a countdown is frozen, the text on screen says exactly why. Where the thing you are waiting on is visible, a sample you can inspect beats a duration you hoped was right, and byte-identical samples mean nothing is going to change. `scripts/snap.py`; `references/environment.md` §look at the screen.
- **Put a timeout on every command, and calibrate it from measurement.** An unbounded call turns a stall into "the task stopped making progress", which is indistinguishable from slow work and costs hours silently. Time the operation once, record it, then derive the bound from it — that is what makes slow and hung distinguishable. A deadline that passes is a measurement, not a verdict. `references/long-task-discipline.md` §bound every wait.
- **Every claim needs evidence.** "Probably", "should be", "in theory" are not findings. Either you observed it, or you label it unverified.
   - **"Done" means the user-visible outcome**, not an internal signal. A blocking dialog still on screen means the task is not done, however many errors disappeared from the log. Absence of a log line is absence of evidence, never evidence of success.
   - **Do not discard a route on compound evidence.** If a failure followed two simultaneous changes, the attribution is a hypothesis, not a finding. Re-run it single-variable before writing the route off -- mis-attributed failures have removed viable approaches for a long time.
   - **Prove the device changed before measuring.** Install success describes the request, not the app on disk. Confirm the artifact actually advanced, or every following observation describes the previous build.
- **Attribute a failure to the right layer before patching again.** When something stops working after a rebuild, first check whether the **unmodified original** fails the same way on the same device and network. Feature-scoped network failures in particular are frequently the app's own TLS/certificate problem (`references/tls-and-cert.md`); chasing a signature check that does not exist burns hours.

## Reference index

Load only what the current step needs.

| File | Load when |
|---|---|
| `references/recon.md` | Starting any new sample; identifying packer, SDKs, code location, ABI |
| `references/server-config-and-updates.md` | **The launch screen, a popup or the tab set is server-sent**; no ad SDK was found; a removed promo came back; anything controlled by a `*Config`/`*Popup` DTO with an `enabled` flag |
| `references/byte-level-patching.md` | You want to change behaviour by editing a few bytes rather than rebuilding a method — equal-length patches, locating an instruction's exact offset, dex header integrity fields, branch polarity, verifier legality |
| `references/packers.md` | The app is packed/hardened, or an edit makes it die before your code runs. Also load before discarding any route as "blocked by the shell" |
| `references/code-virtualization-and-custom-linkers.md` | **No packer, dex is readable, and a re-signed build still dies** — whole classes turned `native`, a private loader with a mismatched SONAME, a self-decrypting payload, a Java-layer "signature killer", and the keep-it/drop-it deadlock |
| `references/java2c-and-jni-sinking.md` | **Whole classes are bare `native` declarations and you are about to hunt for a decrypted DEX** — Java2C has none, ever; the code is in a `.so`. Also the JNI boundary: why a `Java_*` symbol search fails silently |
| `references/vmp-differential-analysis.md` | Method bodies are present but decode as **private opcodes** — a real Dex VMP: the known-plaintext differential, which links can and cannot be automated, how to *prove* a derived opcode table, smali generation, and when the route is closed |
| `references/framework-runtimes.md` | The UI is not native (Flutter / React Native / Unity / Cordova), or Java-layer hooks fire zero times while the UI clearly works |
| `references/dart-aot.md` | The logic lives in a Dart AOT snapshot (`libapp.so`): pinning the Dart version, building a matching decompiler, the object pool and reference indexing, register/boolean conventions, locating and patching Dart code |
| `references/native-and-so.md` | Patching in a `.so`, needing code to run before the app's own code, hand-built native payloads that crash inside the linker, or **deciding which library/ABI is actually loaded and executing** |
| `references/native-tamper-and-suicide.md` | The process dies on its own (no Java stack, or a native crash that looks like a bug); you are about to neutralise a `kill`/`exit`/`abort` path; or a hardened library's sections/function boundaries look wrong |
| `references/detection-and-anti-analysis.md` | The app fights back: it dies after you attach, refuses to run, detects root/hook/debugger. **Cost-first (A/B/C), plus the order of search** (see its Step 3 stage funnel) and when to go static |
| `references/toolchain.md` | Choosing or invoking tools, something is not installed (including "not on PATH but present on disk"), a tool's output smells wrong, or you need to know which tools exist only as a GUI |
| `references/ad-removal.md` | Task involves ads, trackers, sponsored cards, splash/interstitial/reward |
| `references/updates-and-forced-upgrade.md` | The patched build must **keep working over time**; the app has any version check, forced-upgrade dialog, self-update installer, or hot-update/resource channel. Load this for essentially every build you intend to ship. |
| `references/account-gates.md` | Task mentions "no login required", "don't force sign-in", "skip phone binding", "guest mode"; or a screen/feature is unreachable signed-out. Also load before promising that an account-scoped screen will show anything |
| `references/membership-and-limits.md` | Task involves VIP, subscription, paid content, unlock, "fully cracked" |
| `references/server-api.md` | The behavior is decided by a response, or you need to know if a patch can even matter |
| `references/dex-patching.md` | Any actual editing of dex/smali, choosing a patch layer, choosing a tool |
| `references/patch-audit.md` | Proving a patch **landed**, or that it is **legal**: length-vs-bytes comparison, the equal-length blind spot, verifier-level legality (`move-result*` adjacency), text-matching patch traps, and how to report a missing patch |
| `references/repack-and-sign.md` | Rebuilding, signing, installing, or a repacked app misbehaves |
| `references/signature-derived-keys.md` | The app reads `signatures[0]`/`toCharsString()`, or a rebuilt APK installs and runs but every signed request fails (`sign`/`_p`/`uth` empty or `-1`) |
| `references/runtime-data.md` | Local state matters: DataStore, SharedPreferences, SQLite, protobuf caches, tokens — **or your data edit keeps being reverted, or a stored value looks encrypted** |
| `references/dynamic-frida.md` | Frida setup, hooking strategy, tracing caller chains, finding the real call site |
| `references/environment.md` | Device/emulator setup, root, ADB, networking, offline devices, emulator console control and recovery, **the preflight check to run before every experiment block** |
| `references/verification.md` | Defining what "done" means; building the evidence chain |
| `references/tls-and-cert.md` | One feature fails at runtime (login, registration, payment, an API-backed screen) while the rest of the app works |
| `references/third-party-builds.md` | The input is a "cracked"/"modded" build you did not produce — audit it before trusting it |
| `references/long-task-discipline.md` | The task will run long, or you are resuming one. Live record, conclusion grading, drift checkpoints, **deliverable-form drift (rooted-only vs shippable)**, bound-your-waits, **captures-you-never-looked-at**, **long-context decay**, handover |
| `references/pitfalls.md` | Always worth a skim before building. This is the failure catalogue. |
| `references/coverage-and-limits.md` | You need to weigh a claim before trusting it: the evidence behind each covered item, the dependencies this skill does not ship, and the record of what was never exercised |
| `references/desensitization-and-leak-scans.md` | You are about to publish anything derived from real work — evidence, a transcript, a README — or a leak scan reports a hit: what must be desensitised versus kept, the do-not-anonymize list, and how the scan gates a commit |
| `references/precedents/` | You are about to do a kind of work this repository has already converged on — a hardened Flutter target, a zero-event trace, a module whose log is silent, an equal-length patch taken to the device. Positive cases with graded evidence and dead ends |
| `references/handoff-boundaries.md` | A routing decision is about to cross into another discipline: the JNI form table, the packer-versus-loader split, and what "verified" means for each of G1's four deliverable forms |
| `references/advanced-unpacking.md` | **The dump landed but the bodies are empty** (an extraction shell), or decode as private opcodes: the stub-ratio measurement, why FART's hooks died on Android 12-16, the root-side dump, its **boundary**, the layered descent, and where recovery stops |
| `references/lsposed-and-modules.md` | The client-side logic is reachable but **a rebuilt APK is refused**: delivering a system-level hook module instead, its gradle-free build chain, scope configuration and verification, and the layer a Java module cannot reach |
| `references/emulation-and-rpc.md` | You need to **call** a routine rather than change the app — a signing routine, a token, a cipher: emulated execution (Unidbg/Unicorn) with its environment-filling cost, versus service-ifying the live function over Frida RPC |
| `references/native-dbi-and-deobfuscation.md` | A native function is an OLLVM state machine, or you need instruction-level execution evidence: Stalker traces, the trace-to-CFG route, the Stalker/QBDI/emulation decision, and the **measured** zero-event and crash boundaries |
| `references/protocol-reverse.md` | The traffic is protobuf without a schema, gRPC, or QUIC/HTTP3; or a proxy sees TLS while the app still fails — schema recovery, frame capture, and native-side certificate pinning (Flutter/BoringSSL) with its boundaries |
| `references/kernel-and-environment-hardening.md` | Userspace hooking provably cannot reach the check — raw `svc` syscalls, `init_array`-early detection: what each layer can still do, the kernel-route map with its version gate, and when escalating is wrong |
| `references/on-device-tooling.md` | Working **from the phone itself**: MT Manager edit/repack/sign and its built-in APK MCP, LSPosed Manager, Termux+frida, and on-device data inspection |
| `references/split-apk.md` | The target is a **split APK / App Bundle set** (`base.apk` + `split_config.*.apk`), or `pm path <PKG>` returned several files: reading a set, merge versus unified re-signing, and the install refusal each mistake produces |

## Script index

All scripts are parameterized and path-agnostic; pass paths explicitly. Run `--help` or read the header of each.

| Script | Purpose |
|---|---|
| `scripts/doctor.py` | **Run this first.** Which tools exist (including off-PATH and `java -jar` jars), which scripts can run here, and the environment facts that poison experiments: clock skew, leftover forwards/proxy, a device-side frida already running |
| `scripts/dexutil.py` | **Dependency-free dex reader**: structural walk, exact instruction decode, `fix_dex_header`/`verify_dex_header` in the correct order, branch/operand helpers. Shared by the dex scripts; also dumps one method with offsets standalone |
| `scripts/dex_find_insn.py` | Locate an instruction by **decoded semantics** and get its exact byte offset, with context and both sides of any branch. This is how you find a patch site without guessing offsets or scraping listings |
| `scripts/dex_patch_bytes.py` | Apply **equal-length byte patches** from a JSON spec: semantic match, polarity pin via `expect_next`, equal-length enforcement, verifier legality, dex header recompute, re-decode to prove the edit landed. `--dry-run` first |
| `scripts/dex_check_verifier.py` | Tier-3 check: does any **conditional branch target a `move-result*`** (bypassing its producer, so the class fails to load)? Compares two builds and distinguishes pre-existing findings from regressions your patch introduced |
| `scripts/coldstart.py` | Cold-launch and capture a **timed screenshot burst + logcat signals + installed-build facts + launch timing**, and warn when the foreground activity is not your app |
| `scripts/smtool.py` | baksmali/smali wrapper with a bundled classpath (assemble/disassemble dex) |
| `scripts/patch_smali.py` | Method-body replacement in a smali tree, matched by signature |
| `scripts/dex_strpatch.py` | Byte-level string constant patch with **string_ids ordering guard** |
| `scripts/dex_classdiff.py` | Compare two dex class tables (set + access flags) to prove a patch was surgical |
| `scripts/dex_strings.py` | Dump/extract strings and endpoints from dex without a decompiler |
| `scripts/dart_pprefs.py` | Build/query the object-pool offset -> code-site index for a Dart AOT snapshot (arithmetic decode; seconds, not minutes) |
| `scripts/dart_pool_strings.py` | Recover string literals from a Dart AOT snapshot: framed entries, the one-byte vs UTF-16 split, file offsets, and a run-length noise filter |
| `scripts/dart_disasm.py` | Annotated windowed disassembly of Dart AOT code (pool + boolean annotations) plus a B/BL caller index |
| `scripts/find_refs.py` | Count and list callers of a method/field (blast-radius check). Takes a smali tree, a `.dex`, a directory of either, or an `.apk`. Always prints what it scanned, so "the input was unreadable" cannot be mistaken for "nothing references it" |
| `scripts/repack.py` | Rebuild an APK: replace dex, strip only signatures, keep `META-INF/services/`, write a **4-byte-aligned** archive, sign, verify. Also **split sets**: `--split-dir`, `--split-mode resign`/`merge`, `--signer auto/jar/apksigner` |
| `scripts/dexpatch/` | dexlib2 method-level rewriter (for changes that genuinely need new instructions) + build notes |
| `scripts/devsh.py` | Quoting-safe ADB shell helper for rooted devices |
| `scripts/usb_net_proxy.py` | Give an offline device network over USB (adb reverse + local proxy) |
| `scripts/datastore_inject.py` | Encode/inject AndroidX DataStore preferences (protobuf) safely |
| `scripts/probe_api.py` | Probe an app's HTTP API with correct headers, report status/shape |
| `scripts/install_test.py` | Install a build and run a launch/health check with logcat signal extraction |
| `scripts/frida_probe.js` | Four-layer runtime probe: app network layer + OkHttp + java.net + swallowed exception messages |
| `scripts/run_probe.py` | Inject a probe, stream it to a timestamped log file, stay resident while you operate the app |
| `scripts/tls_check.py` | Strict certificate check for one or more hosts (expired / wrong host / untrusted CA) |
| `scripts/preflight.py` | Read-only environment check before every experiment block: device, root, ABI/translation, clock skew, leftover proxy/forwards, dead device server. Run this before blaming a patch. |
| `scripts/lib_map.py` | What is **actually mapped** into a live process: per-library path, base, architecture (`ELF e_machine`), and classification (system / from-APK / runtime-materialized). Answers "which library and which ABI is really executing". |
| `scripts/elf_plt.py` | Resolve a PLT stub to its imported symbol (x86_64 + aarch64) from the **relocation table**, list a symbol's callers, and **byte-diff two libraries naming the symbol each changed stub belongs to**. Run before patching any stub |
| `scripts/so_constpatch.py` | Same-length rewrite of an isolated string constant, for **redirecting a library load instead of defeating a check**. Enforces equal length, refuses substrings of longer identifiers, reports constant-pool hits, patches inside an APK or a bare `.so` |
| `scripts/apk_diff.py` | Entry-level diff of two APKs by content hash: changed / **added** (injection candidates) / removed. Audits a third-party build and proves your own was surgical |
| `scripts/native_crash.py` | Locate a native death from a log or tombstone: signal, fault address, registers, frames split app vs system, the faulting instruction — plus a flag when the fault looks **arranged** rather than accidental |
| `scripts/grab_crash.py` | Recover a stack that a crash-reporter SDK swallowed, when the log shows the app died but prints no backtrace of its own. |
| `scripts/blob_decode.py` | Decode an opaque stored value by searching the parameter space (base64/base64url/hex × rotation × deflate/zlib/gzip) instead of guessing, then re-encode an edited payload with the same parameters. |
| `scripts/snap.py` | Bounded burst screenshot + control-tree capture, with a stall detector and an explicit verdict on whether the accessibility tree is usable at all. Use it so you *look* at the screen instead of driving blind. |
| `scripts/sig_probe.py` | Find the exact `signatures[0].toCharsString()` value: offline candidates from an APK (`--apk`), or the authoritative read from a live package (`--live`) |
| `scripts/spawn_patch_detach.py` | **Spawn under a probe, detach, then drive the UI.** Under spawn the Activity stack often never comes up; memory writes survive detach while hooks do not. Ordering matters: resume *before* waiting for `PATCHED` |
| `scripts/hook_patch_only.js` | The minimal probe for `spawn_patch_detach.py`: neutralise one native death site by offset and report `PATCHED`. `MODULE_NAME`, `FILE_OFFSET`, `PATCH_BYTES`; the replacement must be an equal-length "return" epilogue |
| `scripts/dex_dump_validate.py` | Dedupe, validate and rank dumped dex images: sha256 grouping, header integrity, extraction-shell discrimination via the **trivial-body ratio** (bimodal, not a threshold — `advanced-unpacking.md`), ranking, `--json`, `--trim` for page-aligned captures |
| `scripts/dex_mem_scan.py` | Find embedded dex images in memory captures and extract each at the size **its own header declares**: chunked scanning, magic validation, sha256 dedupe, `--dump DIR`, `--keep-partial` |
| `scripts/lsposed_scaffold.py` | Generate a minimal LSPosed/Xposed **module project skeleton**: manifest with the xposed meta-data, `assets/xposed_init`, the hook class, and build notes for a gradle-free toolchain (javac → d8 → aapt2 → zipalign → apksigner) |
| `scripts/frida_rpc_serve.py` | Bridge a Frida script's `rpc.exports` to a local caller with reconnect handling, so a live native function can be **called** instead of reversed |
| `scripts/rpc_template.js` | The editable companion to `frida_rpc_serve.py`: an `rpc.exports` skeleton plus a native-function call placeholder |
| `scripts/stalker_trace.js` | Instruction-level tracing with Frida Stalker: configurable module/offset targets, trigger selection, the event stream, output-size rules, and `transform` customisation |
| `scripts/stalker_report.py` | Reduce a `stalker_trace.js` log into block histograms and call sequences, and print an explicit diagnostic for the measured **zero-event** case |
| `scripts/mt_mcp_probe.py` | Probe MT Manager's on-device APK MCP (Streamable HTTP, `127.0.0.1:8787/mcp`): JSON-RPC handshake plus grouped `mt_apk_*` tool inventory; prints start-it-by-hand instructions and exits 2 while the service is down |
| `scripts/java2c_probe.py` | The evidence that separates **Java2C** from an extraction shell, a VMP and JNI sinking: per-class `native` density and stub ratio from the dex, plus `Java_*` / `JNI_OnLoad` / registration evidence from the `.so` |
| `scripts/protobuf_decode_raw.py` | **Schema-free protobuf decode**: hex / file / stdin to a JSON tree, every length-delimited field as a candidate set with ties labelled; `--reencode --check` for a byte-exact round trip |
| `scripts/vmp_diff_harness.py` | Differential hardening for Dex-VMP: build a labelled opcode-coverage fixture (**218 of 224 opcodes, measured**), derive a candidate private-opcode map from an original/hardened dex pair, verify it in a closed loop, render smali |
| `scripts/kernelsu_syscall_mask.py` | Generate a KernelSU/APatch syscall-masking scaffold: an installable userspace module plus KPM/LKM/eBPF kernel-side templates, each with its version gate and an explicit unverified label. **A userspace module cannot change a syscall return value** |
| `scripts/scan_leaks.py` | Scan a repository for target identity before it is published: bundle ids in manifest/`pm`/`ps` contexts, serial-shaped tokens, PATs, inline appkey assignments, literal endpoints, host user paths. Built-in do-not-anonymize exemptions, context-bearing findings, `--show-exempt` prints why a hit was suppressed, `--fail-on strong\|any`, exit 0/1/2 with a `RESULT=` token |
| `scripts/svc_scan.py` | Name the syscall behind an inline `svc` and the segment it sits in — which decides whether a libc-level hook can observe the call at all. `--context` shows neighbours, because a byte scan also matches data |
| `scripts/anti_detect_probe.js` | Observer-only probe (patches nothing): path/loader/thread/kill hooks with **caller module + offset**, an environment self-report (`TracerPid`, frida-named mappings), and live streaming so a sub-second target still yields evidence |
