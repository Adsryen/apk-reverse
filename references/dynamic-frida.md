# Dynamic analysis with Frida

Static analysis tells you what code exists. Frida tells you what code **runs**. When they disagree, runtime wins (`references/pitfalls.md` P10).

Use Frida when you need to answer:
- Which method actually renders this element? (static decompilation routinely misleads)
- What is the real call chain at the moment of interest?
- What does the app actually do on startup, in order?
- Which domains does it resolve, and when?
- Is the app detecting my instrumentation?

## Setup

1. **Matching versions.** The `frida` Python package on the host and `frida-server` on the device must be the same version. Mismatch produces confusing handshake failures.
2. **Run the server as root**, and give it a non-obvious name — many hardened apps look for processes/files named `frida-server`.
   ```bash
   adb push frida-server-<ver>-android-<abi> /data/local/tmp/
   adb shell "su -c 'mkdir -p /data/local/tmp/.svc'"
   adb shell "su -c 'cp -f /data/local/tmp/frida-server-<ver>-android-<abi> /data/local/tmp/.svc/kwork'"
   adb shell "su -c 'chmod 755 /data/local/tmp/.svc/kwork'"
   adb shell "su -c '/data/local/tmp/.svc/kwork' &"
   ```
3. **Keep the server alive.** Launching it through a shell that exits can get it reaped. Hold the connection open from the host (spawn it from a script that stays alive), or use a supervisor on device.
4. **Pick the right ABI** — `getprop ro.product.cpu.abi`.
5. **Spawn, don't attach, when timing matters.** Attaching usually misses startup (init, first network calls, splash logic).
   ```python
   device = frida.get_usb_device()
   pid = device.spawn([pkg])
   session = device.attach(pid)
   # ... load script, wait until hooks are installed ...
   device.resume(pid)          # only resume AFTER hooks are ready
   ```
   **Common bug:** resuming before the script has finished loading loses the first ~100–300 ms, which is exactly where init happens. Have the script `send()` a ready signal and resume only after receiving it.

## Frida 17+ gotchas

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

## Reading obfuscated code at runtime

When names are meaningless (`a7`, `x6`, `uf0`), do not patch from names. Instead:

1. Find a **unique anchor**: an API path, a preference key, or an SDK class name from the string table (`scripts/dex_strings.py`).
2. Locate the small class/method that references it (byte search in the dex + a targeted disassembly).
3. Hook that anchor, capture the **stack**, and read off the real chain.
4. Hook the classes the stack reveals — that is where semantics become visible.

## Anti-instrumentation

Signs: the app exits or freezes shortly after attach; `logcat` shows a generic process death with no Java stack; strings like `frida`, `xposed`, `magisk`, `substrate` are referenced by **app code** (not just by an SDK's string list).

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
