# P3 Causal Autonomy Plan

Status: preregistered; do not edit after the first live invocation

Owner issue: TRI-19 judge-readiness continuation

## Question

Can EvoHive turn preserved evidence into a bounded next experiment without a
human choosing the operator after seeing the evidence?

## Fixed policy

The controller reads the three canonical P1 parent artifacts and the P2 Modal
comparison. It extracts only registered signals: verified-59 count, minimum
working violations, number of stopped iterations, and whether sandbox startup
overhead dominated. Rules are evaluated in this order:

1. A verified 59 selects `freeze_candidate`; no development experiment runs.
2. A state below two violations selects `deepen_exact_repair` for a separately
   preregistered follow-up; no experiment runs here.
3. Three passed iterations with no 59 and no improvement below two violations
   select `asymmetric_random_greedy_screen`.
4. Anything else selects `collect_more_evidence`; no experiment runs.

The present evidence should select rule 3. Continuing the stopped
destroy/repair family, spending seeds 64..127, or scaling the same short solver
on Modal are explicitly ineligible.

## Selected-action canary

If rule 3 is selected, the decision artifact is atomically persisted before
compilation or execution. It emits this exact experiment specification:

```text
solver: solver/asymmetric_greedy.c
initialization: empty 32 x 32 grid; no public certificate or P0 candidate
algorithm: seeded randomized point order, greedily accept every valid point
seeds: 1400..1403
restarts: 250 per seed (reported as iters)
workers: 4 local subprocesses
timeout: 120 seconds per trial
acceptance: both existing controller-side exact oracles
cost: 0 USD local compute
```

This is a deliberately cheap structural canary, not a record attempt. It tests
whether the decision changes the executed operator family. It is not expected
to beat the optimized incumbent.

## Promotion and rollback

- Every accepted candidate must pass both local oracles.
- The canary is `eligible_for_confirmation` only if its best score is at least
  the incumbent 58 with zero infrastructure failures and zero oracle
  disagreements.
- Otherwise it is `rolled_back`: `solver/solver.c` remains the canonical
  incumbent byte-for-byte, the negative artifacts are retained, and no seed or
  parameter is tuned or rerun.
- Screening evidence never replaces the incumbent automatically and never
  supports a record claim.
- Seeds 64..127 remain untouched.

## Required artifacts

1. An immutable decision artifact written before action execution, containing
   input artifact hashes, extracted signals, evaluated alternatives, selected
   action, fixed budget and rollback rule.
2. Four standard baseline child artifacts and their parent summary.
3. An immutable transition artifact linking decision to action, proving the
   emitted configuration was executed and recording promotion or rollback.

Run exactly once:

```bash
python -m tripathy_experiment.cli p3-autonomy --seeds 1400-1403 --iters 250 \
  --workers 4 --timeout-seconds 120 --artifact-dir artifacts/runs
```
