#!/usr/bin/env python3
"""Spawn a target under a Frida probe, DETACH, and only then drive its UI.

Why this exists
---------------
Under spawn mode (`frida -f`, or `device.spawn()` + `resume()`) the target is paused
while the script loads and resumed by us. On several real targets the Activity stack
never comes up in that state: `dumpsys window | grep mCurrentFocus` stays `null`,
screenshots come back blank, and the app looks broken when it is merely unrendered.
The same app launched normally, after Frida has left, renders correctly.

The fix is an ordering rather than a different hook:

  1. spawn and attach,
  2. let the probe write its patch into memory (``Memory.patchCode``),
  3. **detach** -- the write is a plain memory write and survives; ``Interceptor``
     hooks go away with the session, which is usually what you want for an
     observation run because it removes the instrumentation from the picture,
  4. start the Activity normally and capture.

What the probe may contain
--------------------------
Anything self-contained. A minimal probe that only neutralises a death site and
sends ``PATCHED`` when done is ``hook_patch_only.js`` beside this script; a probe
that also blocks a component or traces calls works too, but remember that its
``Interceptor`` hooks stop at detach while its memory writes do not.

Requirements
------------
A reachable frida-server (``frida-server -l 127.0.0.1:27099`` plus
``adb forward tcp:27099 tcp:27099``), and ``frida`` importable from the same
interpreter. ``adb`` is used only for the device-side steps and for screenshots.
"""
import argparse
import subprocess
import sys
import time

try:
    import frida
except ImportError:  # keep --help working on a machine without frida
    frida = None

DEFAULT_ADB = "adb"


def build_parser():
    p = argparse.ArgumentParser(
        prog="spawn_patch_detach.py",
        description="Spawn under a Frida probe, detach, then launch and capture the "
                    "app so the UI actually renders.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n"
               "  spawn_patch_detach.py --package com.example.app --js probe.js \\\n"
               "      --activity com.example.app/.MainActivity --captures 3\n")
    p.add_argument("--package", required=True, help="target package name")
    p.add_argument("--js", required=True, help="Frida probe script to load before resume")
    p.add_argument("--activity", default=None,
                   help="component to start after detach, as pkg/.Activity "
                        "(default: let the package start its own launcher)")
    p.add_argument("--frida-host", default="127.0.0.1:27099",
                   help="host:port of the device frida-server (default %(default)s)")
    p.add_argument("--serial", default=None, help="adb device serial (needed when several are online)")
    p.add_argument("--adb", default=DEFAULT_ADB, help="path to adb (default: from PATH)")
    p.add_argument("--wait-patched", type=float, default=15.0,
                   help="seconds to wait for the probe to report PATCHED (default %(default)s)")
    p.add_argument("--detach-settle", type=float, default=3.0,
                   help="pause after detach, before launching (default %(default)s)")
    p.add_argument("--captures", type=int, default=3, help="number of screenshots (default %(default)s)")
    p.add_argument("--interval", type=float, default=18.0,
                   help="seconds between captures (default %(default)s)")
    p.add_argument("--out-prefix", default="capture",
                   help="local filename prefix for screenshots (default %(default)s)")
    p.add_argument("--work-dir", default="/data/local/tmp",
                   help="device-side scratch directory (default %(default)s)")
    p.add_argument("--no-screencap", action="store_true", help="skip screenshots")
    return p


def adb_run(args, adb, serial, timeout=200):
    cmd = [adb] + (["-s", serial] if serial else []) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def root_shell(cmd, adb, serial, timeout=200):
    return adb_run(["shell", "su -c '%s'" % cmd], adb, serial, timeout)


def main(argv=None):
    args = build_parser().parse_args(argv)

    if frida is None:
        print("[!] the 'frida' python package is not importable; install it with "
              "'pip install frida' (host side)", file=sys.stderr)
        return 2

    patched = {"done": False}

    def on_message(msg, data):
        if msg.get("type") == "send":
            payload = msg.get("payload")
            print("[MSG] %s" % payload, flush=True)
            if payload == "PATCHED":
                patched["done"] = True
        elif msg.get("type") == "error":
            print("[ERR] %s" % (msg.get("stack") or msg.get("description")), flush=True)
        else:
            print("[%s] %s" % (msg.get("type", "?").upper(), msg.get("payload")), flush=True)

    adb_run(["shell", "su -c 'am force-stop %s'" % args.package], args.adb, args.serial)
    time.sleep(1.5)

    dev = frida.get_device_manager().add_remote_device(args.frida_host)
    pid = dev.spawn([args.package])
    print("[i] spawned pid=%d" % pid, flush=True)

    session = dev.attach(pid)
    script = session.create_script(open(args.js, encoding="utf-8").read())
    script.on("message", on_message)
    script.load()
    dev.resume(pid)

    deadline = time.time() + args.wait_patched
    while time.time() < deadline and not patched["done"]:
        time.sleep(0.2)
    print("[i] patched=%s" % patched["done"], flush=True)

    time.sleep(1.0)
    session.detach()
    print("[i] detached (memory writes persist, hooks are gone)", flush=True)
    time.sleep(args.detach_settle)

    if args.activity:
        out = adb_run(["shell", "am start -n %s" % args.activity], args.adb, args.serial)
        print("[i] am start: %s" % ((out.stdout or out.stderr or "").strip()), flush=True)

    for i in range(max(1, args.captures)):
        time.sleep(args.interval)
        print("\n=== capture %d ===" % i, flush=True)
        ps = adb_run(["shell", "ps -A -o PID,ETIME,ARGS | grep -i %s" % args.package.split(".")[-1]],
                     args.adb, args.serial)
        print((ps.stdout or "").strip(), flush=True)
        focus = adb_run(["shell", "dumpsys window | grep mCurrentFocus"], args.adb, args.serial)
        print((focus.stdout or "").strip(), flush=True)
        if not args.no_screencap:
            remote = "%s/%s_%d.png" % (args.work_dir, args.out_prefix, i)
            adb_run(["shell", "screencap -p %s" % remote], args.adb, args.serial)
            local = "%s_%d.png" % (args.out_prefix, i)
            adb_run(["pull", remote, local], args.adb, args.serial)
            print("[i] screenshot -> %s" % local, flush=True)

    print("\n[i] inspect the images; do not conclude from logcat alone.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
