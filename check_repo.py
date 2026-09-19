"""Pre-commit checks: every script parses and answers --help; every referenced file exists."""
import ast
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

fail = []

print("== python syntax + --help ==")
for name in sorted(os.listdir('scripts')):
    if not name.endswith('.py'):
        continue
    path = os.path.join('scripts', name)
    try:
        ast.parse(open(path, encoding='utf-8').read())
    except SyntaxError as e:
        fail.append('%s: syntax error %s' % (path, e))
        print('  FAIL %s' % path)
        continue
    r = subprocess.run([sys.executable, '-B', path, '--help'],
                       capture_output=True, text=True, timeout=60)
    # A script may exit non-zero on --help if it uses the "print usage and exit 2"
    # convention. That is acceptable; a traceback is not.
    crashed = 'Traceback (most recent call last)' in (r.stderr or '')
    helped = bool((r.stdout or '').strip()) or bool(r.stderr)
    ok = (not crashed) and helped
    verdict = 'ok' if r.returncode == 0 and not crashed else \
              ('usage-ok rc=%d' % r.returncode if ok else 'CRASH rc=%d' % r.returncode)
    print('  %-32s %s' % ('%s --help' % name, verdict))
    if not ok:
        fail.append('%s --help crashed: %s' % (path, (r.stderr or '')[:300]))

print("\n== markdown references resolve ==")
refs = set(os.listdir('references'))
scripts = set(os.listdir('scripts'))
missing = []
for name in ['SKILL.md', 'README.md'] + ['references/' + f for f in refs if f.endswith('.md')]:
    text = open(name, encoding='utf-8').read()
    for m in re.finditer(r'`?(references/[A-Za-z0-9_\-]+\.md)', text):
        target = m.group(1).split('/')[1]
        if target not in refs:
            missing.append('%s -> %s' % (name, m.group(1)))
    for m in re.finditer(r'`?(scripts/[A-Za-z0-9_\-]+\.(?:py|js))', text):
        target = m.group(1).split('/')[1]
        if target not in scripts:
            missing.append('%s -> %s' % (name, m.group(1)))
if missing:
    for x in sorted(set(missing)):
        print('  MISSING %s' % x)
    fail.extend(missing)
else:
    print('  all referenced reference/script paths exist')

print("\n== every reference file is reachable from SKILL.md or README.md ==")
bodies = open('SKILL.md', encoding='utf-8').read() + open('README.md', encoding='utf-8').read()
unlisted = [f for f in sorted(refs) if f.endswith('.md') and f not in bodies]
for f in unlisted:
    print('  UNLISTED references/%s' % f)
if unlisted:
    fail.append('unlisted references: %s' % unlisted)

print("\n== every script is mentioned somewhere in the docs ==")
all_docs = bodies
for f in refs:
    if f.endswith('.md'):
        all_docs += open('references/' + f, encoding='utf-8').read()
undoc = [s for s in sorted(scripts) if s.endswith(('.py', '.js')) and s not in all_docs]
for s in undoc:
    print('  UNDOCUMENTED scripts/%s' % s)
if undoc:
    fail.append('undocumented scripts: %s' % undoc)

print("\n== result: %d problem(s) ==" % len(fail))
for f in fail:
    print('  - %s' % f)
sys.exit(1 if fail else 0)
