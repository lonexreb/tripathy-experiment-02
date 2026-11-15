# ADR 0002: Anchored recursive self-improvement in disposable Modal Sandboxes

- Status: accepted
- Date: 2026-11-15
- Linear issue: TRI-18

## Context

Track 1 rewards a measurable mathematical improvement and a readable autonomous loop. Research on autoresearch, scientist swarms, and recursive self-improvement repeatedly exposes the same failure: a system can optimize a flawed or self-modified evaluator and call that progress.

## Decision

EvoHive separates four trust zones:

1. **Controller:** owns budgets, provider credentials, the incumbent lineage, and the frozen acceptance rule.
2. **Research plane:** Exa returns untrusted source material; past.dev stores shared evidence. Neither can directly accept a candidate.
3. **Candidate Sandbox:** a fresh Modal Sandbox receives only candidate data and public verifier code. It has no Secrets, no mounted home directory, blocked networking, bounded CPU/memory, and a hard timeout. It is terminated in `finally`.
4. **Trusted verifier:** the controller repeats the exact-integer check after the Sandbox returns. A candidate is accepted only when both checks agree and the score strictly improves.

The recursive part updates the operator-selection policy from accepted and rejected trials. Candidate programs and harness components may be evolved later, but the acceptance verifier, resource ceilings, and stop conditions are immutable during a run.

## Consequences

- Reward hacking cannot change the final judge.
- Provider keys never enter candidate code.
- Every decision has a compact, replayable lineage.
- Network-disabled sandboxes cannot perform Exa or past.dev calls; those remain controller capabilities.
- The same run can be replayed locally without sponsor services.
- Filesystem snapshots may preserve failed workspaces for debugging, but they are evidence only and never automatically promoted.

## Rejected alternatives

- **One agent rewrites everything:** too easy to corrupt the evaluator and too hard to audit.
- **Agent consensus as verification:** correlated mistakes are not independent evidence.
- **A shared writable workspace:** cross-trial contamination makes results difficult to reproduce.
- **Secrets as environment variables inside the Sandbox:** untrusted code could read or exfiltrate them.
