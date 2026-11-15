# EvoHive: Judge Evidence Report

## Verdict

EvoHive reproduced the public 58-point construction from scratch in 10/64 fixed-budget trials. It did not find a verified 59-point construction. Modal reproduced four same-seed local candidates exactly, but was slower at this budget; Exa and past.dev have no live evidence.

## Evidence

| Phase | Result | Safety / interpretation |
|---|---|---|
| P0 `bb6b15b0` | 10/64 reached 58; best 58; 109.31 s | 0 oracle disagreements; cost $0.00 |
| P1.1 `418e67a9` | single-point swaps: 0 verified 59s; minimum 2 conflicts | gate passed; operator family stopped |
| P1.2 `ff52f29c` | destroy 4 / exact repair 5: 0 verified 59s; minimum 2 conflicts | gate passed; operator family stopped |
| P1.3 `e46d5be6` | destroy 8 / exact repair 9: 0 verified 59s; minimum 2 conflicts | gate passed; operator family stopped |
| P2 `eaacf19f` | 4/4 candidate hashes and 4/4 stdout streams match | 4/4 terminated; 0 oracle disagreements |

## Modal timing

Local parallel: **1.07 s**. Local serial-equivalent: **4.16 s**. Modal: **5.90 s** plus **1.62 s** prepare. Cost is unknown, not zero.

## Claim boundaries

- The 58-point result is a from-scratch reproduction, not a discovery.
- No verified 59-point construction exists in this evidence set.
- The Modal run demonstrates isolated parity, not speedup or known cost.
- Exa and past.dev have adapters and fixture tests but no live evidence.

## Integrity

The generator freshly dual-verified **96** accepted candidates and hashed **103** source artifacts. Evidence-set SHA-256: `f2ce796bd3677a1e9271b76cc2dc05f59ad34026190ec4ff58607f13d1830c95`.

Rebuild: `python -m tripathy_experiment.cli judge-report`
