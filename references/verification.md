# Verification — what "done" means

The difference between a hobby patch and a usable deliverable is verification. "It assembles" and "the log is quiet" are not verification.

## The claim ladder

Each rung is stronger evidence. Climb as high as the task requires, and **state clearly which rung you reached**.

| Rung | Claim | Evidence required |
|---|---|---|
| 0 | "The dex was edited" | Byte-level diff of the target method |
| 1 | "The structure is intact" | `dex_classdiff`: same classes, zero `ACC_INTERFACE` drift, unchanged classes byte-identical |
| 2 | "It builds and signs" | Signature verification passes |
| 3 | "It installs and launches" | Process alive, `logcat` free of fatal signatures |
| 4 | "The target behavior changed" | The specific feature observed changed (screen exercised, endpoint observed, UI confirmed) |
| 5 | "Nothing else regressed" | Adjacent features exercised: images, playback, lists, login, settings |
| 6 | "The mechanism is proven" | Independent evidence of *why* — e.g. the SDK's domains are never resolved because init never ran |

**Rung 3 is the minimum for any deliverable. Rung 4 for a claim that the patch solved the problem. Rung 5 before handing it to a user. Rung 6 when the claim is "the subsystem is dead", not merely "the ad is hidden".**

## The control build rule

Before blaming a patch, build a control: **the same pipeline with zero patches**.

```bash
python scripts/repack.py --apk original.apk --dexdir <extracted> --out control.apk
```

- Control fails → your pipeline, the environment, or the device is at fault. Stop debugging the patch (`pitfalls.md` P9).
- Control passes, patched fails → the patch is implicated. Bisect: revert one dex at a time.

Do this **whenever something unexpectedly fails**, and at least once per project.

## Structural verification (automate it)

After every dex edit:

```bash
python scripts/dex_classdiff.py <original.dex> <patched.dex>
```
Expect exactly:
```
only_in_A=0   only_in_B=0
ACC_INTERFACE mismatch: 0
access_flags diff (same interface-ness): 0
```

Caveat, and it is an important one: **this check cannot detect code-item damage.** A whole-tree smali round-trip can pass every table check and still crash with `IncompatibleClassChangeError` (`pitfalls.md` P3). Passing this check is necessary, not sufficient.

Also confirm you changed what you intended and nothing more:
- Reverse the patched dex and inspect the target method.
- Compare unmodified classes byte-for-byte against the original where feasible.

## Runtime verification

```bash
adb -s <serial> logcat -c
adb -s <serial> shell "am start -n <pkg>/<activity>"
sleep 5; adb -s <serial> shell "pidof <pkg>"      # empty == died
sleep 20; adb -s <serial> shell "pidof <pkg>"     # same pid == stable
adb -s <serial> logcat -d -v brief | grep -E 'FATAL|VerifyError|IncompatibleClassChange|uncaughtException|Failure starting process'
```

**Sample the pid twice, spaced apart.** A single reading catches apps that die in a crash loop.

Failure signature → cause table lives in `references/environment.md`.

**Logcat is often not enough.** If the app installs a crash handler (友盟/UCrash/Bugly), the Java stack never reaches logcat. A process that dies with only `uncaughtException time: ...` and no stack **has crashed** — treat it as a failure, not as noise. Extraction techniques: `references/environment.md` §signal extraction.

## Behavioral verification (the part people skip)

Launching proves nothing about your change. Exercise it.

- **Ads removed** → open the screens that had ads (splash, home, detail, player, reward button). Confirm absence *and* confirm the screens still function.
- **A gate patched** → walk the gated flow end to end.
- **A timeout/limit patched** → trigger it.
- **Data patched** → stop the app, clear/re-write the value, cold start, re-check (proves it is not an in-memory artifact).

**And then test the neighbours.** The most common real-world regression is a patch that fixed its target and quietly broke something unrelated:

- Images / cover art render?
- Video or audio playback works?
- Lists scroll and paginate?
- Login / session still valid?
- Settings screens open?
- Downloads still start?

This is exactly how a "generic image-card composable" patch removed all cover art while the ad still showed (`pitfalls.md` P6).

## Screenshot discipline

Capture before/after screenshots for each claim. Text descriptions are not evidence; a screenshot of the screen without the ad, alongside one from the control build with it, is.

## Reporting

```
Build:          <path> <sha256>
Base:           <original apk name/version>
Changes:        <dex → what changed>, one line each
Structural:     dex_classdiff result (per dex)
Signature:      verified (v1/v2/v3)
Device:         <model / android / abi / rooted?>
Runtime:        pid stable over N s; no fatal signatures
Behavior:       <screens exercised>, <before/after>
Regressions:    <adjacent features checked>
Rung reached:   0..6
Residual:       <what is NOT fixed, and the exact reason>
```

**Be explicit about residuals.** "Ad X remains because it is delivered inside the screen's main data payload, and suppressing it at the transport layer takes the whole screen down" is a useful, honest result. Silently omitting it is not.

## Anti-patterns

- Declaring success from a successful assembly.
- Claiming "no ads" from a quiet logcat when the SDK never printed anything either way.
- Concluding from a single launch without exercising the feature.
- Quoting emulator results as device results.
- Reporting a fixed feature without checking adjacent features.
- Hiding a known residual failure.
