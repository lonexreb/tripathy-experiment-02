# P1 Symmetry-Breaking Record Search

Status: completed negative development study; operator family stopped  
Owner issue: TRI-19  
Immutable P0 baseline: Git commit `2914794`, run `bb6b15b0-c0b9-426f-a67d-464cdce1a551`  
Primary target: independently verified cardinality 59 on the `32 x 32` grid

## Development iteration log

### Iteration 1 — single-point tabu swaps

Run `418e67a9-dca8-4d0d-ac3d-1b5355bf6a45` executed the preregistered seeds `1000..1007` for 200,000 swaps each. The infrastructure gate passed with zero failures or oracle disagreements, but the search found no 59. Every trial's best 59-point working state had exactly two forbidden triples, reached immediately after the forced addition at swap zero; 1.6 million subsequent swaps never improved that value. This rejects the single-swap operator as ready for confirmation.

### Iteration 2 — bounded destroy and exact repair

This second development iteration is preregistered before execution:

```text
breaker seeds: 1100..1107
iterations: 200000 single-swap fallback iterations
destroy size: 4 points removed from the verified source 58
repair target: add 5 points to reach 59
exact-repair node cap: 20000 nodes per attempt
attempt schedule: once at startup and after each 20000-swap stall restart
workers: 8
source policy: unchanged round-robin policy across distinct P0 58 candidates
```

At each exact-repair attempt, rebuild the original valid 58, remove four seeded-random distinct points, enumerate all cells whose exact incremental add cost is zero for the resulting valid 54-point base, seeded-shuffle that pool, and depth-first search increasing pool indices for five mutually compatible additions. A branch may add a point only when its current exact add cost is zero. Add/remove operations must be exact inverses, and the node cap counts every attempted branch. A depth-five completion is therefore a valid 59 before controller verification.

If the bounded exact repair fails, the existing fixed-cardinality single-swap search may continue as a fallback. New counters must record repair attempts, nodes, deepest repair depth, destroy size, and whether the best state came from exact repair or swapping. The existing eight artifacts remain immutable.

Iteration 2 passes its infrastructure gate under the same rules as iteration 1. Search progress is classified as:

- **record candidate:** a persisted, dual- and upstream-verified 59;
- **operator progress:** minimum working violations improves below 2 or exact repair reaches depth 5;
- **no progress:** no 59 and minimum working violations remains 2.

Regardless of outcome, seeds `64..127` remain reserved and no record claim is made from development data.

### Iteration 3 — final large-neighborhood test for this operator family

Iteration 2 run `ff52f29c-b4e5-4620-993d-5236b324991e` passed its infrastructure gate but made no search progress. Across 80 destroy-four attempts it explored 1,398 repair nodes, always reached depth four but never depth five, and every trial remained at a two-violation minimum. The repair pools contained only four or five cells, showing that the four-point neighborhood was too rigid rather than node-cap limited.

One final development iteration is preregistered before execution:

```text
breaker seeds: 1200..1207
iterations: 200000 single-swap fallback iterations
destroy size: 8 points removed from the verified source 58
repair target: add 9 points to reach 59
exact-repair node cap: 200000 nodes per attempt
attempt schedule: once at startup and after each 20000-swap stall restart
workers: 8
source policy: unchanged round-robin policy across distinct P0 58 candidates
```

The implementation must expose `--destroy-size` as an artifacted argument and reject invalid values. The exact-repair rules, verification gates, artifact schema, and prohibition on confirmatory seeds remain unchanged. Iteration 3 is the stopping boundary for this operator family:

- a persisted, dual- and upstream-verified 59 is a development record candidate, still with `record_claim: false`;
- a one-violation working state is evidence of operator progress and justifies a separately preregistered follow-up;
- if the minimum remains two and no 59 is found, stop tuning this destroy/repair family and do not spend confirmatory seeds on it.

Iteration 3 executed as run `e46d5be6-98e0-43ae-848b-3a439246c249`. Its infrastructure gate passed, but all eight trials remained at a two-violation minimum and no 59 was found. Across 80 destroy-eight attempts, exact repair explored 27,078 nodes, reached depth eight of nine, and exhausted every sampled repair space without hitting the node cap. The zero-cost pools contained only eight to ten cells. Under the preregistered stop rule, this operator family is closed and the reserved confirmatory seeds were not used.

## Decision

Preserve `solver/solver.c` as the frozen P0 reproduction baseline. Add a separate solver that starts from a dual-verified 58 produced from scratch by P0, raises the working cardinality to 59, and searches arbitrary point sets rather than mirror pairs.

P1 was divided into development and a conditional confirmatory run. Development used persisted P0 candidates and separate development seeds, and could not support a record claim by itself. The local destroy/repair family failed its development gate, so its confirmatory run was cancelled and seeds `64..127` remain untouched.

## Why this is the next move

The P0 solver enforces `y -> 31-y` symmetry on a grid with no fixed integer row, so every candidate has even cardinality. It can reproduce 58 but cannot represent 59. A new search representation is therefore necessary, not merely a larger iteration budget.

## Development hypothesis

Starting from a dual-verified, from-scratch 58, conflict-guided single-point swaps at fixed cardinality 59 can break mirror symmetry while preserving the exact incremental conflict invariant. Under a fixed iteration budget, every emitted candidate will be dual-verified and the search will either produce a valid 59 or an auditable negative result containing its closest approach.

## Frozen boundaries

1. Do not modify `solver/solver.c`, either trusted oracle, the public certificate, or P0 run artifacts.
2. Input candidates must come from the P0 run, have score 58, and be freshly accepted by both controller-side oracles before use.
3. The symmetry breaker receives points as data; it never reads the public benchmark.
4. A 59 is accepted only if both local oracles and the pinned upstream verifier accept the persisted output from a fresh process.
5. Fixed seeds and iteration counts determine the search. Wall time is measured but not used as the stopping rule.
6. Every crash, timeout, malformed output, invalid candidate, and oracle disagreement becomes an immutable artifact.
7. Seeds `0..63` and the published point sets are development data. They cannot be reused for the confirmatory P1 run.
8. No Exa, past.dev, Modal, API keys, or external provider spend is authorized in this development tranche.

## Solver design

Create `solver/symmetry_breaker.c` with a dependency-free C99 interface:

```text
symmetry-breaker --seed S --iters N --target 59 --repair-nodes R --destroy-size K
```

It reads an initial point set from standard input as `count` followed by integer `x y` pairs and writes one JSON object to standard output.

The search should reuse the exact incremental concepts established in P0 for arbitrary points:

- per-cell squared-distance counts;
- exact total violation count;
- conflict contribution for each selected point;
- add/remove operations that are exact inverses;
- a brute-force invariant check whenever a zero-violation state is found.

Algorithm:

1. Validate and load the 58-point input.
2. Force one unselected point to enter, creating a 59-point working state.
3. Repeatedly remove a highly conflicted selected point and add a low-cost unselected point.
4. Use seeded noise, tabu tenure, and periodic restarts from the original 58 to escape cycles.
5. Track minimum violations, restarts, swaps, and any valid odd candidate.
6. Stop at the first exact 59 or fixed iteration exhaustion.

The emitted `points` field must contain only the best valid candidate. A final invalid working state may be summarized by counters but must never be presented as accepted output.

## Controller and evidence

Add a `p1-smoke` CLI command that:

- loads a named P0 parent run and selects only its verified 58-point child artifacts;
- re-verifies the selected source before each breaker invocation;
- builds the breaker from its source hash;
- runs breaker seeds in isolated subprocesses with empty environments, timeouts, and output limits;
- dual-verifies stdout and records source lineage;
- writes one child artifact per breaker seed plus one parent summary without overwriting prior runs.

Required summary metrics:

- best valid score;
- count of verified 59s;
- minimum working violations reported across trials;
- source candidate hashes and P0 trial IDs;
- failures and oracle disagreements;
- wall/CPU time and cost `$0.0`;
- Git SHA and dirty marker;
- explicit `record_claim: false` for the smoke.

## Development smoke gate

Use the already persisted P0 58s only for infrastructure development:

```text
breaker seeds: 1000..1007
iterations: 200000 per seed
workers: 8
source policy: round-robin across distinct P0 58 candidates
```

Pass the infrastructure gate if:

- the C solver compiles cleanly with `-Wall -Wextra -Werror`;
- fixed input, seed, and iterations produce byte-identical output;
- all eight trials produce artifacts;
- both oracles agree on every emitted valid candidate;
- zero false accepts, crashes, timeouts, or malformed outputs occur; and
- each trial reports a closest-approach metric.

Finding 59 is a search success but is not required for the infrastructure gate. Failure to find 59 must be reported plainly.

## Confirmatory protocol — cancelled for this operator family

The paired protocol below would only have run after a development success. The preregistered stop rule fired instead, so it was not executed:

- control: frozen P0 solver with the same total iteration-equivalent CPU budget;
- treatment: P0 construction followed by the symmetry breaker;
- same seed, hardware class, worker count, and total CPU budget;
- primary outcome: any independently verified 59;
- secondary outcomes: probability/time to 58, minimum 59-state violations, unique valid candidates, failures, and CPU cost.

The control's probability of 59 is structurally zero because of parity; its purpose is to quantify the opportunity cost of breaking symmetry, not to establish that 59 requires asymmetry.

Seeds `64..127` remain reserved for a structurally different, separately preregistered algorithm. They must not be spent on further variants of this stopped family.

## Stop rules

- Stop before the smoke if incremental state disagrees with brute force.
- Stop and preserve a fixture on any oracle disagreement.
- Do not tune on confirmatory seeds.
- Do not claim a record from an invalid, unpersisted, or single-oracle candidate.
- Do not start sponsor integrations or a large Modal run in this tranche.
- The iteration-3 stop rule fired: do not increase the node cap, destroy size, or trial count for this operator family.
