# Claude Code Execution Handoff — TRI-19 P0 Reproducibility Gate

Handoff author: primary Codex agent  
Executor: Claude Code  
Source plan: `docs/DEEP_RESEARCH_PLAN.md`  
Independent review: `docs/CLAUDE_PLAN_REVIEW.md`  
Linear objective: TRI-19, establish a real baseline and reproducibility contract  
Authorization: edit and test this repository only; do not commit or push

## Outcome

Replace the misleading “public certificate replay” baseline with a from-scratch, deterministic, dual-verified baseline experiment for AlphaEvolve Problem 59. The tranche succeeds when the implementation and verification acceptance checks pass and the 64-trial gate is recorded honestly, whether or not any trial reaches 58.

This handoff does **not** authorize a record claim, sponsor claim, credential creation, external message, Git commit, push, deployment, or deletion of existing artifacts.

## Read first

Read these files completely before editing:

1. `AGENTS.md`
2. `CLAUDE.md`
3. `project.yaml`
4. `experiment/manifest.json`
5. `artifacts/session-summary.json`
6. `docs/DEEP_RESEARCH_PLAN.md`
7. `docs/CLAUDE_PLAN_REVIEW.md`
8. `src/tripathy_experiment/no_isosceles.py`
9. `src/tripathy_experiment/cli.py`
10. `src/tripathy_experiment/runner.py`
11. existing tests and benchmark files

Preserve every pre-existing user change in the dirty worktree.

## In scope

### 1. Align the declared experiment

Update `project.yaml`, `experiment/manifest.json`, and the typed manifest model only as needed so they agree on:

- active issue `TRI-19`;
- status `running`;
- one trial means one from-scratch seeded solver invocation;
- baseline seeds `0..63`;
- a fixed inner-iteration budget, with wall time measured secondarily;
- public 58 as the external target, never as solver initialization;
- zero-dollar local P0 cost;
- stop conditions and the dual-verification gate.

Do not claim a clean Git tree. Record the current `HEAD` SHA plus `dirty: true` and relevant file/config hashes.

### 2. Pin benchmark semantics

Add immutable upstream provenance under `benchmarks/upstream/`:

- exact official source URL;
- upstream commit SHA or immutable blob URL;
- SHA-256 of the vendored verifier/source and the public point list;
- a short note stating whether degenerate collinear triples are rejected by the official semantics.

Read-only network access is allowed only if needed to fetch the official Google DeepMind GitHub source. Do not use credentials, paste secrets, or contact any other service. If the exact upstream verifier cannot be obtained, do not fabricate it: preserve the blocker in the summary and still complete the independent local oracle and tests.

Do not edit the existing points in `benchmarks/no_isosceles_n32.json`.

### 3. Add a structurally independent oracle

Create `src/tripathy_experiment/perpendicular_bisector_oracle.py` with no import from `no_isosceles.py`.

It must:

- validate grid bounds and uniqueness independently;
- enumerate unordered base pairs and reject an apex that is equidistant from both endpoints;
- return a useful counterexample witness;
- agree with the existing oracle on the public 58 certificate and generated test corpora.

Add tests that:

- differential-check both oracles on at least 2,000 deterministic random sets on grids up to size 8;
- cover duplicates, out-of-bounds points, tiny sets, vertical/horizontal bases, a degenerate collinear triple, and a nondegenerate isosceles triple;
- try each unused cell against the public 58 and require both oracles to reject every addition;
- report any disagreement as a minimized, reproducible fixture.

Do not change `verify()` in `src/tripathy_experiment/no_isosceles.py`.

### 4. Add the from-scratch compiled baseline

Create a dependency-free C99 program at `solver/solver.c`.

Required properties:

- starts from an empty/generated state and never reads or hardcodes the public 58 points;
- deterministic for a fixed seed and iteration count;
- uses `y -> 31-y` mirror pairs for the reproduction phase;
- maintains incremental per-cell squared-distance counts or an equally exact, documented incremental structure;
- performs seeded construction plus ruin/repair in fixed iterations;
- emits one JSON object on stdout containing seed, iterations, points, score, inner-move counters, termination reason, and solver version/hash input;
- sends diagnostics to stderr only;
- handles malformed arguments with a nonzero exit code.

The symmetric baseline is allowed to search only even cardinalities because its purpose is reproducing 58. Add a clear code/doc note that a later record-search operator must break symmetry to reach 59.

Do not add Python package dependencies.

### 5. Add trusted controller commands

Extend the CLI with:

```text
python -m tripathy_experiment.cli verify <benchmark-json>
python -m tripathy_experiment.cli baseline --seeds 0-63 --iters N --workers 8 --artifact-dir artifacts/runs
```

`verify` must print the benchmark SHA-256, score, both oracle results, and any witness.

`baseline` must:

- build or locate the C solver reproducibly;
- run seeds in isolated subprocesses from an empty/generated state;
- enforce a per-process timeout and output-size limit;
- treat stdout as untrusted JSON;
- require both controller-side oracles to agree before accepting a result;
- write one immutable JSON artifact atomically as each trial finishes, including crashes, timeouts, malformed output, invalid candidates, and oracle disagreements;
- never overwrite existing artifacts;
- include run/trial ID, current `HEAD`, dirty marker, source/config hashes, command/config, seed, fixed iterations, wall and CPU time when available, score, both verifier results, failure/termination class, cost `0.0`, and hardware/runtime fingerprint;
- write a parent summary artifact with the number of successes at each score and a 95% exact binomial interval for the rate of reaching 58;
- return nonzero only for infrastructure/contract failure, not merely because zero trials reach 58.

Do not route this baseline through Exa, past.dev, Modal, or the existing public-certificate-seeded swarm.

### 6. Update evidence truthfully

Update `artifacts/session-summary.json` after tests and the gate:

- active issue `TRI-19`;
- current `HEAD` and dirty marker;
- implementation/test evidence;
- parent baseline run ID and child artifact count;
- best from-scratch score and reach-58 count;
- oracle disagreement count;
- cost `0.0`;
- honest blockers and next decision.

Correct or qualify prior claims that called same-algorithm verification independent. Do not delete or rewrite prior run artifacts.

## Out of scope

- no Git commit or push;
- no Linear, Slack, email, deployment, or other external mutation;
- no API keys, credential setup, `.env` secrets, Exa, past.dev, or Modal calls;
- no islands, bandit controller, LLM-generated solver patches, UI, or record attempt;
- no modification of the public certificate points or existing verifier;
- no deletion, renaming, or overwrite of existing run artifacts;
- no subagents.

## Acceptance checks

Run these, adapting only the calibrated iteration count and temporary paths:

```bash
python -m pytest -q
python -m ruff check src tests
python -m mypy
python -m tripathy_experiment.cli validate
python -m tripathy_experiment.cli verify benchmarks/no_isosceles_n32.json
cc -O2 -std=c99 -Wall -Wextra -Werror -o build/solver solver/solver.c
./build/solver --seed 7 --iters 200000 > /tmp/evohive-a.json
./build/solver --seed 7 --iters 200000 > /tmp/evohive-b.json
cmp /tmp/evohive-a.json /tmp/evohive-b.json
python -m tripathy_experiment.cli baseline --seeds 0-63 --iters N --workers 8 --artifact-dir artifacts/runs
```

Then verify programmatically that:

- all tests/lint/type checks pass;
- both oracles accept the public 58 and reject every single-point augmentation;
- deterministic solver outputs are byte-identical;
- exactly 64 new child trial artifacts plus one parent summary exist for the gate;
- every child artifact has the required evidence fields;
- oracle disagreements equal zero;
- failures, if any, are represented as artifacts;
- the session summary matches the parent artifact;
- no secret-like values or provider response bodies appear in new artifacts.

## Stop and report rules

- If the official upstream verifier cannot be pinned, record that blocker and continue only with the two local oracles.
- If the C solver fails deterministic replay or either oracle disagrees, stop before the 64-trial gate and preserve the failing fixture.
- If 0 of 64 trials reach 58, record a failed reproduction gate and stop. Do not tune on those same seeds and rerun as confirmation.
- If at least one reaches 58, record a passed reproduction gate. Do not begin a 59-point record search in this tranche.
- If the full gate would exceed 15 minutes wall-clock after calibration, lower the fixed iteration count transparently, label the run a screening gate rather than a public-method reproduction, and preserve the calibrated rate.

## Final response contract

Return a concise report containing:

1. files changed;
2. exact commands run and their outcomes;
3. parent run ID, child count, best score, reach-58 count, oracle disagreements, wall time, and cost;
4. whether the reproduction gate passed, failed, or was downgraded to screening;
5. unresolved blockers and the next bounded decision;
6. confirmation that no commit, push, credentials, or external mutations occurred.
