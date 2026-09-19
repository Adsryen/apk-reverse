#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot builder: copy the battle-tested tools from the project workspace into
the skill, stripping machine-specific hardcoding.

Run from anywhere:  python build_scripts.py <project_work_dir> <skill_scripts_dir>
"""
import os
import re
import shutil
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else r'E:\ciyuan\work'
DST = sys.argv[2] if len(sys.argv) > 2 else r'E:\ciyuan\apk-reverse\scripts'

# file -> (new name, list of (pattern, replacement))
COPY = {
    r'tools\dex_strpatch.py': ('dex_strpatch.py', []),
    r'tools\dex_classdiff.py': ('dex_classdiff.py', []),
    r'tools\patch_smali.py': ('patch_smali.py', []),
    r'tools\repack.py': ('repack.py', [
        # strip machine-specific defaults; make them explicit args
        (re.compile(r'KS_PATH\s*=\s*r?["\'][^"\']*["\']'), 'KS_PATH = None  # pass --ks on the command line'),
        (re.compile(r"workdir'?,?\s*default=r?['\"][^'\"]*['\"]"), "workdir', default=None"),
    ]),
    r'tools\cyc_proxy.py': ('usb_net_proxy.py', []),
    r'tools\mk_video_prefs.py': ('datastore_inject.py', []),
    r'tools\probe_adverts.py': ('probe_api.py', []),
    r'tools\grab_crash.py': ('grab_crash.py', []),
}


def clean(text):
    """Remove absolute paths that point at one particular machine."""
    text = re.sub(r"r?'[A-Za-z]:\\\\[^'\"]*'", "''", text)
    text = re.sub(r'"[A-Za-z]:\\\\[^"]*"', '""', text)
    return text


def main():
    os.makedirs(DST, exist_ok=True)
    os.makedirs(os.path.join(DST, 'dexpatch'), exist_ok=True)
    for rel, (new, subs) in COPY.items():
        src = os.path.join(SRC, rel)
        if not os.path.isfile(src):
            print('[skip missing] %s' % rel)
            continue
        t = open(src, encoding='utf-8', errors='replace').read()
        for pat, rep in subs:
            t = pat.sub(rep, t)
        out = os.path.join(DST, new)
        with open(out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(t)
        print('[copied] %-24s -> %s' % (rel, new))

    # dexlib2 patcher sources
    for rel, new in [(r'tools\dexpatch\PatchMethod.java', 'PatchMethod.java'),
                     (r'tools\dexpatch\PatchClasses7v2.java', 'PatchMethodExample.java')]:
        src = os.path.join(SRC, rel)
        if os.path.isfile(src):
            t = open(src, encoding='utf-8', errors='replace').read()
            with open(os.path.join(DST, 'dexpatch', new), 'w',
                      encoding='utf-8', newline='\n') as f:
                f.write(t)
            print('[copied] %-24s -> dexpatch/%s' % (rel, new))
        else:
            print('[skip missing] %s' % rel)

    # cp.txt content -> smali_cp.txt template
    cp = os.path.join(SRC, 'tools', 'dexpatch', 'cp.txt')
    if os.path.isfile(cp):
        raw = open(cp, encoding='utf-8').read().strip()
        jars = [j for j in raw.split(';') if j.strip()]
        with open(os.path.join(DST, 'smali_cp.txt'), 'w', encoding='utf-8', newline='\n') as f:
            f.write('# One jar path per line. Adjust the directory to your own tools.\n')
            f.write('# Needed: smali baksmali dexlib2 util antlr-runtime stringtemplate '
                    'jcommander guava\n')
            for j in jars:
                f.write(os.path.basename(j) + '\n')
        print('[wrote] smali_cp.txt (%d jars)' % len(jars))


if __name__ == '__main__':
    main()
