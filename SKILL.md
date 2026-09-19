---
name: apk-reverse
description: Reverse engineer, debloat, de-ad, patch, or re-sign Android APKs, and analyze their runtime and server-side behavior. Use when a task involves an .apk/.aab/.dex/.so sample, smali or dex patching, Frida/objection runtime hooking, repacking and re-signing, removing ads or SDK trackers, probing a mobile app's HTTP API, or deciding whether a client-side patch is even capable of achieving the goal. Covers recon, anti-tamper, ad removal, membership/paywall limits, dex-level surgical patching, repack pitfalls, device and emulator setup, and a hard-won failure catalogue.
---

# APK Reverse Engineering & Patching

Goal of this skill: get to a **verified, installable, still-working artifact** fast, and avoid the whole class of mistakes that silently destroy an APK.

Three rules override everything else in this skill:

1. **Deliver it in the environment the request actually requires.** "It works" is not the goal; "it works under the stated constraint" is. A result obtained with root, or with live instrumentation, or with a host proxy, frequently does **not** satisfy a request for an installable artifact that works on a normal device — and it is easy to present that result as a finished one. Write the constraint down as a testable sentence in the first minutes and re-read it at every checkpoint. If you cannot meet it, say so and label any privileged workaround as a fallback, never as the deliverable. Full treatment: `references/long-task-discipline.md` §the most expensive drift.
2. **Never ship an unverified APK.** "It assembles" is not "it works". Install it, launch it, exercise the feature you changed, on a real device or a close emulator.
3. **Know which layer owns the behavior before you patch.** Ads, paywalls, and feature gates live in different places. Patching the wrong layer either does nothing or breaks the app. Classify first (see step 2 below), patch second.

## Start here: classify the target in seven questions

Answer these before touching a tool. Every one of them changes the whole plan.

1. **Is the app packed/hardened?** → `references/recon.md`
   Read the manifest's `application android:name`. If it is a third-party shell class rather than the app's own Application, you have a packer and must handle it first.
2. **Where does the behavior you want to change actually live?**
   - Ad SDK (Pangle/GDT/AnyThink/Kuaishou/Baidu/Sigmob…) → usually **client-side and removable** → `references/ad-removal.md`
   - Server-issued ad config / sponsored cards → **client renders server data** → `references/ad-removal.md` §server-driven
   - Membership / VIP / paid content → **usually server-authorized, client patch is cosmetic** → `references/membership-and-limits.md` (read this *before* spending hours)
   - Feature flag, UI gate, debug switch → usually client-side
   - Anything decided by an API response → server-side → `references/server-api.md`
3. **Is the app's own code in plain dex, or moved to native/Flutter/Unity?**
   Plain dex → you can patch. Flutter (`libflutter.so` + `libapp.so`) / Unity (`libil2cpp.so`) / pure native → different toolchain entirely. See `references/recon.md` §code-location and `references/framework-runtimes.md`.
      **Runtime check (cheap -- do it before committing to a layer):** hook the obvious Java classes for the UI you care about, then reproduce that UI. If those hooks fire, the behavior is Java-owned. If they fire **zero times** while the UI is plainly on screen, the behavior is drawn by the runtime or by native code, and a dex-only plan will stall. Do not keep hunting in dex after a zero-hit probe -- that is the most expensive wrong turn in this skill's history.
4. **What must the deliverable be able to do?** Write the answer as a testable sentence before
   planning anything, then re-read it at every checkpoint. This is the drift guard, and the drift it
   guards against is the most expensive one in this skill: a runtime-only result (a data edit, a live
   hook, a blocked hostname, a host proxy) can look like success while failing the actual requirement.
   The axes that decide it: **privilege** (unrooted?), **modification form** (a rebuilt, installable
   artifact, or is live instrumentation acceptable?), **ABI/device class**, **network** (must it work
   online?), **persistence** (survives restart / upgrade / fresh install?), **distribution** (must the
   shipped file be self-contained?). → `references/long-task-discipline.md` §the most expensive drift.
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

## The workflow, end to end

1. **Preflight, then Recon** — `scripts/preflight.py` before anything else if a device is involved (it takes seconds and prevents a whole class of false conclusions), then `references/recon.md`. Manifest, package name, version, ABI, dex count, packer, embedded SDKs, where the app's own code lives. Ten minutes here saves hours. **If it is packed, unpack before anything else** (`references/recon.md` §unpacking): you cannot patch code you cannot read, the encrypted payload lengths tell you which dumped dex is the original, and a memory dump must be de-duplicated by hash and structurally validated before any of it is trusted.
2. **Extract strings and endpoints** — build a picture of the app's API surface and SDK inventory from the dex string tables. No decompiler needed for this, and it is fast. Scripts: `scripts/dex_strings.py`.
3. **Trace to the owning class** — find the class that wraps the behavior (the app almost always wraps third-party SDKs in one helper). Reverse-lookup instructions: `references/dex-patching.md` §finding-the-call-site.
4. **Decide the patch layer** — client SDK call / client rendering / client data consumption / server contract. See the table in `references/ad-removal.md`.
5. **Patch surgically** — `references/dex-patching.md`. Prefer **dexlib2 method-level rewriting** over whole-tree smali round-trip. Whole-tree round-trip damages R8-optimized dex in ways that only show up at runtime.
6. **Repack and sign** — `references/repack-and-sign.md`. **Do not strip the whole `META-INF/`.** This single mistake destroys otherwise-correct builds.
7. **Verify on device** — `references/environment.md` + `references/verification.md`. Check: launches, the changed behavior actually changed, nothing unrelated broke, and **the app reaches its normal UI with no blocking dialog**. First prove the artifact actually changed on the device -- a package manager reporting success does not prove an interposed confirmation was accepted (P18). Capture continuously for the first ~20 seconds after launch, **and look at the captures** — sampling gaps are how a blocking modal goes unseen (P20), and a burst of images that were never inspected is not evidence. If the accessibility tree is empty, the image is the primary evidence rather than a fallback.
8. **Log what you learned** — if a failure cost you more than thirty minutes, add it to `references/pitfalls.md`. That file is the most valuable artifact in this skill.

## Non-negotiable constraints

- **Read-only inputs.** Keep the original APK/dex untouched; work on copies. Always keep a known-good baseline to diff against.
- **One variable at a time.** If you change two things and it breaks, you learn nothing. Build a control (same pipeline, zero patches) and compare.
- **Verify structure after every dex edit.** `scripts/dex_classdiff.py` must report zero differences in class set and access flags for classes you did not intend to change.
- **Do not patch a method that is widely shared.** Before patching any helper, count its callers (`scripts/find_refs.py`). A `Long.valueOf` wrapper with 30 callers is not an ad-specific hook.
- **Do not make an API fail to suppress a UI element.** A 404/400 on an endpoint that other features depend on takes the whole screen down with it. Suppress at the data-consumption or render layer instead.
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
| `references/packers.md` | The app is packed/hardened, or an edit makes it die before your code runs. Also load before discarding any route as "blocked by the shell" |
| `references/framework-runtimes.md` | The UI is not native (Flutter / React Native / Unity / Cordova), or Java-layer hooks fire zero times while the UI clearly works |
| `references/dart-aot.md` | The logic lives in a Dart AOT snapshot (`libapp.so`): pinning the Dart version, building a matching decompiler, the object pool and reference indexing, register/boolean conventions, locating and patching Dart code |
| `references/native-and-so.md` | Patching in a `.so`, needing code to run before the app's own code, hand-built native payloads that crash inside the linker, or **deciding which library/ABI is actually loaded and executing** |
| `references/ad-removal.md` | Task involves ads, trackers, sponsored cards, splash/interstitial/reward |
| `references/membership-and-limits.md` | Task involves VIP, subscription, paid content, unlock, "fully cracked" |
| `references/server-api.md` | The behavior is decided by a response, or you need to know if a patch can even matter |
| `references/dex-patching.md` | Any actual editing of dex/smali, choosing a patch layer, choosing a tool |
| `references/repack-and-sign.md` | Rebuilding, signing, installing, or a repacked app misbehaves |
| `references/runtime-data.md` | Local state matters: DataStore, SharedPreferences, SQLite, protobuf caches, tokens — **or your data edit keeps being reverted, or a stored value looks encrypted** |
| `references/dynamic-frida.md` | Frida setup, hooking strategy, tracing caller chains, finding the real call site |
| `references/environment.md` | Device/emulator setup, root, ADB, networking, offline devices, emulator console control and recovery, **the preflight check to run before every experiment block** |
| `references/verification.md` | Defining what "done" means; building the evidence chain |
| `references/tls-and-cert.md` | One feature fails at runtime (login, registration, payment, an API-backed screen) while the rest of the app works |
| `references/third-party-builds.md` | The input is a "cracked"/"modded" build you did not produce — audit it before trusting it |
| `references/long-task-discipline.md` | The task will run long, or you are resuming one. Live record, conclusion grading, drift checkpoints, **deliverable-form drift (rooted-only vs shippable)**, bound-your-waits, handover |
| `references/pitfalls.md` | Always worth a skim before building. This is the failure catalogue. |

## Script index

All scripts are parameterized and path-agnostic; pass paths explicitly. Run `--help` or read the header of each.

| Script | Purpose |
|---|---|
| `scripts/smtool.py` | baksmali/smali wrapper with a bundled classpath (assemble/disassemble dex) |
| `scripts/patch_smali.py` | Method-body replacement in a smali tree, matched by signature |
| `scripts/dex_strpatch.py` | Byte-level string constant patch with **string_ids ordering guard** |
| `scripts/dex_classdiff.py` | Compare two dex class tables (set + access flags) to prove a patch was surgical |
| `scripts/dex_strings.py` | Dump/extract strings and endpoints from dex without a decompiler |
| `scripts/dart_pprefs.py` | Build/query the object-pool offset -> code-site index for a Dart AOT snapshot (arithmetic decode; seconds, not minutes) |
| `scripts/dart_pool_strings.py` | Recover string literals from a Dart AOT snapshot: framed entries, the one-byte vs UTF-16 split, file offsets, and a run-length noise filter |
| `scripts/dart_disasm.py` | Annotated windowed disassembly of Dart AOT code (pool + boolean annotations) plus a B/BL caller index |
| `scripts/find_refs.py` | Count and list callers of a method/field (blast-radius check) |
| `scripts/repack.py` | Rebuild APK with replaced dex, strip only signatures, sign |
| `scripts/dexpatch/` | dexlib2 method-level surgical rewriter (the preferred patch tool) + build notes |
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
| `scripts/blob_decode.py` | Decode an opaque stored value by searching the parameter space (base64/base64url/hex × rotation × deflate/zlib/gzip) instead of guessing, then re-encode an edited payload with the same parameters. |
| `scripts/snap.py` | Bounded burst screenshot + control-tree capture, with a stall detector and an explicit verdict on whether the accessibility tree is usable at all. Use it so you *look* at the screen instead of driving blind. |
