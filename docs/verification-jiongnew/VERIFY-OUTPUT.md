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
== audit: 77 file(s) checked, 0 finding(s). Nothing was written.
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

**One intermittent `exit 1` from `check_repo.py` was observed and not reproduced.** During this pass
`check_repo.py` once returned 1 while printing `result: 0 problem(s)` and 47 lines of all-`ok` script
status — and five subsequent runs (to a file, to `$null`, and through a pipe) all returned 0 with the
same 47 lines. The mechanism is the encoding path documented above: at `check_repo.py:153` the child
is run with `text=True` and no fixed `encoding`, and at `:158-159` `helped` requires at least one of
the two streams to be non-empty while `verdict` reads only `returncode`, so a decode that consumes
both streams turns a healthy script into a recorded FAIL. Recorded rather than dismissed because a
gate that can fail without a cause is worse than one that fails for a stated reason; if you see an
isolated red run whose text says `0 problem(s)`, re-run before investigating the repository.

---

## 5. External checks — what was verified against primary sources

Not a command output: a record of the facts that were re-checked before they were relied on, so a
later reader can tell which of this pass's premises came from a live source and which did not. Kept
here because several of them changed a decision.

| Claim that was checked | Result | Source |
|---|---|---|
| `npx skills` command surface and flags | Confirmed **in use here**: `add <package>`, `--list`/`-l`, `--skill`/`-s`, `--copy`, `-y`, `--full-depth`, `use`, `list`, `find`, `update`, `init`, `remove`, `experimental_sync` | local `npx --yes skills --help`; [justjavac/skills README](https://raw.githubusercontent.com/justjavac/skills/main/README.md) |
| Skill discovery rules and required frontmatter | Confirmed: containers walked one level for `skills/<name>/SKILL.md`, one extra level for `skills/<category>/<name>/SKILL.md`; a shallower `SKILL.md` shadows anything nested; `name` and `description` required; `metadata.internal` hides a skill | same README (§Skill Discovery, §Creating Skills), and [agentskills.io specification](https://agentskills.io/specification.md) |
| `skills/<name>/` is the layout the CLI resolves | Confirmed by the repair commit already in history (`Restructure to the skills/<name>/ layout the skills CLI resolves`) and by `--list` finding 1 skill both before and after this pass | live `npx skills add newliver666/apk-reverse --list` |
| `idalib-mcp` exists, is the recommended headless route, and its prerequisites | Confirmed, with one update worth recording: the IDA **GUI plugin is no longer recommended and will be deprecated** in favour of `idalib-mcp`. Prerequisites as stated: Python 3.11+, IDA Pro 8.3+ (9 recommended), **IDA Free unsupported**, and idalib activated globally. Headless usage: `uv run idalib-mcp --host 127.0.0.1 --port 8745 <binary>` or `--stdio`. Workers are persistent, adopt existing sessions, and self-exit on idle TTL | [mrexodia/ida-pro-mcp README](https://raw.githubusercontent.com/mrexodia/ida-pro-mcp/main/README.md) |
| GhidraMCP is a GUI extension + Python bridge, not headless | Confirmed. Install is "Import the plugin into Ghidra"; the bridge is `bridge_mcp_ghidra.py` talking to `http://127.0.0.1:8080/`. Unattended use therefore means `analyzeHeadless` plus a post-script, not this bridge | [LaurieWired/GhidraMCP README](https://raw.githubusercontent.com/LaurieWired/GhidraMCP/main/README.md) |
| The IDA MCP author's warning about LLMs on obfuscated code | Confirmed verbatim in the README: LLMs will not perform well on obfuscated code, and string encryption / import hashing / control-flow flattening / code encryption / anti-decompilation tricks should be removed first. **Not applied in this pass** — the target is not an OLLVM sample, so citing it here would have been decoration | same README (§Tips for Enhancing LLM Accuracy) |
| blutter's supported scope and build model | Confirmed: **Android `libapp.so`, arm64 only**; auto-detects the Dart version from the engine and builds the matching Dart VM; needs a Haskell-free C++ toolchain (g++>=13 / clang>=16 / MSVC); `bin/` holds per-version executables named `blutter_dartvm<ver>_<os>_<arch>`; output includes `asm/`, `objs.txt`, `pp.txt`, `blutter_frida.js`. Its own TODO still lists obfuscated apps as incompletely supported | [worawit/blutter README](https://raw.githubusercontent.com/worawit/blutter/main/README.md) |
| No prebuilt blutter binary is published | Confirmed by measurement: the repo has **zero GitHub releases** and its `bin/` is gitignored. Building is mandatory — and, measured here, costs **≈78 s**, not "tens of minutes" | local run; blutter README |
| aotopsy's scope, accuracy claims and hard limits | Confirmed from its README: pure Go, static, **no Dart VM and no SDK compile**; ARM64 + x86_64; Dart 2.10–3.13; claims 90.2% name-recovery agreement and 0% fabrication. Its stated **hard AOT floors** match what this pass saw: instance field names ~97–99% absent, local/captured names gone, truly polymorphic dispatch not statically resolvable | [BroNils/aotopsy README](https://raw.githubusercontent.com/BroNils/aotopsy/main/README.md) |
| Which Flutter SDK ships Dart 3.6.0 | **Not confirmed from an authoritative table.** The engine banner (`3.6.0 (stable) (Thu Dec 5 07:46:24 2024 -0800)`) and the snapshot hash are decisive for our purposes, and no `3.6.2` string exists in either `.so`. The Flutter SDK version number was deliberately *not* asserted anywhere in the repository output, because the release-notes page that would have settled it was not reachable in a form that could be quoted | banner + byte search, both local and observed |

Two checks changed what the repository says. First, the blutter build budget and compiler floor were
both wrong in the documentation and are now corrected from measurement. Second, aotopsy turned out to
be the no-toolchain route, which is why `dart-aot.md` now names a front end as a dependency instead of
implying the object pool decodes itself.

One premise from the original brief did **not** survive: "GNU readelf is on PATH" is false on this
host. `readelf` resolves to pyelftools' own `readelf.py`, whose CLI rejects `--dyn-syms` and `-W` as
unrecognized arguments, and MinGW `objdump`/`nm` (binutils 2.28) reject every aarch64 ELF with
`File format not recognized`. All aarch64 cross-checks in this pass therefore went through the
pyelftools / lief / capstone **library APIs**.
