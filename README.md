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
