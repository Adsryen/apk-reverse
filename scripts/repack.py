#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repack an APK with replaced dex files, drop ONLY the signature entries, and re-sign.

Pipeline: replace dex files -> drop signature artifacts -> zip, keeping
AndroidManifest.xml and resources.arsc STORED -> zipalign + sign -> verify.

Everything machine-specific is a parameter or resolved from PATH. No JDK path is
baked in, no keystore password is baked in, no target app is assumed.

Keystore handling:
  --ks <path> is where the keystore lives. If it does not exist, one is generated
  with keytool and its password is stored next to it as <ks>.pass.txt, so the next
  run reuses it. Passwords are never hardcoded in this script. That file is a local
  artifact -- do not commit it.

Usage examples:
  # roundtrip: reuse the original dexes unchanged, proves the pipeline itself works
  python repack.py --apk work/orig.apk --dexdir work/x_orig --out work/out/roundtrip.apk

  # real patch: swap a single dex (name=path), other dexes kept from the apk
  python repack.py --apk work/orig.apk --dex classes8.dex=work/patch/classes8.dex \
      --out work/out/patched.apk

  # no signing, no java tooling required at all
  python repack.py --apk work/orig.apk --dexdir work/x_orig --out work/unsigned.apk --no-sign

Notes:
  * All java tooling is invoked through python subprocess, never through a host
    shell (PowerShell drops arguments in ways that look like tool failures).
  * uber-apk-signer silently skips already-signed apks (reports 0 processed), which
    is why signature entries are always dropped before signing.
  * uber-apk-signer is used for SIGNING to keep the verified path unchanged;
    apksigner is used for VERIFYING when present, with an explicit sdk range.
"""
import argparse
import os
import re
import secrets
import shutil
import subprocess
import sys
import zipfile

STORE_ONLY = ('AndroidManifest.xml', 'resources.arsc')


def log(msg):
    print(msg, flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, errors='replace', **kw)


# ---------------------------------------------------------------------------
# Tool resolution: PATH first, explicit flag second, never a baked-in path.
# ---------------------------------------------------------------------------
def sibling_tool(exe, name):
    """Look for `name` next to `exe`, for JDKs whose bin dir is not on PATH."""
    if not exe:
        return None
    folder = os.path.dirname(exe)
    for cand in (name, name + '.exe', name + '.bat'):
        path = os.path.join(folder, cand)
        if os.path.exists(path):
            return path
    return None


def resolve_tool(name, explicit=None, hint_exe=None):
    if explicit:
        return explicit
    found = shutil.which(name)
    if found:
        return found
    return sibling_tool(hint_exe, name)


def resolve_tools(args):
    """Locate java/keytool/jarsigner/zipalign/apksigner. Missing ones stay None."""
    java = resolve_tool('java', args.java)
    tools = {
        'java': java,
        'keytool': resolve_tool('keytool', args.keytool, java),
        'jarsigner': resolve_tool('jarsigner', args.jarsigner, java),
        'zipalign': resolve_tool('zipalign', args.zipalign),
        'apksigner': resolve_tool('apksigner', args.apksigner),
    }
    return tools


def require(tools, key, why):
    if tools.get(key):
        return tools[key]
    raise SystemExit(
        "error: '%s' was not found on PATH, and it is needed to %s.\n"
        "  install a JDK (17+ recommended) / Android build-tools and put them on PATH,\n"
        "  or pass the path explicitly (--%s <path>).\n"
        "  Path lookup is deliberate: a machine-specific absolute path must never be\n"
        "  baked into this script." % (key, why, key))


# ---------------------------------------------------------------------------
# Keystore
# ---------------------------------------------------------------------------
def read_pwd_file(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as fh:
            txt = fh.read().strip()
        return txt or None
    except OSError:
        return None


def ensure_keystore(ks_path, alias, password, keytool):
    """Return the keystore password, generating the keystore on first use."""
    pwd_file = ks_path + '.pass.txt'

    if os.path.exists(ks_path):
        pwd = password or read_pwd_file(pwd_file)
        if not pwd:
            raise SystemExit(
                'error: keystore %s exists but its password is unknown.\n'
                '  pass --ks-pass <pw>, or write the password into %s' % (ks_path, pwd_file))
        log('[ks] reuse %s (alias=%s)' % (ks_path, alias))
        return pwd

    pwd = password or read_pwd_file(pwd_file)
    generated = pwd is None
    if generated:
        # keytool rejects passwords shorter than 6 characters.
        pwd = secrets.token_urlsafe(12)

    folder = os.path.dirname(ks_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    cmd = [keytool, '-genkeypair', '-keystore', ks_path, '-alias', alias,
           '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000',
           '-storepass', pwd, '-keypass', pwd,
           '-dname', 'CN=apkreverse, OU=dev, O=dev, L=NA, ST=NA, C=NA']
    r = run(cmd)
    if r.returncode != 0:
        log('[ks] keytool failed rc=%d\n%s\n%s' % (r.returncode, r.stdout, r.stderr))
        raise SystemExit(1)

    try:
        with open(pwd_file, 'w', encoding='utf-8') as fh:
            fh.write(pwd + '\n')
        os.chmod(pwd_file, 0o600)
    except OSError as exc:
        log('[ks] could not persist the password: %s' % exc)

    log('[ks] generated %s (alias=%s)' % (ks_path, alias))
    if generated:
        log('[ks] password stored in %s -- local artifact, do not commit it' % pwd_file)
    return pwd


# ---------------------------------------------------------------------------
# Packing
# ---------------------------------------------------------------------------
def collect_replacement_dex(dexdir=None, dex_pairs=None):
    repl = {}
    if dexdir:
        for name in sorted(os.listdir(dexdir)):
            if re.match(r'^classes\d*\.dex$', name):
                repl[name] = os.path.join(dexdir, name)
    for pair in (dex_pairs or []):
        if '=' not in pair:
            raise SystemExit('--dex expects name=path, got %r' % pair)
        name, path = pair.split('=', 1)
        repl[name] = path
    return repl


def is_signature_entry(name):
    """True ONLY for JAR/APK signature artifacts directly under META-INF/.

    META-INF/services/**, META-INF/androidx/**, META-INF/native-image/** and every
    other subdirectory are RUNTIME RESOURCES and must survive repacking. Anything
    that is not directly under META-INF/ is kept by construction.
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


def build_unsigned(apk, repl, out_apk, drop_signatures=True):
    """Write a new apk with dex replaced and only signature entries dropped.

    IMPORTANT (root cause of a startup crash, do not regress):
    Stripping the WHOLE META-INF/ breaks ServiceLoader-based runtime wiring. Android
    reads these registries at runtime, and they live in the APK:
        META-INF/services/kotlinx.coroutines.internal.MainDispatcherFactory
        META-INF/services/io.ktor.client.HttpClientEngineContainer
        META-INF/services/<lib>.core.*                     (third-party SDK registries)
        META-INF/services/<obfuscated-class-name>          (R8-renamed providers)
    Deleting them makes the app die at startup with something like:
        IllegalStateException: Module with the Main dispatcher is missing ...
    and the message never points at META-INF, so the cause is very hard to find.
    Therefore: drop signature artifacts only, keep every META-INF subdirectory.
    """
    seen = set()
    replaced_names = set(repl)
    with zipfile.ZipFile(apk, 'r') as zin, zipfile.ZipFile(out_apk, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            name = item.filename
            base = os.path.basename(name)
            if item.is_dir():
                continue
            if drop_signatures and is_signature_entry(name):
                log('[zip] - %s (signature artifact)' % name)
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
            with open(path, 'rb') as fh:
                data = fh.read()
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


# ---------------------------------------------------------------------------
# Sign / verify
# ---------------------------------------------------------------------------
def sign_apk(unsigned_apk, workdir, ks, alias, password, tools, signer_jar):
    java = require(tools, 'java', 'run the signer jar')
    if not os.path.exists(signer_jar):
        raise SystemExit(
            'error: signer jar not found: %s\n'
            '  pass --signer-jar <path>, or set APK_SIGNER_JAR.\n'
            '  Any zipalign+apksigner based signer works here.' % signer_jar)

    outdir = os.path.join(workdir, 'signed')
    if os.path.isdir(outdir):
        shutil.rmtree(outdir, ignore_errors=True)
    os.makedirs(outdir, exist_ok=True)

    cmd = [java, '-jar', signer_jar,
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
        outs = [os.path.join(outdir, f) for f in os.listdir(outdir)] \
            if os.path.isdir(outdir) else []
        if not outs:
            raise SystemExit('signing produced no output')
        cand = outs[0]
    return cand


def verify_apk(apk, tools, signer_jar=None, expect_signed=True):
    log('== verify: %s' % apk)
    ok = True
    sig_checks = 0  # real signature-verification tools that actually ran

    # 1) apksigner -- the authoritative check, but ONLY with an explicit sdk range.
    #
    # READ THIS BEFORE CONCLUDING THE SIGNATURE IS BROKEN:
    # `apksigner verify` with no range checks the signature schemes implied by the
    # APK's own minSdkVersion. With minSdk >= 24 it prints v1/v2 as false while the
    # files in META-INF are perfectly fine, which looks exactly like a failed signing
    # step. Always pass --min-sdk-version / --max-sdk-version so the v1/v2/v3 results
    # are meaningful.
    if tools.get('apksigner'):
        sig_checks += 1
        r = run([tools['apksigner'], 'verify', '--print-certs', '--verbose',
                 '--min-sdk-version', '21', '--max-sdk-version', '34', apk])
        log('[verify:apksigner] rc=%d\n%s' % (r.returncode, ((r.stdout or '') +
            (r.stderr or '')).strip()[:3000]))
        if r.returncode != 0:
            ok = False
    else:
        log('[verify:apksigner] skipped: apksigner not on PATH.\n'
            '  Do NOT judge the signature from a bare `apksigner verify`: with\n'
            '  minSdk >= 24 its default range reports v1/v2 as false even when the\n'
            '  signature is valid. The correct invocation is:\n'
            '    apksigner verify --print-certs --verbose --min-sdk-version 21 '
            '--max-sdk-version 34 <apk>')

    # 2) signer jar's own verify (also re-checks alignment)
    if signer_jar and os.path.exists(signer_jar) and tools.get('java'):
        sig_checks += 1
        r = run([tools['java'], '-jar', signer_jar, '-a', apk, '-y'])
        log('[verify:signer] rc=%d\n%s' % (r.returncode, (r.stdout or '').strip()))
        if r.returncode != 0 and 'DOES NOT VERIFY' in (r.stdout or ''):
            ok = False

    # 3) jarsigner (v1 / JAR signature)
    if tools.get('jarsigner'):
        sig_checks += 1
        r = run([tools['jarsigner'], '-verify', '-certs', apk])
        txt = ((r.stdout or '') + (r.stderr or '')).strip()
        log('[verify:jarsigner] rc=%d\n%s' % (r.returncode, txt[:2000]))
        if 'jar verified' not in txt and 'verified' not in txt.lower():
            log('[verify:jarsigner] note: not reported as verified (see output above)')

    # 4) keytool cert dump
    if tools.get('keytool'):
        r = run([tools['keytool'], '-printcert', '-jarfile', apk])
        log('[verify:keytool] rc=%d\n%s' % (r.returncode, (r.stdout or '').strip()[:1500]))

    # 5) zipalign check
    if tools.get('zipalign'):
        r = run([tools['zipalign'], '-c', '-v', '4', apk])
        log('[verify:zipalign] rc=%d' % r.returncode)
        if r.returncode != 0:
            log((r.stdout or '').strip()[:1500])
    else:
        log('[verify:zipalign] skipped: zipalign not on PATH')

    # 6) v2/v3 APK Signing Block presence, read straight from the file
    with open(apk, 'rb') as fh:
        blob = fh.read()
    log('[verify:v2block] %s' % ('present' if b'APK Sig Block 42' in blob else 'MISSING'))

    # A build nobody could verify is not a passing build. Saying OK here would
    # violate the first rule of this skill ("an APK is not done until it is
    # verified"): report UNVERIFIED and fail instead.
    if expect_signed and sig_checks == 0:
        log('[result] UNVERIFIED: no signature verification tool was available '
            '(apksigner / jarsigner / signer jar). This is NOT an OK result.')
        return False
    return ok


def fingerprint(apk, tools):
    if not tools.get('keytool'):
        return []
    r = run([tools['keytool'], '-printcert', '-jarfile', apk])
    return re.findall(r'(SHA1|SHA256):\s*([0-9A-F:]+)', r.stdout or '')


def main():
    ap = argparse.ArgumentParser(
        description='Repack an APK with replaced dex files, drop only the signature '
                    'entries, re-sign and verify.')
    ap.add_argument('--apk', required=True, help='source apk to use as the template')
    ap.add_argument('--out', required=True, help='output apk path')
    ap.add_argument('--dexdir', help='directory of classes*.dex to swap in')
    ap.add_argument('--dex', action='append', default=[],
                    help='name=path, repeatable, e.g. classes8.dex=work/patch/classes8.dex')
    ap.add_argument('--workdir', default=None,
                    help='scratch directory (default: next to --out)')
    ap.add_argument('--ks', default=None, help='keystore path (created on first use)')
    ap.add_argument('--ks-alias', default='apkreverse', help='keystore alias')
    ap.add_argument('--ks-pass', default=None,
                    help='keystore password; default: <ks>.pass.txt, else generated')
    ap.add_argument('--signer-jar', default=None,
                    help='jar used for zipalign+sign (default: $APK_SIGNER_JAR or '
                         'uber-apk-signer.jar)')
    ap.add_argument('--no-sign', action='store_true', help='stop after writing the apk')
    ap.add_argument('--java', default=None, help='path to java (default: from PATH)')
    ap.add_argument('--keytool', default=None, help='path to keytool (default: from PATH)')
    ap.add_argument('--jarsigner', default=None, help='path to jarsigner (default: from PATH)')
    ap.add_argument('--zipalign', default=None, help='path to zipalign (default: from PATH)')
    ap.add_argument('--apksigner', default=None, help='path to apksigner (default: from PATH)')
    args = ap.parse_args()

    tools = resolve_tools(args)
    signer_jar = args.signer_jar or os.environ.get('APK_SIGNER_JAR', 'uber-apk-signer.jar')

    apk = os.path.abspath(args.apk)
    out = os.path.abspath(args.out)
    if not os.path.exists(apk):
        raise SystemExit('missing apk: %s' % apk)

    # Default the scratch dir next to --out; never to a machine-specific path.
    workdir = os.path.abspath(args.workdir) if args.workdir else os.path.dirname(out)
    if not workdir:
        workdir = os.getcwd()
    os.makedirs(workdir, exist_ok=True)
    out_folder = os.path.dirname(out)
    if out_folder:
        os.makedirs(out_folder, exist_ok=True)

    repl = collect_replacement_dex(args.dexdir, args.dex)
    log('[in ] %s (%d bytes)' % (apk, os.path.getsize(apk)))
    log('[tools] java=%s keytool=%s apksigner=%s zipalign=%s'
        % (tools['java'], tools['keytool'], tools['apksigner'], tools['zipalign']))
    log('[repl] %s' % (', '.join('%s<-%s' % (k, v) for k, v in sorted(repl.items())) or '<none>'))

    unsigned = os.path.join(workdir, 'unsigned.apk')
    if os.path.exists(unsigned):
        os.remove(unsigned)
    build_unsigned(apk, repl, unsigned)
    log('[zip] unsigned written: %d bytes' % os.path.getsize(unsigned))
    for row in zip_report(unsigned):
        log('[zip]   ' + row)

    if args.no_sign:
        shutil.copy2(unsigned, out)
    else:
        if not args.ks:
            raise SystemExit(
                "error: --ks is required when signing (there is no default keystore).\n"
                "  e.g. --ks work/out/release.keystore")
        keytool = require(tools, 'keytool', 'create the keystore on first use')
        password = ensure_keystore(os.path.abspath(args.ks), args.ks_alias,
                                   args.ks_pass, keytool)
        signed = sign_apk(unsigned, workdir, os.path.abspath(args.ks), args.ks_alias,
                          password, tools, signer_jar)
        shutil.copy2(signed, out)

    log('[out] %s (%d bytes)' % (out, os.path.getsize(out)))
    log('== zip layout of final apk')
    for row in zip_report(out):
        log('   ' + row)

    ok = verify_apk(out, tools, signer_jar, expect_signed=not args.no_sign)
    if not args.no_sign:
        for algo, val in fingerprint(out, tools):
            log('[cert] %s %s' % (algo, val))
        log('[result] %s' % ('OK' if ok else 'CHECK-FAILED'))
    else:
        log('[result] UNSIGNED (--no-sign): good for inspection, not installable as-is')
    log('[reminder] repacking is not done until the app launches and the changed '
        'behavior is exercised on a device: see scripts/install_test.py')
    return 0 if ok else 2


if __name__ == '__main__':
    sys.exit(main())
