# EvoHive Judge-Readiness Ledger

Updated: 2026-11-15
Current evidence commit: `bdac57b` (P0–P3 implementation, live evidence and generated report)
Current CI: GitHub Actions run `43769286544`, passed on `bdac57b`
Claim policy: a capability receives credit here only when a persisted run demonstrates it

## Executive verdict

EvoHive demonstrates the core autoresearch loop end to end: measured failure evidence caused a persisted operator decision, the emitted experiment ran exactly, and an underperforming canary rolled back without mutating the incumbent. P3 is committed with green CI, and the repository now includes a one-command evidence demo plus a rubric-mapped submission and timed script. The entry is submission-ready under its honest scope. Its main weakness is mathematical improvement—it reproduced 58 but did not find 59—and only Modal has live sponsor evidence. Exa and past.dev must stay explicitly unclaimed unless credentials become available.

## Core judging criteria

Scores are internal readiness estimates on a five-point scale, not predicted judge scores.

| Criterion | Current | Evidence | Missing bar |
|---|---:|---|---|
| Scientific rigor | 5/5 | Frozen manifest; two structurally independent local oracles; pinned upstream verifier; preregistered stop rules; immutable accepted and rejected artifacts | Maintain these invariants in sponsor-backed runs |
| Novelty | 3/5 | Anchored self-improvement design; verifier outside the optimized object; rejected solver lineage retained; P3 selected a structurally different canary from measured evidence | Extend the demonstrated policy beyond one deterministic transition |
| Results | 2/5 | Reproduced 58 from scratch in 10/64 trials; three honest negative 59-search iterations | A verified improvement above 58, or a much stronger cross-benchmark systems result |
| Autonomy / self-improvement | 4/5 | P3 transition `67bec1d8`: canonical P1/P2 evidence selected `asymmetric_random_greedy_screen`; decision preceded action; config matched; best 40 triggered rollback; incumbent hash unchanged | Demonstrate repeated transitions or a live research/memory-influenced branch |
| Interpretability / reproducibility | 5/5 | Per-trial artifacts, source/config hashes, failure classes, deterministic replay, green evidence CI, one-command demo; generated report freshly re-verifies 100 candidates across 110 artifacts | Keep report and demo current in CI |

Core readiness: **19/25**. The main limiting dimension is mathematical results.

## Sponsor readiness

| Sponsor | Current | Evidence | Required next proof |
|---|---:|---|---|
| Modal | 4/5 | P2 run `eaacf19f-08a7-46c3-8b89-6486492c601f`: four parallel network-blocked VM Sandboxes, 4/4 same-seed candidate hashes equal to local, 0 oracle disagreements, 0 failures, 4/4 terminated; evidence commit `bdac57b` has green CI | A budget where Modal improves throughput (here it was slower: 5.90 s vs 1.07 s local parallel); authoritative cost; provider-side isolation attestation |
| Exa | 0/5 | Adapter and tests only; no credential and no live run | A sourced research event that changes a later experiment and is visible in lineage |
| past.dev | 0/5 | Adapter and tests only; no credential and no live run | At least two roles write/read memory, with a recorded later action that changes because of recalled evidence |

Sponsor claims must be removed or qualified in the pitch until these proofs exist.

## Highest-impact sequence

1. **P2 Modal causal experiment — complete (run `eaacf19f`, commit `9c8b919`, CI `43767285572`):** agreement 4/4, zero failures, isolation probe clean, no speedup, cost unknown.
2. **Judge evidence view — complete in the containing snapshot:** machine-readable JSON and concise Markdown are generated from 110 artifacts; 100 accepted candidates are freshly dual-verified; CI checks staleness.
3. **Causal autonomy loop — complete (transition `67bec1d8`):** evidence selected a new operator, the decision preceded action, the action matched its emitted spec, and a best score of 40 rolled back with the incumbent unchanged.
4. **Judge delivery — complete in the containing snapshot:** `judge-demo`, `docs/SUBMISSION.md` and `docs/DEMO_SCRIPT.md` provide the verified narrative, three-minute flow and Q&A.
5. **Exa and past.dev live proofs:** only after credentials exist. Until then, keep fixture tests but mark them as unverified integrations.
6. **Results strategy:** start a stronger asymmetric-from-scratch search or add a second benchmark. This needs a new frozen manifest before compute.

## Submission truth table

| Claim | Allowed now? | Qualification |
|---|---|---|
| “EvoHive reproduced the public 58 from scratch” | Yes | 10/64 fixed-budget trials; two public symmetry classes; not a discovery |
| “EvoHive found 59” | No | No verified 59 exists |
| “The local-repair family improved the search” | No | All three iterations stayed at a two-conflict minimum |
| “EvoHive preserves and learns from failures” | Yes, qualified | P3 provides one causal evidence-to-decision-to-action transition with rollback; this is not yet a repeated open-ended loop |
| “Modal safely runs parallel experiments” | Yes, qualified | One run, four Sandboxes, results identical to local; isolation is requested configuration plus an in-Sandbox self-report |
| “Modal makes the search faster” | No | At 100000 iterations Modal took 5.90 s against 1.07 s local parallel and 4.16 s local serial-equivalent |
| “The Modal run cost $X” | No | Cost is unknown; Modal exposes no authoritative per-Sandbox figure to this client |
| “Exa drives the research loop” | No | No live Exa run or credential |
| “past.dev provides cross-agent memory” | No | No live past.dev run or causal cross-agent evidence |

## Non-negotiable completion checks

- Green CI at the submitted SHA.
- No secrets or raw provider response bodies in artifacts.
- Every score claim points to an immutable run ID and verifier result.
- Every sponsor claim points to a live run, not an adapter or fixture.
- The demo can be reproduced from a clean checkout with documented commands.
- A judge can distinguish reproduction, negative evidence, and new discovery immediately.
