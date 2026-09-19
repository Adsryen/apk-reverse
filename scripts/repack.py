#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repack + resign pipeline for the ciyuan Android app.

Pipeline: replace dex files -> strip META-INF/ -> zip (AndroidManifest.xml and
resources.arsc kept STORED) -> zipalign + sign via uber-apk-signer -> verify.

Keystore defaults (generated on first use with keytool):
    file   : <work>/out/cyc.keystore
    alias  : cyc
    storepass / keypass : cyc123456

Usage examples:
  # roundtrip: reuse original dexes unchanged, proves the pipeline itself works
  python tools/repack.py --apk work/orig.apk --dexdir work/x_orig --out work/out/roundtrip.apk

  # real patch: swap a single dex (name=path), other dexes kept from the apk
  python tools/repack.py --apk work/orig.apk --dex classes8.dex=work/x_orig/patch/classes8.dex \
      --out work/out/patched.apk

Notes:
  * All java tooling is invoked through python subprocess (never through the
    PowerShell argument passing path, which drops arguments).
  * uber-apk-signer silently skips already signed apks (reports 0 processed),
    which is why META-INF/ is always stripped before signing.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile

JAVA = r'C:\Program Files\Java\jdk-17.0.4.1\bin\java.exe'
KEYTOOL = r'C:\Program Files\Java\jdk-17.0.4.1\bin\keytool.exe'
JARSIGNER = r'C:\Program Files\Java\jdk-17.0.4.1\bin\jarsigner.exe'
SIGNER_JAR = os.environ.get('APK_SIGNER_JAR', 'uber-apk-signer.jar')

KS_PATH = None  # pass --ks on the command line
KS_ALIAS = os.environ.get('APK_KS_ALIAS', 'apkreverse')
KS_PASS = os.environ.get('APK_KS_PASS', '')

STORE_ONLY = ('AndroidManifest.xml', 'resources.arsc')


def log(msg):
    print(msg, flush=True)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, errors='replace', **kw)
    return r


def ensure_keystore(path=KS_PATH, alias=KS_ALIAS, password=KS_PASS):
    if os.path.exists(path):
        log('[ks] reuse %s' % path)
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cmd = [KEYTOOL, '-genkeypair', '-keystore', path, '-alias', alias,
           '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000',
           '-storepass', password, '-keypass', password,
           '-dname', 'CN=apkreverse, OU=dev, O=dev, L=NA, ST=NA, C=NA']
    r = run(cmd)
    if r.returncode != 0:
        log('[ks] keytool failed rc=%d\n%s\n%s' % (r.returncode, r.stdout, r.stderr))
        raise SystemExit(1)
    log('[ks] generated %s (alias=%s pass=%s)' % (path, alias, password))
    return path


def collect_replacement_dex(dexdir=None, dex_pairs=None):
    repl = {}
    if dexdir:
        for name in sorted(os.listdir(dexdir)):
            if re.match(r'^classes\d*\.dex$', name):
                repl[name] = os.path.join(dexdir, name)
    for pair in (dex_pairs or []):
        if '=' not in pair:
            raise SystemExit('--dex expects name=path, got %r' % pair)
        name, p = pair.split('=', 1)
        repl[name] = p
    return repl


def is_signature_entry(name):
    """True only for JAR/APK signature artifacts directly under META-INF/.

    META-INF/services/**, META-INF/androidx/**, META-INF/native-image/** and all
    other subdirectories are RUNTIME RESOURCES and must survive repacking.
    """
    if not name.upper().startswith('META-INF/'):
        return False
    rest = name[len('META-INF/'):]
    if '/' in rest:
        return False
    up = rest.upper()
    if up == 'MANIFEST.MF':
        return True
    return up.endswith(('.SF', '.RSA', '.DSA', '.EC'))


def build_unsigned(apk, repl, out_apk, drop_meta=True):
    """Write a new apk with dex replaced and only signature entries dropped.

    IMPORTANT (root cause of a crash, do not regress):
    Stripping the WHOLE META-INF/ breaks ServiceLoader-based runtime wiring.
    This APK ships ServiceLoader registrations that Android reads at runtime:
        META-INF/services/kotlinx.coroutines.internal.MainDispatcherFactory -> kc
        META-INF/services/io.ktor.client.HttpClientEngineContainer -> OkHttpEngineContainer
        META-INF/services/io.ktor.serialization.kotlinx.KotlinxSerializationExtensionProvider
        META-INF/services/kotlinx.coroutines.CoroutineExceptionHandler -> wc
        META-INF/services/com.arialyy.aria.* , META-INF/services/wt2 , META-INF/services/xx1
    Deleting them makes the app die at startup with:
        IllegalStateException: Module with the Main dispatcher is missing ...
    So only signature artifacts are removed here; META-INF subdirectories are kept.
    """
    seen = set()
    replaced_names = set(repl)
    with zipfile.ZipFile(apk, 'r') as zin, zipfile.ZipFile(out_apk, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            name = item.filename
            base = os.path.basename(name)
            if item.is_dir():
                continue
            if drop_meta and is_signature_entry(name):
                continue
            if name in replaced_names:
                continue
            data = zin.read(name)
            keep = name in STORE_ONLY or base in STORE_ONLY
            zi = zipfile.ZipInfo(name, date_time=item.date_time)
            zi.compress_type = zipfile.ZIP_STORED if keep else zipfile.ZIP_DEFLATED
            zi.external_attr = item.external_attr
            zi.internal_attr = item.internal_attr
            zi.create_system = item.create_system
            zout.writestr(zi, data)
            seen.add(name)
        for name, path in sorted(repl.items()):
            with open(path, 'rb') as f:
                data = f.read()
            zi = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(zi, data)
            log('[zip] + %s  (%d bytes <- %s)' % (name, len(data), path))
            seen.add(name)
    return seen


def zip_report(apk):
    rows = []
    with zipfile.ZipFile(apk, 'r') as z:
        for i in z.infolist():
            if i.filename in STORE_ONLY or os.path.basename(i.filename) in STORE_ONLY:
                rows.append('%s method=%d (0=STORED)' % (i.filename, i.compress_type))
            if re.match(r'^classes\d*\.dex$', i.filename):
                rows.append('%s %d bytes method=%d crc=%08x' % (
                    i.filename, i.file_size, i.compress_type, i.CRC))
    return rows


def sign_apk(unsigned_apk, workdir, ks, alias=KS_ALIAS, password=KS_PASS):
    outdir = os.path.join(workdir, 'signed')
    if os.path.isdir(outdir):
        shutil.rmtree(outdir, ignore_errors=True)
    os.makedirs(outdir, exist_ok=True)
    cmd = [JAVA, '-jar', SIGNER_JAR,
           '--apks', unsigned_apk,
           '--ks', ks, '--ksAlias', alias,
           '--ksPass', password, '--ksKeyPass', password,
           '-o', outdir, '--verbose']
    r = run(cmd)
    log('[sign] rc=%d' % r.returncode)
    log(r.stdout.strip())
    if r.stderr.strip():
        log('[sign][stderr] ' + r.stderr.strip())
    cand = os.path.join(outdir, os.path.basename(unsigned_apk))
    if not os.path.exists(cand):
        outs = [os.path.join(outdir, f) for f in os.listdir(outdir)] if os.path.isdir(outdir) else []
        if not outs:
            raise SystemExit('signing produced no output')
        cand = outs[0]
    return cand, r.stdout


def verify_apk(apk):
    log('== verify: %s' % apk)
    ok = True
    # 1) uber-apk-signer verify (also re-checks zipalign)
    r = run([JAVA, '-jar', SIGNER_JAR, '-a', apk, '-y'])
    log('[verify:signer] rc=%d\n%s' % (r.returncode, r.stdout.strip()))
    if r.returncode != 0 or 'Verified' not in r.stdout:
        ok = ok and ('DOES NOT VERIFY' not in r.stdout)
    # 2) jarsigner (v1 / jAR signature)
    r2 = run([JARSIGNER, '-verify', '-certs', apk])
    txt = (r2.stdout or '') + (r2.stderr or '')
    log('[verify:jarsigner] rc=%d\n%s' % (r2.returncode, txt.strip()[:2000]))
    # 3) keytool cert dump
    r3 = run([KEYTOOL, '-printcert', '-jarfile', apk])
    log('[verify:keytool] rc=%d\n%s' % (r3.returncode, r3.stdout.strip()[:1500]))
    # 4) v2/v3 APK Signing Block presence
    with open(apk, 'rb') as f:
        blob = f.read()
    has_v2 = b'APK Sig Block 42' in blob
    log('[verify:v2block] %s' % ('present' if has_v2 else 'MISSING'))
    return ok and (r.returncode == 0)


def fingerprint(apk):
    r = run([KEYTOOL, '-printcert', '-jarfile', apk])
    sha = re.findall(r'(SHA1|SHA256):\s*([0-9A-F:]+)', r.stdout)
    return sha


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apk', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--dexdir')
    ap.add_argument('--dex', action='append', default=[], help='name=path, repeatable')
    ap.add_argument('--ks', default=KS_PATH)
    ap.add_argument('--no-sign', action='store_true')
    ap.add_argument('--workdir', default=None)
    args = ap.parse_args()

    apk = os.path.abspath(args.apk)
    out = os.path.abspath(args.out)
    if not os.path.exists(apk):
        raise SystemExit('missing apk: %s' % apk)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    os.makedirs(args.workdir, exist_ok=True)

    repl = collect_replacement_dex(args.dexdir, args.dex)
    log('[in ] %s (%d bytes)' % (apk, os.path.getsize(apk)))
    log('[repl] %s' % ', '.join('%s<-%s' % (k, v) for k, v in sorted(repl.items())))

    unsigned = os.path.join(args.workdir, 'unsigned.apk')
    if os.path.exists(unsigned):
        os.remove(unsigned)
    build_unsigned(apk, repl, unsigned)
    log('[zip] unsigned written: %d bytes' % os.path.getsize(unsigned))
    for row in zip_report(unsigned):
        log('[zip]   ' + row)

    if args.no_sign:
        shutil.copy2(unsigned, out)
    else:
        ks = ensure_keystore(args.ks)
        signed, _ = sign_apk(unsigned, args.workdir, ks)
        shutil.copy2(signed, out)

    log('[out] %s (%d bytes)' % (out, os.path.getsize(out)))
    log('== zip layout of final apk')
    for row in zip_report(out):
        log('   ' + row)
    ok = verify_apk(out)
    sha = fingerprint(out)
    for algo, val in sha:
        log('[cert] %s %s' % (algo, val))
    log('[result] %s' % ('OK' if ok else 'CHECK-FAILED'))
    return 0 if ok else 2


if __name__ == '__main__':
    sys.exit(main())
