# P2 Modal Causal Parallelism Plan

Status: completed once; fixed run `eaacf19f-08a7-46c3-8b89-6486492c601f`
Owner issue: TRI-19 judge-readiness continuation
Purpose: turn Modal from an architectural claim into measured sponsor evidence

## Hypothesis

For the same frozen solver source, seeds and iteration budget, parallel Modal VM Sandboxes will return byte-equivalent or candidate-equivalent valid results to local subprocesses, with zero controller-oracle disagreements and no credentials or network access inside the sandboxes. Modal should improve wall-clock exploration throughput relative to serial local execution, while exposing its startup/compile overhead relative to local parallel execution.

## Fixed experiment

```text
solver: solver/solver.c at the P0 evidence version
seeds: 1300..1303
iterations: 100000 per seed
local workers: 4
Modal workers: 4 independent Sandboxes
Modal runtime: vm
Modal networking: blocked
Modal secrets: none
Modal CPU / memory / timeout: 1 CPU / 512 MiB / 120 seconds
```

Seeds `64..127` remain untouched. The experiment is systems evidence, not a record attempt.

## Required design

1. The controller reads and hashes `solver/solver.c` locally.
2. Each Modal Sandbox receives that exact source as data, compiles it with the frozen C99 flags and executes exactly one seed.
3. The sandbox has `block_network=True`, `runtime="vm"`, no Secrets, no mounts and a bounded lifetime.
4. Sandbox stdout is untrusted, size-limited and parsed by the local controller.
5. Both local oracles verify every candidate after it returns.
6. The controller writes immutable child artifacts for every success, crash, timeout, malformed output and verifier disagreement.
7. A parent comparison artifact links the local and Modal arms seed-by-seed and reports candidate hashes, scores, agreement, wall/CPU time when available, startup overhead, failures and estimated/known cost.
8. Every Sandbox is terminated in `finally`, including error paths.

## Acceptance gate

- Four local and four Modal child artifacts plus parent summaries exist.
- Zero oracle disagreements and zero false accepts.
- Every Modal artifact records VM runtime, blocked networking, no secrets and termination outcome.
- Same-seed local and Modal candidate hashes agree, or every mismatch is retained and explained.
- The comparison reports local-serial-equivalent time, local-parallel time and Modal wall time without claiming a speedup when startup overhead dominates.
- A deterministic replay test and fake-Modal failure tests pass in CI without requiring Modal credentials.
- Live run cost is recorded if available; otherwise it is explicitly unknown, never silently zero.

## Stop rules

- Stop on any controller-oracle disagreement.
- Preserve partial artifacts on Modal errors.
- Do not inject Exa, past.dev, GitHub, Linear or other credentials.
- Do not modify the frozen solver or verifier to make cross-environment results agree.
- Do not make a mathematical improvement claim from this experiment.

## Outcome

The acceptance gate passed: all eight trials were accepted, all four same-seed
candidate hashes and stdout streams matched, both oracles agreed on every result,
and all four Modal Sandboxes terminated. Modal took 5.90 seconds after a 1.62-second
cached-image prepare, compared with 1.07 seconds for local parallel execution and a
4.16-second local serial-equivalent sum. The throughput hypothesis was therefore
falsified at this budget; no speedup is claimed. Provider cost is unknown rather
than zero. The immutable run artifacts contain the complete timings, isolation
self-report, source read-back hashes, Sandbox IDs, and limitations.
