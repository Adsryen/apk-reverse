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

## The most expensive drift: solving it in an environment the deliverable will never see

There is one drift in this domain that costs more than all the others, because it produces a
result that looks like success and is not one.

**A runtime-only result is easy to obtain and easy to mistake for a finished artifact.**

Editing a data file, hooking a live process, blocking a hostname, holding a proxy open — each of
these can make the app behave correctly *on the machine where you did it*, with no repackaging
required. It is often the fastest path to a visible win. It is also frequently **not the
deliverable at all**, because the requirement was never "make it work here".

The constraint axes that decide this — check every one against the original request, and write
down the answer as a testable sentence before you start:

| Axis | The question | Why it silently invalidates work |
|---|---|---|
| **Privilege** | must it run **unrooted**? | a rooted-only result cannot be given to a normal user at all |
| **Modification form** | must it be a **rebuilt/installable artifact**, or is a live-instrumentation result acceptable? | hooks and data edits do not ship inside an APK |
| **ABI / device class** | which ABI, which device family? | an emulator-only or x86-only result is not evidence for a physical ARM device |
| **Network** | must it work **online**? | a fix that depends on being offline or on a host proxy fails the moment it is used normally |
| **Persistence** | must it survive restart, upgrade, and a fresh install? | in-memory and session-scoped state evaporates |
| **Distribution** | does the *shipped file* have to be self-contained? | anything that needs a helper on the machine is not a shippable artifact |

**Checkpoint question, asked at the same moments as the drift checks above:**

> *If I handed over exactly what exists right now, would it satisfy the constraint sentence I wrote
> at the start?*

If the answer is no, you have made real progress on a **component**, and that is worth stating as
such — but it is not the task. Do not let "it works" stand in for "it works under the constraint".

**What to do instead of over-claiming.** Split the result into two explicitly labelled parts:

1. **What is achievable inside the constraint**, and how far along it is.
2. **The unconstrained workaround** (needs root / needs a host / needs a proxy), stated as a
   deliberate fallback, with its requirements made obvious to the reader.

A privileged workaround is genuinely useful — it can be the difference between using the app and
not. It becomes a problem only when it is presented as the deliverable. Report it as a fallback,
keep the constrained goal open, and say plainly which one you have.

**Also watch the inverse**: if the constraint is "must be a rebuilt artifact", do not let a working
runtime result quietly close the investigation. Use it for what it is good for — it proves the
mechanism and identifies the exact code or data to change — then port that finding into the
artifact. The runtime result is the map, not the destination.

## Bound every wait

A long task stalls in ways that produce no information and consume the most valuable resource you
have: wall-clock time and the next person's patience. Three habits prevent almost all of it.

**1. Every command has a timeout, and its absence is the bug.** A helper that shells out without a
timeout can hang forever, and the failure presents as "the task stopped making progress" rather
than "this call blocked". Pass an explicit timeout on every subprocess, every HTTP request, every
device call. When one expires, the result is **unknown**, not failed — record it that way and
re-check state before retrying.

**2. Calibrate the expected duration from measurement, not from a guess.** A timeout only means
something if it is set relative to how long the operation *should* take, because that is what makes
"slow" and "hung" distinguishable. Guessed budgets are either so short that healthy work gets killed,
or so long that a stall looks like patience.

So: **measure once, write it down, then derive the bound.**

| Operation class | How to bound it |
|---|---|
| host-side tool (`baksmali`, `apksigner`, a compiler) | seconds to low minutes; time it once, then set roughly 3–5× observed |
| device shell call (`adb shell …`) | seconds — **except** the first `su` after a reboot, which can prompt and block |
| install / push of a large artifact | minutes; scales with size, not with the app's complexity |
| app cold start to first frame | tens of seconds — **longer with a packer**, which does real work before your code runs |
| a step needing a human or an external service | **unbounded in principle** — do not wait at all (see P22) |
| waiting for an on-screen state change | bound it *and* sample it (point 3) |

Record the observed durations in the live record. They are exactly the kind of mechanical fact that
gets re-derived painfully after a context loss, and having them turns a later timeout into an
interpretable signal instead of a mystery.

**Exceeding the expected window is itself the finding.** It tells you something about state — the
device is wedged, the app never reached that phase, the action never happened — and that is a
different investigation from waiting longer. Re-check state instead of extending the deadline.

**3. Every wait has a deadline, an observable to sample, and a look.** "Wait for the operation to
finish" is not a plan. Name the observable, how often you will sample it, how long you will sample
before giving up, and what you conclude on expiry:

```
waiting for: <observable>          e.g. the overlay is gone / the counter incremented
sample:      <interval + how>      e.g. every 15 s: screenshot + current window focus
give up at:  <deadline>            e.g. 150 s
on expiry:   <what I conclude>     e.g. "did not complete within the window" -- not "cannot work"
```

**Sample with your eyes rather than sleeping blind.** When the step is gated on something visible — a
screen, a dialog, a progress indicator — capture it and **look at it** instead of sleeping through the
interval. A fixed sleep either wastes time or measures the wrong instant; a look tells you what
actually happened, and byte-identical consecutive samples tell you nothing is going to change
(`environment.md` §look at the screen). This is the cheapest way to avoid spending rounds on a state
that was never going to arrive.

Three rules that follow:

- **A deadline that passes is a measurement, not a verdict.** "Still not finished after N seconds"
  tells you about latency and reliability. It does not tell you the approach is impossible, and
  writing it down as impossible is how a viable route gets discarded.
- **Never busy-poll a long job while you have independent work.** Start it, do the other thing, and
  collect it when it settles. Polling wastes the same resource the task is already spending.
- **Prefer a bounded observable over a fixed sleep.** Poll the state you actually care about, with a
  cap — and prefer a sample you can inspect over a duration you hope is right.

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
