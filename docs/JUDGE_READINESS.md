# EvoHive Judge-Readiness Ledger

Updated: 2026-11-15
Current evidence: P0/P1 commit `3402f10`; P2 implementation, live evidence and audit hardening are in the containing snapshot
Current CI: GitHub Actions run `43765802565`, passed on `8eff91e`; remote CI for the P2 snapshot is pending
Claim policy: a capability receives credit here only when a persisted run demonstrates it

## Executive verdict

EvoHive is scientifically credible but not yet judge-ready. It is strong on rigor and reproducibility, honest about negative results, and has a real compiled search system. It has not beaten the public 58-point construction, and of its sponsor integrations only Modal has measured evidence (P2 run `eaacf19f`, agreement without a speedup); Exa and past.dev remain architecture claims. The shortest route to a competitive submission is to demonstrate the full experiment substrate—parallel isolated search, exact controller verification, measurable memory/research influence, and a concise audit view—without overstating the mathematical result.

## Core judging criteria

Scores are internal readiness estimates on a five-point scale, not predicted judge scores.

| Criterion | Current | Evidence | Missing bar |
|---|---:|---|---|
| Scientific rigor | 5/5 | Frozen manifest; two structurally independent local oracles; pinned upstream verifier; preregistered stop rules; immutable accepted and rejected artifacts | Maintain these invariants in sponsor-backed runs |
| Novelty | 3/5 | Anchored self-improvement design; verifier outside the optimized object; rejected solver lineage retained; fixed-iteration C search | Show the loop adapting from evidence rather than describing adaptation |
| Results | 2/5 | Reproduced 58 from scratch in 10/64 trials; three honest negative 59-search iterations | A verified improvement above 58, or a much stronger cross-benchmark systems result |
| Autonomy / self-improvement | 2/5 | Search-policy and swarm scaffolding exist; P1 changed operators from measured failures | Demonstrate an automated evidence -> decision -> new experiment transition with a budget and rollback |
| Interpretability / reproducibility | 5/5 | Per-trial artifacts, source/config hashes, failure classes, deterministic replay, green CI, public commands | Add a judge-facing summary that reconstructs the full lineage in under two minutes |

Core readiness: **17/25**. The limiting dimensions are results and demonstrated autonomy.

## Sponsor readiness

| Sponsor | Current | Evidence | Required next proof |
|---|---:|---|---|
| Modal | 4/5 | P2 run `eaacf19f-08a7-46c3-8b89-6486492c601f`: four parallel network-blocked VM Sandboxes, 4/4 same-seed candidate hashes equal to local, 0 oracle disagreements, 0 failures, 4/4 terminated; fake-sandbox failure tests | A committed SHA with green CI; a budget where Modal improves throughput (here it was slower: 5.90 s vs 1.07 s local parallel); authoritative cost; provider-side isolation attestation |
| Exa | 0/5 | Adapter and tests only; no credential and no live run | A sourced research event that changes a later experiment and is visible in lineage |
| past.dev | 0/5 | Adapter and tests only; no credential and no live run | At least two roles write/read memory, with a recorded later action that changes because of recalled evidence |

Sponsor claims must be removed or qualified in the pitch until these proofs exist.

## Highest-impact sequence

1. **P2 Modal causal experiment — done (run `eaacf19f`):** agreement 4/4, zero failures, isolation probe clean, no speedup, cost unknown. Remaining: obtain green remote CI for the evidence snapshot.
2. **Judge evidence view:** generate one machine-readable and one concise Markdown summary from run artifacts—no hand-copied metrics.
3. **Causal autonomy loop:** let the controller select the next preregistered operator from failure evidence, record the decision input/output and preserve rollback. Do not spend reserved confirmatory seeds on stopped P1 code.
4. **Exa and past.dev live proofs:** only after credentials exist. Until then, keep fixture tests but mark them as unverified integrations.
5. **Results strategy:** start a structurally different asymmetric-from-scratch search or add a second benchmark where EvoHive can demonstrate improvement. This needs a new frozen manifest before compute.

## Submission truth table

| Claim | Allowed now? | Qualification |
|---|---|---|
| “EvoHive reproduced the public 58 from scratch” | Yes | 10/64 fixed-budget trials; two public symmetry classes; not a discovery |
| “EvoHive found 59” | No | No verified 59 exists |
| “The local-repair family improved the search” | No | All three iterations stayed at a two-conflict minimum |
| “EvoHive preserves and learns from failures” | Partly | Failure lineage is preserved; automated policy influence still needs a causal run |
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
