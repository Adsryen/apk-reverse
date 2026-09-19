#!/usr/bin/env python3
"""Environment doctor: what can actually run here, and what is missing.

Why this exists
---------------
This skill ships a lot of scripts, and the most common failure mode reported by
users is not "the script is wrong" but "the script would not start and I could not
tell why" - a missing jar, a Python module that does not exist on this interpreter,
a device that is not connected. That wastes a whole round before any reverse
engineering happens.

Run this once before a work block. It answers three questions:

  1. Which capabilities are available right now (static / native / dynamic / device)?
  2. For every script, is it runnable as-is, or what exactly is missing?
  3. Are there environment facts that will silently poison experiments
     (clock skew, a leftover proxy, a dead device server, a wrong-ABI device)?

It never installs anything and never touches a target. Read the report, then go.

Usage
-----
    python doctor.py                     # short capability report
    python doctor.py --scripts           # per-script runnability table
    python doctor.py --device <serial>   # include device checks
    python doctor.py --json              # machine-readable
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- probing

def extra_tool_dirs():
    """Directories to search beyond PATH.

    Tools like jadx and apktool are frequently installed into a project-local or
    versioned directory and invoked by full path, so a pure PATH probe reports them
    missing and the capability table lies. Point APKREV_TOOLS at one or more
    directories (os.pathsep-separated) and they are searched too.
    """
    dirs = []
    env = os.environ.get('APKREV_TOOLS')
    if env:
        dirs.extend(d for d in env.split(os.pathsep) if d)
    # a tools/ dir beside the skill is a common convention and safe to probe
    dirs.append(os.path.join(os.path.dirname(HERE), 'tools'))
    return [d for d in dirs if os.path.isdir(d)]


def which(name: str):
    hit = shutil.which(name)
    if hit:
        return hit
    exts = ['']
    if os.name == 'nt':
        exts = ['.exe', '.bat', '.cmd', '.ps1', '']
    for d in extra_tool_dirs():
        for root, _dirs, files in os.walk(d):
            if root.count(os.sep) - d.count(os.sep) > 3:
                continue
            for f in files:
                stem, ext = os.path.splitext(f)
                if stem.lower() == name.lower() and ext.lower() in exts:
                    return os.path.join(root, f)
    return None


def run(cmd, timeout=15):
    """Run a command, returning (rc, stdout+stderr). Never raises, always bounded."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout)
        return p.returncode, p.stdout.decode('utf-8', 'replace').strip()
    except FileNotFoundError:
        return 127, 'not found'
    except subprocess.TimeoutExpired:
        return 124, 'TIMEOUT after %ss' % timeout
    except Exception as e:  # pragma: no cover
        return 1, '%s: %s' % (type(e).__name__, e)


def have_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


# ---------------------------------------------------------------- capability matrix

def python_info():
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 9)
    return {
        'version': '%d.%d.%d' % (v.major, v.minor, v.micro),
        'ok': ok,
        'note': '' if ok else 'scripts target 3.9+; older interpreters may fail on syntax',
    }


def tool_info():
    """name -> (found_path, version_string)"""
    out = {}
    probes = [
        ('java', ['java', '-version']),
        ('javac', ['javac', '-version']),
        ('adb', ['adb', 'version']),
        ('frida', ['frida', '--version']),
        ('frida-ps', ['frida-ps', '--version']),
        ('objection', ['objection', '--version']),
        ('apktool', ['apktool', '--version']),
        ('jadx', ['jadx', '--version']),
        ('python', [sys.executable, '--version']),
        ('unzip', ['unzip', '-v']),
        ('git', ['git', '--version']),
        ('sqlite3', ['sqlite3', '--version']),
        ('node', ['node', '--version']),
        ('tshark', ['tshark', '-v']),
        ('mitmdump', ['mitmdump', '--version']),
        ('rizin', ['rizin', '-v']),
        ('rabin2', ['rabin2', '-v']),
        ('gdb', ['gdb', '--version']),
        ('readelf', ['readelf', '--version']),
        ('adb-devices', ['adb', 'devices']),
    ]
    for name, cmd in probes:
        if which(cmd[0]) is None and cmd[0] != sys.executable:
            # A tool that ships as a runnable .jar is not on PATH but is still usable
            # via `java -jar`. Reporting it as missing makes the capability table lie.
            jar_hit = None
            for d in [HERE, os.path.dirname(HERE)] + extra_tool_dirs():
                if not os.path.isdir(d):
                    continue
                for root, _dirs, files in os.walk(d):
                    if root.count(os.sep) - d.count(os.sep) > 3:
                        continue
                    for f in files:
                        if f.lower() == (name + '.jar').lower():
                            jar_hit = os.path.join(root, f)
                            break
                    if jar_hit:
                        break
                if jar_hit:
                    break
            if jar_hit:
                out[name] = {'path': jar_hit,
                             'version': 'runnable as: java -jar %s' % os.path.basename(jar_hit),
                             'note': 'jar-only (not a PATH command)'}
            else:
                out[name] = {'path': None, 'version': None, 'note': 'not on PATH'}
            continue
        rc, txt = run(cmd)
        first = ''
        for line in txt.splitlines():
            line = line.strip()
            if line:
                first = line
                break
        out[name] = {
            'path': which(cmd[0]) or cmd[0],
            'version': first[:160],
            'note': '' if rc == 0 else 'exit %d: %s' % (rc, txt[:120]),
        }
    return out


# jar/libraries the dex tooling needs; kept as a list so doctor can name them
JAR_HINTS = ['baksmali', 'smali', 'dexlib2', 'apksigner', 'uber-apk-signer', 'd2j']


def java_toolchain():
    """Find the jars a smali round-trip needs, wherever they live."""
    found = {}
    roots = [os.path.join(HERE, 'dexpatch'), HERE,
             os.path.join(HERE, 'libs'), os.path.join(HERE, 'jar')]
    extra = os.environ.get('APKREV_JARS')
    if extra:
        roots.extend(extra.split(os.pathsep))
    for r in roots:
        if not os.path.isdir(r):
            continue
        for dirpath, _dirs, files in os.walk(r):
            for f in files:
                if f.lower().endswith('.jar'):
                    found.setdefault(f, os.path.join(dirpath, f))
    return found


def script_dependencies():
    """Static, best-effort dependency map: script -> (required_modules, required_bins)."""
    return {
        'smtool.py': ([], ['java']),
        'patch_smali.py': ([], []),
        'find_refs.py': ([], []),
        'dex_strings.py': ([], []),
        'dex_classdiff.py': ([], []),
        'dex_strpatch.py': ([], []),
        'repack.py': ([], ['java']),
        'install_test.py': ([], ['adb']),
        'preflight.py': ([], ['adb']),
        'lib_map.py': ([], ['adb']),
        'apk_diff.py': ([], []),
        'snap.py': ([], ['adb']),
        'native_crash.py': ([], []),
        'grab_crash.py': ([], ['adb']),
        'blob_decode.py': ([], []),
        'datastore_inject.py': ([], []),
        'sig_probe.py': ([], ['java']),
        'probe_api.py': ([], []),
        'tls_check.py': ([], []),
        'usb_net_proxy.py': ([], ['adb']),
        'devsh.py': ([], ['adb']),
        'elf_plt.py': ([], []),
        'so_constpatch.py': ([], []),
        'dart_pool_strings.py': ([], []),
        'dart_pprefs.py': ([], []),
        'dart_disasm.py': ([], []),
        'run_probe.py': (['frida'], ['adb']),
        'frida_probe.js': ([], []),  # needs a frida host, checked separately
    }


def script_report(tools, jars):
    deps = script_dependencies()
    rows = []
    for name in sorted(deps):
        path = os.path.join(HERE, name)
        mods, bins = deps[name]
        missing_mods = [m for m in mods if not have_module(m)]
        missing_bins = [b for b in bins if which(b) is None]
        # scripts that shell out to the frida host
        if name in ('run_probe.py', 'frida_probe.js') and which('frida') is None:
            if 'frida' not in missing_bins:
                missing_bins.append('frida')
        ok = os.path.isfile(path) and not missing_mods and not missing_bins
        rows.append({
            'script': name,
            'present': os.path.isfile(path),
            'runnable': ok,
            'missing': missing_mods + missing_bins,
        })
    return rows, deps


def device_report(serial=None):
    if which('adb') is None:
        return {'available': False, 'reason': 'adb not on PATH'}
    cmd = ['adb'] + (['-s', serial] if serial else []) + ['devices', '-l']
    rc, txt = run(cmd, timeout=20)
    if rc != 0:
        return {'available': False, 'reason': txt[:200]}
    devices = []
    for line in txt.splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith('*'):
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append({'serial': parts[0], 'state': parts[1],
                            'info': ' '.join(parts[2:])[:160]})
    out = {'available': True, 'devices': devices, 'raw': txt[:400]}
    if not devices:
        out['reason'] = 'no device/emulator attached'
        return out

    tgt = serial or devices[0]['serial']
    props = {}
    for key in ('ro.product.cpu.abi', 'ro.product.cpu.abilist', 'ro.build.version.release',
                'ro.build.version.sdk', 'ro.product.model'):
        rc, v = run(['adb', '-s', tgt, 'shell', 'getprop', key], timeout=15)
        props[key] = v if rc == 0 else ''
    out['target'] = tgt
    out['props'] = props

    # root?
    rc, v = run(['adb', '-s', tgt, 'shell', 'su -c id'], timeout=15)
    out['root'] = (rc == 0 and 'uid=0' in v)
    out['root_raw'] = v[:120]

    # clock skew: a classic silent experiment-poisoner
    rc, dev_epoch = run(['adb', '-s', tgt, 'shell', 'date +%s'], timeout=15)
    try:
        dev_t = int(dev_epoch.strip())
        out['clock_skew_s'] = abs(time.time() - dev_t)
    except Exception:
        out['clock_skew_s'] = None

    # leftover forwards and proxies
    rc, fwd = run(['adb', '-s', tgt, 'forward', '--list'], timeout=15)
    out['forwards'] = [l for l in fwd.splitlines() if l.strip()][:10]
    rc, prox = run(['adb', '-s', tgt, 'shell', 'settings get global http_proxy'], timeout=15)
    out['http_proxy'] = prox.strip()[:120]

    # is a frida server already running on device? (a common source of "the app
    # suddenly detects instrumentation" while you believe nothing is attached)
    rc, ps = run(['adb', '-s', tgt, 'shell', 'ps -A'], timeout=20)
    hits = [l for l in ps.splitlines()
            if 'frida' in l.lower() and 'grep' not in l.lower()]
    out['device_frida_processes'] = [h.strip()[:140] for h in hits[:6]]
    return out


# ---------------------------------------------------------------- reporting

def capability_summary(tools, dev, py):
    caps = {}
    caps['static (dex/zip/strings)'] = py['ok']
    caps['repack + sign'] = bool(tools['java']['path']) and py['ok']
    caps['smali round-trip'] = bool(tools['java']['path']) and py['ok']
    caps['native ELF patching'] = py['ok']
    caps['jadx decompile'] = bool(tools['jadx']['path'])
    caps['apktool unpack'] = bool(tools['apktool']['path'])
    caps['device work'] = bool(dev.get('available') and dev.get('devices'))
    caps['root on device'] = bool(dev.get('root'))
    caps['frida dynamic'] = bool(tools['frida']['path'])
    caps['emulator/home'] = bool(tools['adb']['path'])
    return caps


def main():
    ap = argparse.ArgumentParser(description='Check what this environment can actually do.')
    ap.add_argument('--device', default=None, metavar='SERIAL', help='probe this device')
    ap.add_argument('--scripts', action='store_true', help='per-script runnability table')
    ap.add_argument('--json', action='store_true', help='emit JSON')
    args = ap.parse_args()

    py = python_info()
    tools = tool_info()
    jars = java_toolchain()
    dev = device_report(args.device)
    rows, _deps = script_report(tools, jars)
    caps = capability_summary(tools, dev, py)

    if args.json:
        print(json.dumps({'python': py, 'tools': tools, 'jars': jars,
                          'device': dev, 'capabilities': caps, 'scripts': rows},
                         indent=2, ensure_ascii=False))
        return 0

    print('=' * 74)
    print('apk-reverse environment doctor')
    print('=' * 74)
    print('platform : %s %s / %s' % (platform.system(), platform.release(), platform.machine()))
    print('python   : %s  %s' % (py['version'], '' if py['ok'] else '<-- ' + py['note']))

    print('\n--- capabilities ---')
    for k, v in caps.items():
        print('  [%s] %s' % ('OK ' if v else '-- ', k))

    print('\n--- tools ---')
    for name, info in tools.items():
        if name in ('adb-devices',):
            continue
        mark = 'OK ' if info['path'] else '-- '
        ver = info['version'] or info['note']
        print('  [%s] %-12s %s' % (mark, name, (ver or '')[:96]))

    print('\n--- java jars found near this skill ---')
    if jars:
        for k, v in sorted(jars.items()):
            print('  %s' % k)
    else:
        print('  (none) - a smali round-trip needs baksmali/smali/dexlib2 jars.')
        print('  Set APKREV_JARS=<dir-with-jars> to point this script at them.')

    print('\n--- device ---')
    if not dev.get('available'):
        print('  unavailable: %s' % dev.get('reason'))
    elif not dev.get('devices'):
        print('  no device attached (adb works)')
    else:
        print('  target   : %s' % dev.get('target'))
        for k, v in (dev.get('props') or {}).items():
            print('  %-9s: %s' % (k.replace('ro.', ''), v))
        print('  root     : %s' % ('yes' if dev.get('root') else 'no'))
        skew = dev.get('clock_skew_s')
        if skew is not None:
            flag = ' <-- FIX THIS, clock drift poisons time-based checks' if skew > 30 else ''
            print('  clock skew: %ss%s' % (skew, flag))
        if dev.get('forwards'):
            print('  leftovers : adb forward entries still present: %s' % dev['forwards'])
        if dev.get('http_proxy', '').strip() not in ('', 'null', ':0'):
            print('  leftovers : device http_proxy = %s' % dev['http_proxy'])
        if dev.get('device_frida_processes'):
            print('  WARNING   : a frida process is already running on device:')
            for p in dev['device_frida_processes']:
                print('              %s' % p)
            print('              If the target dies only while this is up, you are looking at')
            print('              a probe aimed at YOU. Stop it before concluding anything.')

    if args.scripts:
        print('\n--- scripts ---')
        ready = [r for r in rows if r['runnable']]
        notready = [r for r in rows if not r['runnable']]
        for r in ready:
            print('  [OK ] %s' % r['script'])
        for r in notready:
            why = []
            if not r['present']:
                why.append('file missing')
            if r['missing']:
                why.append('missing: ' + ', '.join(r['missing']))
            print('  [-- ] %-24s %s' % (r['script'], '; '.join(why)))
        print('\n  runnable: %d / %d' % (len(ready), len(rows)))
    else:
        ready = sum(1 for r in rows if r['runnable'])
        print('\n  scripts runnable here: %d / %d  (use --scripts for the table)'
              % (ready, len(rows)))

    print('\nRead references/long-task-discipline.md before a long block:')
    print('  bound every wait, look at the screen while you wait, and record the '
          'time-to-death before patching.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
