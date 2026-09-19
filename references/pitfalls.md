# Pitfalls — the failure catalogue

Every entry here cost real time and produced a **silently broken artifact**. Skim this before building. When you lose more than thirty minutes to something new, add it here.

Each entry: **symptom → root cause → why it is hard to see → what to do instead.**

---

## P1. Stripping the whole `META-INF/` breaks the app at startup

**Symptom**
```
java.lang.IllegalStateException: Module with the Main dispatcher is missing.
Add dependency providing the Main dispatcher, e.g. 'kotlinx-coroutines-android'
```
App dies immediately on launch. Sometimes a different `ClassNotFoundException` for an unrelated library class.

**Root cause**
`META-INF/` is not only signatures. It holds **ServiceLoader registrations** that Android reads at runtime. Deleting the directory to prepare for re-signing deletes them too.

Real examples found in one APK:
```
META-INF/services/kotlinx.coroutines.internal.MainDispatcherFactory  -> kc
META-INF/services/io.ktor.client.engine.HttpClientEngineContainer    -> OkHttpEngineContainer
META-INF/services/io.ktor.serialization.kotlinx.KotlinxSerializationExtensionProvider
META-INF/services/kotlinx.coroutines.CoroutineExceptionHandler       -> wc
META-INF/services/com.arialyy.aria.core.inf.IUtil
META-INF/services/com.arialyy.aria.core.listener.IEventListener
```

**Why it is hard to see**
The error message names Kotlin coroutines, not your repack. You will spend an hour blaming the dex.

**Do instead**
Strip **only** signature artifacts, and only at the top level of `META-INF/`:

```python
SIG = ('MANIFEST.MF',)
SIG_EXT = ('.SF', '.RSA', '.DSA', '.EC')

def is_signature_entry(name):
    if not name.upper().startswith('META-INF/'):
        return False
    rest = name[len('META-INF/'):]
    if '/' in rest:          # services/, androidx/, native-image/ ... keep
        return False
    up = rest.upper()
    return up in SIG or up.endswith(SIG_EXT)
```

`scripts/repack.py` already does this.

---

## P2. Byte-level string patching without an ordering check rejects the whole dex

**Symptom**
App cannot load any class:
```
ClassNotFoundException: Didn't find class "<App.Application>" on path: DexPathList[[zip file ".../base.apk"]]
```
`Application` construction fails, process never starts.

**Root cause**
Dex requires the `string_ids` table to be **sorted**. Replacing a string with an equal-length string keeps all offsets valid, but changes where that entry *should* sit in the sorted order. If the new value crosses its neighbours, the loader rejects the entire dex.

Concrete case: `/app/adverts` sat between `/api/v1/crashtrack/upload?chk=` and `/app/configs/`. Replacing it with `/app/noadver` put `n` after `c` → out of order → whole dex rejected. Replacing with `/app/blocked` (`b < c`) was accepted.

**Why it is hard to see**
`checksum` (adler32) and `signature` (SHA-1) recompute perfectly, so every integrity check passes. `baksmali` parses the file fine. Only the runtime loader cares about ordering.

**Do instead**
Always run the ordering guard: `scripts/dex_strpatch.py` looks up the target's neighbours in `string_ids` and refuses any replacement outside `(prev, next)`. Pick a candidate that stays inside the interval.

---

## P3. Whole-tree smali round-trip damages R8-optimized dex

**Symptom**
App installs, then dies with:
```
java.lang.IncompatibleClassChangeError: Found interface io.ktor.client.engine.HttpClientEngine,
but class was expected
    at io.ktor.client.engine.HttpClientEngine.access$checkExtensions(...)
```
(or `VerifyError`, or a class-load failure in an unrelated library)

**Root cause**
`baksmali` → `smali` rebuild does not faithfully reproduce R8's synthetic access bridges / optimization artifacts. The class is still declared as an interface, but the bridge method that ART expects to find as a class member is gone.

**Why it is hard to see**
A structural diff of `class_def` entries shows **nothing**: same class count, zero `ACC_INTERFACE` mismatches, zero access-flag differences. The damage is at the code-item / reference level, invisible to table-level checks. It only appears at runtime.

**Do instead**
Use **method-level surgical rewriting** with dexlib2 — read the dex, replace only the target method's implementation, write it back. See `scripts/dexpatch/`. Never rebuild the whole tree for a one-method change.

---

## P4. Rewriting the same dex twice makes ART refuse to start the process

**Symptom**
```
E/ActivityManager: Failure starting process <pkg>
I/ActivityManager: Force stopping <pkg> appid=... user=0: start failure
```
No Java exception anywhere. `logcat` shows a splash screen appearing then vanishing. `baksmali` still parses the dex, and `smali` re-assembles it fine.

**Root cause**
Serializing a dex a second time loses metadata that the first serialization preserved. Chaining two patch tools over the same file (`patch A → patch B → repack`) triggers this.

**Why it is hard to see**
Both intermediate files look valid and round-trip cleanly. Only ART rejects the final one.

**Do instead**
**Combine all edits to one dex into a single read/write pass.** One program, one `loadDexFile`, apply every change, one `writeDexFile`.

---

## P5. Killing an endpoint to hide a UI element takes the whole screen down

**Symptom**
Home screen becomes the app's generic error state ("something went wrong / retry"), or a blank screen, after redirecting or 404-ing an ad endpoint.

**Root cause**
The ad request is a **child request** of the screen's main data load. When it throws, the parent load fails with it.

Concrete case: `/app/adverts` was redirected to a nonexistent path. That endpoint is requested from inside `MainScreenStore.loadData` as a sub-request, so the home screen's entire data load failed.

**Why it is hard to see**
Removing ads *sounds* like it should only remove ads. The coupling is invisible until runtime.

**Do instead**
Suppress at the **data-consumption** or **render** layer, not at the transport layer. Let the request succeed and discard/ignore the result. Never make a shared endpoint fail.

---

## P6. Patching a shared helper breaks unrelated features

**Symptom**
Images stop loading, video playback fails, or downloads break — after patching something that looked ad-specific.

**Root causes, two variants**
- Patching a generic utility: a `Long.valueOf`-style boxing helper had **30+ callers** across player, download, paging and history sync. Patching it would have broken all of them.
- Patching a "card" renderer you assumed was ad-only: the composable's signature was `(itemModel, ColorScheme, Modifier, onClick, ContentScale, Shape, Composer, II)` — a **generic image card** shared by normal content. Making it `return-void` killed all cover art and the player pipeline.

**Why it is hard to see**
The class name and the model type it consumes suggest it is ad-specific. It is not.

**Do instead**
Before patching any method, **count its callers** (`scripts/find_refs.py`). If it has many, or if its parameters look content-generic (image/graphics/`Modifier`/`ContentScale` parameters), it is not specific to your target. Also check whether the parameter model type is shared with non-ad content.

---

## P7. Client-side VIP forgery breaks the app instead of unlocking it

**Symptom**
Blank screen; or logged in, but playback fails.

**Root cause**
The authoritative gate is server-side. Real access is granted by an API response. Forcing the client's local `isVip()` to `true` makes the client believe it has rights the server will not honor, so it walks a path that assumes data it never receives.

Concrete case: `/v2/sections/{id}/play-url` returns **401** with no token and **401** with a forged `Bearer` token; metadata endpoints returned 200 but deliberately omitted any play URL. Patching local VIP state produced a white screen.

**Do instead**
Determine server authority **before** patching. See `references/membership-and-limits.md`. If the gate is server-side, the honest deliverable is "not achievable client-side", plus any genuinely client-side wins (unlocking UI, removing ads).

---

## P8. DataStore / protobuf hand-editing fails silently

**Symptom**
App dies with a bare `uncaughtException` and **no stack trace** (a crash-reporter SDK swallowed it). Or the app launches but ignores your injected value.

**Root cause (encoding)**
AndroidX `Preferences` maps are protobuf `map<string, Value>` fields. An entry needs **two** levels of tag:

```
outer : 0A <len(entry)>
inner : 0A <len(key)> <key>  12 <len(value)> <value>
```

Writing only the inner part produces a file `DataStore` cannot deserialize.

**Root cause (lifecycle)**
`DataStore` caches in memory and writes back. Editing the file while the app runs is either ignored or overwritten. Also the file is owned by the app's uid — a file written as root with the wrong owner is unreadable to the app.

**Do instead**
- Encode with `scripts/datastore_inject.py` (implements both tag levels).
- `force-stop` the app first, write, then start.
- Preserve ownership: write via `su`, then `chown` to the app uid (or `cp -f` over the existing file, which keeps its owner).
- If a value must survive a **fresh install**, code-level patching is the only way — runtime data is not part of the APK.

---

## P9. Blaming the patch when the device or environment is broken

**Symptom**
Every build fails, including a completely unmodified original.

**Root causes seen in practice**
- Device in a bad state: `Failure starting process` for *all* builds (including stock). **A device reboot fixed it.**
- Offline device: app shows a generic network error, easily mistaken for a server rejection or signature problem.
- App data directory uid mismatch after reinstall: crashes in a database-init path (`Cannot open database ... Directory ... doesn't exist`). Fix with `chown -R <uid>:<uid> /data/user/0/<pkg>`.
- Emulator that cannot run the app at all (different ABI, missing platform pieces). A working emulator is not evidence about a real device.

**Do instead**
**Always run a control.** Install and launch the **unmodified original** under the exact same conditions. If the original fails too, stop debugging your patch.

---

## P10. Trusting static decompilation over runtime behavior

**Symptom**
You patch what the decompiler showed, and nothing changes; or the app crashes in a path you did not know existed.

**Root cause**
Decompiler output is a guess reconstructed from bytecode. Interface/class relationships, inlined code, and obfuscated bridges are regularly misrepresented. Also, dead code and shadowed branches look identical to live ones.

**Do instead**
Rank evidence: **live runtime behavior > captured network traffic > served assets > current process/config state > persisted state > generated artifacts > source > comments and dead code.** Use source to *explain* runtime, not to *override* it.

---

## P11. Assuming a repackaged APK ships runtime data

**Symptom**
A fix verified on the target device does not work after a fresh install.

**Root cause**
Some fixes are **runtime data**, not code: a DataStore value, a preferences file, a cached token. Those live in `/data/data/<pkg>/` and are gone on a clean install.

**Do instead**
Ask, for every fix: *is this in the APK or in app data?* If it is app data and the deliverable is an APK, re-implement it as a **code-level** change (patch the read path so it always yields the desired value).

---

## P12. PowerShell (or any shell) eats device-side commands

**Symptom**
`adb shell "su -c '...'"` fails with host-side path or parsing errors: "Could not find a part of the path", "Missing type name after '['", unexpanded `$VAR`, or a regex that got mangled.

**Root cause**
The host shell expands `$`, `|`, `>`, and quotes **before** adb sees them. Windows PowerShell additionally mangles `$var:`, `[^"]` and `$(`.

**Do instead**
Never build device commands inline in the host shell. Either:
- call adb from a small script file (`scripts/devsh.py`), or
- put the device-side logic in a script that you push and execute.

Same rule for `javac`: always pass `-encoding UTF-8` when sources contain non-ASCII, or the compiler reads them as the platform default and fails.

---

## P13. Trusting `apksigner verify` output at face value

**Symptom**
You signed with v1+v2+v3 explicitly enabled, then verification reports:
```
Verified using v1 scheme (JAR signing): false
Verified using v2 scheme (APK Signature Scheme v2): false
Verified using v3 scheme (APK Signature Scheme v3): true
```
Looks like v1/v2 silently did not happen, so you go re-engineer the signing step.

**Root cause**
`apksigner verify` decides **which schemes it is meaningful to check from the APK's own `minSdkVersion`**. When `minSdkVersion >= 24`, v1 is not required for install, and the tool reports it as `false` rather than "not applicable". The signatures are present and valid.

**Why it is hard to see**
Nothing in the output says "skipped because of minSdk". It reads exactly like a failure.

**Do instead**
Always verify with an explicit range so every scheme is evaluated:
```
apksigner verify --print-certs --verbose --min-sdk-version 21 --max-sdk-version 34 <apk>
```
Cross-check the fact independently: a real v1 signature means `META-INF/*.SF` and `META-INF/*.RSA` exist in the zip.

---

## P14. Treating same-size dex dumps as duplicates

**Symptom**
You deduplicate a memory dump by file size, keep one of each, and later find the kept dex is unusable (or silently wrong).

**Root cause**
Two dumps from the same process can have **identical byte length but different content** — different classes, even different dex version headers. One may additionally be structurally broken (header fields inconsistent with body, parser walks off the end of a table).

**Why it is hard to see**
Size equality is a tempting shortcut and is usually right for *file* duplicates. Here it is coincidence: two distinct dex objects were allocated to equal-length blocks.

**Do instead**
- Deduplicate by hash, never by size.
- Validate every candidate before trusting it: check the `dex\n0xx` magic, then sanity-check the reported `file_size` / `header_size` / map offsets against the actual byte length.
- Cross-check against the packing format when possible: with length-preserving encryption, **the encrypted payload's byte length equals the plaintext dex's byte length** — that mapping is the strongest signal for which dump is the original.

---

## P15. Frida version skew produces errors that look like a broken target

**Symptom**
Attach fails or the script dies immediately with errors such as:
```
unable to locate Android dynamic linker
Java is not defined
```
on a device where Frida is clearly running.

**Root cause**
A host `frida` package newer than the device's `frida-server` (or the reverse) is unsupported. Additionally, some newer host versions dropped the built-in Java bridge, so `Java.perform` is undefined unless you inline the bridge yourself.

**Why it is hard to see**
The error names the linker or a missing global, not a version mismatch. It reads like an Android compatibility problem or an anti-instrumentation defense.

**Do instead**
- Pin host package and device server to the **identical** version before debugging anything else. Print both versions side by side first.
- If the target is an older Android release, prefer the oldest version that still supports your API needs rather than the newest.
- On a device with multiple attached targets, do not rely on automatic USB selection — see `references/dynamic-frida.md`.

---

## P16. Blaming your own patch for a server-side TLS failure

**Symptom**
After repacking, the app launches and browsing works, but **login / registration** fails with a network error. The obvious suspect is the new signature breaking the API contract, so you start hunting for a signature check in the client.

**Root cause**
The failure is at the TLS layer, not the application layer: the API host's certificate is expired (or the chain does not validate), and that particular request path validates against the **system trust store**. Shipping a different signature is irrelevant.

Crucially, one app can carry **two independent trust chains**: requests through the app's own HTTP client (which may install a permissive `SSLSocketFactory` and `HostnameVerifier`) succeed, while requests through `java.net.URL.openConnection()` use the system defaults and fail. That is why "some features work" and "login does not".

**Why it is hard to see**
The user-visible message is a generic "network error". The real exception is usually swallowed by the app's own `try/catch`. And a client-side patch is the most recent change, so it gets blamed by default.

**Do instead**
- Capture the whole exception chain before theorizing. The give-away is
  `CertPathValidatorException: timestamp check failed` → `CertificateException: Chain validation failed` → `SSLHandshakeException: Chain validation failed`.
- Confirm independently of the app: strictly validate the host's certificate from your host machine and check `notAfter` against the device clock. See `references/tls-and-cert.md`.
- Run the control: does the **unmodified original** fail the same way on the same device and network? If yes, it was never your patch.

---

## P17. Trusting UI automation to prove whether a patch worked

**Symptom**
Your script taps a button, nothing happens, and you conclude the patch broke the control. Or you tap, see no visible change, and conclude the feature is dead.

**Root cause**
Device input and screenshots are far less reliable than they look:
- `input tap` can silently fail on specific widgets even with correct coordinates (ROM-dependent).
- `input` needs `INJECT_EVENTS`; under a plain shell it fails quietly.
- `screencap` can return a **zero-byte** file on some ROMs.
- Form submission can be rejected by local validation before any request is made, so "the button does nothing" is a validation failure, not a broken handler.

**Why it is hard to see**
All of these produce the same observable: nothing happens. A zero-byte screenshot often goes unnoticed and is treated as "no change".

**Do instead**
- Read back the widget tree (`uiautomator dump`) instead of trusting pixels: it gives real `bounds`, control text, and **field contents with lengths**. Verify every field is populated correctly *before* submitting.
- Compare field values, not just presence — one case that burned an hour was two password fields of different length, causing local validation to `return` before any network call.
- Treat "no visible change" as unproven, not as a negative result: confirm with an independent signal (logcat, a runtime probe, or a server-side request appearing in the capture).
- If a tap does not register, fall back to launching the Activity directly or invoking the handler, rather than retrying coordinates.

---

## P18. The package manager reported success, but the build was never installed

**Symptom**
Every install logs `Success`, so you run the next experiment and read its result — but the app being
tested is still the previous build. Screenshots show stale UI or the launcher, and results look
"unchanged".

**Root cause**
On many ROMs a package installer interposes its own confirmation. The install command can return success
for the *request*, while the actual install waits on a prompt — sometimes a password or account
confirmation — that nobody fills in. The app stays at its old version indefinitely.

This is the most expensive failure in this skill's history: because the command "succeeded", the stale
behaviour was measured across many rounds, and each measurement looked like a genuine negative result.

**Why it is hard to see**
The success signal is real; it just answers a different question than the one you asked. Nothing in a
normal install/launch script distinguishes "installed" from "install requested".

**Do instead**
- After installing, **prove the artifact changed**: compare `dumpsys package <pkg> | grep -E 'versionName|lastUpdateTime'` before and after, or hash the on-device APK and compare it to what you built.
- If a confirmation UI exists, drive it explicitly (type the credential, press the confirm control) and then re-verify.
- Make the check a precondition of the run, not an afterthought: if the version did not change, **abort** rather than measuring.
- Keep build artifacts named after the change they contain so a stale install is obvious from a screenshot.

---

## P19. Substituting an internal signal for the user-visible outcome

**Symptom**
An error disappears from the log, no crash is recorded, and you report the problem solved. The user
immediately shows you the same problem still on screen.

**Root cause**
The internal signal and the user-visible outcome are different claims. Suppressing one error path does
not remove the symptom if the symptom is produced by a **different** path — and a blocking dialog often
is. The log going quiet proves that one code path was affected; it says nothing about whether the user's
problem is gone.

**Why it is hard to see**
The signal is specific, measurable, and genuinely changed. It is a true statement being used to support a
false one.

**Do instead**
- Define "done" as the **user-visible behaviour**: the blocking UI is gone, the app reaches its normal
  screen, the feature works. Nothing else counts.
- Treat the absence of a log line as absence of evidence, never as evidence of success.
- When a symptom persists after an internal signal improves, assume there is **another** producer of the
  symptom and go find it, rather than assuming your fix is merely incomplete.
- Also verify the opposite direction: confirm the original symptom is reproducible **before** you patch,
  so you know what disappearing would even look like.

---

## P20. "I did not capture it" treated as "it is not there"

**Symptom**
Screenshots taken every few seconds after launch show no blocking dialog, so the dialog is declared gone —
then it turns out to be present the whole time.

**Root cause**
Sampling is not observation. A transient state that appears and is then covered (a second window, a
navigation, a system prompt) can fall entirely between samples. The modal appears, gets occluded, and
every frame you happened to take shows something else.

**Why it is hard to see**
The captures are real and consistently show the same thing, which feels like corroboration. Conviction
grows with the number of frames, even though all of them share the same blind spot.

**Do instead**
- For anything time-sensitive, capture **continuously** (recording) or in a dense burst immediately after
  launch, not on a fixed slow interval.
- **Look at every frame**, not only at file sizes. A byte-size cluster that "looks familiar" is not a
  reading.
- State conclusions with their sampling: "not observed in N consecutive seconds of recording" is honest;
  "does not occur" is not.
- When something is reported present by a human who is looking at the screen, believe the screen. Your
  capture gap is the more likely explanation.

---

## P21. Changing two things at once, then attributing the result

**Symptom**
A build fails, and you conclude that the mechanism you were most curious about is the culprit — then
exclude it from consideration for a long time. Later, a clean experiment shows it was the other change
all along.

**Root cause**
Two edits, one observation, no attribution. The failure is real; the explanation is invented. Worse, the
invented explanation survives because it sounds plausible and no one re-tests it.

**Why it is hard to see**
The experiment "worked" in the sense that it produced a result. Acting on a wrong attribution feels
exactly like acting on a right one until much later.

**Do instead**
- One variable per install-and-launch cycle. Where a combination is unavoidable, add a third run that
  isolates each half.
- Write the attribution into your notes **with the run that proves it**. An unproven cause is a
  hypothesis; keep it labelled as one.
- When a route is about to be discarded, re-check whether the evidence was actually single-variable. A
  discarded route with compound evidence should be re-opened before being abandoned.
- Prefer semantically inert controls (a change nothing reads) to prove "edits of this class are allowed"
  separately from "this specific edit is allowed".

---

## P22. Waiting for something that requires a human to advance

**Symptom**
An automation loop polls for minutes or longer, waiting for a state that never arrives on its own. Time
is consumed while nothing at all can change.

**Root cause**
The awaited state is gated on a human action — a consent prompt, a permission dialog, an installer
confirmation, a captcha. No amount of waiting resolves it. Automated polling is the wrong instrument for
a state whose transition is external.

**Why it is hard to see**
Polling is cheap-looking and the loop reports progress (timestamps, unchanged screenshots), which creates
an impression of work being done.

**Do instead**
- Before waiting on a state, ask what would cause it to change. If the answer is "a person", stop waiting
  and either perform the action programmatically or hand it back.
- Bound every wait with a deadline and an explicit failure branch that **does something different**, not
  just a longer timeout.
- Detect stalls by change, not by elapsed time: if N consecutive samples are identical, break out.
- Prefer driving the prompt to completion over waiting it out — the same prompt usually recurs, so
  automating it once pays back immediately.

---

## P23. The fix lives in a file the app rewrites

**Symptom**
You change a value in the app's data, the write succeeds, the file reads back correctly — and after
the next launch the value is back to what it was. Often byte for byte identical, which makes it look
like nothing happened at all.

**Root cause**
The stored value is a **cache, not a source of truth**. Either the app re-fetches it and re-persists
it, or it rewrites the file from its own defaults on every start. Your edit was never authoritative.

Compounding it: the intuitive way to protect the file — a restrictive mode or a changed owner — **does
not work**, because the app does not open-and-write the existing file. It **deletes the file and
creates a new one**, and a new file is created with the app's own mode and owner. Nothing is inherited,
so `chmod`/`chown` are silently ineffective.

**Why it is hard to see**
Verification is usually done immediately after writing, while the file is still correct. The rewrite
only happens on the next start, which is one step further along than you looked. And the "fix" that
seems obviously right (tighten permissions) fails without any error.

**Do instead**
- **Verify after a relaunch, not after the write.** The write succeeding is not the finding; surviving
  a restart is.
- **Distinguish the two causes with one offline launch.** If the value survives with the network down,
  it came from the server. If it does not, the app is regenerating it locally — and then a data edit is
  the wrong layer entirely; patch the read path instead.
- To make a data edit stick, use the **immutable attribute** and confirm it took effect:
  ```bash
  su -c "chattr +i <file>"; su -c "lsattr <file>"     # expect the 'i' flag
  ```
  It is enforced by the filesystem against the delete itself, which is why it holds where permissions
  do not. Undo with `chattr -i`.
- Then **exercise the feature**, not just the value. A blocked write the app depends on can make it
  misbehave; "the file still has my value" is not "the app still works".
- Remember a lock is **device state, not artifact state** — it does not travel with an APK. Record it
  as an environment requirement. The only form that ships is a code patch (`runtime-data.md`).

---

## P24. The artifact changed, but the wrong one is executing

**Symptom**
The build differs from the original, the pipeline reports success, the file on disk is genuinely
modified — and the app behaves exactly as before. Or a native hook reports nothing while the feature
plainly runs.

**Root cause**
Something other than your edit is being used at runtime:

- **Wrong ABI.** A fat APK ships several `lib/<abi>/` directories; the package manager extracts and
  loads **one**. Editing `arm64-v8a` while the device loads `armeabi-v7a` produces a byte-different,
  behaviorally identical build.
- **The library is not from the APK at all.** Some libraries are written into the app's data directory
  at runtime rather than extracted from the package. Patching the APK copy changes a file nobody loads.
- **Multiple processes.** The work was done in, or the check lives in, a different process than the one
  you are observing.
- **A stale install.** The package manager reported success for a request that did not replace what is
  on disk (`P18`).

**Why it is hard to see**
Every local indicator agrees: the diff is non-empty, the build is signed, the install returned success.
Nothing in the *build* pipeline can detect this, because the build is fine. The contradiction only
exists at runtime.

**Do instead**
- **Ask the running process what it loaded**, before editing: `scripts/lib_map.py --pkg <pkg>`.
  Libraries whose path is not under the installed APK's lib directory were materialized at runtime
  and belong to whatever produced them.
- Confirm the ABI the package manager actually chose (`dumpsys package <pkg> | grep primaryCpuAbi`)
  rather than the one you assumed from the manifest.
- **If the library you patched is not in the live mapping, stop.** No amount of re-patching helps; the
  plan is wrong.
- Treat a behaviorally identical rebuild as **positive evidence that your edit is not being loaded**,
  not as "the change had no effect". Those are different conclusions and only one of them is actionable.

---

## P25. "The search found nothing" treated as "the data is not there"

**Symptom**
You scan an artifact for a known-present value — a UI label, a marker string, an endpoint — get zero
hits, and conclude the content is stripped, encrypted, or otherwise unavailable. A route gets written
off on that basis.

**Root cause**
The search used the wrong representation. A byte scan for UTF-8 text returns nothing against content
that is stored as UTF-16, or compressed, or framed inside a container, or split across fragments. The
data is present; the needle was encoded differently from the haystack.

**Why it is hard to see**
"Zero results" is a clean, confident-looking output. It feels like a measurement, so it gets recorded
as a finding, and findings propagate into the plan.

**Do instead**
- **Before concluding absence, search more than one encoding.** UTF-8 and UTF-16LE will between them
  cover most text storage:
  ```python
  blob.find(needle.encode('utf-8')), blob.find(needle.encode('utf-16-le'))
  ```
- **Search the shortest distinctive fragment.** Text is often assembled from pieces or templates, so a
  full sentence can be absent while its parts are present.
- **Try the value without its framing.** A hit rate of zero is also the expected result for content
  that is inside a compressed or encoded container — decode the container first (`runtime-data.md`,
  `scripts/blob_decode.py`).
- **State a negative result with its scope**: "no UTF-8 or UTF-16LE literal match in this artifact"
  is a finding. "The string does not exist" is a guess wearing a finding's clothes.
