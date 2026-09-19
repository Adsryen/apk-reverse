#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方法级 smali 补丁器。

设计要点（踩坑后确定）：
- 只替换「.method 声明行的下一行」到「.end method 之前」的指令体，
  保留原 .method / .end method / .annotation 段不动，避免破坏修饰符与注解。
- 补丁清单要求显式给出自洽的 .registers 值：smali 汇编器会校验寄存器不越界，
  registers 必须 >= max(参数寄存器数) 且 >= 指令里用到的最大寄存器编号 + 1。
  参数寄存器数：static 方法 = 参数个数；非 static = 参数个数 + 1（this）。
- 补丁清单是 JSON 列表，每条：
  {
    "file":   "com/example/Helper.smali",              # path relative to smali tree root
    "method": ".method public final show(Landroid/app/Activity;)V",  # exact .method line
    "registers": 3,
    "body": ["invoke-interface {p3}, ...;", "return-void"],
    "note": "干掉插屏广告"                                # 可选，仅用于报告
  }

用法：
  python patch_smali.py <smali_tree> <patch.json> [--dry-run]
"""
import json
import os
import re
import sys


def split_methods(text):
    """把 smali 文本切成 [(method_decl, start_idx, end_idx)]，按行索引。"""
    lines = text.split('\n')
    out = []
    start = None
    decl = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith('.method ') and start is None:
            start, decl = i, s
        elif s == '.end method' and start is not None:
            out.append((decl, start, i))
            start, decl = None, None
    return lines, out


def patch_one(path, decl_wanted, registers, body):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    lines, methods = split_methods(text)
    hits = [m for m in methods if m[0] == decl_wanted.strip()]
    if not hits:
        return False, 'method not found: %s' % decl_wanted
    if len(hits) > 1:
        return False, 'ambiguous (%d matches): %s' % (len(hits), decl_wanted)
    _, start, end = hits[0]
    # 保留 .method 行；重写内部：.registers + body
    new_inner = ['    .registers %d' % registers, '']
    for b in body:
        new_inner.append('    ' + b)
    new_lines = lines[:start + 1] + new_inner + [''] + lines[end:]
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(new_lines))
    return True, 'ok'


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    tree = sys.argv[1]
    spec = sys.argv[2]
    dry = '--dry-run' in sys.argv
    with open(spec, 'r', encoding='utf-8') as f:
        patches = json.load(f)
    ok = fail = 0
    for p in patches:
        full = os.path.join(tree, p['file'].replace('/', os.sep))
        if not os.path.isfile(full):
            print('[MISS-FILE] %s' % p['file'])
            fail += 1
            continue
        if dry:
            with open(full, 'r', encoding='utf-8') as f:
                _, methods = split_methods(f.read())
            found = any(m[0] == p['method'].strip() for m in methods)
            print('[%s] %s :: %s' % ('DRY-OK' if found else 'DRY-MISS', p['file'], p['method']))
            ok += 1 if found else 0
            fail += 0 if found else 1
            continue
        okk, msg = patch_one(full, p['method'], p['registers'], p['body'])
        print('[%s] %s :: %s  (%s)' % ('OK' if okk else 'FAIL', p['file'], p['method'].split('(')[0].replace('.method ', ''), msg))
        ok += 1 if okk else 0
        fail += 0 if okk else 1
    print('\npatched=%d failed=%d%s' % (ok, fail, ' [dry-run]' if dry else ''))
    return 0 if fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
