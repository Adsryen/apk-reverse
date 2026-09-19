# Verification output

The four repository gates, run against the tree **after** the changes described in
`REPO-DECISIONS.md`. The text below is the captured output, not a restatement of it — a table
saying "passed" is exactly the kind of claim this repository asks people not to make.

Environment: Python 3.14.0 on Windows 11, `npx` 11.6.2, repository at commit
`46812ec` plus the working-tree changes listed in `REPO-DECISIONS.md`.

| # | Command | Exit | Result |
|---|---|---|---|
| 1 | `python -B check_repo.py` | 0 | 0 problems |
| 2 | `python -B check_refs.py` | 0 | 0 dangling |
| 3 | `python -B build_scripts.py . <audit-out>` | 0 | 0 findings |
| 4 | `npx skills add newliver666/apk-reverse --list` | 0 | Found 1 skill |

---

## 1. python -B check_repo.py

Every skill discovered, frontmatter valid, each script runnable, documented paths resolve, README paths explicit and existing.

Exit code: **0**. Output (47 lines):

```
== skills discovered ==
  skills/apk-reverse

== frontmatter ==
  1 checked

== apk-reverse: python syntax + --help ==
  apk_diff.py                      ok
  blob_decode.py                   ok
  coldstart.py                     ok
  dart_disasm.py                   ok
  dart_pool_strings.py             ok
  dart_pprefs.py                   ok
  datastore_inject.py              ok
  devsh.py                         usage-ok rc=2
  dex_check_verifier.py            ok
  dex_classdiff.py                 ok
  dex_find_insn.py                 ok
  dex_patch_bytes.py               ok
  dex_strings.py                   ok
  dex_strpatch.py                  ok
  dexutil.py                       usage-ok rc=2
  doctor.py                        ok
  elf_plt.py                       ok
  find_refs.py                     ok
  grab_crash.py                    ok
  install_test.py                  ok
  lib_map.py                       ok
  native_crash.py                  ok
  patch_smali.py                   usage-ok rc=2
  preflight.py                     ok
  probe_api.py                     ok
  repack.py                        ok
  run_probe.py                     ok
  sig_probe.py                     ok
  smtool.py                        usage-ok rc=2
  snap.py                          ok
  so_constpatch.py                 ok
  tls_check.py                     ok
  usb_net_proxy.py                 ok

== apk-reverse: reference and script paths resolve ==
  all referenced reference/script paths exist

== README paths are explicit and exist ==

== result: 0 problem(s) ==
```

---

## 2. python -B check_refs.py

Every cross-reference naming a section of another document must reach a real heading there.

Exit code: **0**. Output (36 lines):

```
== markdown documents ==
  README.md
  skills/apk-reverse/SKILL.md
  skills/apk-reverse/references/account-gates.md
  skills/apk-reverse/references/ad-removal.md
  skills/apk-reverse/references/byte-level-patching.md
  skills/apk-reverse/references/code-virtualization-and-custom-linkers.md
  skills/apk-reverse/references/dart-aot.md
  skills/apk-reverse/references/detection-and-anti-analysis.md
  skills/apk-reverse/references/dex-patching.md
  skills/apk-reverse/references/dynamic-frida.md
  skills/apk-reverse/references/environment.md
  skills/apk-reverse/references/framework-runtimes.md
  skills/apk-reverse/references/long-task-discipline.md
  skills/apk-reverse/references/membership-and-limits.md
  skills/apk-reverse/references/native-and-so.md
  skills/apk-reverse/references/native-tamper-and-suicide.md
  skills/apk-reverse/references/packers.md
  skills/apk-reverse/references/patch-audit.md
  skills/apk-reverse/references/pitfalls.md
  skills/apk-reverse/references/recon.md
  skills/apk-reverse/references/repack-and-sign.md
  skills/apk-reverse/references/runtime-data.md
  skills/apk-reverse/references/server-api.md
  skills/apk-reverse/references/server-config-and-updates.md
  skills/apk-reverse/references/signature-derived-keys.md
  skills/apk-reverse/references/third-party-builds.md
  skills/apk-reverse/references/tls-and-cert.md
  skills/apk-reverse/references/toolchain.md
  skills/apk-reverse/references/updates-and-forced-upgrade.md
  skills/apk-reverse/references/verification.md
  skills/apk-reverse/scripts/dexpatch/README.md

== section references: 166 reachable ==

== result: 0 dangling, 0 warning(s) ==
```

---

## 3. python -B build_scripts.py . <audit-out>

Audit for machine-specific leftovers: absolute paths and credential literals.

Exit code: **0**. Output (2 lines):

```
== audit: 76 file(s) checked, 0 finding(s). Nothing was written.
   re-run with --apply to copy, and with --scrub to neutralise absolute-path literals.
```

---

## 4. npx skills add newliver666/apk-reverse --list

The skills CLI must still discover the skill after the changes.

Exit code: **0**. Output (28 lines):

```

            
           
           
           
  
  

   skills 

  Tip: use the --yes (-y) and --global (-g) flags to install without prompts.
[?25l
  Source: https://github.com/newliver666/apk-reverse.git
[?25h[?25l

[?25h[?25l
  Found 1 skill
[?25h

  Available Skills

    apk-reverse

      Reverse engineer, debloat, de-ad, patch, or re-sign Android APKs, and analyze their runtime and server-side behavior. Use when a task involves an .apk/.aab/.dex/.so sample, smali or dex patching, Frida/objection runtime hooking, repacking and re-signing, removing ads or SDK trackers, probing a mobile app's HTTP API, or deciding whether a client-side patch is even capable of achieving the goal. Covers recon, anti-tamper, ad removal, membership/paywall limits, dex-level surgical patching, repack pitfalls, device and emulator setup, and a hard-won failure catalogue. Load the body before planning any patch work: it opens with a symptom index and four gates that must be cleared first.


  Use --skill <name> to install specific skills

```

---

## Two notes about running these gates

Both were found by experiment during this pass and are worth knowing before trusting a
green run.

**`check_repo.py` and `check_refs.py` have no argparse.** Passing `--help` does not print
usage — it is silently ignored and the full check runs, producing byte-identical output to a
normal invocation. A "low-impact probe" assumption about these two is wrong.

**Do not set `PYTHONIOENCODING=utf-8` when running `check_repo.py`.** Doing so produced a
spurious exit 1 with one script (`dex_strpatch.py`) reported as crashed. Root cause is at
`check_repo.py:152-154`: `subprocess.run(..., text=True)` does not pin an encoding, so the
parent decodes the child's UTF-8 output as `cp936`, the reader thread raises
`UnicodeDecodeError`, both streams come back empty, `helped` (line 158) goes false and the run
is recorded as FAIL (lines 164-165). Clearing the variable and re-running restores exit 0. The
same lines also carry a diagnostic inconsistency: `verdict` checks only `returncode` while `ok`
additionally requires `helped`, so a run with both streams empty and returncode 0 prints `ok`
yet is recorded as crashed in the results block.

This is also why `check_refs.py` failed once during this pass and now passes: it resolves
cross-references **within the skill only** and has no fallback outside it, so a sentence in
`SKILL.md` pointing at a path outside the skill directory read as dangling. It was right to
fail; the reference was rewritten rather than the checker.
