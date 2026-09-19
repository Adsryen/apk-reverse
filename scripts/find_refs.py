#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find every reference to a method/field/class, so you can judge blast radius
BEFORE patching it.

This is the check that prevents the classic mistake: patching something that looked
ad-specific but is actually a general utility with dozens of callers.

Usage
-----
  # references to a method, from a smali tree or a directory of dex files
  python find_refs.py <tree_or_dex_dir> 'Lcom/pkg/Helper;->showAd(Landroid/app/Activity;)V'

  # a whole class (all of its members)
  python find_refs.py <tree_or_dex_dir> 'Lcom/pkg/Helper;'

  # a field
  python find_refs.py <tree_or_dex_dir> 'Lcom/pkg/Helper;->count:I'

  # just the counts, no listing
  python find_refs.py <tree_or_dex_dir> 'Lcom/pkg/Helper;->showAd' --count-only

Reading the result
------------------
  few callers, all inside one feature area   -> safe to patch
  many callers, or callers in unrelated pkgs -> general utility. DO NOT patch it.
                                                Go one level up and patch the
                                                specific caller instead.

Also inspect the signature. If it mentions Modifier / ContentScale / Shape / View /
ColorScheme or a content-generic model type, it is shared UI, not your target.
"""
import argparse
import os
import re
import sys

TEXT_EXT = ('.smali',)
REF_RE_TMPL = r'invoke[^\n]*%s|sget[^\n]*%s|sput[^\n]*%s|new-instance[^\n]*%s|check-cast[^\n]*%s'


def iter_files(root):
    if os.path.isdir(root):
        for dp, _, fs in os.walk(root):
            for fn in fs:
                if fn.endswith(TEXT_EXT):
                    yield os.path.join(dp, fn)
    else:
        yield root


def method_owner(text, idx):
    """Map a character offset to the enclosing .method declaration."""
    head = text.rfind('.method ', 0, idx)
    if head < 0:
        return '?'
    end = text.find('\n', head)
    return text[head:end].strip()


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('root')
    ap.add_argument('needle')
    ap.add_argument('--count-only', action='store_true')
    ap.add_argument('--max-print', type=int, default=60)
    a = ap.parse_args()

    esc = re.escape(a.needle)
    # match the needle plus one more char so we do not match a longer prefix
    pat = re.compile(REF_RE_TMPL % (esc, esc, esc, esc, esc))

    total = 0
    per_file = []
    printed = 0
    for fp in iter_files(a.root):
        try:
            t = open(fp, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        hits = list(pat.finditer(t))
        if not hits:
            continue
        total += len(hits)
        per_file.append((len(hits), fp, hits, t))

    per_file.sort(reverse=True)
    print('[total refs] %d across %d files' % (total, len(per_file)))
    print()
    for cnt, fp, hits, t in per_file:
        rel = fp
        print('%-70s %d' % (rel, cnt))
        if a.count_only:
            continue
        for m in hits:
            if printed >= a.max_print:
                print('  ... (truncated)')
                return 0
            owner = method_owner(t, m.start())
            print('    in %s' % owner)
            print('      %s' % m.group(0).strip())
            printed += 1

    if total == 0:
        print('[note] no references found. Check the descriptor prefix "L...;" and '
              'exact obfuscated names, or disassemble the dex first with smtool.py.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
