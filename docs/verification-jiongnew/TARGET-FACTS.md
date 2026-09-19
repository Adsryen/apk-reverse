# Target facts — `jiongnew.apk`

Everything here is **observed** unless labelled otherwise. Method: read-only analysis of the APK
(`zipfile` + `androguard` 4.x + direct dex structure parsing) plus install/launch on two devices.
Nothing in this file comes from the handover document — where the handover and the measurements
disagree, the disagreement is recorded.

```
sha256   0C2B063E6D1A3BD05777611ABF2F1A64056E290E4F6728C1B12DC202747DC645
size     74,394,920 B (70.95 MiB)
entries  1,982   (zip testzip() == None)
```

## Manifest

Read with androguard's AXML parser. The handover document warned that hand-reading the binary AXML
gets the class-name prefix wrong; that warning held up — the parser is the reason these values are
trustworthy rather than the string scrape the handover was reduced to.

| Field | Value |
|---|---|
| `package` | `com.tingfeng.tool` |
| `application android:name` | **`app.video.guoguo.GApplication`** |
| `main activity` | `app.video.guoguo.SplashActivity` |
| `versionCode` / `versionName` | `84` / `1.5.8.0` |
| `minSdk` / `targetSdk` / `compileSdk` | `24` / `35` / `34` |
| `extractNativeLibs` | `true` |
| `usesCleartextTraffic` | `true` |
| `debuggable` | absent (release build) |
| `allowBackup` | `false` |
| application tag count | 1 |

Two questions the handover explicitly left open, now closed:

1. **`application android:name` is `app.video.guoguo.GApplication` — not a packer stub.**
   This is an ordinary app class. The handover's string scrape only surfaced a 穿山甲/pangle stub
   and could not rule out a shell; the parsed manifest rules it out. Combined with the absence of
   hardening-library names in the native list, this target has **no packer on the dex side**
   (observed) — though see `FINDINGS.md` for the *loader* signal that muddies this.
2. **The app does not run.** It aborts during startup on every attempt, on two different devices.
   Detail below; this is the single most consequential fact about the target.

Counts: 115 activities, 14 services, 2 receivers, 18 providers, 28 permissions.
All non-app components belong to bundled ad SDKs (kwad/ksad, qq.e, baidu mobads, beizi, sigmob,
meishu, bytedance openlive, windmill) plus Flutter plugins (`io.flutter.plugins.*`, `urllauncher`,
`imagepicker`) and Sentry (`io.sentry.android.core.*`).

## Dex

| File | Bytes | Compressed |
|---|---|---|
| `classes.dex` | 8,636,420 | 3,243,680 |
| `classes2.dex` | 7,910,800 | 2,918,337 |
| `classes3.dex` | 7,067,828 | 2,503,205 |
| `classes4.dex` | 4,032,596 | 1,509,375 |
| **total** | **27,647,644** | 10,174,597 |

Per-dex string-table sizes measured directly from the header (`string_ids_size` at `0x38`):
63,267 / 55,279 / 46,693 / 27,549.

**Cross-check against the handover:** the four dex sizes match the handover's table to the byte.
Also present at APK root and not mentioned in the handover: `DebugProbesKt.bin`,
`kotlin-tooling-metadata.json`, `androidsupportmultidexversion.txt` — a Kotlin app.

## Native libraries

36 libraries, 18 per ABI (`arm64-v8a` + `armeabi-v7a`), total 92,097,048 B uncompressed. The
handover's 36/18+18 count reproduces exactly.

Largest: `lib/armeabi-v7a/libapp.so` 13,730,388 · `lib/arm64-v8a/libapp.so` 12,256,160 ·
`libjingle_peerconnection_so.so` (WebRTC/声网) 11,377,944 / 6,536,952 · `libflutter.so`
10,814,192 / 7,614,304 · `libcore.so` 6,723,088 / 4,937,444 · `libloader.so` 6,221,896 / 4,540,264 ·
`libalivcffmpeg.so` 6,136,472 / 5,092,604 · `libsaasCorePlayer.so` 4,885,216 / 3,440,932 ·
`libsentry.so` 681,784 / 440,816 · `liblua-core.so` 384,472 / 265,796 ·
`libplt-base.so` 373,056 / 245,956 · `libsaasDownloader.so` 354,496 / 267,916 ·
`libdevInfo.so` 280,632 / 153,228 · `libti-monitor.so` 115,872 / 66,324 ·
`libsgcore.so` 92,360 / 112,500 · `libsentry-android.so` 16,832 / 12,080 ·
`libzeus_direct_dex.so` 14,160 / 9,756 · `libpangleflipped.so` 10,064 / 9,756 ·
`libdatastore_shared_counter.so` 7,112 / 4,416.

Packer-name scan (rglob over `libjiagu`, `libDexHelper`, `libnesec`, `libmobisec`, `libsecexe`,
`libshella`, `libsgmain`, `libtup`, `libprotectClass`, `libexec.so`, `libexecmain`, `StubApp`,
`libnativehelper`, `libapktool`): **zero hits**. Consistent with the handover.

`libloader.so` is the interesting one — 6.2 MB with the largest `.dynsym` in the set, and the
reason it was the right sample for `elf_plt.py`. See `TOOL-VERDICTS.md`.

## Flutter / Dart

Pinned from the engine banner, which is the authoritative source and does not depend on symbols:

```
lib/arm64-v8a/libflutter.so @ 0x1fe035:
  3.6.0 (stable) (Thu Dec 5 07:46:24 2024 -0800) on "android_arm64"
```

Snapshot identity, from blutter's own `extract_dart_info`:

```
Dart 3.6.0
Snapshot  f956f595844a2f845a55707faaaa51e4
Target    arm64 / android
Flags     product no-code_comments no-dwarf_stack_traces_mode
          dedup_instructions no-tsan no-msan compressed-pointers
```

So: **Dart 3.6.0, compiled with compressed pointers, in a PRODUCT build with code comments and
Dwarf stack traces stripped.** The `product` flag matters — it is the reason field and local names
are absent at the format level, not merely hard to recover.

`libapp.so` is stripped: `.dynsym` is 144 bytes. Its ELF header is `EM_AARCH64` (e_machine `0xB7`)
for the arm64 ABI and `EM_ARM` (`0x28`) for the v7a one.

No `assets/flutter_assets/version` file exists (21 entries under `flutter_assets/`), so the usual
cheap version probe fails here — the banner above is the reliable route.

**Discrepancy worth recording:** `aotopsy doctor` reports **Dart 3.6.2** for the same
`libapp.so`, while the engine banner and the snapshot hash both say 3.6.0. See `FINDINGS.md`.

## Assets

| Asset | Bytes | Note |
|---|---|---|
| `assets/1274036544` | 6,632,594 | 穿山甲/pangle plugin container (`ZEUS_PLUGIN_PANGLE` in manifest) |
| `assets/gdt_plugin/gdtadv2.jar` | 2,238,863 | 腾讯优量汇 plugin (contains dex) |
| `assets/bdxadsdk.jar` | 1,302,180 | 百度 ad SDK |
| `assets/flutter_assets/assets/jiong_white.zip` | 986,623 | theme resources |
| `assets/flutter_assets/assets/jiong_black.zip` | 986,413 | theme resources |
| `assets/flutter_assets/NOTICES.Z` | 123,708 | Flutter licence bundle |
| `assets/reward.json` | 16,404 | ← see below |
| `assets/feed.json` | 16,251 | ← |
| `assets/splash.json` | 10,843 | ← |
| `assets/intertitial.json` | 10,592 | ← note the spelling |
| `assets/banner.json` | 9,151 | ← |
| `assets/draw.json` | 4,644 | **not in the handover inventory** |
| `assets/fullscreen.json` | 4,201 | **not in the handover inventory** |
| `assets/ksad_idc.json` | 327 | Kuaishou IDC list |
| `assets/dexopt/baseline.prof`, `.profm` | 4,235 / 385 | Kotlin/Android baseline profiles |

Also `assets/flutter_assets/packages/luavm/lua/*.lua` (10 Lua files: dkjson, http, url, ftp, ltn12,
smtp, socket, tp, headers, mbox, mime) and `liblua-core.so` — a third logic surface beside dex and
Dart. Not pursued in this pass.

The handover listed 5 ad-config JSONs; the measurement finds **7**. The two additions
(`draw.json`, `fullscreen.json`) are the same shape as the other five.

**The ad-config JSONs are not ad configuration.** They are test fixtures bundled inside the
美数/meishu aggregation SDK, and their read path is dead code in this build. The load-bearing parts:

- Reader: `classes3.dex` → `Lcom/meishu/sdk/core/utils/TestToolUtil;->getTest{Splash,Banner,
  Intertitial,Fullscreen,Reward,Draw,Feed}Json(Landroid/content/Context;Z)Ljava/lang/String;`
  → `Context.getAssets()` + `const-string/jumbo "splash.json"`. Seven methods, seven filenames. (observed)
- The only callers are `TestToolUtil.getJsonByType` and `AdLoader.getTestData()`, and **neither has
  a single `invoke` referencing it anywhere in the four dex** (coverage: 175,829 method bodies with
  code; the 362 bodies that decoded uncleanly were rechecked by raw byte search for the target
  `method_idx` — zero hits). (observed)
- Dart cannot be the reader: `intertitial` (the distinctive misspelling) has **zero** hits in
  `libapp.so` in both UTF-8 and UTF-16LE, so the Dart side cannot even form the filename. The files
  also sit in `assets/` rather than `assets/flutter_assets/` and are absent from `AssetManifest.json`,
  so `rootBundle` structurally cannot reach them. (observed)
- Content self-identifies as fixture data: `reward.title="测试激励视频"`, `feed.title="测试"`,
  `splash.clk_area="测试测试测试"`, `appstore_id="1234567"`, monitor hosts contain `-demo`. (observed)
- **Runtime confirmation of the dead-path conclusion** (run independently by the lead after the
  static analysis): `getExternalCacheDir()/.adConfig/jsonConfig/` does not exist, and no
  `*adConfig*` / `*jsonConfig*` path exists anywhere under either the external or the private data
  directory. The only directory the app did create under `cache/` is `sentry/`. (observed)
- No on/off field exists in any of the seven files: matching
  `enable|show|switch|open|close|disable|isOpen|isPlay|visible|frequency|interval` yields
  **zero** candidates. (observed)

Consequence: deleting the seven JSONs is safe and pointless — no caller, so no dependency, so no
effect on ads. The handover's hypothesis that "the convergence point is probably the config
consumption layer" is **refuted** for this asset family. The real convergence point is a
two-layer aggregation boundary (Dart `windmill_ad_plugin` ↔ `com.windmill.windmill_ad_plugin`
MethodChannel at `WindmillAd.createAdInstance`, channel names
`com.windmill/{splash,reward,interstitial,banner,native}`; below that
`com.meishu.sdk.core.loader.AdLoader.loadAd` → `https://sdk.1rtb.net/sdk/req_ad` fanning out to
CSJ/GDT/KS/BAIDU/OPPO/HW/TopOn). (observed for the mechanism, inferred for its completeness)

## Launch behaviour — the app does not start

`observed`. This is the fact that constrains everything else.

Installed and launched on the Android 11/arm64 physical device:

```
adb -s SSBYPJKFNVEU6PGA install -r -t jiongnew.apk     -> Success (4.1 s)
   codePath  = /data/app/~~fDojk_Ku0C15jUkrmP36vA==/com.tingfeng.tool-gncxaby8OxxhG9E1TuF3aw==
   primaryCpuAbi = arm64-v8a, versionCode 84, targetSdk 35
adb -s SSBYPJKFNVEU6PGA shell am start -n com.tingfeng.tool/app.video.guoguo.SplashActivity
```

Timeline on the device (logcat):

```
04:41:59.217  Start proc 20512 for pre-top-activity {...SplashActivity}
04:41:59.280  E LoaderLog: 10026 / 101004
04:41:59.307  E Instrumentation: Uninitialized ActivityThread, likely app-created
               Instrumentation, disabling AppComponentFactory
04:41:59.765  I InputDispatcher: Focus entered window ... SplashActivity    <- window shown
04:42:00.297  F libc: FORTIFY: pthread_mutex_lock called on a destroyed mutex (0x7260f77b30)
04:42:00.301  F OpenGLRenderer: Failed to set damage region ... EGL_NOT_INITIALIZED
04:42:00.352  F libc: Fatal signal 6 (SIGABRT), code -1 (SI_QUEUE) in tid 20512
               (m.tingfeng.tool), pid 20512
04:42:00.409  E DEBUG: failed to open directory /proc/20512/fd: Permission denied
04:42:00.410  F crash_dump64: failed to attach to thread 20512, already traced by 0 ()
04:42:00.411  W tombstoned: crash socket received short read of length 0 (expected 12)
04:42:00.444  I Zygote: Process 20512 exited cleanly (0)
04:42:00.453  I ActivityManager: Process com.tingfeng.tool (pid 20512) has died: fg TOP
```

Survival time ≈ 1.1 s from window focus to abort, ~1.3 s from process start.

**Environmental control (single variable changed):** the same APK on the other attached device —
`emulator-5554`, x86_64, SDK 28, a different ROM and a different ABI — reproduces the identical
signature:

```
05:42:54.501  E LoaderLog: 10020 / 101003
05:42:55.547  F libc: FORTIFY: pthread_mutex_lock called on a destroyed mutex (0x7639156ff120)
05:42:55.855  I Zygote: Process 16507 exited cleanly (0)
```

Same loader line, same FORTIFY abort, ≈1.04 s vs ≈1.07 s. Two devices, two ABIs, two Android
versions, same death. This **rules out** target-specific-to-one-ROM behaviour and rules out a pure
root/Magisk detection as the sole cause. The crash is a property of the app, not of the device.

**The crash channel is owned by a third party.** Three independent signals say so:

1. `crash_dump64` cannot attach — `already traced by 0 ()`. Something else already holds the
   thread via ptrace.
2. No tombstone is written. `/data/tombstones/` newest file is `tombstone_23` from 03:54, while
   this crash happened at 04:42; `tombstoned` logs `crash socket received short read of length 0`.
3. `tombstoned` receives the request for a *different* pid than the one that died
   (`received crash request for pid 23771` while the dying pid was 23813), and `crash_dump64`
   can no longer find the threads (`failed to attach to thread ...: No such process`).

The mechanism is visible in the emulator log immediately before the abort: Sentry's NDK layer is
live and installing itself —

```
05:42:54.877  V libnb: enter native_bridge2_getTrampoline
               Java_io_sentry_ndk_NativeScope_nativeSetTrace, trampoline_addr 0x76391344a080
05:42:54.878  V libnb: ...Java_io_sentry_ndk_NativeScope_nativeAddBreadcrumb, trampoline_addr ...
```

Sentry's native crash handler replaces the signal handlers; the platform handler then cannot
attach and the ordinary evidence trail (tombstone, backtrace, `AndroidRuntime` fatal block) is
destroyed. `libsentry.so` / `libsentry-android.so` are in the APK and
`io.sentry.android.core.SentryInitProvider` is a declared provider. (observed)

**Root cause of the abort itself: not localized.** What is established is the abort site's *shape*
— a `pthread_mutex_lock` on an already-destroyed mutex, on the **main** thread (tid == pid), i.e. a
native lifecycle/teardown ordering bug reached from the startup path, not the fault of an
obfuscation trick or a deliberate anti-tamper abort. Attempts to get a symbolized stack were made
and failed for stated reasons:

- Platform route: impossible. `crash_dump` is pre-empted (above); no tombstone exists to read.
- `setenforce 0` to relax SELinux: rejected — `setenforce: Couldn't set enforcing status to '0':
  Invalid argument`. Permissive mode was not obtainable on this ROM.
- Frida spawn-gating (the documented workaround when platform crash handling is unavailable):
  the device carries a disguised frida-server (`/data/local/tmp/odm_service`, listening
  `127.0.0.1:27099`). `frida-ps -H 127.0.0.1:27099` enumerates processes, but `spawn` fails with
  `Failed to spawn: connection closed`, so the pre-signal-handler window cannot be opened through
  that server. **unverified** whether a plain frida-server would succeed where this one does not.

So the honest statement is: *the app aborts deterministically in native code during startup, on the
main thread, and the platform's ability to show us where has been taken away by a bundled crash
reporter.* The `LoaderLog` line and the app-created `Instrumentation` indicate non-standard startup
plumbing is also in play, but their contribution to the abort is **inferred, not established** —
see `FINDINGS.md` for why that distinction was kept rather than collapsed.

## What this target can and cannot exercise

Kept explicit, because the useful output of this pass is partly a list of what was *not* testable.

| Exercisable | Not exercisable |
|---|---|
| Flutter/Dart AOT analysis (Dart 3.6.0, object pool, call graph) | `native_crash.py`'s "artificially constructed crash" verdict — the crash here is a real internal fault; there is no decoy to detect |
| Multi-dex scale (27.6 MB over 4 files) | `so_constpatch.py`'s "redirect the checker library" scenario — there is **no integrity-check library** in this target |
| `elf_plt.py` at scale (`libloader.so`, 36,974 relocations) | Every hardening scenario in `packers.md` / `code-virtualization-and-custom-linkers.md` — no packer |
| `lib_map.py` against a live process | A **durable** live process at all — the 1.1 s window is the constraint |
| `dart_*` scripts on a real stripped `libapp.so` | Any repack/install verification loop — the unmodified app already fails to start, so there is no working baseline to regress against |
| Config-driven ad analysis (and its refutation) | — |
