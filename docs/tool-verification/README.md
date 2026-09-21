# Tool verification record

This directory is the **evidence record for the `apk-reverse` skill measured against real
targets**, kept separate from the skill itself so the Coverage statement in `SKILL.md` can be
checked against the runs behind it, and so a later reader can tell which claims were *observed*,
which were *inferred*, and which are still *unverified*.

It is **not** a set of target-specific notes kept for reuse, and it deliberately carries **no target
identity**. The measurements are about the **tools and the skill**; they stay valid whichever APK
produced them. Where a concrete figure was needed to make a point (a class count, a file size, a
build time) the figure is kept and the target is named generically.

Targets measured: Flutter AOT applications, multi-dex, mid-size native library sets, no packer.

The APKs themselves are **not** in this repository (`.gitignore` excludes `*.apk`).

## Strength labels

Every claim carries one of three labels, used the same way `references/verification.md` uses them:

- **observed** — reproduced here, with the exact command and its output.
- **inferred** — follows from observed facts, but the step itself was not executed.
- **unverified** — assumed or reported by a tool and not independently confirmed.

## Index

| File | Covers |
|---|---|
| `TOOL-VERDICTS.md` | One verdict per tested script and external toolchain, with the independent cross-check behind it |
| `FINDINGS.md` | Findings about the skill itself: defects, contradictions, boundary evidence |
| `REPO-DECISIONS.md` | What changed in the repo as a result, and what deliberately did not |

## Extension-pass record

The extension pass (the six coverage gaps named in the external review: module ecosystem, extraction
shells and VMP, emulation/RPC, native DBI, kernel-level environment, protocol layers) keeps its
evidence here, one file per topic, in the same three labels:

| File | Covers |
|---|---|
| `EXTENSION-device-run.md` | The on-device run against a hardened Flutter sample: the two control runs, the frida refusals, the **twice-corrected** pid-drift attribution, the failed-dump artefacts checked with `dex_dump_validate.py`, and a shared-device hazard measured with Stalker |
| `EXTENSION-unpacking.md` | Extraction-shell diagnosis by trivial-body ratio, `dex_dump_validate.py` against a fixture derived from the sample's own shell dex, and the tool's own defect found during the run |
| `EXTENSION-rootdump.md` | The root-side `/proc/<pid>/maps` + `mem` route that does not use frida: 17 real dex images recovered, the shell skeleton they are not, four device-shell traps, and the negative result on anonymous/ART-heap scanning |
| `EXTENSION-lsposed.md` | Module route: the gradle-free build chain with timings, three build traps, LSPosed config-DB anatomy, the module that could never have worked, and the root-hiding configuration the device actually has |
| `EXTENSION-emulation-rpc.md` | ASC/`ddc` measured on a hardened APK, Frida-RPC exercised end to end on a live device, and the unidbg build repair |
| `EXTENSION-native-dbi.md` | Stalker: the zero-event boundary, the crash from following a hot libc export, and an offline protobuf round-trip that caught a defect in its own decoder |
| `EXTENSION-kernel-ondevice.md` | The MT Manager APK MCP probe, the module-environment facts it could verify, and the kernel routes that this device's 4.14 kernel puts out of reach |

## Adding a run

Record the tools, versions and exact commands, and label each claim. Keep target-specific facts out:
what belongs here is what a future reader can apply to a *different* APK — a defect, a measured
cost, a method that did or did not work, and the cross-check that settled it.
