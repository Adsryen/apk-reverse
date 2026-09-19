# Dynamic analysis with Frida

Static analysis tells you what code exists. Frida tells you what code **runs**. When they disagree, runtime wins (`references/pitfalls.md` P10).

Use Frida when you need to answer:
- Which method actually renders this element? (static decompilation routinely misleads)
- What is the real call chain at the moment of interest?
- What does the app actually do on startup, in order?
- Which domains does it resolve, and when?
- Is the app detecting my instrumentation?

## Setup — version alignment is a hard gate

**Do this first.** Nearly every "Frida is broken on this device" report is a version mismatch, and the error text rarely says so. The host `frida` package and the device-side `frida-server` must be the **same version**, and that version must actually support the device's Android release. Align, then debug everything else.

| Symptom | Cause | Fix |
|---|---|---|
| `unable to locate Android dynamic linker` | host/server too new for this Android release | drop to an older frida line (16.x is a safe baseline for older ROMs) |
| `Java is not defined` / `Java.perform is not a function` | that build ships no bundled Java bridge | align to a build that has it, or inline the bridge (see *17+ gotchas*) |
| `Failed to connect to remote frida-server` / `unexpected message` / `invalid message` | host package and device server differ | download both from the same release tag |
| `Java.choose` / `Java.use` throws immediately | bridge present but the VM is not ready | wrap everything in `Java.perform` |
| Attached, but hooks fire in the wrong process | USB auto-selection grabbed the emulator | use an explicit remote device (below) |
| `HOOK-OK` prints and nothing ever fires | not a version problem | go to *Hook never fires* |

### Prefer a remote device over USB

With a physical device *and* an emulator attached, `frida.get_usb_device()` can silently pick the emulator — you then attach to the wrong process and chase phantom failures for a long time. Address the device explicitly:

```bash
adb devices -l                                  # get <serial>
adb -s <serial> forward tcp:27042 tcp:27042
frida -H 127.0.0.1:27042 -f <app.package> -l probe.js --no-pause
```

```python
device = frida.get_device_manager().add_remote_device('127.0.0.1:27042')
```

Keep `-s <serial>` on every other adb call too, or you will drift between targets mid-session.

### Attach by PID when the process list is incomplete

`device.enumerate_processes()` can return a list that simply does not contain the app you are
targeting, while `adb shell ps -A | grep <pkg>` shows it running. This is an enumeration gap,
not a permission problem, and no amount of retrying fixes it. Resolve the pid through adb and
attach to it directly:

```python
import subprocess

def find_pid(serial, pkg):
    out = subprocess.run(['adb', '-s', serial, 'shell', 'ps -A -o PID,NAME'],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == pkg:
            return int(parts[0])          # last match wins; use the main process
    return None

pid = find_pid(serial, pkg)
session = device.attach(pid)              # works where attach(pkg) raises ProcessNotFound
```

Two related behaviours worth knowing:

- `attach(<package name>)` raises `ProcessNotFoundError` in exactly this situation, which is
  easy to misread as "the app is not running".
- A pid captured earlier goes stale the moment the process is recycled. Re-resolve it
  immediately before each injection rather than reusing a value from an earlier step.

### Verify the runtime before blaming the script

A script that reports nothing at all is usually not seeing the Java layer. Two failure modes
look identical from the host — test for both in one go:

```javascript
// send({ runtime: Script.runtime, java: typeof Java, objc: typeof ObjC });
```

- `Java` is `undefined` ⇒ the script runtime has no Java bridge. Pass `runtime='v8'`
  explicitly when creating the script; some builds default to a runtime without it.
- The bridge exists but every hook misses ⇒ you attached to the wrong process, or the layer
  below is native (go to the four-layer probe / `references/native-and-so.md`).

### Start the device server so it survives

Run it as root, give it a non-obvious name out of obvious paths, and **detach it from the shell's session**. A process started with `nohup ... &` from an `adb shell` that then exits gets reaped mid-run — the hooks work for a minute and then stop.

```bash
adb push frida-server-<ver>-android-<abi> /data/local/tmp/
adb shell "su -c 'mkdir -p /data/local/tmp/.svc'"
adb shell "su -c 'cp -f /data/local/tmp/frida-server-<ver>-android-<abi> /data/local/tmp/.svc/kwork'"
adb shell "su -c 'chmod 755 /data/local/tmp/.svc/kwork'"
adb shell "su -c 'setsid /data/local/tmp/.svc/kwork >/dev/null 2>&1 </dev/null &'"
adb shell "su -c 'pgrep -f kwork'"     # must still be alive after the shell returned
```

If `setsid` is unavailable, hold the adb connection open instead: run `adb shell "su -c '/data/local/tmp/.svc/kwork'"` as a host-side background job and leave it running for the whole session.

### Spawn, don't attach, when timing matters

ABI must match the device (`getprop ro.product.cpu.abi`). Attaching usually misses startup — init, the first network calls, and splash logic all happen before you get a session.

```python
device = frida.get_device_manager().add_remote_device('127.0.0.1:27042')
pid = device.spawn([pkg])
session = device.attach(pid)
# ... load the script, wait until it reports that hooks are installed ...
device.resume(pid)          # resume ONLY after hooks are ready
```

**Common bug:** resuming before the script has finished loading loses the first ~100–300 ms, which is exactly where init happens. Have the script `send()` a ready signal (the probe template below sends `PROBE-READY`) and resume only after receiving it.

## Frida 17+ gotchas

The preferred fix for every symptom in the table above is **version alignment**. Use these only when you genuinely must run a 17+ build.

- The **built-in Java bridge was removed**. `Java.perform(...)` is not available unless you inline the bridge yourself:
  ```python
  bridge = open(<site-packages>/frida_tools/bridges/java.js, encoding='utf-8').read()
  script = bridge + "\nObject.defineProperty(globalThis,'Java',{value:bridge,configurable:true});\n" + my_js
  ```
  Pass the whole thing through a small loader script (below).
- **Export lookup renamed.** Use a compatibility helper rather than a single API:
  ```javascript
  function resolveExport(name) {
    try { if (Module.getGlobalExportByName) return Module.getGlobalExportByName(name); } catch (e) {}
    try { if (Module.findExportByName) return Module.findExportByName(null, name); } catch (e) {}
    try { const l = Process.findModuleByName('libc.so'); if (l) return l.getExportByName(name); } catch (e) {}
    return null;
  }
  ```
- **Large script injection times out.** A multi-hundred-KB bridge + script can exceed the transport timeout. Use a tiny loader and post the real payload:
  ```python
  loader = "recv('go', m => { eval(m.payload.code); }); send('loader-ready');"
  sc = session.create_script(loader)
  sc.load()
  sc.on('message', on_message)          # wait for 'loader-ready'
  sc.post({'type': 'go', 'payload': {'code': BIG_JS}})
  ```

## Hook strategy

### Java layer (Kotlin/Java app)
```javascript
Java.perform(() => {
  const Cls = Java.use('com.example.Helper');
  Cls.showAd.overload('android.app.Activity').implementation = function (a) {
    send({ tag: 'Helper.showAd', stack: Java.use('android.util.Log').getStackTraceString(
        Java.use('java.lang.Throwable').$new()) });
    return this.showAd(a);   // observe, then delegate
  };
});
```
- **Use `overload(...)`** — obfuscated classes often have several methods with the same name.
- To find obfuscated names, enumerate at runtime rather than guessing from decompiled short names:
  ```javascript
  Java.enumerateLoadedClasses({
    onMatch: n => { if (n.indexOf('example') >= 0) send(n); },
    onComplete: () => send('done')
  });
  ```
- **Call stacks are the highest-value signal.** `Log.getStackTraceString(new Throwable())` or `Java.use('android.util.Log').getStackTraceString(...)` gives you the real chain from the framework down to the method — far more reliable than reading smali.

### Native layer
```javascript
const f = resolveExport('open');
Interceptor.attach(f, {
  onEnter(args) { this.p = args[0].readCString(); },
  onLeave(ret) { if (this.p) send({ tag: 'open', path: this.p }); }
});
```

### Network / domain observation (cheap and very informative)
```javascript
const Inet = Java.use('java.net.InetAddress');
Inet.getAllByName.overload('java.lang.String').implementation = function (h) {
  send({ tag: 'dns', host: h });
  return this.getAllByName(h);
};
```
This is often the **decisive evidence** for an ad-removal claim: if the ad SDK's domains are *never resolved*, the subsystem never started — a much stronger statement than "logcat was quiet". It also works for SDKs that bypass the system HTTP proxy.

## The four-layer probe template

When the question is "why did this request fail / where did it go", do not hook one class and hope. Ship **one long-lived script that hooks four layers at once**; whichever layer fires first localizes the problem immediately. This is the single most productive artifact of a runtime investigation — reuse it verbatim.

The layers, and why each one is there:

1. **The app's own network wrapper** — enumerate `getDeclaredMethods` and wrap *every* overload, so you do not have to guess the entry point.
2. **OkHttp end to end** — `newCall`, `Request$Builder.build`, `RealCall.execute`, `AsyncCall.run`, `RealInterceptorChain.proceed`. The last two are the ones that fire for asynchronous calls.
3. **`java.net.URL.openConnection`** — plenty of login/register paths never touch OkHttp; they use `HttpsURLConnection` and a completely different trust configuration.
4. **`Throwable.getMessage`** — pulls out the original text of exceptions an upper layer caught and swallowed. Without it, a caught failure looks like "nothing happened".

Rules that make the difference between a usable probe and a wasted session:

- **Write to a file as well as to `send()`.** Stdout is lossy and the CLI drops messages; the file is the evidence.
- **Let it stay resident.** Hook before the app touches the network, then leave it running while you drive the UI. A one-shot script misses everything that happens after its first second.
- **Wrap every hook in its own `try/catch`.** One missing class must not take down the other three layers.
- **Never capture an overload in a `var`.** Inside a loop, `var ov = ...` leaves every hook pointing at the *last* overload: they install cleanly and then mis-report forever. Use `let` or `.forEach()`.

`scripts/frida_probe.js` is the same probe in a fuller form (per-arity dispatch, DNS layer, dedup and hard caps). The script below is the minimal portable one — paste it into any loader and it adapts to the target.

```javascript
// probe.js — four-layer network + swallowed-exception probe.
const APP_PKG = '<app.package>';
const APP_NET_CLASS = 'com.example.app.net.HttpHelper';   // the app's own wrapper, once you have found it
const LOGFILE = '/data/user/0/' + APP_PKG + '/files/probe.log';   // app-private: always writable by the app
const MAX_THROW = 400;                                    // Throwable.getMessage is hot — cap it
const INTERESTING = /(network|http|ssl|cert|fail|timeout|refused|unable|error|exception)/i;  // widen for the app's UI language

let out = null;
try { out = new File(LOGFILE, 'a'); } catch (e) {}

function log(ev, data) {
  const line = JSON.stringify(Object.assign({ t: Date.now(), ev: ev }, data));
  try { send(line); } catch (e) {}
  try { if (out !== null) { out.write(line + '\n'); out.flush(); } } catch (e) {}
}

function stack(n) {
  try {
    const t = Java.use('java.lang.Throwable').$new();
    return Java.use('android.util.Log').getStackTraceString(t).split('\n').slice(1, (n || 6) + 1).join(' | ');
  } catch (e) { return '<no stack>'; }
}

function sa(args) {                       // a hook must never die inside its own logging
  try {
    const o = {};
    for (let i = 0; i < args.length; i++) o['a' + i] = args[i] === null ? 'null' : '' + args[i];
    return o;
  } catch (e) { return { err: '' + e }; }
}

// 1) the app's own wrapper: every declared method, every overload, separately wrapped
function hookAppNet(cls) {
  try {
    const C = Java.use(cls);
    const ms = C.class.getDeclaredMethods();
    for (let i = 0; i < ms.length; i++) {
      try {
        const name = ms[i].getName();
        const ps = ms[i].getParameterTypes();
        const sig = [];
        for (let j = 0; j < ps.length; j++) sig.push(ps[j].getName());
        const ov = C[name].overload.apply(C[name], sig);
        ov.implementation = function () {
          try { log('APP-NET', { cls: cls, m: name, args: sa(arguments), stack: stack(5) }); }
          catch (e) { log('PROBE-ERR', { at: 'app-net', msg: '' + e }); }
          return ov.apply(this, arguments);
        };
      } catch (e) { log('HOOK-SKIP', { cls: cls, m: ms[i].getName(), msg: '' + e }); }
    }
    log('HOOK-OK', { layer: 'app-net', cls: cls, n: ms.length });
  } catch (e) { log('HOOK-FAIL', { layer: 'app-net', cls: cls, msg: '' + e }); }
}

// 2) OkHttp end to end — internal class names moved between major versions, so try every location
function hookOkHttp() {
  const targets = [
    ['okhttp3.OkHttpClient', 'newCall'],
    ['okhttp3.Request$Builder', 'build'],
    ['okhttp3.RealCall', 'execute'],
    ['okhttp3.RealCall$AsyncCall', 'run'],
    ['okhttp3.internal.http.RealInterceptorChain', 'proceed'],        // okhttp 3.x
    ['okhttp3.internal.connection.RealInterceptorChain', 'proceed']   // okhttp 4.x / 5.x
  ];
  for (let i = 0; i < targets.length; i++) {
    const cn = targets[i][0], mn = targets[i][1];
    try {
      const ovs = Java.use(cn)[mn].overloads;    // every overload of that name; use .overload('<sig>') if this is undefined
      for (let j = 0; j < ovs.length; j++) {
        const ov = ovs[j];                       // block-scoped: every hook keeps its own overload
        ov.implementation = function () {
          try { log('OKHTTP', { cls: cn, m: mn, args: sa(arguments), stack: stack(6) }); }
          catch (e) { log('PROBE-ERR', { at: cn, msg: '' + e }); }
          return ov.apply(this, arguments);
        };
      }
      log('HOOK-OK', { layer: 'okhttp', cls: cn, m: mn, overloads: ovs.length });
    } catch (e) { log('HOOK-SKIP', { layer: 'okhttp', cls: cn, m: mn, msg: '' + e }); }
  }
}

// 3) java.net.URL — login/register frequently bypasses OkHttp entirely
function hookRawUrl() {
  try {
    const U = Java.use('java.net.URL');
    const o0 = U.openConnection.overload();
    o0.implementation = function () {
      try { log('RAW-URL', { url: '' + this.toString(), stack: stack(6) }); } catch (e) {}
      return o0.apply(this, arguments);
    };
    try {
      const o1 = U.openConnection.overload('java.net.Proxy');
      o1.implementation = function () {
        try { log('RAW-URL', { url: '' + this.toString(), proxy: true, stack: stack(6) }); } catch (e) {}
        return o1.apply(this, arguments);
      };
    } catch (e) {}
    log('HOOK-OK', { layer: 'url' });
  } catch (e) { log('HOOK-FAIL', { layer: 'url', msg: '' + e }); }
}

// 4) Throwable.getMessage — the original text of an exception an upper layer caught and swallowed
function hookThrowable() {
  try {
    const T = Java.use('java.lang.Throwable');
    const seen = {};
    let n = 0;
    T.getMessage.implementation = function () {
      const msg = this.getMessage();          // self-call inside the replacement is fine (Frida guards it)
      try {
        if (msg !== null && msg !== undefined && n < MAX_THROW) {
          const cls = '' + this.getClass().getName();
          const interesting = cls.indexOf('Exception') >= 0 || cls.indexOf('Error') >= 0 || INTERESTING.test('' + msg);
          const key = cls + '|' + msg;
          if (interesting && seen[key] === undefined) {   // dedup: this method is on a very hot path
            seen[key] = 1; n++;
            log('THROW', { cls: cls, msg: '' + msg, stack: stack(4) });
          }
        }
      } catch (e) {}
      return msg;
    };
    log('HOOK-OK', { layer: 'throwable' });
  } catch (e) { log('HOOK-FAIL', { layer: 'throwable', msg: '' + e }); }
}

Java.perform(function () {
  hookAppNet(APP_NET_CLASS);
  hookOkHttp();
  hookRawUrl();
  hookThrowable();
  log('PROBE-READY', { pkg: APP_PKG, logfile: LOGFILE });   // the host waits for this before resuming
});
```

Read the log after driving the UI. `RAW-URL` (with no `OKHTTP` events) is how you learn the request went over `HttpsURLConnection` — a different trust path entirely (`references/server-api.md` § TLS). `THROW` is how you learn an upper layer swallowed the real error.

```bash
# pull the record (app-private path needs root to read)
adb -s <serial> shell "su -c 'cat /data/user/0/<app.package>/files/probe.log'" > probe.log
```

## Hook never fires — debug in this order

`HOOK-SKIP` / `HOOK-FAIL` lines answer this before you start guessing. When every layer reports `HOOK-OK` and still no event arrives:

1. **Does the class / method / overload actually exist?** A misspelled obfuscated name, a renamed okhttp internal class, or an overload taking `Object` instead of `String` all produce a wrapper that is simply never invoked.
2. **Is the ClassLoader the right one?** Multi-dex, plugin-loaded and packed apps can hold several loaders; `Java.use` uses the app loader by default and throws `ClassNotFoundException` for a class that is plainly in the APK. Enumerate and switch:
   ```javascript
   Java.enumerateClassLoaders({
     onMatch: function (l) { try { if (l.findClass('<app.net.Class>')) Java.classFactory.loader = l; } catch (e) {} },
     onComplete: function () {}
   });
   ```
3. **Is that code path reached at all?** Layer 4 settles it: if `THROW` events show the app failing earlier, your hook's call site is never executed and no amount of hooking will help.
4. **Did your UI action trigger business logic?** A tap that looks fine but fails a local form check returns before any network call. Verify the input actually reached the field (`references/environment.md` § UI automation), not just that the button animated.

## `Java.choose` also matches dead instances

`Java.choose('com.example.app.MainActivity', ...)` returns **every** instance the VM still tracks, including finished and destroyed ones. Walking their view tree then yields an empty list — that is normal, not a bug in your script. Filter first, and prefer a direct reflective call over simulating a tap:

```javascript
Java.choose('com.example.app.MainActivity', {
  onMatch: function (a) {
    try {
      if (a.isFinishing() || a.isDestroyed()) return;     // dead instance: skip it
      send({ tag: 'live', view: '' + a.findViewById(<viewId>) });
    } catch (e) {}
  },
  onComplete: function () {}
});
```

## Reading obfuscated code at runtime

When names are meaningless (`a7`, `x6`, `uf0`), do not patch from names. Instead:

1. Find a **unique anchor**: an API path, a preference key, or an SDK class name from the string table (`scripts/dex_strings.py`).
2. Locate the small class/method that references it (byte search in the dex + a targeted disassembly).
3. Hook that anchor, capture the **stack**, and read off the real chain.
4. Hook the classes the stack reveals — that is where semantics become visible.

## Anti-instrumentation

Signs: the app exits or freezes shortly after attach; `logcat` shows a generic process death with no Java stack; strings like `frida`, `xposed`, `magisk`, `substrate` are referenced by **app code** (not just by an SDK's string list).

**Rule this out first — it is not always a detector.** A process that dies right after you
attach is frequently the ROM rather than the app: on aggressive OEM ROMs, merely backgrounding
the app (pressing HOME, switching away) triggers a freeze, and the logcat signature is a state
transition such as `state: R -> F` while hooks stop with no Java stack. That looks identical to
a detector killing you. Check `references/environment.md` for that signature, and keep the app
in the foreground, before building an anti-anti plan.

Countermeasures, in order of least disruption:
1. Spawn + late resume, so hooks are installed before the check runs.
2. Rename `frida-server` and move it out of obvious paths.
3. Hook the detector itself and neuter it — find it by hooking the suspicious API (e.g. `/proc/self/maps` reads, `File.exists`, `Runtime.exec`) and inspecting the stack.
4. Only then consider a gadget-based approach.

**Remember:** most `frida`/`root` strings in a decompiled APK belong to third-party SDKs' own detection lists, not to the app. Verify that **app code** references them before doing anti-anti work.

## What to capture for the record

- spawn time, hook-ready time, resume time
- every hook hit with a stack (bounded — cap output)
- DNS hosts in order, with timestamps
- the exact build under test (hash) and the control build's results
