# Baseline validation — 8 October 2026

## Offline regression suite
22 tests pass using `python -m unittest -v`. Tests cover wrong-company rejection,
invalid input, HTTP availability states, employee-count semantics, exact evidence
pointers, repeated snapshots, refresh changes, stale-evidence retention, source
corruption, duplicate inputs, exhausted work budgets and HTML escaping.

## Live operational smoke test
- Source: official Brønnøysundregistrene entity API.
- Inputs: first 100 entities from the public `/api/enheter?size=100` response.
- This is **not** a random sample, the Signalpost annual-accounts universe,
  an independently labelled truth set or an official evaluation batch.
- 100 inputs; 100 outputs; all 100 registry lookups available; 0 failed.
- 803 supported registry claims.
- Elapsed time: 149.473 seconds, four workers, 300-second soft work budget.
- No paid API or model calls.
- Separate evidence audit: all 803 claims resolve to matching source JSON values,
  exact requested company numbers and intact SHA-256 source snapshots.
- Raw registry data stays in ignored local run artifacts and is not published.

No external recall/coverage, model quality, official score or qualification has
been measured. A 100-company run does not establish performance for the larger
organizer batch or its still-to-be-confirmed hard execution budget.

Input file SHA-256: `4e2acffa8bd2308ef7ed21e1924fdcb2162342aa1babd7317e1ffdb52cb47b02`.

## Reproduce the checks
```bash
python -m unittest -v
python demo.py
python verify_evidence.py runs/demo
python traceatlas.py --input companies.txt --output runs/live --workers 4 --budget-seconds 300
python verify_evidence.py runs/live
```
Live data and latency change. Re-run with a declared input list and archive the
complete output directory to compare results. The evidence auditor verifies
stored claim support; it does not independently establish source truth.
