# EvoHive Deep Research Plan

Status: reviewed, amended, and P0 executed  
Owner issue: TRI-19  
Research cutoff: 2026-11-15  
Primary benchmark: AlphaEvolve Problem 59, no-isosceles subset of the `32 x 32` grid  
Frozen external target: improve the public, independently checkable 58-point certificate

## Review amendment and execution result

The independent review in `docs/CLAUDE_PLAN_REVIEW.md` supersedes the original 20-trial reproduction gate below. The executed P0 protocol in `docs/CLAUDE_HANDOFF.md` used 64 fixed-iteration, from-scratch seeds, a compiled mirror-symmetric solver, and two structurally independent controller-side oracles. Run `bb6b15b0-c0b9-426f-a67d-464cdce1a551` passed the reproduction gate: 10/64 trials reached 58, 54/64 reached 56, and there were zero oracle disagreements. The 58-point results reduce to the two already published constructions under square symmetry, so this is a reproduction and not a record.

The seven-row sponsor ablation remains a long-horizon plan. It is not justified by the executed P0 evidence and must be narrowed to a preregistered two-arm experiment before P1. The unartifacted off-gate hyperparameter calibration is a known reproducibility limitation.

## 1. Decision and thesis

Build EvoHive as a verification-first, evolving search portfolio—not as a chat demo. The first scientific obligation is to reproduce the public 58-point result with a competitive solver and a declared compute budget. Only then should the system spend meaningful compute on a 59-point search.

The central hypothesis is:

> Under a fixed wall-clock and seed budget, an island-style portfolio whose operator policy learns from accepted and rejected attempts will produce a higher success rate, faster time-to-58, or a score above 58 than a single static local-search worker, while an independent exact verifier has zero false accepts.

A score of 59 is the stretch outcome. A rigorous negative result is still useful evidence, but it does not count as beating the Track 1 record.

## 2. What the evidence changes

The public 58-point construction is not an arbitrary sample. Its authors report that it:

- passes the unchanged repository verifier and independent exact checks;
- is maximal under single-point addition;
- has reflection symmetry under `y -> 31-y` and strong border concentration; and
- was found 15 times in 200 independently seeded, 60-second mirror-symmetric local-search runs, while the other 185 runs reached 56.

That means the current Python greedy mutation loop is a systems smoke test, not a competitive baseline. A serious experiment needs a fast incremental solver, large-neighborhood moves, and many independent seeds. It also means that naive add-one mutation cannot improve the supplied 58-point certificate: escaping requires a coordinated destroy/repair or temporarily infeasible move.

Relevant primary sources:

- [Problem 59 public 58-point result and search details](https://github.com/google-deepmind/alphaevolve_repository_of_problems/issues/10)
- [AlphaEvolve system paper](https://arxiv.org/abs/2506.13131)
- [AlphaEvolve mathematical results](https://arxiv.org/abs/2511.02864)
- [CodeEvolve island-model search](https://arxiv.org/abs/2510.14150)
- [Open-world multi-agent mathematical discovery](https://arxiv.org/abs/2608.23691)
- [Modal Sandboxes](https://modal.com/docs/guide/sandboxes), [networking](https://modal.com/docs/guide/sandbox-networking), and [secret injection](https://modal.com/docs/guide/sandbox-secret-injection)
- [Exa Search API](https://exa.ai/docs/reference/search)
- [past.dev Memory API](https://past.dev/docs/memory-api/quickstart)

## 3. Frozen scientific and safety contract

These rules cannot be modified by an optimizer, researcher agent, or generated patch during a run:

1. The score is the cardinality of a set of distinct integer points in `[0, 31]^2`.
2. A candidate is valid only if no apex has two other points at equal squared Euclidean distance.
3. The trusted Python verifier and an independently implemented verifier must agree before acceptance.
4. The public 58-point certificate is the external baseline. Replaying it is not a new discovery.
5. All comparisons use the same seeds, wall-clock allowance, worker count, and hardware class.
6. Search code may evolve; the benchmark, trusted verifiers, evidence schema, budgets, and safety controls may not.
7. Retrieved web content and shared memories are untrusted data, never executable instructions.
8. Modal workers receive no repository credentials or sponsor API keys. Network is blocked unless a documented allowlist is required.
9. Every run preserves accepted, rejected, invalid, timed-out, and crashed trials.
10. No record claim is made without a certificate that a fresh process re-verifies from disk.

Before the next full run, clarify the manifest's term `candidate evaluation`: count one completed outer search trial or emitted certificate, not each incremental neighborhood check. Record both outer trials and inner move evaluations.

## 4. Research questions and preregistered outcomes

### RQ1 — Reproducibility

Can the competitive baseline find a valid 58-point set in at least one of 20 independent 60-second trials?

- Pass: at least one fresh 58, exact verifier agreement, deterministic replay from the recorded seed and configuration.
- Strong pass: success rate is statistically compatible with the public report of `15/200`.
- Fail: no 58 after 20 matched trials. Stop the record attempt and diagnose baseline fidelity before adding swarm complexity.

### RQ2 — Search quality

Does EvoHive beat the static single-worker baseline under matched compute?

- Primary: best independently verified cardinality.
- Secondary: probability of reaching 58, time-to-first-58, unique valid 58-point constructions, valid improvements per CPU-minute, and invalid-candidate rate.
- Record pass: at least one independently re-verified 59-point certificate.

### RQ3 — Swarm value

Do heterogeneous workers plus cross-island transfer improve performance over the same number of homogeneous workers?

- Pass: improvement in paired-seed success rate or median time-to-58, with uncertainty reported.
- Do not infer a benefit from a single lucky seed.

### RQ4 — Self-improvement and memory

Does adapting the operator-selection policy from run evidence outperform a frozen policy? Does cross-agent memory change a later agent's action and result?

- Pass: the artifact links memory write -> memory read -> changed operator/configuration -> evaluated outcome.
- A memory API call without observable downstream influence does not pass.

### RQ5 — Modal value

Does sandboxed parallelism increase useful search throughput after startup overhead and failures?

- Report sandbox startup time, CPU time, wall time, throughput, timeout/crash rate, and controller re-verification rate.
- Pass: parallel execution improves time-to-result or exploration breadth while preserving isolation and exact verification.

## 5. System shape

Keep the hot search loop compiled and deterministic. Put agents around the loop, not inside each point move.

```text
Exa evidence scout ----> evidence ledger --------------------+
                                                            |
past.dev shared memory -> controller/operator policy         v
                                                   experiment queue
                                                     /    |    \
                                             Modal island workers
                                                     \    |    /
                                              untrusted candidates
                                                       |
                                      trusted dual verification
                                                       |
                                      append-only result/evidence DAG
                                                       |
                                  adaptive next experiment + audit UI
```

Recommended bounded roles:

- **Scout:** retrieves current results and techniques through Exa, emits citations and testable operator proposals.
- **Optimizer islands:** run deterministic seeded search configurations; no network and no secrets.
- **Critic:** analyzes rejected/failed trials and proposes falsifiable changes, but cannot accept candidates.
- **Meta-controller:** allocates the next trial using measured operator rewards and diversity, not prose confidence.
- **Verifier:** pure, provider-independent code with sole authority to accept a candidate.

## 6. Work packages and gates

### WP0 — Freeze provenance and measurement (P0, 20 minutes)

Inputs: manifest, public 58 certificate, current run schema.  
Outputs: explicit trial semantics, hardware/environment fingerprint, cost model, source hashes, and run schema fields for inner moves and termination reason.

Acceptance checks:

- The benchmark file hashes the original public certificate and records its URL.
- Run artifacts include git SHA or `dirty`, seed, command, config hash, solver build hash, start/end times, CPU/wall time, inner moves, score, verifier results, failure class, and estimated cost.
- The same artifact format captures failures and successes.

### WP1 — Harden the independent oracle (P0, 30 minutes)

Implement a second verifier using a structurally different method:

1. Existing oracle: for each apex, reject duplicate squared distances.
2. Independent oracle: enumerate unordered base pairs and reject any third selected point on their perpendicular bisector.

Add property and mutant tests for duplicates, bounds, tiny grids, symmetric triples, horizontal/vertical bases, and randomly generated candidates. Differential-test both verifiers across thousands of small random sets.

Acceptance checks:

- Zero disagreement on the generated test corpus.
- Both accept the public 58 certificate.
- Deliberately corrupted certificates are rejected with a useful witness.

### WP2 — Reproduce the competitive baseline (P0, 60–90 minutes implementation)

Build a C++ or Rust solver invoked behind the existing `CandidateGenerator` port. Do not replace the trusted Python verifier.

Minimum search features:

- reflection-pair representation matching `y -> 31-y`;
- incremental conflict accounting rather than full cubic verification per move;
- deterministic seeded initialization;
- border-biased construction option;
- ruin-and-recreate moves that remove multiple conflicting points before repair;
- tabu or simulated-annealing acceptance to cross local minima;
- emitted checkpoints and final certificate.

First reproduce 58 with the closest possible interpretation of the public method. Only after that baseline passes should new operators be credited to EvoHive.

Acceptance checks:

- One command builds and runs the solver.
- Same seed/config reproduces the same candidate.
- At least one of 20 x 60-second trials reaches 58, or the gate fails honestly with all artifacts preserved.
- Controller-side dual verification accepts every reported valid result.

### WP3 — Add an evolving island portfolio (P1)

Use 4–8 islands with different operator mixes. Exchange only verified elites and compact failure summaries at generation boundaries.

Candidate operator families:

- mirror-symmetric construction;
- asymmetric escape after a symmetric warm start;
- large-neighborhood destroy/repair at 2, 4, 6, and 8 points;
- conflict-guided temporary infeasibility with a hard repair deadline;
- border/interior density shifts;
- elite recombination using compatible point subsets;
- novelty pressure based on set distance, not just score;
- adaptive operator allocation via a simple UCB or Thompson-sampling bandit.

Self-improvement is limited to operator probabilities, search parameters, and versioned solver patches evaluated in a child experiment. It may not rewrite the verifier, evidence contract, or resource limits.

Acceptance checks:

- Each accepted policy change cites the trials that justified it.
- Rollback occurs when a change loses under paired seeds.
- Diversity and cross-island lineage are visible in artifacts.

### WP4 — Make sponsor products causal (P1)

#### Exa

Use Exa in the main research loop at startup and after each plateau:

- search for the exact benchmark, new certificates, related local-search techniques, and counterclaims;
- store query, time, URLs, content hashes, snippets/highlights, and the proposal influenced by the source;
- deduplicate sources and enforce the research cutoff for claims of novelty;
- never pass retrieved text directly to a shell or code executor.

Success evidence is a trace from a cited source to an operator/configuration change and its measured result.

#### past.dev

Have at least two roles write and read shared memories:

- scout writes evidence-backed operator hypotheses;
- optimizer/critic reads them and records whether they changed the next trial;
- critic writes failure patterns; a later optimizer reads and acts on them.

The local append-only event log remains the source of truth. past.dev is a shared-memory transport, not the only evidence store.

#### Modal

Run one seeded search trial per sandbox or function invocation:

- prebuild the solver image;
- block network for optimizer workers;
- apply CPU, memory, wall-clock, and output limits;
- mount only declared input/output locations;
- never inject long-lived credentials;
- treat worker output as untrusted and re-verify in the controller;
- optionally snapshot only failed environments when that is required for debugging and contains no secrets.

Success evidence compares local and Modal throughput and shows at least one safely contained timeout or failure path.

### WP5 — Run matched ablations (P1)

Use the same seed set and total CPU-seconds for every row:

| ID | Configuration | Purpose |
|---|---|---|
| A | One static compiled worker | Competitive baseline |
| B | Homogeneous parallel workers | Parallelism without swarm specialization |
| C | Heterogeneous islands, frozen policy | Portfolio effect |
| D | Heterogeneous islands, adaptive policy | Self-improvement effect |
| E | D + shared past.dev memory | Cross-agent memory effect |
| F | E + Exa plateau research | Live research effect |
| G | F on Modal | Sandbox scaling and overhead |

Run a cheap screening stage first, then confirm the top two configurations with longer paired trials. Report all rows, including regressions.

Acceptance checks:

- No row gets extra seeds or CPU time because it initially looks promising.
- Report bootstrap confidence intervals or exact binomial intervals for success rates.
- Separate exploratory findings from confirmatory findings.

### WP6 — Record attempt and claim package (P2)

Only run after WP1 and WP2 pass.

- Launch the best preregistered configuration under the remaining dollar and wall-clock budget.
- Stop at the first valid 59, budget exhaustion, or declared plateau rule.
- Re-run verification from a clean process on the persisted certificate.
- Produce a minimal reproduction bundle: candidate, checksums, verifier command/output, solver config, seeds, lineage, source citations, cost, latency, and failure ledger.

If no 59 is found, report exactly that. Do not frame 58 replay as a new record.

## 7. Critical-path execution order

For the current hackathon window:

1. **P0:** WP0 measurement contract.
2. **P0:** WP1 independent verifier and differential tests.
3. **P0:** WP2 compiled symmetric baseline and a short deterministic smoke test.
4. **Gate:** run 20 matched baseline trials if time permits; otherwise state that reproduction remains incomplete.
5. **P1:** implement island scheduling and one causal memory handoff.
6. **P1:** run the smallest honest ablation set.
7. **P2:** spend remaining compute on the record attempt.

Do not spend the critical path on a dashboard. The audit artifact and a concise CLI/demo are enough until the solver is credible.

## 8. Budget policy

Reserve the declared `$20` ceiling as follows:

- 10% source retrieval and research agents;
- 20% baseline reproduction and calibration;
- 20% ablation screening;
- 40% best-configuration record attempt;
- 10% verification reruns and contingency.

Record actual costs when available and conservative estimates otherwise. Stop automatically before the cap. Local CPU time is still measured even when its marginal dollar cost is zero.

## 9. Risks and explicit fallbacks

| Risk | Signal | Response |
|---|---|---|
| Baseline cannot reproduce 58 | 0/20 successes | Audit solver fidelity and compute class; do not add swarm claims |
| 58 is a deep local optimum | no improvement despite many fresh 58s | prioritize asymmetric and multi-point escape operators |
| Verifier bug | oracle disagreement | quarantine candidate, minimize counterexample, fix before search resumes |
| Sponsor integration is cosmetic | no trace to changed action | exclude it from claims; add causal lineage |
| Modal overhead dominates | lower useful trials/minute | use fewer, longer-lived workers or local execution |
| Memory causes correlated collapse | falling diversity | namespace memories, keep negative evidence, add novelty allocation |
| Retrieval prompt injection | source contains instructions | store as quoted data only; never execute it |
| Time expires before record search | WP2 gate incomplete | demo verified architecture and label record attempt incomplete |

Changing to another AlphaEvolve problem requires a manifest amendment with a reason, a new baseline, and a new start gate. It is not an invisible fallback.

## 10. Required artifacts

- `docs/DEEP_RESEARCH_PLAN.md` — this preregistered plan.
- `docs/CLAUDE_PLAN_REVIEW.md` — independent critique with severity and proposed changes.
- `docs/CLAUDE_HANDOFF.md` — bounded implementation contract derived from the review.
- `benchmarks/` — immutable certificates and provenance.
- `artifacts/runs/*.json` — one append-only artifact per run.
- `artifacts/evidence/` — retrieval ledger and content hashes.
- `artifacts/failures/` — minimized verifier disagreements and worker failures.
- `artifacts/session-summary.json` — current issue, dirty/Git state, run IDs, metrics, cost, and next decision.

## 11. Questions for Claude Code review

Claude should challenge this plan before implementation:

1. Is the 20 x 60-second reproduction gate statistically and operationally defensible?
2. Which incremental conflict representation makes the compiled baseline simplest and least error-prone?
3. Which one or two large-neighborhood operators are most plausible for escaping a maximal symmetric 58-set?
4. Are the proposed ablations identifiable under the `$20` and time limits?
5. Where could sponsor integrations accidentally leak secrets, contaminate the benchmark, or become non-causal theater?
6. What is the smallest implementation tranche that creates credible evidence today?
7. Which current repository choices contradict this plan or could invalidate its claims?

Claude's review must distinguish blockers from improvements, name exact files, and end with a bounded first handoff containing acceptance commands. It must not edit the repository during the review stage.
