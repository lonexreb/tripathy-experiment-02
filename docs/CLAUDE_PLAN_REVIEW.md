# Claude Code Review of the EvoHive Research Plan

Review mode: read-only (`Read`, `Glob`, and `Grep` only)  
Reviewer: Claude Code 2.1.325  
Reviewed issue: TRI-19  
Reviewed artifact: `docs/DEEP_RESEARCH_PLAN.md`  
Repository edits during review: none

## Executive verdict

**Not executable as written, but salvageable.** The direction is right: reproduce 58 from scratch first, and let only a verifier accept candidates. The plan, manifest and code currently describe three different experiments, though.

- **What $20 can defend:** a from-scratch, dual-verified reproduction of 58 plus one two-arm ablation.
- **What it cannot defend:** the seven-row ablation ladder, or any expectation of 59.
- **The binding constraint is not dollars.** It is the manifest's 60 wall-clock minutes and 200 "candidate evaluations", plus the fact that no cost is recorded at all.

This review is from reading only: I ran no tests or commands and did not open the three run artifacts. I wrote no files.

## Blockers (severity, evidence, exact files)

| # | Severity | Blocker | Evidence | Files |
|---|---|---|---|---|
| B1 | Critical | Manifest and plan define different experiments, so the start gate is not passed for TRI-19. | Manifest hypothesis is a "three-role swarm" against a "single-agent greedy/ruin-and-recreate" baseline, seeds `[7,19,43]`, issue TRI-18, status `planning`. The plan is an island portfolio against a compiled static worker with 20 seeds; the summary says `running` on TRI-19. `"linear_issue": "TRI-18"` is hard-coded in the run output. | `experiment/manifest.json`, `project.yaml`, `artifacts/session-summary.json`, `src/tripathy_experiment/swarm.py:189` |
| B2 | Critical | The reproducibility command is a replay, not a reproduction. | `--grid-size 32` loads the public certificate as the initial incumbent with target 58, which plan rule 4 says is not a discovery. The certificate is reported maximal under single addition, so `greedy_add` is a no-op and acceptance needs a strict improvement. The stagnation rule therefore ends every such run after 3 generations. | `src/tripathy_experiment/cli.py:56-58`, `src/tripathy_experiment/swarm.py:142,183` |
| B3 | Critical | There is no verifier independence today. | `LocalCandidateExecutor` calls the same `verify()` as the "trusted" check. `_SANDBOX_VERIFIER` is a copy of the same per-apex algorithm. The summary's `modal_sandbox_agreed_with_trusted_verifier: true` is agreement of one algorithm with itself. | `src/tripathy_experiment/adapters.py:169-179,241-265`, `artifacts/session-summary.json` |
| B4 | Critical | Benchmark fidelity is asserted, not evidenced. | The plan cites the "unchanged repository verifier", but it is not vendored and no upstream commit or content hash is recorded. `retrieved_at` equals the manifest cutoff to the second. The local verifier rejects collinear triples such as `(0,0),(1,0),(2,0)`; whether upstream counts degenerate triangles is not pinned anywhere. A stricter local rule would keep a 59 safe but handicap the search; a looser one would invalidate it. | `benchmarks/no_isosceles_n32.json`, `tests/test_no_isosceles.py:18`, `docs/DEEP_RESEARCH_PLAN.md` §2 |
| B5 | High | No Git SHA is possible for any existing evidence. | `git_sha: null`. The solver, swarm, adapters, ports, benchmark and runs are all untracked or modified. | `artifacts/session-summary.json`, working tree |
| B6 | High | Artifacts do not preserve failures. | The artifact is written once, after `run()` returns, so a crash or timeout loses every trial. There is no config hash, termination reason, inner-move count, hardware fingerprint or cost. `cost_usd` is null and no cost model exists. | `src/tripathy_experiment/runner.py:53-56`, `src/tripathy_experiment/swarm.py:186-201` |
| B7 | High | WP2 targets a port that does not exist. | The plan says "behind the existing `CandidateGenerator` port". `ports.py` defines only `ResearchSearch`, `SharedMemory` and `CandidateExecutor`; search runs inline through `mutate()`. | `src/tripathy_experiment/ports.py`, `src/tripathy_experiment/swarm.py:116` |
| B8 | High | Statistical gates are under-powered and the ladder is unidentifiable. | See review questions 1 and 4 below. | `docs/DEEP_RESEARCH_PLAN.md` §4, WP5 |
| B9 | High | A mirror-symmetric search cannot output 59. | `y -> 31-y` has no fixed integer row, so every symmetric set has even size. That matches the reported 56/58 outcomes. The plan's only mandated representation can reach 60, never 59. | `docs/DEEP_RESEARCH_PLAN.md` WP2 |
| B10 | Medium | The summary's 32-grid run does not match the manifest command. | It records 6 trials. `--generations 4 --agents 3` with the 3-generation stagnation stop should yield 9. | `artifacts/session-summary.json`, `experiment/manifest.json` |

## Material improvements

- **Budget by iterations, not seconds.** "Deterministic replay from the recorded seed" contradicts a 60-second wall cutoff. Fix an inner-move budget calibrated once to about 60 seconds, and report seconds as secondary.
- **Fix the symmetry operator.** `symmetric_ruin` uses point reflection `(31-x, 31-y)`, not the `y -> 31-y` mirror the certificate has (`no_isosceles.py:112-117`).
- **Use the certificate's structure.** By the reviewer's read of the file, 56 of the 58 points are symmetric under both mirrors (14 orbits of 4), plus the pair `(1,2),(1,29)`. That suggests searching orbit space for a core, then augmenting asymmetrically.
- **Give the policy a dense reward.** `OperatorPolicy.learn` rewards only strict incumbent improvement. At 58 every weight decays uniformly, so "adaptive" equals "frozen". Use post-repair score or moves-to-56.
- **Do not penalise operators for provider outages.** An executor exception currently counts as an invalid candidate and multiplies the weight by 0.6 (`swarm.py:137-146`).
- **Make the memory test non-tautological.** `inherited_from_agent` is set whenever another agent has a valid entry with score `>=` the parent, so `cross_agent_memory_observed` is true by construction (`swarm.py:109-113`, `tests/test_swarm.py`).
- **Use Modal for search, not for verification.** A point list is data, not code, so a sandbox per verification isolates nothing and costs about 3 seconds per trial. Run one seeded trial per function call on a prebuilt image.
- **Check the Modal image.** `modal_app.py` uses Python 3.11 with `pip_install(".")` while the adapter builds a bare 3.12 image. Confirm the former installs the local package against the Modal docs.

## Answers to the seven review questions

### 1. Is the 20 x 60-second gate defensible?

No.

- At the public rate of `15/200` (7.5%), the chance of at least one 58 in 20 trials is about 79%. A perfect replica fails the gate about one time in five.
- "Compatible with 15/200" is vacuous at `n=20`, since even `0/20` is not rejected at 5%.
- Use 64 trials: the chance of zero successes is about 0.7% at 7.5% and about 6% at a 4.3% rate. On 8 cores this is roughly eight minutes of wall time.
- Their 60 seconds is on unknown hardware, another reason to fix iterations.

### 2. Which incremental conflict representation?

A per-cell distance histogram.

- Keep `cnt[cell][d]`, the number of selected points at squared distance `d` from each of the 1024 cells (`d <= 1922`, about 2 MB as `uint8`).
- Adding or removing a point is 1024 increments or decrements, exact inverses of each other.
- Adding `q` is feasible if every `cnt[q][d] <= 1` and `cnt[p][d(p,q)] == 0` for every selected `p`.
- It mirrors the trusted oracle's apex-and-distance definition, so it is easy to cross-check.
- One C99 file with no dependencies is enough. Rust or C++ adds a toolchain for nothing.

### 3. Which escape operators?

- **Symmetry-breaking destroy and repair:** remove `k` mirror pairs (`k = 2..4`) and refill with unpaired points. This is the only route to 59 given the even-cardinality restriction of pure mirror symmetry.
- **Ruin and exact recreate:** remove 6–8 points and solve the freed cells by small branch-and-bound instead of random greedy refill.
- Defer tabu, novelty pressure, and recombination.

### 4. Are the ablations identifiable?

No.

- Separating a 7.5% from a 15% success rate at 80% power needs about 275 trials per arm.
- Seven arms is about 32 core-hours. That is affordable in dollars but breaks the 60-minute and 200-evaluation stops.
- Rows E–G also change provider, latency, and failure modes, not one factor.
- Run A against D only, with paired seeds, on a dense metric, and label it exploratory.

### 5. Where can sponsor integrations leak, contaminate, or become theater?

- **Exa:** the query is constant every generation. Its only effect is a keyword match on "symmetr" or "mirror" in `OperatorPolicy.choose`, which the fixture also triggers. Raw highlights are copied into every event, where a later LLM critic would read them.
- **past.dev:** recall is not filtered by `run_id`, so an earlier run's 58 seeds a "from scratch" arm and breaks seed determinism. The remote `valid` flag is trusted when choosing a parent. `write()` polls for up to 20 seconds per trial, which alone can exceed the 60-minute cap. The endpoints are untested.
- **Secrets:** up to 500 characters of provider error body go into `provider_failures`, and those artifacts are destined for Slack and Linear (`adapters.py:237`).
- **Modal:** no secrets are passed today, which is good; the theater point is the sandbox-per-verification design.

### 6. What is the smallest credible tranche?

A second oracle, the single-file solver, and 64 from-scratch trials with one artifact per trial.

### 7. Which repository choices contradict the plan?

Blockers B1, B2, B3, B7, and B10, plus the point-reflection operator. Also, `ExperimentManifest` ignores `dataset`, `reproducibility`, and the seeds, so `validate` passes a manifest whose command contradicts its own hypothesis (`src/tripathy_experiment/model.py`).

## Revised P0 tranche

1. **P0.0 Amend and commit.** Move the manifest to TRI-19 with the plan's hypothesis, seeds 0–63, an iteration budget, and "trial = one seeded solver invocation". Commit the tree so a SHA exists.
2. **P0.1 Pin the benchmark.** Vendor the upstream verifier verbatim with its commit SHA, and add a SHA-256 of the points. This settles the degenerate-triangle question.
3. **P0.2 Add the second oracle.** Put a perpendicular-bisector verifier in its own module with no imports from `no_isosceles.py`.
   - Differential-test it on a few thousand random sets on grids up to 8.
   - Add each of the 966 unused cells to the certificate and require both oracles to reject. This also tests the public maximality claim.
4. **P0.3 Write `solver/solver.c`.** Histogram state, y-mirror pair moves, seeded RNG, fixed iterations, JSON on stdout.
5. **P0.4 Add a `baseline` CLI subcommand.** It runs the seeds as subprocesses, dual-verifies each output in the controller, and writes one artifact per trial as it finishes, including crashes, timeouts, and invalid outputs.
6. **P0.5 Run the gate.** 64 trials locally, with an exact binomial interval in the summary.

Deferred: Modal, Exa, past.dev, islands, bandit, LLM roles, and any UI.

## Exact acceptance commands

`verify` and `baseline` are subcommands the tranche must add, and `<N>` is the calibrated iteration count.

```bash
git status --porcelain | wc -l          # 0 before any run
python -m pytest -q
python -m ruff check src tests
python -m mypy
python -m tripathy_experiment.cli validate
python -m tripathy_experiment.cli verify benchmarks/no_isosceles_n32.json
mkdir -p build && cc -O2 -std=c99 -o build/solver solver/solver.c
./build/solver --seed 7 --iters 2000000 > /tmp/a.json
./build/solver --seed 7 --iters 2000000 > /tmp/b.json
cmp /tmp/a.json /tmp/b.json
python -m tripathy_experiment.cli baseline --seeds 0-63 --iters <N> --workers 8 --artifact-dir artifacts/runs
ls artifacts/runs/*.json | wc -l        # previous count + 64
```

The gate passes if at least one of 64 trials reaches 58, there are zero oracle disagreements, and every artifact carries SHA, seed, iterations, config hash, termination reason, and wall/CPU seconds.

## Handoff constraints

- Do not modify `verify()` in `src/tripathy_experiment/no_isosceles.py` or the points in `benchmarks/no_isosceles_n32.json`.
- No new Python dependencies, no network calls, no provider keys, and no Modal in this tranche. Estimated spend is `$0`; record `cost_usd: 0.0`, not null.
- Solver output is untrusted. Only controller-side agreement of both oracles accepts a candidate.
- Write artifacts before reporting, and never overwrite or delete the existing runs.
- Make no record claim and no swarm, memory, or sponsor claim. If 0 of 64 reach 58, stop and report that.
- Update `artifacts/session-summary.json` with the SHA, TRI-19, and the run IDs.

**Recommended first tranche for one session:** P0.0–P0.5 exactly as listed. This is approximately four new files (`oracle2.py`, `solver/solver.c`, one test file, and the vendored verifier) plus edits to `cli.py`, `runner.py`, and the manifest. The review estimates 90 minutes of implementation and about 10 minutes of compute, ending when the acceptance commands pass or the gate fails with all 64 artifacts preserved.

## Primary-agent disposition

The review is accepted with one authorization correction: this task does not include permission to create a Git commit. The execution handoff will record the current `HEAD` plus a dirty-tree marker and hashes of relevant files. It will not commit, push, delete, overwrite existing run artifacts, or create credentials.
