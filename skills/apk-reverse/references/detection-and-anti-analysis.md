# Detection, anti-analysis, and when to stop fighting it

Load this when the app fights back: it dies or misbehaves after you attach, refuses to run on your
device, detects root/emulator/hook/debugger, or when your dynamic tool simply will not work on the
environment you have.

This file is a **decision** file, not a bypass catalogue. The expensive mistake it exists to prevent is
spending hours escalating against a detection layer when a cheaper route — usually static — was
available the whole time.

## Step 0: the cheapest decision in this file

**Dynamic analysis is a convenience, not a prerequisite.** Everything that ends in an installable
artifact is decided statically: you edit a file and repackage. Dynamic work is how you *find* things,
and it is often the fastest way — but when it is blocked or unavailable, the correct move is usually to
switch to static, not to escalate.

So before doing anything clever, ask:

1. Is the thing I still need to learn actually discoverable statically? (Strings, code structure,
   call sites, comparisons — usually yes.)
2. Do I need the process to run *to verify*, or only to *find*? Verification can often be done by
   observing the shipped artifact's behaviour, which a hostile process still exposes.

If either answer allows a static path, take it and stop reading this file.

## Step 1: is it detection, or is it your environment?

Detection has a distinctive shape: **it is reproducible, tied to your instrumentation, and absent in the
same app run without it.** Everything else that looks like detection is usually one of these:

| Looks like detection | Usually is | How to tell |
|---|---|---|
| app dies right after attach | hook timing, a bad script, or a genuine RASP layer | run the same app with **no** hooks: alive? then it is your instrumentation or a hooking detector |
| app refuses to start at all | ABI mismatch, missing native lib for this device, install problem | check the live mapping (`scripts/lib_map.py`) and that a clean unmodified build starts |
| app exits on this device only | emulator/root detection, **or** a device-state problem | run preflight; try the same build on a different device class |
| app hangs forever | a frozen thread from a bad patch, or a real ANR | `pitfalls.md` P7 and the "never make it not return" rule |
| dynamic tool "cannot attach" | **the tool cannot work on this environment at all** | see Step 3 — this is the one people waste days on |

**Rule: reproduce with the control first.** Instrumentation-free run, then instrumented run, same
build. That single comparison separates "the app detects me" from "my tooling is broken", and it takes
one round.

## Step 2: if it *is* detection, decide by cost, not by pride

Three legitimate outcomes. Pick one deliberately and say which you picked.

**A. Work around it — only when the workaround is small and stable.**
Worth it when the detector is a simple, localised check you can neutralise in one place, and the
workaround lives in *your* environment rather than in the shipped artifact. Examples of the class:
running on a device the app does not object to, using a build that satisfies the check, or a single
one-line gate in a helper. Also legitimate: naming the artefact differently, using a different device
profile, or simply doing the work on a device that the app accepts.

**B. Change route.** When the workaround is a moving target, switch to static analysis and stay there.
This is the right answer more often than it feels like. Hooking-detection especially tends to escalate:
each hide provokes a stronger check, and you end up maintaining a cat-and-mouse setup that is worth
nothing at delivery time.

**C. Accept and report.** If the detection blocks the *deliverable* rather than your analysis — for
example, the app verifies something the user's device will not have — then the honest output is a
statement of what is blocked, with the evidence. Do not ship a build whose only purpose is to defeat a
detector you were not asked about.

**Signal to stop escalating:** you have spent more effort on the analysis environment than on the
change the user asked for. That is the drift this skill treats as most expensive, in its runtime form
(`long-task-discipline.md` §the most expensive drift).

## Step 3: when the tool cannot work here at all

Some environments cannot run a given dynamic tool, and no amount of trying will change that. Recognise
it and move on — this is a *finding about the environment*, and recording it prevents the next person
from repeating the attempt.

**The instructive class: an emulator that executes a different architecture than it reports.** A device
may advertise one ABI while the process runs libraries of another through a translation layer. This
shows up as a tool that reports the device is fine, then fails to attach, attach-and-die, or attach and
see nothing. Symptoms worth treating as a hard signal:

- the tool's own attach path fails with an error that mentions tracer, ptrace, or a debugger — on an
  environment where translation is in play;
- attaching kills the process immediately, repeatedly, with no Java stack;
- the tool attaches but **no** hook ever fires, including hooks on code you know runs.

**Do not spend the session proving it is impossible.** Establish it once, with one clean reproduction,
write the environment fact down, and switch to static.

**What to do instead:** the entire static toolchain is architecture-agnostic — string tables, code
structure, call-site counts, byte-level patching. None of it needs the app to run. If your verification
also needed the app to run, use the device-level observables instead: does the UI change, do the logs
fall silent, does a file appear or stop appearing. Those are properties of the shipped artifact, and they
do not care that you could not attach.

## Step 4: what a detection layer means for the deliverable

Two distinct questions — keep them separate, because conflating them produces either a broken artifact
or an unnecessary retreat.

1. **Does it block your analysis?** → handle with Step 2/3. This is your problem, and it is temporary.
2. **Will it block the patched build on the user's device?** → this is a property of the artifact. A
   root check that merely requires an unrooted device is usually irrelevant to a repackaged APK. A
   **self-integrity or signature check** is a different matter entirely, and it belongs to
   `references/native-tamper-and-suicide.md` and `references/signature-derived-keys.md`.

Ask explicitly: *does this check fire because of how the app is built, or because of where I am running
it?* Only the first kind follows your build into delivery.

**Root is an environment fact, not a defeat.** "Runs only on a rooted device" is a legitimate analysis
environment and an illegitimate deliverable when the request was an installable build for a normal phone.
Say which one you actually have.

## Step 5: keep a one-line environment fact

When you conclude that something cannot be done in this environment, write one line in the task record:

```
cannot: <tool/technique>  in <environment>   because: <observed failure>   route taken: <alternative>
```

That single line is what saves a future round. It is also the difference between "we could not attach,
so we did X" and an unqualified "dynamic analysis is impossible", which is a claim you have not earned
and which will mislead the next reader.

## Checklist

- [ ] Controlled the comparison: same build with and without instrumentation
- [ ] Preflight run, so device state is excluded before blaming a detector
- [ ] Classified: detection vs environment vs my own tooling
- [ ] Chose A/B/C deliberately and can say which, and why
- [ ] If the tool cannot work here: established it **once**, recorded the fact, switched route
- [ ] Separated "blocks my analysis" from "blocks the deliverable"
- [ ] Nothing in the shipped artifact exists solely to fool a detector
- [ ] Recorded the one-line environment fact if a route was closed
