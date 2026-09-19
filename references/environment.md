# Environment — device, emulator, tooling, networking

## Pick your target

| Option | Pros | Cons |
|---|---|---|
| **Rooted physical device, native ABI** | Truest behavior; native libs load natively; Frida works well | One at a time; USB flakiness |
| **Emulator with root** | Disposable; snapshots; easy reset | Different ABI; some apps detect it or refuse to run; native ARM libs may need translation |
| **Static only** | No device needed | Cannot verify anything. Never claim success from static analysis alone. |

**Rule:** the artifact must be verified where the user will run it. An emulator that runs the app is **not** evidence about a physical ARM device, and vice versa.

**Important:** if the app ships only `arm64-v8a` native libraries and your emulator is x86_64, it may still run via ARM translation — but translation changes timing, and some native checks misbehave. Prefer a real ARM device for the final verification pass.

## ADB basics worth pinning down

```bash
adb devices -l
adb -s <serial> shell getprop ro.product.cpu.abi
adb -s <serial> shell getprop ro.build.version.release
adb -s <serial> shell getprop ro.build.version.sdk
```

Root:
```bash
adb -s <serial> shell "su -c id"
```
`pm grant` and `pm install` frequently require root on OEM builds; the `shell` user gets `SecurityException`.

**Always specify `-s <serial>` when more than one device is attached** — otherwise adb errors out or picks the wrong one.

## Shell quoting (a real time sink)

The host shell expands `$`, `|`, `>`, and quotes **before** adb sees them. Windows PowerShell additionally mangles `$var:`, `[^"...`, and `$(...)`.

Symptom: "Could not find a part of the path", "Missing type name after '['", "no closing quote".

**Fix:** never inline device commands in the host shell. Use a small helper that calls adb from a script file and passes the command as a single argument:

```python
subprocess.run([ADB, '-s', SERIAL, 'shell', 'su -c "%s"' % cmd])
```
See `scripts/devsh.py`.

Same class of bug: `javac` reads sources using the platform default encoding. Pass `-encoding UTF-8` or non-ASCII comments break the build.

## Giving an offline device network over USB

Use when the device has no usable network (broken Wi-Fi, no SIM, restricted network) but your host does. **`adb reverse` runs on the device's loopback, so it needs no device-side network interface at all.**

```bash
# 1) host HTTP/HTTPS proxy (CONNECT-capable)
python scripts/usb_net_proxy.py 8080 proxy.log

# 2) forward device-localhost:8080 to host:8080
adb -s <serial> reverse tcp:8080 tcp:8080

# 3) point the device at it
adb -s <serial> shell "su -c 'settings put global http_proxy 127.0.0.1:8080'"
```

Notes:
- `adb reverse` **does not survive a device reboot** — recreate it after any restart.
- Keep the host proxy process alive; if it dies, the device goes offline again.
- Some SDKs bypass the system proxy entirely (many ad SDKs do). Proxy logs therefore **undercount** traffic — do not conclude "no ad traffic" from proxy logs alone; confirm with a runtime DNS hook.
- Clean up when done: `settings put global http_proxy :0`.

## Emulator notes

- Verify the app can install at all. INSTALL failures on emulators are common (ABI, min SDK, vendor checks) and are usually not related to your patch.
- Snapshot/rollback is the main advantage — use it to A/B two builds quickly.
- Never quote emulator behavior as proof for a device-only question (and vice versa).

## Install / reinstall

```bash
adb -s <serial> shell "su -c 'pm uninstall <pkg>'"
adb push out.apk /data/local/tmp/x.apk
adb -s <serial> shell "su -c 'pm install -r -t -d /data/local/tmp/x.apk'"
```
- `-r` reinstall (keep data, same signing key) · `-t` allow test-only · `-d` allow downgrade
- Different signing key than the installed app → must uninstall first (data is lost)
- Vendor installers may reject `adb install`; pushing + `su -c pm install` usually works

**After reinstalling:** if you restored a data directory, fix ownership, or the app crashes in a DB-init path:
```bash
su -c "chown -R <uid>:<uid> /data/user/0/<pkg>"
su -c "restorecon -R /data/user/0/<pkg>"
```
`<uid>` from `dumpsys package <pkg> | grep userId=`.

## Signal extraction (what to actually read)

```bash
adb -s <serial> logcat -c                                  # clear before the run
adb -s <serial> shell "am start -n <pkg>/<activity>"
adb -s <serial> logcat -d -v brief | grep -E '<pkg>|FATAL|VerifyError|IncompatibleClassChange|uncaughtException'
```

Failure signatures worth memorizing:

| Log line | Likely cause |
|---|---|
| `FATAL EXCEPTION` + Java stack | App-level crash — read the stack |
| `VerifyError` / `IncompatibleClassChangeError` | Damaged dex (round-trip or bad rewrite) → `pitfalls.md` P3 |
| `Failure starting process` (no stack, by `ActivityManager`) | ART refused the dex, or device state is broken → `pitfalls.md` P4, P9 |
| `ClassNotFoundException: <App.Application>` | Dex rejected wholesale (ordering / structure) → `pitfalls.md` P2 |
| `uncaughtException` with **no stack**, right after launch | A crash-reporter SDK swallowed it. Check whether the process is gone, and look for the SDK's own log file under the app's data dir |
| App alive but nothing rendered | A swallowed exception in the UI path; hunt the crash-reporter's log file |

**Crash-reporter SDKs hide your stack traces.** When an app installs a global uncaught-exception handler (友盟/UCrash/Bugly etc.), the Java stack never reaches `logcat` — only a line like `uncaughtException time: ...`. Three ways to get the stack:
1. **Frida**, hooking `Thread.setDefaultUncaughtExceptionHandler` or the handler class (most reliable).
2. **Race the reporter's log file**: it writes a file under `<app data>/<sdk>/...` then uploads and deletes it. Poll it every ~0.2 s from the device shell and copy on sight:
   ```bash
   while [ $i -lt 400 ]; do
     for f in <dir>/*.log; do [ -f "$f" ] && cp -f "$f" /data/local/tmp/capture.log; done
     i=$((i+1)); sleep 0.2
   done
   ```
3. Run a build with the reporter disabled (not always possible).

## Determinism

Before concluding anything from a failure: **reboot the device and retry**, and **run a control build with zero patches**. A surprising share of "my patch broke it" turns out to be device state (`pitfalls.md` P9).
