# Repack and sign

Rebuilding is the step where otherwise-correct patches die. Two mistakes account for nearly all of it: **stripping `META-INF/`** and **recompressing entries that must stay stored**.

## The rules

**1. Strip only signature artifacts, never the whole directory.**

`META-INF/` contains ServiceLoader registrations the app needs at runtime. Details and the exact failure in `references/pitfalls.md` P1.

```python
SIG_EXT = ('.SF', '.RSA', '.DSA', '.EC')
def is_signature_entry(name):
    if not name.upper().startswith('META-INF/'):
        return False
    rest = name[len('META-INF/'):]
    if '/' in rest:                 # keep services/, androidx/, native-image/ ...
        return False
    up = rest.upper()
    return up == 'MANIFEST.MF' or up.endswith(SIG_EXT)
```

**2. `AndroidManifest.xml` and `resources.arsc` must stay uncompressed (STORED).**

Recompressing them produces builds that fail to install or misbehave.

**3. Keep the APK's zip entry metadata.** Preserve `compress_type`, `external_attr`, `date_time` for entries you copy through.

**4. Changing any dex changes nothing about resources.** If you only edited dex, do not touch `res/`, `assets/`, or `lib/`.

**4a. A full `apktool b` rebuild rewrites resource paths even when you edited none.** Decoding with
`apktool d` (without `-s`) and rebuilding re-encodes resources, and obfuscated short names are
expanded back to readable ones — an entry originally shipped as `res/-B.png` comes back as
`res/drawable-hdpi/<real-name>.png`. Expect an entry-level diff against the original to show on the
order of a thousand "removed + added" pairs that are **pure renames**, not content changes.

This is expected and usually harmless, but two consequences matter:

- **Never read that diff as "I broke something".** Compare by identity (rename-aware, or by content
  hash grouped by size) before drawing a conclusion. A toy diff that reports 1100 changes when you
  edited one method is a **tool** artifact and will send you hunting a bug that does not exist.
- **It changes the byte layout of the whole archive.** On a target that fingerprints its own file
  against a stored hash, or whose protection binds offsets into a container, a full rebuild is a much
  larger change surface than a dex-only swap. If your only edit is dex, prefer replacing the
  `classes*.dex` entries inside the original zip (`compress_type` preserved) over a full rebuild.
  Keep that dex-only path as a fallback for exactly this reason.

If you must avoid resource churn entirely, decode with `-s` (do not decode resources) and only
rebuild what you changed.

**5. Signing creates new `MANIFEST.MF`/`*.SF`/`*.RSA`.** That is expected — the check is that **no signature artifact from the ORIGINAL** survives, and **no non-signature entry was lost**.

## Repacking an unpacked (de-shelled) app

When the sample was packed, the dex you are about to patch came out of a memory dump while the APK still carries the shell. Build a **de-shelled base APK** first, then treat it as an ordinary APK for the rest of this document.

1. **Assemble the base.** Start from the original APK: replace `classes*.dex` with the dumped real dexes, and delete the shell library under `lib/<abi>/` plus the encrypted `assets/` payloads. Strip **only** signature artifacts — `META-INF/*.SF|*.RSA|*.DSA|*.EC` and the top-level `MANIFEST.MF`. Never delete the whole `META-INF/` (`references/pitfalls.md` P1).
2. **Decode with `apktool`.** `apktool d base.apk` gives the smali tree and a **readable text manifest**.
3. **Fix the manifest.** Point `application android:name` at the app's real Application class and **remove** `android:appComponentFactory`. Grep the decoded tree for leftover shell class references before building.
4. **Patch, then rebuild.** `apktool b` → `zipalign -p -f 4` → `apksigner` (v1+v2+v3) → install and verify against the checklist at the end of this file.

Why `apktool` rather than editing binary AXML in place: changing `android:name` in binary AXML means hand-editing the string pool and the attribute/chunk sizes around it, and a mis-sized chunk produces an APK that installs but throws far from the edit, typically in component lookup at startup. The text round-trip moves the risk to "did the rebuild preserve everything else", which item 5 of the checklist verifies directly.

## Pipeline

`scripts/repack.py` implements all of the above. Conceptually:

```
open original (zip)
  for each entry:
    skip entries that are signature artifacts (per rule 1)
    skip entries being replaced
    copy through, preserving compression + attributes
  write replacement entries
close
sign (v1 + v2 + v3)
verify
```

Usage:

```bash
python scripts/repack.py --apk original.apk --dexdir extracted_dex_dir --out out.apk
# or replace specific dex files:
python scripts/repack.py --apk original.apk --dexdir extracted_dex_dir \
  --dex "classes7.dex=patched/classes7.dex" \
  --dex "classes8.dex=patched/classes8.dex" \
  --out out.apk
```

`--dexdir` supplies the untouched dex files; `--dex name=path` overrides specific ones.

## Signing

Two viable routes.

**Route A — `uber-apk-signer` (handy, wraps zipalign + apksigner):**
```bash
java -jar uber-apk-signer.jar --apks in.apk --ks ks.jks \
  --ksAlias <alias> --ksPass <pass> --ksKeyPass <pass> -o out_dir
```
Known quirk: `-o` and `--overwrite` are mutually exclusive; passing both errors out. Also, it **silently skips already-signed APKs** (`0 processed`) — so de-sign first.

**Route B — `zipalign` + `apksigner` directly (most explicit):**
```bash
zipalign -p -f 4 unsigned.apk aligned.apk
apksigner sign --ks ks.jks --ks-pass pass:<pass> --key-pass pass:<pass> \
  --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true \
  --out signed.apk aligned.apk
apksigner verify --print-certs --verbose \
  --min-sdk-version 21 --max-sdk-version 34 signed.apk
```

Enable **v1 + v2 + v3**. v1 is needed for older Android; v2/v3 for modern verification.

Generate a keystore once:
```bash
keytool -genkeypair -v -keystore ks.jks -alias <alias> \
  -keyalg RSA -keysize 2048 -validity 36500 \
  -storepass <pass> -keypass <pass> \
  -dname "CN=<name>, OU=dev, O=dev, L=NA, ST=NA, C=NA"
```

## `apksigner verify` picks schemes from the APK's own minSdk

`apksigner verify` decides which signature schemes to check from the APK's own `minSdkVersion`. With `minSdk >= 24` it prints v1/v2 as `false` **by design**, even though `META-INF/*.SF` is present and the signature is valid. That output is indistinguishable from "signing did not apply" and sends you into a re-signing loop over a file that was never wrong.

Always pass the explicit range (Route B above) and read the scheme list from that run only. Never judge a build from a default-argument `apksigner verify`.

## Installing over an existing app

| Situation | Command |
|---|---|
| Same signing key as installed version | `pm install -r` — keeps app data (login state, caches) |
| Different signing key | `pm uninstall` first, then install. **App data is lost.** |
| OEM installer refuses (`INSTALL_FAILED_*`, vendor restrictions) | push the APK and install via root: `su -c 'pm install -r -t -d /data/local/tmp/app.apk'` |
| Downgrade needed | add `-d` |
| Test-only flag needed | add `-t` |

Useful detail: keeping the same keystore across builds lets you iterate with `-r` and **preserve a logged-in session**, which matters a lot when the feature you are testing needs auth.

## Post-install / post-upgrade hazards

- **Data directory uid mismatch.** After reinstall the app uid increments; a restored `/data/user/0/<pkg>` directory owned by the old uid is unreadable. Symptom: crash in a DB-init path (`Cannot open database`). Fix:
  ```
  su -c "chown -R <uid>:<uid> /data/user/0/<pkg>"
  su -c "restorecon -R /data/user/0/<pkg>"
  ```
  Get `<uid>` from `dumpsys package <pkg> | grep userId=`.
- **Restoring a data backup can itself cause this.** Prefer `cp -f` over an existing file (preserves owner) rather than deleting and re-extracting.

## Verify the build, not just the signature

Signature verification proves the file is well-formed. It does **not** prove the app works. Always:

1. `apksigner verify` passes with the explicit SDK range above — a default-args run can report v1/v2 `false` on a perfectly valid signature.
2. Install succeeds.
3. Launch succeeds; process stays alive.
4. `logcat` shows no `FATAL EXCEPTION` / `VerifyError` / `IncompatibleClassChangeError` / `uncaughtException`.
5. `META-INF/services/*` count matches the original.
6. Unchanged dex files are byte-identical to the original (compare hashes); in a de-shelled build, compare against the de-shelled base instead.

Build a **control** at least once: same pipeline, zero patches. If the control fails, your pipeline or environment is at fault, not your patch (`references/pitfalls.md` P9).
