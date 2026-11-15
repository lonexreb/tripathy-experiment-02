# EvoHive — Hackathon Submission

## One-line pitch

EvoHive is an autoresearch runtime that can change its search strategy without
being allowed to change the verifier, rewrite failed history, or silently keep
an underperforming mutation.

## The problem

Autonomous research demos often conflate proposal, execution and evaluation.
The same agent edits code, chooses the metric and declares success; failures
disappear and “self-improvement” is hard to distinguish from post-hoc tuning.

EvoHive makes those boundaries executable. Its first benchmark is AlphaEvolve
Problem 59: select as many points as possible from a 32×32 integer grid without
forming an isosceles triangle. The public construction has 58 points.

## What we built

```text
immutable evidence ──> preregistered policy ──> persisted decision
       ▲                                                │
       │                                                ▼
two independent oracles <── untrusted output <── bounded experiment
       │                                                │
       └──────────── promote or rollback ───────────────┘
```

- Dependency-free compiled search programs with fixed seeds and budgets.
- Two structurally independent exact controller-side oracles.
- Immutable per-trial success and failure artifacts with source/config hashes.
- Preregistered stop rules and reserved confirmatory seeds.
- A causal evidence-to-decision-to-action transition with automatic rollback.
- A narrow Modal gateway using fresh network-blocked VM Sandboxes, no secrets
  or mounts, bounded resources, untrusted output and `finally` termination.
- A report generator that reconstructs claims from artifacts and fails CI when
  committed human/machine views are stale.

## Verified results

| Result | Evidence |
|---|---|
| Reproduced public 58 from an empty grid | 10/64 trials in run `bb6b15b0`; zero oracle disagreements |
| Tested three symmetry-breaking families | 24/24 trials preserved; zero 59s; all stopped at two conflicts |
| Modal parity | 4/4 same-seed candidate hashes and stdout matched local; 4/4 Sandboxes terminated |
| Causal autonomy | Transition `67bec1d8` selected a new operator from P1/P2 evidence before action |
| Safe rollback | P3 scores 39,39,40,39; incumbent source stayed byte-identical at `ab141274…` |
| Auditability | 110 source artifacts hashed; 100 accepted candidates freshly dual-verified |

No verified 59 exists. The 58 is a reproduction, not a discovery. Modal was
slower than local at this budget and provider cost is unknown. Those are
results, not footnotes.

## Why it fits Track 1

EvoHive is a working autoresearch framework, not a single solver. The research
object can evolve while the evidence contract stays fixed. P3 demonstrates
that distinction causally: three negative operator iterations and measured
Modal overhead caused the policy to reject more of the same, choose an
asymmetric-from-scratch canary, execute its exact emitted spec, and roll it
back when it scored 40 against incumbent 58.

## Sponsor use

Modal is used in the main systems evidence loop: four independent VM Sandboxes
received the exact solver source, compiled and ran one seed each with networking
blocked and no attached secrets or mounts. Local controller oracles made every
acceptance decision. The run demonstrates isolation and parity, not speedup.

Exa and past.dev have adapters and fixture tests only. No live credential or
causal run exists, so this submission makes no sponsor claim for them.

## Two-minute verification

```bash
python -m pip install -e '.[dev]'
python -m tripathy_experiment.cli judge-demo
```

The command follows `experiment/evidence-index.json`, rejects path escapes or
inconsistent parent/child links, recomputes counts, reruns both oracles over 100
candidates, hashes 110 artifacts, checks the committed report, and prints the
judge view. CI run `43769286544` is green at evidence commit `bdac57b`.

## Judging-criteria map

- **Scientific rigor:** frozen hypotheses, budgets and stop rules; two exact
  oracles; reserved seeds; failures retained.
- **Novelty:** verifier-anchored self-improvement with persisted causal decisions
  and rollback, rather than self-reported agent success.
- **Results:** reproducible 58 and honest negative 59 evidence; no record claim.
- **Autonomy:** evidence selected a different operator and emitted the executed
  experiment before the result existed.
- **Interpretability/reproducibility:** every claim resolves to immutable run
  IDs; one command reconstructs the story from a clean checkout.

## Links

- Repository: <https://github.com/lonexreb/tripathy-experiment-02>
- Human evidence report: `artifacts/judge/judge-report.md`
- Machine evidence report: `artifacts/judge/judge-report.json`
- Readiness/claim ledger: `docs/JUDGE_READINESS.md`
