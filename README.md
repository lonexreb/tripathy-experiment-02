# EvoHive

EvoHive is a verification-first autoresearch swarm for Iterate AI Research Hackathon Track 1. It borrows the useful parts of the other tracks without diluting the entry:

- **Track 1 is the scored objective:** beat a public mathematical construction.
- **Track 2 contributes bounded recursive self-improvement:** the outer loop updates its search-operator policy from trial evidence; the model and verifier stay frozen.
- **Track 3 contributes the swarm:** scouts, proposers, experimenters, and critics share accepted and negative results.
- **Exa is the live research feed:** every generation searches for newer bounds, constructions, and search methods, and source URLs are attached to proposals.
- **past.dev is multiplayer memory:** every worker recalls other workers' evidence before proposing and writes its own outcome afterward.
- **Modal is the containment layer:** each candidate evaluation runs in a fresh, network-blocked Sandbox with bounded CPU, memory, and lifetime. The controller re-verifies the result.

The first benchmark is [AlphaEvolve Problem 59](https://github.com/google-deepmind/alphaevolve_repository_of_problems/issues/10): find the largest subset of the `32 x 32` integer grid containing no isosceles triangle. The frozen public baseline is a verifier-valid 58-point certificate.

## Why this plan is competitive

The novelty is not “more agents.” It is an **anchored self-improvement loop**:

1. Exa refreshes the system's view of the record and relevant methods.
2. Multiple agents recall one another's successful and failed experiments.
3. Each agent proposes a candidate from a distinct search operator.
4. Modal isolates evaluation; the candidate has no provider credentials or network.
5. A trusted controller-side verifier independently checks every result.
6. Only strict improvements enter the incumbent lineage.
7. The meta-policy changes which operators receive compute next generation.

That directly addresses the judging criteria: a real benchmark, measurable results, autonomy, transparent decisions, reproducibility, and honest negative evidence.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,modal]'
pytest
python -m tripathy_experiment.cli validate
python -m tripathy_experiment.cli run --grid-size 12 --generations 3 --agents 3
```

The local command requires no credentials and writes a complete JSON evidence bundle under `artifacts/runs/`.

Use the public 58-point seed:

```bash
python -m tripathy_experiment.cli run --grid-size 32 --generations 4 --agents 3
```

Run candidate evaluations in Modal Sandboxes:

```bash
python -m tripathy_experiment.cli run --grid-size 12 --generations 1 --agents 2 --backend modal
```

Enable sponsor adapters only after setting controller-side secrets:

```bash
EXA_API_KEY=... PAST_API_KEY=... \
python -m tripathy_experiment.cli run \
  --grid-size 32 --generations 10 --agents 3 \
  --backend modal --search exa --memory past
```

Never pass these keys to a Sandbox. For a production version, put them in named Modal Secrets and use Modal's outbound secret-injection policy; the untrusted workload should never be able to read raw values.

## Evidence contract

Every run records:

- run ID, seed, grid size, trial budget, and provider modes;
- every proposal's parent, agent, strategy, sources, and inherited memory;
- sandbox and independent-verifier results;
- accepted and rejected candidates;
- search-policy weights before and after feedback;
- wall-clock latency and explicit provider failures.

`artifacts/runs/<run-id>.json` is the machine-readable source of truth. Failed experiments are retained.

## Repository map

- `experiment/manifest.json`: frozen question, hypothesis, metric, baseline, budget, and stop rule.
- `benchmarks/no_isosceles_n32.json`: public baseline certificate and provenance.
- `src/tripathy_experiment/no_isosceles.py`: independent exact-integer verifier.
- `src/tripathy_experiment/swarm.py`: evolving multi-agent research loop.
- `src/tripathy_experiment/adapters.py`: Exa, past.dev, local, and Modal boundaries.
- `docs/adr/0002-evohive-anchored-rsi.md`: architecture and safety decision.
- `src/tripathy_experiment/parallel_comparison.py`: provider-independent P2 local-vs-sandbox controller.
- `src/tripathy_experiment/modal_gateway.py`: the narrow Modal gateway used by P2.

## Current scope

This starter deliberately evolves search policy and candidate constructions, not foundation-model weights. That is a stronger hackathon claim: it is bounded, testable, cheap enough to reproduce, and its evaluator remains outside the object being optimized.

## P0 from-scratch baseline (TRI-19)

The `run --grid-size 32` command above starts from the public 58-point certificate, so it is a
replay, not a reproduction. Its "independent" sandbox check runs the same per-apex algorithm as
the controller. The P0 baseline replaces both:

```bash
python -m tripathy_experiment.cli verify benchmarks/no_isosceles_n32.json
python -m tripathy_experiment.cli baseline --seeds 0-63 --iters 1000000 --workers 8 --artifact-dir artifacts/runs
```

- `solver/solver.c` is a dependency-free C99 local search that starts from an empty grid and never
  reads the certificate. It is symmetric under `y -> 31-y`, so it only reaches even sizes; a
  record search for 59 needs a symmetry-breaking operator.
- Every result is accepted only when the distance oracle (`no_isosceles.py`) and the
  perpendicular-bisector oracle (`perpendicular_bisector_oracle.py`) both accept it.
- Each trial writes one immutable artifact, failures included, plus one parent summary.
- Upstream verifier provenance and semantics are pinned in `benchmarks/upstream/PROVENANCE.json`.

## P1 symmetry-breaking development smokes (TRI-19) — operator family stopped

Plan and iteration log: `docs/P1_SYMMETRY_BREAKING_PLAN.md`. The P0 solver and its artifacts are
frozen; P1 added a separate solver and controller. **No 59 was found in three development
iterations, no record is claimed, and the destroy/repair operator family is closed as stopped**
under the stop rule preregistered for iteration 3. Confirmatory seeds `64..127` were never used
and will not be spent on this family.

```bash
# iteration 3 (current solver; final run for this operator family)
python -m tripathy_experiment.cli p1-smoke \
  --parent-run bb6b15b0-c0b9-426f-a67d-464cdce1a551 \
  --seeds 1200-1207 --iters 200000 --repair-nodes 200000 --destroy-size 8 \
  --workers 8 --artifact-dir artifacts/runs
```

- `solver/symmetry_breaker.c` reads a verified 58-point set on stdin. Once at startup and after
  every stall restart it runs a bounded destroy / exact-repair attempt: remove `--destroy-size`
  seeded-random points, collect every cell with zero exact add cost, and depth-first search for
  destroy-size + 1 mutually compatible additions under the `--repair-nodes` cap. If that fails it
  falls back to conflict-guided single-point swaps at cardinality 59. `--destroy-size` is required
  and must be between 1 and the input count. The solver recounts its violation total by brute
  force at every new minimum, restart and exit, emits only a valid set in `points`, and reports the
  lowest-violation 59-point working state separately as `closest_approach`.
- `src/tripathy_experiment/symmetry_breaking.py` selects the distinct verified 58s of the named P0
  run, re-verifies the source before every invocation, recounts the closest approach itself,
  validates the echoed destroy size and repair counters, and writes one immutable child artifact
  per breaker seed plus a parent summary with a `search_progress` class.
- A 59 counts only after a fresh process re-reads the persisted child artifact and both oracles
  plus the pinned upstream verifier accept it. A smoke always records `record_claim: false`.
- Seeds `64..127` are reserved; the controller refuses them.

| Iteration | Run | Seeds | Gate | Verified 59s | Closest approach | Repair (attempts / exhausted / deepest) | Search progress |
|---|---|---|---|---|---|---|---|
| 1: single-point tabu swaps | `418e67a9-dca8-4d0d-ac3d-1b5355bf6a45` | 1000..1007 | passed | 0 | 2 triples, at swap 0 | n/a | none |
| 2: destroy 4 / repair 5, 20000 nodes | `ff52f29c-b4e5-4620-993d-5236b324991e` | 1100..1107 | passed | 0 | 2 triples, at swap 0 | 80 / 80 / 4 of 5 | no progress |
| 3: destroy 8 / repair 9, 200000 nodes | `e46d5be6-98e0-43ae-848b-3a439246c249` | 1200..1207 | passed | 0 | 2 triples, at swap 0 | 80 / 80 / 8 of 9 | **no progress — stopped** |

Iteration 3 detail: all 80 destroy-eight attempts enumerated their whole search space (27078 nodes
in total; the 200000-node cap was never reached) and none reached depth 9. After removing eight
points the zero-cost pool held only 8 to 10 cells: the eight removed points and at most two
others. Every trial returned the unchanged 58-point source, and the swap fallback never improved
on the two-violation state it starts from.

What this does and does not show: the from-scratch 58s are locally rigid under these operators
(single swaps, and 80 sampled removals each of four and of eight points). It is not a proof that
no 59 exists, and "exhausted" is the solver's own report rather than an independently checked
enumeration.

Earlier solver versions are kept unchanged in `solver/rejected/` (`symmetry_breaker_iter1.c`,
`symmetry_breaker_iter2.c`); their SHA-256 hashes match the ones recorded in runs `418e67a9` and
`ff52f29c`. Replaying those runs byte-for-byte needs those sources, because the command line and
output schema changed between iterations.

## P2 Modal causal comparison (TRI-19) — systems evidence, no speedup

Preregistered in `docs/P2_MODAL_CAUSAL_PLAN.md` and run once. The frozen `solver/solver.c`
ran seeds 1300..1303 at 100000 iterations in four local subprocesses and in four independent
Modal Sandboxes (`runtime="vm"`, `block_network=True`, 1 CPU, 512 MiB, 120-second lifetime, no
Secrets, no mounts). Each Sandbox received the source as data, compiled it with the frozen C99
flags and ran one seed. Its stdout was treated as untrusted and accepted only by both local
oracles. This is not a record attempt and makes no mathematical claim.

```bash
python -m tripathy_experiment.cli p2-compare --seeds 1300-1303 --iters 100000 --workers 4 \
  --artifact-dir artifacts/runs
```

The live arm needs an authenticated local Modal profile. The tests use fake sandboxes and need
no credentials.

Run `eaacf19f-08a7-46c3-8b89-6486492c601f` (execution-time base HEAD `8eff91e`,
dirty worktree recorded honestly, exact file hashes in every artifact):

| Metric | Result |
|---|---|
| Gate status | passed |
| Trials accepted | 8 of 8 (4 local, 4 Modal) |
| Scores by seed (both arms) | 1300: 54, 1301: 56, 1302: 54, 1303: 56 |
| Same-seed candidate hashes agree | 4 of 4 (stdout byte-identical 4 of 4) |
| Oracle disagreements / false accepts | 0 / 0 |
| Failures | none in either arm |
| Local parallel wall time | 1.07 s |
| Local serial-equivalent time | 4.16 s (sum of per-trial wall times, not a separate serial run) |
| Modal wall time, four Sandboxes | 5.90 s, plus 1.62 s prepare with a cached image |
| Modal per-Sandbox mean | 2.47 s solve, 2.94 s overhead (create, upload, read-back, compile, probe, terminate) |
| Sandboxes created / terminated | 4 / 4, none left running |
| Cost | unknown: Modal exposes no authoritative per-Sandbox cost to this client |

Modal was slower than both local arms here: startup overhead dominates a one-second solve, so
no speedup is claimed. What the run does show is that isolated Sandboxes reproduce the local
results exactly and that the controller, not the Sandbox, decides acceptance.

Limits: one run of four seeds; the isolation probe (network blocked, no credential-like
environment names) is reported from inside the untrusted Sandbox, with no provider-side
attestation; `GPG_KEY`, a public fingerprint name from the python base image, is allowlisted by
name and its value is never read. One gateway preflight on off-experiment seed 1399 (run
`fc905c4a-ff66-4ce5-a12a-609eaef96478`) preceded the run and is kept as an artifact.

## P3 causal autonomy canary (preregistered, not yet run)

`docs/P3_CAUSAL_AUTONOMY_PLAN.md` freezes a deterministic policy over the three P1 parent
artifacts and the P2 comparison. The expected branch rejects more work in the stopped
destroy/repair family and emits a structurally different asymmetric-from-scratch canary. Its
decision must be persisted before action; a result below the incumbent 58 rolls back without
changing `solver/solver.c`. Seeds 64..127 remain untouched.

```bash
python -m tripathy_experiment.cli p3-autonomy --seeds 1400-1403 --iters 250 \
  --workers 4 --timeout-seconds 120 --artifact-dir artifacts/runs
```

## Judge evidence report

Build the two-minute Markdown view and its machine-readable companion directly from the
immutable run artifacts:

```bash
python -m tripathy_experiment.cli judge-report
python -m tripathy_experiment.cli judge-report --check-report
```

The generator follows `experiment/evidence-index.json`, reloads and hashes all 103 linked
artifacts, and freshly runs both local oracles over all 96 accepted candidates. It refuses
missing, escaped or inconsistent artifact references. No result metric is copied from the
index. Generated views live in `artifacts/judge/` and CI checks that they are current.
