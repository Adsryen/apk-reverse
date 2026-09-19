# Native & SO Layer

Load this when the Java/dex layer is blocked or unsuitable, when you need code to run **before** the app's
own code, or when a native library is the only editable place left.

The Java layer is usually the right choice. Go native when you need one of these:

- execution **earlier than any app code** (before `Application.onCreate`, before static initialisers),
- a change that survives the app re-loading or re-initialising its Java state,
- a host the integrity checks do not cover while the dex is covered.

## Picking a host library

A library is usable only if all three hold. Verify each; do not assume.

1. **Loaded in your scenario** — confirm in `/proc/<pid>/maps`, not by inspecting the APK.
2. **Editable** — per the boundary map you built in `packers.md`.
3. **Has a call the runtime makes for you** — an exported `JNI_OnLoad` is ideal, because the runtime
   invokes it automatically when the library is loaded by the app, with no trigger of your own.

Prefer a host whose exported JNI entry point exists *and* which appears in `maps`.

## The auto-load trap: `DT_NEEDED` does not call `JNI_OnLoad`

Adding a `DT_NEEDED` entry so one library drags in another is a natural idea. It maps the second library,
but **`JNI_OnLoad` is not invoked for it** — that callback only fires when the runtime loads a library
through the normal library-load API. A dependency loaded purely by the dynamic linker is mapped, not
initialised.

If you rely on `DT_NEEDED`, your entry point must be an **ELF constructor** or a `DT_INIT` entry, not
`JNI_OnLoad`. Conversely, if your host exports `JNI_OnLoad` and you control when the app loads it, that is
the simplest reliable trigger.

Related: a constructor/`DT_INIT` runs so early that the VM may not exist yet. Retry, and treat failure as
non-fatal — a library that logs nothing must never take the process down.

## Relocations and page permissions

This is where most hand-built native payloads fail, and the failure looks like a crash **inside the
dynamic linker**, not inside your code.

Rules that follow from how Android maps libraries:

- **A relocation target must be writable at load time.** The linker writes the computed address into the
  target slot. If the slot lives in a section that is mapped read-only, the write faults
  (`SEGV_ACCERR` in `plain_relocate_impl`).
- **Modern Android refuses W+X segments.** Adding a read/write/execute segment to get both properties is
  rejected; the loader will not give you one.
- Together these mean: relative relocations cannot heal pointer slots that sit in an executable-only page.

### Bootstrapping when relocations cannot work

If your payload's internal pointers all live in the same page as the code that reads them, and that page
must be executable, you cannot use relocations. Do the fixup at runtime instead:

1. derive the runtime page base (a PC-relative instruction gives you this without any relocation),
2. make the page writable/executable via a direct `mprotect` **syscall** (do not depend on the libc
   symbol being imported; a syscall needs no linkage),
3. write the pointer slots yourself, computed from the runtime base,
4. restore the page to read+execute,
5. then branch into your entry point.

Every pointer you need is `runtime_base + fixed_offset`. No relocation is added, so the segment
properties never have to change.

Do **not** try to make a page writable by re-mapping it over itself with an anonymous fixed mapping:
that severs the file mapping, and any other thread executing code on that page faults immediately. Use a
permission change, not a re-map.

## Replacing a Java method from native code

You can redirect a Java method's implementation without touching dex:

- Look up the method id, walk to the `ArtMethod` structure, and rewrite its **quick entry point**.
- Emit a short stub: load a target address from a literal pool and branch to it; return values follow the
  normal calling convention (arguments are already in place, return in the usual register).
- **Always preserve the original code you overwrote.** If the method can be entered through its own
  entry point, a naive redirect makes it jump into your stub, which jumps back into the same entry —
  infinite recursion. Copy the overwritten instructions into a trampoline and branch back after them.
- **Do not patch a method whose entry still points at a shared interpreter bridge.** Methods that have
  not been compiled by JIT/AOT share an entry; rewriting it breaks every method that shares it.
  A practical guard: if two unrelated target methods report the identical entry address, both are still
  on the bridge — refuse to patch rather than corrupting the process.
- Also refuse when the first instruction at the entry is PC-relative (address computed from the current
  program counter): copying it elsewhere silently changes what it points to.

Make installation **fail-safe**: if any precondition is not met, skip the patch and let the app run
unmodified. A hook that silently does not apply is survivable; a hook that corrupts a shared entry is not.

## Finding call sites without symbols

Stripped and obfuscated libraries still expose structure:

- Scan the code section for the pattern that reaches your target (a PC-relative address computation
  followed by an indirect branch through a table slot). A method reached through a **cached table slot**
  will ignore a rewrite of its own entry point, because callers never read that field — another reason
  the entry-point rewrite must be validated per call site.
- Dump the executable range and disassemble around candidate offsets instead of trusting symbol names.
- When a payload was produced by a just-in-time compiler on the target, the displacement between its
  pages is often zero, which is exactly why relocation-free bootstrapping is required (above).

## Cross-architecture notes

- **arm64** is the common case on modern devices; prefer it and make sure the host library you pick
  actually exists for that ABI.
- **x86_64** appears on emulators. Shells and payloads are ABI-specific: a file built for one ABI will
  not be loaded on the other, and the failure mode looks like a missing library rather than a mismatch.
- Keep your build artifacts per-ABI and label them. Mixing them is a common source of "it crashed for no
  reason" when the same APK behaves differently on an emulator versus a device.

## Verification

A native patch earns no credit until the behaviour changes **and** the app stays healthy:

- log a marker from your entry point so you know it ran at all;
- confirm the library is in `maps`;
- confirm the app reaches its normal UI afterwards;
- keep the original library so you can produce an unmodified control build.

Never conclude "the hook works" from the absence of a crash. Absence of effect is the normal outcome of a
hook that never installed.
