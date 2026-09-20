# Repository decisions, and the evidence behind them

The pass was framed as a choice between two ways to split the skill. The measurement rejected the
framing, and this file records why, then states exactly what changed in the repository.

---

## The decision: **no second skill.** Fix skill A instead.

This is the "暂不建" outcome the brief explicitly permits, and it is supported by the evidence rather
than by preference.

### Why the framing did not survive contact with the target

The two candidate splits were:

- **by entry point** — everything reached from an APK (including Flutter/IL2CPP) stays in A; only
  standalone ELF goes to B. Cost: A keeps growing.
- **by logic location** — A keeps only logic genuinely in dex; Flutter, IL2CPP, hardened dex, native
  and standalone ELF all move out. Cost: four references (~962 lines) relocate.

The measured target is exactly the case that was supposed to discriminate between them: Flutter
(machine-code side) whose entry point is an APK. It produced a third answer.

**The problem is not where the content lives. It is one missing dependency.** Everything the kit does
*after* a snapshot dumper has produced `pp.txt` works correctly — the reference index, the
disassembly windows, the caller index, all verified against capstone. The single thing it cannot do
is get *from the binary to* `pp.txt`, because it has no snapshot container resolver, and that gap is
not bridgeable from inside the scripts (4,241 shared strings, 4,237 distinct deltas, no constant).

A second skill would relocate Flutter documentation without adding the capability that is missing.
The gap would travel with the documents. Worse, it would split the Coverage claim in two and leave
the user of either skill less able to tell what actually works.

### The supporting evidence, in order of weight

1. **The kit works where it was tested.** `dart_disasm.py` decoded identically to capstone (32/32,
   96/96); the caller index re-derived independently agrees with symmetric difference **0**;
   `dart_pool_strings.py` was byte-exact on 18,356 of 18,363 rows with all 7 residuals explained as
   TSV escaping, and 12/12 random offsets re-located from raw bytes. These are not the results of a
   tool that needs replacing.
2. **The blocker is a front end, and free front ends exist.** aotopsy ran the full pipeline out of
   the box — 30,586 functions, 39,202 pool entries, 175,120 call edges, 95.7% BLR annotation — with
   **no toolchain**: pure Go, no compiler, no Dart SDK. That is the "decoding the object pool"
   capability, delivered as a binary.
3. **A split would contradict the Coverage section's own structure.** Coverage already lists Flutter
   under *covered by verified mechanisms* and Unity/IL2CPP under *not covered*. The real defect is
   that the Flutter line overstates what ships. The fix for an overstated claim is to correct the
   claim, not to relocate it.
4. **The cost of the split lands on the wrong people.** Moving `dart-aot.md`,
   `native-and-so.md`, `native-tamper-and-suicide.md` and `code-virtualization-and-custom-linkers.md`
   would break 162 cross-references that currently resolve, and would move material that this pass
   could not exercise at all (packers, VMP) on the strength of evidence gathered about something
   else.

### What the second skill *would* have been, stated so the decision can be revisited

If a future pass ever does need one, the boundary the evidence points at is **"standalone machine-code
targets with no APK"** — a plain `.so`/ELF analysed on its own. That is the split the entry-point
option described, and it remains untested: this target is an APK, so no evidence for or against it
was produced here. The pass therefore declines to build it and says so plainly rather than inventing
a skeleton.

### Selective installation, measured — and what it implies for shared tooling

The brief asked for the shared-tooling question to be settled by the actual install product rather
than by preference. Measured with `npx skills add newliver666/apk-reverse --skill apk-reverse -y
--copy` in an empty directory:

- The skill is copied **whole and self-contained** into each detected agent directory — `.agents/`,
  `.claude/`, `.kiro/`, `.pi/`, `.qwen/`, `.zcode/`, six in total on this host — plus a
  `skills-lock.json` at the root.
- Every file lands under `<agent>/skills/apk-reverse/`: `SKILL.md`, all 28 `references/*.md`, all 34
  `scripts/*` including the `dexpatch/` subdirectory. **Nothing outside the skill directory is
  installed.** The repository's root-level `docs/` and the three maintenance checkers are absent from
  the product, as intended.
- There is **no cross-skill sharing mechanism** in the installed layout.

Consequence for this decision: had the skill been split, the two halves would each have needed their
own copy of any shared script, or a path that points outside the skill directory — and the latter
does not survive installation, because it is not part of the product. So the "shall we put shared
tools in a root `shared/`" question resolves itself: it cannot work that way, and with one skill there
is nothing to share. The record is kept here because the observation is what makes the reasoning
checkable rather than asserted.

---

## Changes made

### `references/dart-aot.md`

| Change | Reason |
|---|---|
| Documented a **pinned front end** (aotopsy v1.6.0, sha256 `5a90bcf2…fdc1`; Dart 2.10–3.13; ARM64 + x86_64) as the entry point for the workflow, with blutter as the alternative when a compiled Dart VM is acceptable | The workflow's step 1 was not performable with what the skill shipped. Measured: the kit cannot go from a string to a pool offset. |
| Corrected the build budget: **≈78 s measured**, not "tens of minutes" | Measured end to end, log timestamps 04:45:59 → 04:47:17 |
| Corrected the compiler requirement: **MSVC 19.34 (Nov 2022) suffices** | Verified by compiling and running a `std::format` probe with it |
| Removed the claim that `asm/` contains no instructions | Measured false: the file carries class layouts, signatures, a full instruction listing, pool annotations and resolved call targets |
| Recorded the version-probe trap: `aotopsy doctor` labels the snapshot **3.6.2**, the engine banner and snapshot hash say **3.6.0**, and 3.6.0 is correct | Three independent facts agree on 3.6.0; aotopsy's number is a structural profile label and must not be passed to a VM-compiling tool |
| Noted that the two-byte chaining test in §7 did not hold here | 9,840 two-byte CJK candidates → 2,081 chained runs, all junk |

### `references/references-index` / script defects

`dart_pprefs.py` is fixed in the repository. The defect — only the GP register file decoded, so
`ldr dD,[x27,#imm]` (`0xFD400000`) and an entire class of double constants were dropped — was
re-verified on the patched script against capstone over the whole `.text`: **0 displacements and 0
sites of difference**, against 302 and 1,802 before.

`find_refs.py`, `elf_plt.py` and the `so_constpatch.py` alignment defect are **documented but not
fixed**. The repository's rule is that nothing ships unrun, and the fixes for these were not
exercised against the real target in this pass:

- `find_refs.py` — accepting `.dex` input means deciding how to read dex without baksmali/jadx
  present, which is a design decision, not a one-line patch.
- `elf_plt.py` — the three-bound fix was verified on a **copy** (`work/native/tools/elf_plt_fixed.py`),
  not in the repository, so the repository version is untouched.
- `so_constpatch.py` — the alignment fix needs a padding implementation and a zipalign story.

Each is recorded in `docs/tool-verification/FINDINGS.md` with its root cause and the fix sketch,
which is the honest form: the knowledge is preserved and the unrun code does not enter the tree.

### `SKILL.md` — Coverage

Rewritten so the Flutter line states what was measured:

- **In coverage:** Flutter/Dart AOT analysis *given a snapshot dump* — pool-reference counting,
  disassembly windows, caller indexing and patching — all verified on a real Dart 3.6.0
  `libapp.so`, with the front end named as a documented dependency.
- **Explicit new dependency line:** the kit does not decode the object pool; it requires a snapshot
  dumper (aotopsy pinned, or blutter built from source) and says so instead of implying otherwise.
- **Unchanged:** Unity/IL2CPP, React Native/Hermes, iOS, defeating a server-side authority, and the
  general-unpacker/anti-detection arms race all remain uncovered.
- **Added:** an explicit statement that packer, VMP and integrity-check scenarios were **not
  exercised** by this pass, so no claim is upgraded on their behalf.

### `SKILL.md` — the three hand-off points

Written from the perspective that a hand-off is a pointer, and that duplicating content across two
places is how the two copies drift. Each one says what the other side owns.

1. **JNI** — Java declaring a native method ↔ its `.so` implementation. Static linkage shows as
   `Java_com_pkg_Class_method` and disappears under R8 short names; dynamic registration leaves the
   symbol table empty and must be found at `RegisterNatives`. This target ships the static form
   (`FlutterJNI.loadLibrary` appears in `classes3.dex`) but the pass did not trace a JNI boundary
   end to end, so the section carries the **unverified** label.
2. **Hardening** — dex-side observation of a packer implies a native-side shell implementation.
   **Not exercised here**: this target has no packer. Recorded as a pointer with that stated.
3. **Existing boundary documents** — `native-and-so.md` and `native-tamper-and-suicide.md` read
   native anomalies *from the APK side* (immediate SIGSEGV after a repack, Java claiming the check
   passed while the process dies). That belongs in A; deep native work is the other side. The new
   section points each way rather than repeating either.

### `docs/tool-verification/`

New directory holding this pass's evidence record. `README.md` states the folder is a *measurement
record, not shipped target data*, carries the strength-label convention, and requires that **no target
identity is recorded** — only what a future reader can apply to a different APK. It is referenced from
`SKILL.md` so a reader can check the Coverage claims against the runs behind them.

No APK is in the repository (`.gitignore` already excludes `*.apk`) and no credential or token
appears in any file.

### `README.md`

Updated for the directory tree, the install command and the division of labour between the skills,
plus a pointer to the verification record.

---

## Verification

All four gates were re-run against the final tree:

- `python -B check_repo.py`
- `python -B check_refs.py`
- `python -B build_scripts.py . <out>`
- `npx skills add newliver666/apk-reverse --list`

Two behaviours of the checkers worth knowing, both established by experiment during this pass:
`check_repo.py` and `check_refs.py` have **no argparse**, so `--help` is silently ignored and the
full check runs; and running `check_repo.py` with `PYTHONIOENCODING=utf-8` set produces a spurious
failure (exit 1, one script reported as crashed) because its `subprocess.run(..., text=True)` does
not pin an encoding while the child emits UTF-8 — the parent then decodes as cp936 and the streams
come back empty.
