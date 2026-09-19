#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sync a script directory to a publish location, and audit it for machine-specific leftovers.

WHY THIS EXISTS
---------------
An Agent Skill gets copied across machines and across runtimes (Claude Code, Codex,
DeepSeek Harness). Anything machine-specific that survives the copy becomes a
landmine: a baked-in JDK path, a keystore password, a home directory that only
exists on the author's box. This tool does two things:

  1. AUDIT (default, read-only): report every absolute-path literal and every
     credential-looking constant, with file and line number.
  2. SYNC (--apply): copy matching files to the destination, optionally after
     neutralising the absolute-path literals it found (--scrub).

The audit is the default on purpose: a silent copy is exactly how the leftovers
travel from the author's machine into someone else's first run.

USAGE
-----
  python build_scripts.py scripts2 out                  # audit only, nothing written
  python build_scripts.py scripts out --apply           # copy
  python build_scripts.py scripts out --apply --scrub   # copy, neutralising abs paths
  python build_scripts.py scripts out --pattern '*.py' --pattern '*.js'

Exit codes: 0 = clean, 2 = findings reported (audit mode), 1 = usage or IO error.

NOTES
-----
  * A finding is a heuristic, not a verdict: `/data/local/tmp/...` is a legitimate
    Android device path and is deliberately NOT reported; a drive-letter path is.
  * --scrub rewrites `'<abs path>'` literals into `''`, which keeps the file
    syntactically valid but leaves the decision (and the fix) to a human. It never
    runs unless --apply is also given.
"""
import argparse
import fnmatch
import os
import re
import shutil
import sys

DEFAULT_PATTERNS = ('*.py', '*.js', '*.java', '*.md', '*.txt')

# Absolute-path literals that belong to one particular machine.
# Deliberately excluded: /data/... (an Android device path, not a host path).
WINDOWS_LITERAL = re.compile(r"(?P<prefix>(?:r|u|b)?r?)(?P<quote>['\"])"
                             r"(?P<path>[A-Za-z]:[\\/][^'\"]*)(?P=quote)")
POSIX_LITERAL = re.compile(r"(?P<prefix>(?:r|u|b)?r?)(?P<quote>['\"])"
                           r"(?P<path>/(?:home|Users|mnt)/[^'\"]*)(?P=quote)")

# Any drive-letter or foreign-home path outside a quoted literal as well.
# Tuned to avoid the two false-positive families that made an earlier version of
# this audit useless: a URL scheme ("https://" contains "s:" + "/") and a Python
# escape sequence ("is:\n" contains "s:" + "\"). Hence: the previous character must
# not be alphanumeric, a drive letter must be followed by a real backslash (not an
# escape letter, not a second separator), and the POSIX form must start a path.
BARE_ABS = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"[A-Za-z]:\\(?![ntr0bxu'\"\\])\S{2,}"
    r"|/(?:home|Users|mnt)/[A-Za-z0-9_.\-]{2,}"
    r")")

CREDENTIAL_HINT = re.compile(
    r"(?i)(BEGIN [A-Z ]*PRIVATE KEY|storepass\s*=\s*['\"][^'\"]|"
    r"keypass\s*=\s*['\"][^'\"]|password\s*=\s*['\"][^'\"]|"
    r"api[_-]?key\s*=\s*['\"][^'\"]|secret\s*=\s*['\"][^'\"]{6,})")


def collect(src, patterns):
    """Return [(absolute_path, relative_path)] for every matching file."""
    out = []
    for root, _dirs, files in os.walk(src):
        for name in sorted(files):
            if any(fnmatch.fnmatch(name, p) for p in patterns):
                full = os.path.join(root, name)
                out.append((full, os.path.relpath(full, src)))
    return out


def audit(path, rel):
    """Return [(kind, lineno, detail)] for one file."""
    findings = []
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            lines = fh.readlines()
    except OSError as exc:
        return [('io-error', 0, str(exc))]

    for lineno, line in enumerate(lines, 1):
        for match in BARE_ABS.finditer(line):
            findings.append(('abs-path', lineno, match.group(0)[:90]))
        if CREDENTIAL_HINT.search(line):
            findings.append(('credential', lineno, line.strip()[:110]))
    return findings


def scrub(text):
    """Neutralise absolute-path literals; returns (new_text, count)."""
    total = 0

    def repl(_match):
        return "''"

    for pattern in (WINDOWS_LITERAL, POSIX_LITERAL):
        text, count = pattern.subn(repl, text)
        total += count
    return text, total


def main():
    ap = argparse.ArgumentParser(
        description='Sync a script directory to a publish location and audit it for '
                    'machine-specific leftovers (absolute paths, hardcoded credentials).')
    ap.add_argument('src', help='source directory to publish from')
    ap.add_argument('dst', help='destination directory to publish into')
    ap.add_argument('--pattern', action='append', default=list(DEFAULT_PATTERNS),
                    help='glob to include, repeatable (default: %s)'
                         % ' '.join(DEFAULT_PATTERNS))
    ap.add_argument('--apply', action='store_true',
                    help='actually copy files (default is audit only)')
    ap.add_argument('--scrub', action='store_true',
                    help='with --apply, neutralise absolute-path literals in the copies')
    args = ap.parse_args()

    if not os.path.isdir(args.src):
        print('error: source directory not found: %s' % args.src)
        return 1

    files = collect(args.src, args.pattern)
    if not files:
        print('error: no files matched %s in %s'
              % (', '.join(args.pattern), args.src))
        return 1

    total_findings = 0
    scrubbed = 0
    copied = 0

    for full, rel in files:
        findings = audit(full, rel)
        abs_findings = [f for f in findings if f[0] == 'abs-path']
        cred_findings = [f for f in findings if f[0] == 'credential']
        other = [f for f in findings if f[0] not in ('abs-path', 'credential')]

        if findings:
            print('-- %s' % rel)
            for kind, lineno, detail in abs_findings + cred_findings + other:
                print('   [%s] line %d: %s' % (kind, lineno, detail))
            total_findings += len(findings)

        if not args.apply:
            continue

        target = os.path.join(args.dst, rel)
        os.makedirs(os.path.dirname(target) or '.', exist_ok=True)

        if args.scrub and (abs_findings or cred_findings):
            with open(full, encoding='utf-8', errors='replace') as fh:
                text = fh.read()
            new_text, count = scrub(text)
            if count:
                with open(target, 'w', encoding='utf-8', newline='\n') as fh:
                    fh.write(new_text)
                scrubbed += count
                print('   -> copied with %d absolute-path literal(s) neutralised' % count)
                copied += 1
                continue

        shutil.copy2(full, target)
        copied += 1

    print('')
    if not args.apply:
        print('== audit: %d file(s) checked, %d finding(s). Nothing was written.'
              % (len(files), total_findings))
        print('   re-run with --apply to copy, and with --scrub to neutralise '
              'absolute-path literals.')
        return 2 if total_findings else 0

    print('== sync: %d file(s) copied to %s (%d literal(s) scrubbed), %d finding(s) reported.'
          % (copied, args.dst, scrubbed, total_findings))
    return 0


if __name__ == '__main__':
    sys.exit(main())
