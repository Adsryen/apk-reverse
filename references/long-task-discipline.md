# Long-Task Discipline

Load this when a task is likely to run long: many rounds, many experiments, or a conversation that will
exceed what can be held in context. Also load it before resuming a task someone else (or a past you)
started.

The failure mode this file prevents is not tooling — it is **judgement drift**. Over a long task, three
things reliably go wrong, and each is expensive in a way that is invisible while it happens:

1. **You re-derive what you already proved.** Rounds get spent rediscovering a boundary or a mechanism
   that was established earlier and then lost.
2. **You re-walk a route that was already excluded.** The exclusion is real, but the reason has been
   forgotten, so the route looks promising again.
3. **A wrong conclusion keeps steering.** An early mis-attribution is written into your mental model and
   silently removes good options, or props up bad ones, for a long time afterwards.

All three come from the same cause: **conclusions living in context instead of on disk**.

## Keep a live record, not a log

Maintain one artifact — a single file — that is the task's authoritative state. Update it as things are
learned, not at the end. What matters is not size; it is that every entry is **actionable later**.

Keep these sections:

| Section | Contents | Why |
|---|---|---|
| **Operating rules** | things that must be true every run (how to install, how to launch, how to capture) | prevents repeating a mechanical mistake |
| **Confirmed facts** | each with the run that proved it | the basis everything else builds on |
| **Refuted conclusions** | what you believed, why it was wrong, what replaced it | stops a dead idea from coming back |
| **Dead routes** | ruled out, with the evidence | the single biggest time saver |
| **Open questions** | what is still unknown | keeps the next step honest |
| **Environment** | device, ports, tool paths, credentials locations | avoids re-discovery |

Two rules make this file worth having:

- **Every claim carries its evidence.** "The shell rejects this" must include the run that showed it,
  including the exact failure text. An unattributed claim is how a false conclusion gets adopted later.
- **Refutations are first-class entries.** When you find that an earlier conclusion was wrong, record
  *both* the wrong conclusion and why it was wrong. Deleting the mistake loses the most valuable thing
  you learned.

## Grade your own conclusions

Label every non-obvious statement with its strength, and never let a weaker label inherit the authority
of a stronger one:

| Grade | Meaning | May it justify a decision? |
|---|---|---|
| **Observed** | reproduced it, with the exact command and output | yes |
| **Inferred** | follows from an observation, but the step is reasoned | provisionally |
| **Hypothesis** | plausible, untested | only as something to test |
| **Refuted** | tested and found false | never — keep it only as a warning |

Most long-task damage comes from hypotheses drifting upward into "facts" simply by being repeated. If
you catch yourself referring to something as established, check the grade in the record. If it is not
observed, go observe it or label it again.

## Single-variable discipline across the whole task

The most common source of a wrong *and durable* conclusion is a compound experiment: two changes, one
failure, one invented explanation. Because the failure is real, the explanation feels earned.

Consequences to enforce:

- When a route is about to be abandoned, **re-read why it was abandoned**. If the evidence was compound,
  the abandonment is not yet justified — re-run it single-variable before writing it off.
- Keep a semantic control in your pipeline: a build with **no** changes, run through the same
  install-and-launch path. If the control fails, nothing else you measure is meaningful.

## Guard against drift at natural checkpoints

Do these cheaply, and only when they can change a decision — not as ceremony.

- **Before starting a new experiment**: read the refuted-conclusions and dead-routes sections. If your
  plan appears there, stop and read why.
- **Before declaring progress**: ask what the *user-visible* outcome is right now. An internal signal
  improving is not progress (see P19). Re-state the actual target.
- **After any surprise**: write it down immediately with evidence, before you have a theory. Theories
  written after the fact are hard to distinguish from observations.
- **When context feels long**: prefer writing to the record over re-reading conversation. The record is
  what survives; the conversation is what gets truncated.
- **When resuming**: read the record first, and treat anything not in it as unknown, even if it feels
  familiar.

## Handover

A handover is the record plus three things, written for someone with **no** memory of the task:

1. **Operating rules first** — anything mechanical that silently wastes time if unknown.
2. **Honest current state** — including what is *not* achieved. An optimistic summary costs the next
   person far more than an accurate one, because they will build on it.
3. **The next best step, and why** — plus the dead routes, so they do not start there.

Two things belong in every handover, because they are the hardest to recover:

- **What you got wrong**, with the evidence that corrected it.
- **What you never actually verified**, stated plainly. "Never confirmed" is more useful than silence.

## Avoiding the opposite failure

Discipline can itself become a burden. Guard against that too:

- **Do not log everything.** Record only what would change a future decision or prevent a repeated
  mistake. A record nobody reads is worse than no record, because it looks like coverage.
- **Do not treat the record as authority.** It is a summary; the environment is ground truth. If the
  record and a fresh observation disagree, re-test — do not defend the record.
- **Do not let grades calcify.** A hypothesis that becomes testable should be tested, not archived.
- **Do not let the record's structure dictate the work.** If a section is empty because it is not
  relevant to this task, leave it empty.
