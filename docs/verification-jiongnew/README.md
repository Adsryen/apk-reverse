# jiongnew.apk 实测记录

This directory is the **evidence record for the `apk-reverse` skill measured against a real
target**, not target-specific data the skill ships for reuse. It exists so the Coverage
statement in `SKILL.md` can be checked against the runs behind it, and so a later reader can
tell which claims were *observed*, which were *inferred*, and which are still *unverified*.

Target: `jiongnew.apk` — Flutter AOT, 4 dex, 36 native libraries, no packer.
sha256 `0C2B063E6D1A3BD05777611ABF2F1A64056E290E4F6728C1B12DC202747DC645`, 74,394,920 B, 1,982 entries.

The APK itself is **not** in this repository (`.gitignore` excludes `*.apk`).

## Strength labels

Every claim below carries one of three labels, used the same way `references/verification.md`
uses them:

- **observed** — reproduced here, with the exact command and its output.
- **inferred** — follows from observed facts, but the step itself was not executed.
- **unverified** — assumed or reported by a tool and not independently confirmed.

## Index

| File | Covers |
|---|---|
| `TOOL-VERDICTS.md` | One verdict per tested script, with the independent cross-check behind it |
| `TARGET-FACTS.md` | What the target is: manifest, dex, natives, assets, versions, and what it does at launch |
| `FINDINGS.md` | Findings about the skill itself: defects, contradictions, boundary evidence |
| `REPO-DECISIONS.md` | What changed in the repo as a result, and what deliberately did not |
