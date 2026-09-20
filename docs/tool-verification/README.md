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

## Adding a run

Record the tools, versions and exact commands, and label each claim. Keep target-specific facts out:
what belongs here is what a future reader can apply to a *different* APK — a defect, a measured
cost, a method that did or did not work, and the cross-check that settled it.
