#!/usr/bin/env python3
"""Budget gate for the apk-reverse skill: keep the always-loaded part from creeping.

`check_repo.py` proves the repository is *consistent* (paths resolve, indexes are complete).
This proves it is not *bloating*. Those are different failures, and the second has no natural
counter-pressure: every pass adds a reference, an index row and a coverage claim, and nothing in
the repository notices.

What is measured, and why each measure is shaped the way it is:

  1. **Content lines vs index lines.** An index row is the price of discoverability: one line per
     bundled file, and this skill ships 38 references and 48 scripts, so ~100 of its lines are
     structural. Counting them against a prose budget would push the skill to drop files it needs,
     so the budget applies to the *narrative* lines — rules, workflow, gates, classification —
     which is the part that actually competes for attention. Anthropic's Agent Skills guidance
     says "keep SKILL.md under 500 lines"; its own `skill-creator` ships 480 and `mcp-builder` 237.
     Here the narrative budget is 460, and the total is reported for context, not as a verdict.
  2. **Index row length.** The index tables are the largest part of SKILL.md and the easiest to
     grow by accident: each new entry is written by someone who knows the detail, and the detail
     lands in the row. An index row says *when to load the file*; the file says what is in it.
  3. **Restated conclusions** (reported as notes, never as failures). A conclusion legitimately
     appears in the benchmark matrix, in the evidence record, and in the coverage statement —
     those three exist to state results. The check flags a concept that has spread *beyond* those
     homes, because that is when a future correction has to hunt for every copy. It is a note
     rather than a failure precisely because the three legitimate homes make a high count normal.
  4. **Reference discoverability.** Every reference must be reachable from SKILL.md or nothing will
     ever load it. (`check_repo.py` also enforces this; the duplication is deliberate, because a
     dead reference is invisible in a way a broken path is not.)

Usage:
    python check_budget.py            # report; exit 1 if a hard limit is exceeded
    python check_budget.py --strict   # treat every warning as a failure
    python check_budget.py --json
"""
import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.join(ROOT, 'skills', 'apk-reverse')
SKILL = os.path.join(SKILL_DIR, 'SKILL.md')
REFS = os.path.join(SKILL_DIR, 'references')

CONTENT_LINES_OK = 460        # narrative budget
CONTENT_LINES_HARD = 560      # past this, something is structurally wrong
INDEX_ROW_SOFT = 250          # chars of description per row
INDEX_ROW_HARD = 400          # a row longer than this is a paragraph, not an index entry
INDEXES = ('Symptom index', 'Reference index', 'Script index')

# Concepts that have been restated once already. Reported, not enforced -- see the docstring.
RESTATED = {
    'trivial-body is bimodal': [r'bimodal'],
    'Java2C native density (2000x)': [r'82\.76', r'2,?000x'],
    'Stalker exclusion keeps the process alive': [r'keeps? the (?:target|process) alive'],
    'Dex-VMP coverage fixture (218/224)': [r'218 of 224', r'218/224'],
    'ezAndroid is JNI sinking, not a VMP': [r'JNI sinking'],
    'KernelSU userspace cannot change a syscall': [r'userspace module.{0,60}cannot change'],
    'protobuf proto3 explicit zero': [r'proto3.{0,40}(?:explicit )?zero'],
}
# Documents whose job is to state results; a concept appearing here is not drift.
LEGITIMATE_HOMES = ('tests/benchmark.md', 'docs/tool-verification/')


def skill_lines():
    with open(SKILL, encoding='utf-8') as fh:
        return fh.read().splitlines()


def index_rows(lines):
    """(index line count, [(section, first-cell, desc-length)] for over-long rows)."""
    n = 0
    long_rows = []
    cur = None
    for ln in lines:
        if ln.startswith('## '):
            cur = ln[3:].strip()
            continue
        if not (cur and any(cur.startswith(i) for i in INDEXES) and ln.startswith('|')):
            continue
        if set(ln) <= set('|-: '):
            continue
        cells = [c.strip() for c in ln.strip().strip('|').split('|')]
        if len(cells) < 2:
            continue
        n += 1
        if cells[0].lower() in ('file', 'script', 'what you observe', 'status'):
            continue
        desc = cells[-1]
        if len(desc) > INDEX_ROW_SOFT:
            long_rows.append((cur, cells[0][:44], len(desc)))
    return n, long_rows


def check_size(lines):
    n_idx, _ = index_rows(lines)
    content = len(lines) - n_idx
    if content <= CONTENT_LINES_OK:
        lv, msg = 'ok', 'SKILL.md %d narrative lines + %d index lines = %d total (budget %d narrative)' % (
            content, n_idx, len(lines), CONTENT_LINES_OK)
    elif content <= CONTENT_LINES_HARD:
        lv, msg = 'warn', ('SKILL.md narrative is %d lines, over the %d budget by %d (%d index lines '
                           'excluded). Move detail into references/ and leave a pointer.' %
                           (content, CONTENT_LINES_OK, content - CONTENT_LINES_OK, n_idx))
    else:
        lv, msg = 'fail', 'SKILL.md narrative is %d lines, past the hard limit of %d' % (
            content, CONTENT_LINES_HARD)
    return lv, msg, n_idx, content


def check_index_rows(lines):
    _, long_rows = index_rows(lines)
    out = []
    for section, key, size in long_rows:
        hard = size > INDEX_ROW_HARD
        out.append(('warn' if hard else 'warn',
                    '%s: row for %s is %d chars (soft limit %d)%s' %
                    (section, key, size, INDEX_ROW_SOFT,
                     ' -- that is a paragraph, not an index entry' if hard else '')))
    return out


def check_restated():
    notes = []
    files = (glob.glob(os.path.join(REFS, '*.md')) +
             glob.glob(os.path.join(ROOT, 'docs', 'tool-verification', '*.md')) +
             [SKILL, os.path.join(ROOT, 'README.md'), os.path.join(ROOT, 'tests', 'benchmark.md')])
    corpus = {}
    for f in files:
        if os.path.isfile(f):
            try:
                rel = os.path.relpath(f, ROOT).replace('\\', '/')
                corpus[rel] = open(f, encoding='utf-8').read()
            except OSError:
                pass
    for label, pats in RESTATED.items():
        hits = [p for p, t in corpus.items() if any(re.search(x, t, re.I) for x in pats)]
        # files whose job is to state results do not count as drift
        drift = [h for h in hits if not any(h.startswith(l) for l in LEGITIMATE_HOMES)]
        if len(drift) > 3:
            notes.append('restated in %d non-record files: %s -- %s' %
                         (len(drift), label, ', '.join(sorted(d.split('/')[-1] for d in drift))))
    return notes


def check_discoverable():
    body = open(SKILL, encoding='utf-8').read()
    out = []
    for f in sorted(glob.glob(os.path.join(REFS, '*.md'))):
        name = os.path.basename(f)
        if name not in body:
            out.append(('fail', 'references/%s is never mentioned in SKILL.md -- nothing will '
                                 'load it' % name))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--strict', action='store_true', help='treat warnings as failures')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    lines = skill_lines()
    lv, msg, n_idx, content = check_size(lines)
    findings = [(lv, msg)]
    findings += check_index_rows(lines)
    findings += check_discoverable()
    notes = check_restated()

    if args.json:
        print(json.dumps({'findings': [{'level': l, 'message': m} for l, m in findings],
                          'notes': notes, 'index_lines': n_idx, 'content_lines': content}, indent=2))
    else:
        for l, m in findings:
            print('%s %s' % ({'ok': '  ok  ', 'warn': ' WARN ', 'fail': ' FAIL '}[l], m))
        for m in notes:
            print(' note  %s' % m)
        n_fail = sum(1 for l, _ in findings if l == 'fail')
        n_warn = sum(1 for l, _ in findings if l == 'warn')
        print()
        print('== budget: %d failure(s), %d warning(s), %d note(s) ==' % (n_fail, n_warn, len(notes)))

    n_bad = sum(1 for l, _ in findings if l == 'fail' or (args.strict and l == 'warn'))
    return 1 if n_bad else 0


if __name__ == '__main__':
    sys.exit(main())
