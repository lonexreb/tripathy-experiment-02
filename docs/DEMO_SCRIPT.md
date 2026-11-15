# EvoHive Demo Script

Target length: 3 minutes. Do not improvise a 59, Modal speedup, cost, Exa or
past.dev claim.

Before the session, use the README's `uv` setup with Python 3.12 and run the
command once from a clean checkout. The live demo itself makes no network or
provider call.

## 0:00–0:25 — Hook

“Most self-improving research agents can edit the thing that judges them.
EvoHive cannot. The search program may change; the two exact verifiers,
immutable evidence ledger, budget and rollback boundary stay outside it.”

Show the loop in `docs/SUBMISSION.md`.

## 0:25–0:55 — Real benchmark and result

“On AlphaEvolve Problem 59, the public construction has 58 points. Our frozen
from-scratch solver reproduced 58 in 10 of 64 trials. We did not find 59.”

Run:

```bash
python -m tripathy_experiment.cli judge-demo
```

Point to the P0 row and the explicit claim boundaries.

## 0:55–1:30 — Why failures matter

“We then tested three symmetry-breaking families. All 24 trials stayed at a
two-conflict minimum. The third iteration hit its preregistered stop rule, so
the framework retained the failures and refused to spend confirmatory seeds on
that operator family.”

Point to P1.1–P1.3 and `solver/rejected/`.

## 1:30–2:05 — Causal self-improvement

“Before P3 ran, commit `14f7012` froze the policy. It read the canonical P1 and
P2 summaries, rejected more destroy/repair and persisted a decision selecting
an asymmetric-from-scratch canary. About 20 milliseconds later the emitted
config ran exactly. Its best score was 40, so it rolled back and the incumbent
hash stayed unchanged.”

Point to P3 `67bec1d8`; open its decision and transition artifacts if asked.

## 2:05–2:30 — Modal

“For systems evidence, four fresh network-blocked Modal VM Sandboxes compiled
the exact source and ran four seeds. Their outputs matched local byte-for-byte,
all four terminated, and the trusted local controller re-verified them. Modal
was slower here—5.90 seconds versus 1.07 local parallel—so we claim isolation
and parity, not speedup.”

## 2:30–3:00 — Close

“This report is not slides copied from logs. The demo just hashed 110 linked
artifacts and reran two oracles over 100 accepted candidates. If a link, count,
hash, candidate or committed view drifts, CI fails. EvoHive’s contribution is a
research loop that can change its mind without changing the truth.”

## Fast judge Q&A

**Did you beat 58?** No. We reproduced 58 from scratch; no verified 59 exists.

**Then what improved?** The research process: evidence causally changed the
operator, the exact emitted experiment ran, and a weak mutation rolled back.

**Why two oracles?** They use different formulations—per-apex equal distances
and perpendicular bisectors—so a shared implementation error is less likely.

**Is Modal faster?** Not at this workload. Startup dominates. The demonstrated
value is isolated parallel execution with local trust boundaries.

**What about Exa and past.dev?** Adapters and tests exist; no live evidence, so
we do not claim those sponsor integrations.

**Can the agent overwrite evidence?** Artifacts are create-only, source/config
hashes are recorded, earlier failures remain committed, and the report/CI
reconstructs the linked graph.

**What would you do next?** Run a separately preregistered structurally stronger
asymmetric solver or a second benchmark. Do not tune the stopped P1 family or
spend reserved seeds without a qualifying candidate.
