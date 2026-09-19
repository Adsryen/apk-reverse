# Recon — build the picture before touching anything

Ten minutes here prevents hours of wrong work. Answer the five questions from `SKILL.md` with concrete evidence.

## 1. Identity

```bash
# Without a full decompiler (fast, works everywhere):
aapt dump badging app.apk | head -20
# or, from the extracted manifest:
#   package name, versionName, versionCode, sdkVersion, targetSdkVersion
```

Record: package name, version name/code, min/target SDK, all requested permissions, all declared components.

**Note:** some `aapt` builds choke on non-ASCII paths. Normalize sample paths to ASCII before running tooling.

## 2. Is it packed?

Read `AndroidManifest.xml` → `application android:name`.

| What you see | Meaning |
|---|---|
| The app's own class (e.g. `com.example.app.App`) | **No packer.** Dex is directly editable. |
| A vendor class (`com.stub.StubApp`, `com.secneo...`, `com.tencent.StubShell`, `s.h.e.l.l.*`, `com.nagain.*`, …) | **Packed.** Unpack first. |
| `android:appComponentFactory` overridden to a vendor class | **Packed or wrapped** — often a runtime shell that loads a second APK. |
| `assets/` contains a second `.apk`, `.jar`, or an encrypted blob | Wrapped/loader build. |

Signs in `lib/`: lone `.so` files with names unlike normal libraries (a custom-named shell lib), plus unusual `assets/` artifacts.

**Loaded-shell check (highest fidelity):** if the app runs and its own classes are reachable, it is unpacked *at runtime* regardless of what the manifest says. If the app's own code is not among the dex classes, it is packed on disk.

## 3. Where does the app's own code live?

| Indicator | Code location |
|---|---|
| Plain `classes*.dex`, app classes visible in them | **Dex** — patchable with dexlib2/smali |
| `libflutter.so` + `libapp.so` | **Flutter (Dart AOT)** — dex contains only a thin shell |
| `libil2cpp.so` + `assets/bin/Data/` | **Unity (IL2CPP)** — native |
| `libmono*.so` + `assets/bin/Data/Managed/` | **Unity (Mono)** — managed DLLs under `assets/` |
| `libreactnativejni.so` + `assets/index.android.bundle` | **React Native** — JS bundle under `assets/` |
| `libhermes.so` | **Hermes bytecode** |
| Almost everything in `.so` | **Native** — different toolchain entirely |

For a **Kotlin/Java app**, note the module layout: app code often lives in a small subset of dex files while large SDKs occupy the rest. Finding which dex holds the app's package is a huge time-saver:

```bash
python scripts/dex_strings.py <dex_dir> --find 'Lcom/example/app/' --per-file
```

Consequence for editing: you usually only need to replace **one or two dex files**, which keeps the repack minimal.

## 4. SDK and library inventory

Extract strings across all dex and group by vendor markers. This reveals ads, analytics, crash reporting, attribution, and any anti-tamper SDK, in one pass.

```bash
python scripts/dex_strings.py <dex_dir> --urls
python scripts/dex_strings.py <dex_dir> --find 'anythink|openadsdk|com.qq.e|umeng|bugly|crashsdk'
```

What to look for:

- **Ad networks / aggregators**: `openadsdk` `TTAdSdk` `Pangle` `com.qq.e` `GDTAd` `anythink` `ATSDK` `ksad` `mobads` `sigmob` `bdxadsdk`
- **Analytics / crash / attribution**: `umeng` `bugly` `crashsdk` `appsflyer` `adjust` `UMCrash`
- **Identity / device id**: `oaid` `msa` `SupplementaryDID` `freemme`
- **Anti-tamper / root / hook detection**: `libsgcore` `libInno` `libqmcheat`, strings like `frida` `xposed` `magisk` `substrate`, `/system/xbin/su`
- **Media stack**: `libmpv` `libavcodec` `libplayer` `libgdx`

Important distinction: **a vendor marker in the string table does not mean the app uses that feature**. Presence of `xposed`/`frida` strings is often just an SDK's own detection list. Decide based on *behavior*, not on strings (`references/verification.md`).

## 5. Signature and tamper checks

Search the app's **own** packages only (ignore third-party SDKs) for:

- `getPackageInfo`, `PackageInfo`, `signatures`, `GET_SIGNATURES`, `Signature` → app-side signature verification
- hardcoded SHA-1/SHA-256 hex constants, base64 license blobs → certificate pinning to the original signer
- `checkSignature`, `verifySignature`, `signCheck` → a named check

**Beware false positives.** `SignatureCheck` and `verifySignature` exist inside `okhttp3` (`SuppressSignatureCheck`, `BasicCertificateChainCleaner.verifySignature`) — TLS plumbing, not app tamper checks. Likewise a native `lib*.so` named like a security library may be an ad SDK's payload decryptor, not a shell.

Confirm by checking whether **app code** references it. If the only callers are library-internal, it is not your problem.

## 6. API surface

```bash
python scripts/dex_strings.py <dex_dir> --urls
```

Collect: base URLs, DoH/DoT lookups, path constants, CDN hosts, custom headers.

Treat **unique** strings as navigation aids — they can often be searched byte-wise in the dex to find the owning class (see `references/dex-patching.md` §finding-the-call-site).

Two patterns worth recognizing early:
- **Dynamic gateway**: the real API host is fetched at runtime (e.g. via a DNS TXT record over DoH). The hardcoded host in dex may be only a fallback. This affects server-side analysis, not patching.
- **Minimal headers / no request signing**: if auth is just `Authorization: Bearer` plus a static app-name header, then a repackaged client is not distinguishable to the server by request signature — which matters for `references/server-api.md`.

## Recon output

Write a short profile before patching. Minimum:

```
package / version / ABI
packed? (evidence)
code location (dex / flutter / native)
app code in which dex files
ad SDK(s) and the app's wrapper class
analytics/crash SDKs
anti-tamper: present? where? app-side or library-internal?
API base + notable endpoints
device plan (rooted real device / emulator / static only)
```
