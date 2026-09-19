---
name: apk-reverse
description: Reverse engineer, debloat, de-ad, patch, or re-sign Android APKs, and analyze their runtime and server-side behavior. Use when a task involves an .apk/.aab/.dex/.so sample, smali or dex patching, Frida/objection runtime hooking, repacking and re-signing, removing ads or SDK trackers, probing a mobile app's HTTP API, or deciding whether a client-side patch is even capable of achieving the goal. Covers recon, anti-tamper, ad removal, membership/paywall limits, dex-level surgical patching, repack pitfalls, device and emulator setup, and a hard-won failure catalogue.
---

# APK Reverse Engineering & Patching

Goal of this skill: get to a **verified, installable, still-working artifact** fast, and avoid the whole class of mistakes that silently destroy an APK.

Two rules override everything else in this skill:

1. **Never ship an unverified APK.** "It assembles" is not "it works". Install it, launch it, exercise the feature you changed, on a real device or a close emulator.
2. **Know which layer owns the behavior before you patch.** Ads, paywalls, and feature gates live in different places. Patching the wrong layer either does nothing or breaks the app. Classify first (see step 2 below), patch second.

## Start here: classify the target in five questions

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
   Plain dex → you can patch. Flutter (`libflutter.so` + `libapp.so`) / Unity (`libil2cpp.so`) / pure native → different toolchain entirely. See `references/recon.md` §code-location.
4. **Does the app verify its own signature, or does the server?**
   App-side → you must bypass it. Server-side → re-signing silently breaks the app later. See `references/repack-and-sign.md` and `references/server-api.md`.
5. **What is your device situation?** → `references/environment.md`
   Rooted real device (best), emulator with root, or no device (static only). Also: this determines whether Frida is usable.

## The workflow, end to end

1. **Recon** — `references/recon.md`. Manifest, package name, version, ABI, dex count, packer, embedded SDKs, where the app's own code lives. Ten minutes here saves hours.
2. **Extract strings and endpoints** — build a picture of the app's API surface and SDK inventory from the dex string tables. No decompiler needed for this, and it is fast. Scripts: `scripts/dex_strings.py`.
3. **Trace to the owning class** — find the class that wraps the behavior (the app almost always wraps third-party SDKs in one helper). Reverse-lookup instructions: `references/dex-patching.md` §finding-the-call-site.
4. **Decide the patch layer** — client SDK call / client rendering / client data consumption / server contract. See the table in `references/ad-removal.md`.
5. **Patch surgically** — `references/dex-patching.md`. Prefer **dexlib2 method-level rewriting** over whole-tree smali round-trip. Whole-tree round-trip damages R8-optimized dex in ways that only show up at runtime.
6. **Repack and sign** — `references/repack-and-sign.md`. **Do not strip the whole `META-INF/`.** This single mistake destroys otherwise-correct builds.
7. **Verify on device** — `references/environment.md` + `references/verification.md`. Check: launches, no logcat exception, the changed behavior actually changed, and nothing unrelated broke.
8. **Log what you learned** — if a failure cost you more than thirty minutes, add it to `references/pitfalls.md`. That file is the most valuable artifact in this skill.

## Non-negotiable constraints

- **Read-only inputs.** Keep the original APK/dex untouched; work on copies. Always keep a known-good baseline to diff against.
- **One variable at a time.** If you change two things and it breaks, you learn nothing. Build a control (same pipeline, zero patches) and compare.
- **Verify structure after every dex edit.** `scripts/dex_classdiff.py` must report zero differences in class set and access flags for classes you did not intend to change.
- **Do not patch a method that is widely shared.** Before patching any helper, count its callers (`scripts/find_refs.py`). A `Long.valueOf` wrapper with 30 callers is not an ad-specific hook.
- **Do not make an API fail to suppress a UI element.** A 404/400 on an endpoint that other features depend on takes the whole screen down with it. Suppress at the data-consumption or render layer instead.
- **Every claim needs evidence.** "Probably", "should be", "in theory" are not findings. Either you observed it, or you label it unverified.

## Reference index

Load only what the current step needs.

| File | Load when |
|---|---|
| `references/recon.md` | Starting any new sample; identifying packer, SDKs, code location, ABI |
| `references/ad-removal.md` | Task involves ads, trackers, sponsored cards, splash/interstitial/reward |
| `references/membership-and-limits.md` | Task involves VIP, subscription, paid content, unlock, "fully cracked" |
| `references/server-api.md` | The behavior is decided by a response, or you need to know if a patch can even matter |
| `references/dex-patching.md` | Any actual editing of dex/smali, choosing a patch layer, choosing a tool |
| `references/repack-and-sign.md` | Rebuilding, signing, installing, or a repacked app misbehaves |
| `references/runtime-data.md` | Local state matters: DataStore, SharedPreferences, SQLite, protobuf caches, tokens |
| `references/dynamic-frida.md` | Frida setup, hooking strategy, tracing caller chains, finding the real call site |
| `references/environment.md` | Device/emulator setup, root, ADB, networking, offline devices |
| `references/verification.md` | Defining what "done" means; building the evidence chain |
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
| `scripts/find_refs.py` | Count and list callers of a method/field (blast-radius check) |
| `scripts/repack.py` | Rebuild APK with replaced dex, strip only signatures, sign |
| `scripts/dexpatch/` | dexlib2 method-level surgical rewriter (the preferred patch tool) + build notes |
| `scripts/devsh.py` | Quoting-safe ADB shell helper for rooted devices |
| `scripts/usb_net_proxy.py` | Give an offline device network over USB (adb reverse + local proxy) |
| `scripts/datastore_inject.py` | Encode/inject AndroidX DataStore preferences (protobuf) safely |
| `scripts/probe_api.py` | Probe an app's HTTP API with correct headers, report status/shape |
| `scripts/install_test.py` | Install a build and run a launch/health check with logcat signal extraction |
